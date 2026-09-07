#!/usr/bin/env python3
"""Detect Granicus VoteCast overlays in extracted frames, then parse and validate.

Torrance overlays the vote as a templated "Voting Results" slide holding the
result line, a tally row, and one labelled row per member. Three board families:

- Format B — dark VoteCast HD overlay (Yes/No person glyphs); current era.
- Format A — white ~480x360 slide (2024–mid-2026); coloured letter blocks.
- Format C — mid-2010s white Citicable slide (Yea/Nay + green Y column); same
  family as A but marks sit higher/farther right and need the Furey-era roster.

Stages: cheap numpy gate -> Tesseract keyword detect -> cluster consecutive
frames sharing a tally -> parse the sharpest frame -> bind the latest agenda
cuepoint -> transcript double-check of result + motion -> validate vs roster.

    python3 pipeline/detect_and_parse_votes.py --clip 14821
    python3 pipeline/detect_and_parse_votes.py --clip 12849 --year 2016 --allow-unverified-roster
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import csv
import datetime as dt
import difflib
import io
import json
import os
import re

import subprocess
import sys
import time
from collections import Counter
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard
import manifest as manifest_mod
import roster as roster_mod

# Fractional bounds of the VoteCast panel inside the 1280x720 frame. The video is
# pillarboxed, and the lower-third agenda banner starts around y=0.67, so the
# board box stops above it to keep banner prose out of the name parse.
BOARD_BOX = (0.115, 0.200, 0.890, 0.660)
OVERLAY_BOX = (0.100, 0.100, 0.900, 0.890)

# Vertical slice of the board crop holding the "Result: Motion Passed" bar.
# The primary span is the historical crop. A higher/wider alternate recovers
# faint bars (14821 seq 5 at t=16234) where the primary stretch alone returns
# blank; both are swept and the best fuzzy score wins.
RESULT_BAR_SPAN = (0.17, 0.30)
RESULT_BAR_WIDTH = 0.60
RESULT_BAR_GEOMETRIES = (
    (RESULT_BAR_SPAN, RESULT_BAR_WIDTH),
    ((0.12, 0.30), 0.70),
    ((0.10, 0.28), 0.65),
)

# Black points for the result-bar contrast stretch, tried in order.
RESULT_BAR_BLACK_POINTS = (40, 20)

# Numeric gate thresholds. The extract stage runs this same gate while a
# window's segments are still local, so the constants live in one place and
# neither stage can drift from the other.
GATE_BOARD_DARK = 0.45
GATE_BOARD_SAT = 18.0
GATE_INNER_DARK = 0.60
GATE_INNER_SAT = 14.0
# Format A is the 480x360 white slide used through July 2026. These are
# full-frame statistics because the Format B BOARD_BOX cuts off its title and
# result line. The dark gate is deliberately retained unchanged: it is only a
# cheap candidate gate and also admits near-black filler and dark chamber
# shots, so a hit is not evidence by itself that a vote board is present.
GATE_BRIGHT_FRACTION = 0.35
GATE_BRIGHT_SAT = 30.0
# The archive changes from 480px to 1280px at the same format boundary. This
# keeps unrelated bright slides in Format B meetings out of the established
# gate set. Survey representatives are 2x annotated copies (960px), so they
# still exercise the same branch as their 480px sources.
GATE_FORMAT_A_MAX_WIDTH = 1000

FORMAT_A = "A"
FORMAT_B = "B"
# Mid-2010s Citicable white slide (e.g. 2016 clip 12849). Same "Voting Results"
# family as Format A, but green Y/N letter boxes sit higher and farther right,
# so Format A's mark region cuts the first member and the wrong roster era
# rejects the rest. Format B is the later dark VoteCast HD overlay.
FORMAT_C = "C"
BRIGHT_FORMATS = frozenset({FORMAT_A, FORMAT_C})

TALLY_LABELS = ("yes", "no", "abstain", "recuse")
# Yes / No / Abstain are printed on every Format B board. Recuse is a fourth
# box that VoteCast omits when nobody recused (clip 14798 is 6-0-0 with no
# Recuse square). A missing Recuse *label* is therefore a real layout, not a
# lost OCR digit. A missing Recuse *digit* on a four-box board is still fatal.
REQUIRED_TALLY_LABELS = ("yes", "no", "abstain")
# The printed label per tally column, plus the spellings VoteCast and Tesseract
# actually produce. "yes" and "no" are matched exactly: they are too short for
# a prefix shortcut, which is what let "None", "Notice" and "Nominations" all
# register as the No column.
TALLY_LABEL_WORDS: dict[str, tuple[str, ...]] = {
    "yes": ("yes", "ayes", "aye", "yea"),
    "no": ("no", "noes", "nay", "nays"),
    "abstain": ("abstain", "abstains", "abstained", "abstention", "abstentions"),
    "recuse": ("recuse", "recuses", "recused", "recusal", "recusals"),
}
# Only labels this long get the leading-characters shortcut, so a mangled
# "Abstaln" or "Recusa" still counts while a stray "no..." word cannot.
TALLY_PREFIX_MIN_LEN = 4
DETECT_KEYWORDS = (
    "votingresults",
    "votingresult",
    "voteresults",
    "voteresult",
    "votingresultsboard",
)
RESULT_WORDS = ("passed", "passes", "failed", "fails", "carried", "tie")

CLUSTER_GAP_SECONDS = 30.0
# A board onset is a sampled-frame time, not an event time: the 1 fps grid's
# phase depends on which segment the window started at (< 1 s, and it changes
# whenever placement changes), the EXTINF-accumulated clock drifts against true
# PTS (~0.8 s, same sign for the whole clip), and cuepoints are integer seconds.
# A cuepoint this close to the onset cannot be resolved by the timestamp alone
# and must not be resolved silently. 2.5 s flags the two at-risk 14798 boards
# and none of the 8 published 14821 votes (seq 6 clears at 3.40 s).
BINDING_UNCERTAINTY_SECONDS = 2.5
# How far either side of a detected cluster neighbouring frames are read. Also
# read back by extract_vote_windows.py off expand_group's signature, so the two
# stages cannot drift apart.
CONSENSUS_PAD_SECONDS = 4.0
# Two votes are separate records only when the board actually left the screen
# between them. Tally equality is not a boundary: a consent calendar runs
# several 7-0-0-0 votes seconds apart, and one frame whose tally failed to read
# is not the start of a new vote.
BOARD_ABSENT_RUN = 2
# A tally has to hold for this many consecutive frames before it is treated as
# a new board rather than a misread of the current one.
TALLY_STABLE_FRAMES = 2
OCR_UPSCALE = 3

# Tesseract is invoked once per frame across ~26k frames per meeting. Without a
# timeout one hang permanently occupies a ProcessPoolExecutor worker and
# as_completed never returns, so the whole run stalls with no diagnostic. A
# board crop takes well under a second; this is ~100x headroom.
TESSERACT_TIMEOUT = 60.0

# VoteCast draws a solid colour-coded person glyph beside each member name.
# That block of colour survives compression far better than the ~8 pixel grey
# word printed under the name, so it is read alongside the OCR'd word and the
# two have to agree.
#
# Hues measured off Sep 1 2026 boards: yes 114-124, recuse 36-37, no 8-11,
# abstain matches the blue "Abstain" label. The bands below are the measured
# cores with dead zones between them, because JPEG chroma subsampling on an
# 11x11 glyph moves hue by more than the old NO/RECUSE boundary gap of 25-37
# allowed for. A hue landing in a dead zone yields no icon at all, which costs
# a rejection; the old wide bands turned the panel's green edge glow at hue
# 80.7 into a YES that could override a correct read.
ICON_HUE_CLASSES: tuple[tuple[float, float, str], ...] = (
    (0.0, 20.0, "NO"),
    (30.0, 46.0, "RECUSE"),
    (100.0, 150.0, "YES"),
    (185.0, 250.0, "ABSTAIN"),
    (345.0, 360.0, "NO"),
)
ICON_MIN_PIXELS = 25
ICON_MAX_PIXELS = 600
ICON_MASK_MAX_PIXELS = 40000
# A person glyph is a roughly square ~11x11 block. The panel border artefacts
# that used to classify as votes are 3x150 slivers, so bounding-box side length,
# aspect ratio and fill separate them from real glyphs on geometry alone,
# independently of hue.
ICON_MIN_SIDE = 6
ICON_MAX_SIDE = 30
ICON_MIN_ASPECT = 0.55
ICON_MAX_ASPECT = 1.8
ICON_MIN_FILL = 0.35
# Member rows sit below the tally boxes; ignore the coloured tally labels above.
ICON_REGION_TOP = 0.55
# Distance from a glyph's left edge to the left edge of its name column, in
# board pixels. Measured at 28-29px on every row of every Sep 1 board; the old
# 70px ceiling was wide enough to reach a border artefact at the panel edge.
ICON_MIN_LEFT_GAP = 12
ICON_MAX_LEFT_GAP = 48

# A vote is only as good as the number of frames that agree on it, so the
# winning read has to be held by a real share of the cluster rather than by
# whichever frame happened to be counted first.
#
# "Share of the cluster" means share of the frames that actually produced a read
# of that field, not of every frame in the cluster. The two denominators are not
# interchangeable and using the wrong one blocks on absence instead of on
# disagreement. The result bar is faint grey prose on a grey band: across clip
# 14821 it reads on 1 to 4 frames of a 3 to 7 frame cluster, but when it reads
# at all the frames never contradict each other. Measured against every frame it
# scored 2/7, 1/3 and 4/4, which failed a 50% floor on three of four published
# votes that were correct -- the same false-negative shape as demanding both
# channels for every member.
MIN_RESULT_AGREEMENT = 0.5
MIN_VOTE_AGREEMENT = 0.5

# Cuepoints that mark no substantive business. Binding a vote to one of these
# means the cuepoint advanced while the board was still on screen.
AGENDA_NON_ITEM = re.compile(
    r"none\s+scheduled|no\s+items|\brecess\b|\breconvene\b|\bclosed\s+session\b",
    re.IGNORECASE,
)
# Only the heading is tested against those patterns. Granicus titles carry the
# heading followed by the full body text, and the body routinely *mentions* a
# non-item without being one: clip 14821's adjournment cuepoint reads
# "14. ADJOURNMENT Adjournment of City Council meeting to Tuesday, September 15
# 2026, at 5:00 p.m. for closed session with regular business commencing...".
# Matched over the whole string, "closed session" at character 101 marked a real
# 7-0-0-0 motion to adjourn as non-substantive business. Every genuine non-item
# says so in its heading ("11. AGENCY AGENDAS - None Scheduled").
AGENDA_HEADING_CHARS = 60

# Only the key the plan names. A broader list risks silently spending an
# unrelated credential that happens to be exported in the shell.
GEMINI_KEY_ENVS = ("GEMINI_API_KEY",)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

VISION_PROMPT = """You are reading a screenshot of a Torrance City Council
"Voting Results" slide. Return STRICT JSON only, no prose and no code fences,
with exactly these keys:

{"ayes": int, "noes": int, "abstentions": int, "recused": int,
 "result": "passed" | "failed" | "tie",
 "individual_votes": {"<name printed on the slide>": "YES"|"NO"|"ABSTAIN"|"RECUSE"|"ABSENT"},
 "motion_text": string or null}

Rules: copy the four tally numbers exactly as printed above the Yes/No/Abstain/
Recuse labels. Use the member names exactly as printed, including the
"Councilmember" or "Mayor" prefix. Every listed member must appear in
individual_votes. If a value is unreadable, omit that member rather than
guessing."""

VISION_FORMAT_A_NOTE = """
This is the older white Format A slide. Its tally labels are Yea, Nay, Abstain,
and Recuse; interpret Yea as ayes and Nay as noes. Read the full single-column
member list and the letter inside each coloured vote block."""


# --- stage timing ----------------------------------------------------------

def merge_timing(clip_id: str, stage: str, payload: dict) -> Path:
    """Merge one stage's numbers into logs/timing_{clip}.json.

    Stages run minutes or hours apart and either can be re-run alone, so each
    one updates its own key instead of owning the whole file. A regression in
    any stage then shows up as a diff against the previous meeting's file.
    """
    path = disk_guard.work_dir("logs") / f"timing_{clip_id}.json"
    doc: dict = {}
    if path.exists():
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError:
            doc = {}
    doc["clip_id"] = str(clip_id)
    doc.setdefault("stages", {})
    doc["stages"][stage] = {
        **payload,
        "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    stages = doc["stages"]
    doc["totals"] = {
        "wall_seconds": round(
            sum(s.get("wall_seconds", 0.0) for s in stages.values()), 2
        ),
        "mb_downloaded": round(sum(s.get("mb_downloaded", 0.0) for s in stages.values()), 1),
        "frames_sampled": max(
            (s.get("frames_sampled", 0) for s in stages.values()), default=0
        ),
        "frames_written": max(
            (s.get("frames_written", 0) for s in stages.values()), default=0
        ),
    }
    path.write_text(json.dumps(doc, indent=2))
    return path


# --- image helpers ---------------------------------------------------------

def crop_fractional(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    w, h = image.size
    return image.crop(
        (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    )


def frame_stats_image(image: Image.Image) -> dict:
    """Cheap numeric signature used to gate the expensive OCR pass.

    The fractional crops mean this reads the same picture regions whatever the
    frame is scaled to, which is what lets the extract stage run a cheap
    downscaled version of the gate before committing to full resolution.
    """
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    board = np.asarray(
        crop_fractional(image, BOARD_BOX).convert("RGB"), dtype=np.float32
    )
    h, w, _ = arr.shape
    inner = arr[int(0.1 * h) : int(0.9 * h), int(0.1 * w) : int(0.9 * w)]

    def sat(block: np.ndarray) -> float:
        return float((block.max(axis=2) - block.min(axis=2)).mean())

    return {
        "frame_width": image.width,
        "frame_height": image.height,
        "board_dark_fraction": float((board.mean(axis=2) < 40).mean()),
        "board_saturation": sat(board),
        "inner_dark_fraction": float((inner.mean(axis=2) < 40).mean()),
        "inner_saturation": sat(inner),
        "bright_fraction": float((arr.mean(axis=2) > 200).mean()),
        "frame_saturation": sat(arr),
    }


def frame_stats(path: str) -> dict:
    with Image.open(path) as image:
        return frame_stats_image(image)


def passes_dark_gate(stats: dict) -> bool:
    return (
        stats["board_dark_fraction"] >= GATE_BOARD_DARK
        and stats["board_saturation"] <= GATE_BOARD_SAT
    ) or (
        stats["inner_dark_fraction"] >= GATE_INNER_DARK
        and stats["inner_saturation"] <= GATE_INNER_SAT
    )


def passes_bright_gate(stats: dict) -> bool:
    # Missing keys fail closed: synthetic or stale stats dicts must not raise,
    # and must not be classified as Format A.
    width = stats.get("frame_width")
    bright = stats.get("bright_fraction")
    sat = stats.get("frame_saturation")
    if width is None or bright is None or sat is None:
        return False
    return (
        width <= GATE_FORMAT_A_MAX_WIDTH
        and bright >= GATE_BRIGHT_FRACTION
        and sat <= GATE_BRIGHT_SAT
    )


def frame_format(stats: dict) -> str | None:
    """Classify a gated frame, preserving the established dark-board route.

    Bright 480-class frames are provisionally Format A; `classify_bright_format`
    upgrades them to Format C when the green mark column matches the mid-2010s
    layout. Dark HD overlays stay Format B.
    """
    if passes_dark_gate(stats):
        return FORMAT_B
    if passes_bright_gate(stats):
        return FORMAT_A
    return None


def classify_bright_format(image: Image.Image) -> str:
    """Distinguish Format C (2010s green Y column) from Format A (2024–26).

    Format C marks sit farther right (~x 379 on 480-wide) and start above the
    Format A region top. Format A marks sit near x 360 and begin lower.
    """
    marks = find_format_c_marks(image)
    if len(marks) >= 5:
        median_left = sorted(m["left"] for m in marks)[len(marks) // 2]
        if median_left >= FORMAT_C_MARK_LEFT_MIN:
            return FORMAT_C
    return FORMAT_A


def passes_gate(stats: dict) -> bool:
    return frame_format(stats) is not None


def passes_gate_relaxed(stats: dict, dark_margin: float, sat_margin: float) -> bool:
    """`passes_gate` widened by a fixed margin on every threshold.

    Downscaling moves the statistics slightly, so the extract stage screens the
    cheap gate tier with this and re-runs the real gate on the full-resolution
    bytes of whatever survives. With non-negative margins the relaxed test can
    only ever be a superset, so nothing the real gate would have accepted is
    thrown away before it is asked.
    """
    return (
        stats["board_dark_fraction"] >= GATE_BOARD_DARK - dark_margin
        and stats["board_saturation"] <= GATE_BOARD_SAT + sat_margin
    ) or (
        stats["inner_dark_fraction"] >= GATE_INNER_DARK - dark_margin
        and stats["inner_saturation"] <= GATE_INNER_SAT + sat_margin
    ) or (
        stats.get("bright_fraction", -1) >= GATE_BRIGHT_FRACTION - dark_margin
        and stats.get("frame_saturation", 999) <= GATE_BRIGHT_SAT + sat_margin
        and stats.get("frame_width", GATE_FORMAT_A_MAX_WIDTH + 1)
        <= GATE_FORMAT_A_MAX_WIDTH
    )


def prep_for_ocr(crop: Image.Image) -> Image.Image:
    """Light text on a near-black panel OCRs far better inverted and upscaled."""
    gray = ImageOps.autocontrast(ImageOps.invert(crop.convert("L")))
    return gray.resize(
        (gray.width * OCR_UPSCALE, gray.height * OCR_UPSCALE), Image.LANCZOS
    )


def prep_format_a_for_ocr(image: Image.Image) -> Image.Image:
    """Prepare the full dark-on-light Format A slide without inversion."""
    gray = ImageOps.autocontrast(image.convert("L"))
    return gray.resize(
        (gray.width * OCR_UPSCALE, gray.height * OCR_UPSCALE), Image.LANCZOS
    )


def sharpness(crop: Image.Image) -> float:
    gray = np.asarray(crop.convert("L"), dtype=np.float32)
    lap = (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    return float(lap.var())


# --- tesseract -------------------------------------------------------------

TESS_OK = "ok"
TESS_TIMEOUT = "timeout"
TESS_FAILED = "failed"

# Counted per process. The detect pass runs inside ProcessPoolExecutor workers
# whose counters never reach the parent, so `detect_frame` carries its own
# status back in the frame record and this only aggregates the parse stage.
TESS_STATS: dict[str, int] = {"calls": 0, "timeouts": 0, "failures": 0}


def run_tesseract(
    image: Image.Image, psm: int = 6, timeout: float = TESSERACT_TIMEOUT
) -> tuple[list[dict], str]:
    """OCR one image to word boxes, reporting whether Tesseract itself failed.

    Returns (words, status). A hung or crashed Tesseract is not the same thing
    as a frame with no text on it, and the old code returned the empty list for
    both: a systematic OCR failure was indistinguishable from "this meeting
    contains no votes". The timeout matters just as much -- this runs once per
    frame across ~26k frames, and one hang with no deadline permanently
    occupies a pool worker so `as_completed` never returns and the run stalls
    with no diagnostic at all.

    The pixels go in on stdin rather than through a temp file, which keeps tens
    of thousands of create/close events per meeting away from the endpoint
    security agent for data that never needed to exist.
    """
    TESS_STATS["calls"] += 1
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    try:
        result = subprocess.run(
            [
                "tesseract", "stdin", "stdout", "--psm", str(psm),
                "-c", "tessedit_create_tsv=1", "tsv",
            ],
            input=buffer.getvalue(),
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # subprocess.run kills and reaps the child before re-raising.
        TESS_STATS["timeouts"] += 1
        return [], TESS_TIMEOUT
    except OSError:
        TESS_STATS["failures"] += 1
        return [], TESS_FAILED
    if result.returncode != 0:
        TESS_STATS["failures"] += 1
        return [], TESS_FAILED
    stdout = result.stdout.decode("utf-8", "replace")
    words = []
    for row in csv.DictReader(io.StringIO(stdout), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            words.append(
                {
                    "text": text,
                    "left": int(row["left"]),
                    "top": int(row["top"]),
                    "width": int(row["width"]),
                    "height": int(row["height"]),
                    "conf": float(row["conf"]),
                }
            )
        except (KeyError, ValueError):
            continue
    return words, TESS_OK


def tesseract_words(image: Image.Image, psm: int = 6) -> list[dict]:
    """`run_tesseract` for the callers that cannot act on a failure anyway."""
    return run_tesseract(image, psm=psm)[0]


def words_text(words: list[dict]) -> str:
    return " ".join(w["text"] for w in words)


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def tally_label_for(token: str) -> str | None:
    """Which tally column a single OCR'd word is the label for, if any.

    "yes" and "no" have to match a known spelling exactly. The old prefix
    shortcut used `label[:4]`, which for "no" is just "no", so every word
    longer than two characters starting with those letters -- "None",
    "Notice", "Nominations" -- registered as the No column. That both handed
    `parse_tally` the wrong box to read a digit out of and gave `detect_frame`
    a free label hit on frames with no board on them.
    """
    for label, spellings in TALLY_LABEL_WORDS.items():
        if token in spellings:
            return label
        if (
            len(label) >= TALLY_PREFIX_MIN_LEN
            and len(token) >= TALLY_PREFIX_MIN_LEN
            and token.startswith(label[:TALLY_PREFIX_MIN_LEN])
        ):
            return label
    return None


def count_label_hits(words: list[dict], flat: str) -> int:
    """How many of the four tally columns are labelled on this board.

    Word-level matching is what keeps "None" out of the No column, but
    Tesseract also splits the longer labels across boxes ("Abst ain"), so the
    two labels long enough to be unambiguous are additionally allowed to match
    the concatenated string.
    """
    hits = {tally_label_for(squash(w["text"])) for w in words}
    hits.discard(None)
    for label in TALLY_LABEL_WORDS:
        if len(label) >= TALLY_PREFIX_MIN_LEN and label in flat:
            hits.add(label)
    return len(hits)


def detect_frame(path: str, force_ocr: bool = False) -> dict:
    stats = frame_stats(path)
    format_name = frame_format(stats)
    gated = format_name is not None
    record = {
        "frame": path,
        "stats": stats,
        "gate": gated,
        "format": format_name,
        "detected": False,
    }
    if not (gated or force_ocr):
        return record

    with Image.open(path) as image:
        if format_name in BRIGHT_FORMATS:
            format_name = classify_bright_format(image)
            record["format"] = format_name
            ocr_image = prep_format_a_for_ocr(image)
        else:
            ocr_image = prep_for_ocr(crop_fractional(image, BOARD_BOX))
        words, ocr_status = run_tesseract(ocr_image)
    record["ocr_status"] = ocr_status
    flat = squash(words_text(words))
    has_title = any(key in flat for key in DETECT_KEYWORDS)
    label_hits = count_label_hits(words, flat)
    has_result = any(word in flat for word in RESULT_WORDS)

    if format_name in BRIGHT_FORMATS:
        # On the 480x360 slide the title reads reliably, while the tiny boxed
        # tally row can collapse to one label. Requiring Format B's two labels
        # missed a surveyed real board; the bright/low-saturation gate plus the
        # exact "Voting Results" title is specific to Formats A and C.
        #
        # 2019–2023 meetings flood the bright gate with closed-session / recess
        # splash cards and agenda decks that never show a Voting Results board
        # (oral roll-call era). Reject those explicitly so they cannot satisfy
        # a garbled title match if keywords are broadened later.
        splash = any(
            key in flat
            for key in (
                "isinclosedsession",
                "isinrecess",
                "wewillresume",
                "torrancecares",
            )
        )
        record["detected"] = bool(
            has_title and (label_hits >= 1 or has_result) and not splash
        )
    else:
        splash = False
        record["detected"] = bool(has_title and label_hits >= 2) or bool(
            label_hits >= 3 and has_result
        )
    record["ocr_text"] = words_text(words)
    record["signals"] = {
        "title": has_title,
        "label_hits": label_hits,
        "result_word": has_result,
        "splash": splash,
    }
    return record


# --- board parsing ---------------------------------------------------------

def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0.0


def group_rows(words: list[dict], tolerance: float = 0.6) -> list[list[dict]]:
    """Cluster words into visual rows by vertical centre.

    The tolerance is scaled by the median word height on the board, never by
    the height of one particular word. The old version took the row's *first*
    word as the reference and used `max(ref_height, word_height)`, so a single
    tall glyph set the window for everything after it. On the second member row
    that first word is the person icon misread as text ("ry", h=62), which
    opened a 37px window and swallowed the vote value line sitting 40px below.
    Names and values then shared one row, and every downstream step that looks
    for the value *under* a name found nothing.

    Words are walked in vertical order and a new row starts wherever the gap
    exceeds the window, which is the same thing as splitting on gaps in the y
    histogram. One outsized glyph can still join a row it is near, but it can
    no longer widen that row for its neighbours.
    """
    if not words:
        return []
    board_span = tolerance * _median([w["height"] for w in words])

    ordered = sorted(words, key=lambda w: (w["top"] + w["height"] / 2, w["left"]))
    rows: list[list[dict]] = [[ordered[0]]]
    for word in ordered[1:]:
        centre = word["top"] + word["height"] / 2
        row = rows[-1]
        row_centre = _median([w["top"] + w["height"] / 2 for w in row])
        # Cap the row's own median by the board median so a row that happens to
        # hold only tall glyphs cannot grow its own window either.
        span = min(tolerance * _median([w["height"] for w in row]), board_span)
        if abs(centre - row_centre) <= span:
            row.append(word)
        else:
            rows.append([word])

    for row in rows:
        row.sort(key=lambda w: w["left"])
    rows.sort(key=lambda r: _median([w["top"] + w["height"] / 2 for w in r]))
    return rows


TALLY_KEYS = ("ayes", "noes", "abstentions", "recused")
TALLY_KEY_MAP = {
    "yes": "ayes",
    "no": "noes",
    "abstain": "abstentions",
    "recuse": "recused",
}


def parse_tally_detail(rows: list[list[dict]]) -> tuple[dict[str, int] | None, str | None]:
    """Read the numbers printed above the tally label row.

    Returns (tally, reason_it_failed). Yes, No and Abstain must all be labelled
    and each must have a digit. Recuse is optional: boards that never draw that
    box (14798) default recused to 0. A four-box board whose Recuse digit was
    lost still rejects -- that is the old `setdefault(0)` bug, where a letter
    in the No column silently became a unanimous vote.
    """
    label_row: dict[str, dict] | None = None
    best_found: dict[str, dict] = {}
    for row in rows:
        found: dict[str, dict] = {}
        for word in row:
            label = tally_label_for(squash(word["text"]))
            if label:
                found.setdefault(label, word)
        if not all(name in found for name in REQUIRED_TALLY_LABELS):
            continue
        if len(found) > len(best_found):
            best_found = found
    if not best_found:
        return None, (
            "tally label row not found "
            "(need Yes/No/Abstain; Recuse is optional)"
        )
    label_row = best_found

    label_top = min(w["top"] for w in label_row.values())
    numbers = [
        w
        for row in rows
        for w in row
        if re.fullmatch(r"\d{1,2}", w["text"]) and w["top"] < label_top
    ]
    if not numbers:
        return None, "no tally digits found above the label row"
    # Keep only the numeric row nearest above the labels.
    nearest = max(n["top"] for n in numbers)
    numbers = [n for n in numbers if abs(n["top"] - nearest) <= max(n["height"] for n in numbers)]

    tally: dict[str, int] = {}
    for label, label_word in label_row.items():
        centre = label_word["left"] + label_word["width"] / 2
        best = min(
            numbers,
            key=lambda n: abs((n["left"] + n["width"] / 2) - centre),
            default=None,
        )
        if best is None:
            continue
        if abs((best["left"] + best["width"] / 2) - centre) > 4 * best["width"]:
            continue
        tally[TALLY_KEY_MAP[label]] = int(best["text"])

    required_keys = [TALLY_KEY_MAP[name] for name in REQUIRED_TALLY_LABELS]
    if "recuse" in label_row:
        required_keys.append("recused")
    missing = [key for key in required_keys if key not in tally]
    if missing:
        return None, (
            "no digit could be associated with the "
            + ", ".join(missing)
            + " column; refusing to default it to zero"
        )
    tally.setdefault("recused", 0)
    return tally, None


def parse_tally(rows: list[list[dict]]) -> dict[str, int] | None:
    return parse_tally_detail(rows)[0]


def parse_result(rows: list[list[dict]]) -> tuple[str | None, str | None]:
    for row in rows:
        text = words_text(row)
        flat = squash(text)
        if flat.startswith("result") or "result" in flat[:12]:
            payload = re.sub(r"(?i)^\W*resu\w*\W*", "", text).strip()
            normalized = roster_mod.normalize_result(payload)
            if normalized:
                return normalized, payload
    for row in rows:
        text = words_text(row)
        normalized = roster_mod.normalize_result(text)
        if normalized and "motion" in squash(text):
            return normalized, text.strip()
    return None, None


def _crop_to_text_columns(arr: np.ndarray, pad: int = 6) -> np.ndarray:
    """Trim a result-bar band to the columns that actually carry glyphs.

    "Motion Passed" occupies about 65 of the 595 pixels the band is cropped to,
    so nine tenths of what Tesseract received was blank bar. psm 7 reads that
    as a mostly-empty line, and worse, the percentile stretch was computed over
    the whole strip: the brightest row mean on a real bar is only 66/255, so
    the blank majority set the black point and the faint grey prose never
    separated from the background. Selecting the text columns first, then
    stretching, gives the stretch only pixels that matter.

    Text columns stand out by variance: a blank column of the bar is flat,
    a column crossing a glyph swings between bar grey and text grey.
    """
    if arr.shape[0] < 2 or arr.shape[1] < 2:
        return arr
    variance = arr.var(axis=0)
    peak = float(variance.max())
    if peak <= 1.0:
        return arr
    columns = np.where(variance > peak * 0.10)[0]
    if columns.size < 2:
        return arr
    left = max(0, int(columns.min()) - pad)
    right = min(arr.shape[1], int(columns.max()) + 1 + pad)
    if right - left < 8:
        return arr
    return arr[:, left:right]


def _result_bar_payload(text: str) -> str:
    """Strip Result:/Voting Results prefixes so fuzzy matching sees the outcome."""
    payload = re.sub(r"(?i)^\W*resu\w*\W*", "", text).strip()
    payload = re.sub(r"(?i)voting\s*results\W*", "", payload).strip()
    payload = re.sub(r"(?i)^\W*resu\w*\W*", "", payload).strip()
    return payload


def _result_bar_variants(arr: np.ndarray, tag_prefix: str) -> list[tuple[str, Image.Image]]:
    """Contrast-stretch and threshold variants for one cropped result-bar array."""
    variants: list[tuple[str, Image.Image]] = []
    if arr.size == 0:
        return variants
    for black_point in RESULT_BAR_BLACK_POINTS:
        lo, hi = np.percentile(arr, [black_point, 99.5])
        norm = np.clip((arr - lo) / max(float(hi - lo), 1e-3), 0.0, 1.0)
        tag = f"{tag_prefix}p{black_point}"
        variants.append(
            (f"{tag}stretch", Image.fromarray((255 * (1.0 - norm)).astype("uint8")))
        )
        for threshold in (0.55, 0.65):
            variants.append(
                (
                    f"{tag}threshold{int(threshold * 100)}",
                    Image.fromarray((255 * (norm < threshold)).astype("uint8")),
                )
            )
    return variants


def read_result_bar(board: Image.Image) -> tuple[str | None, str | None]:
    """Re-read just the result bar when the whole-board pass drops the line.

    The bar prints faint grey prose on a mid-grey band. Against the board's
    global histogram that contrast is marginal, so Tesseract silently omits the
    row on many frames. Isolating the band and stretching its own histogram
    recovers it, which matters because a vote with no readable result is
    rejected outright.

    Multiple crop geometries and a sharpened pass are swept because the faint
    14821 5-1-0-1 bar is blank under the historical 0.17/0.60 crop alone, while
    that same crop is still the best read on other boards in the same meeting.
    """
    width, height = board.size
    best: tuple[float, str, str] | None = None

    for (span_top, span_bot), bar_width in RESULT_BAR_GEOMETRIES:
        strip = board.crop(
            (
                0,
                int(span_top * height),
                int(bar_width * width),
                int(span_bot * height),
            )
        ).convert("L")
        if strip.size[0] < 2 or strip.size[1] < 2:
            continue

        prepared = [
            ("raw", strip),
            (
                "sharp",
                ImageOps.autocontrast(strip).filter(ImageFilter.SHARPEN),
            ),
        ]
        for prep_name, prepared_strip in prepared:
            arr = np.asarray(prepared_strip, dtype=np.float32)
            if arr.size == 0:
                continue
            # Keep only the rows belonging to the bright band, dropping the
            # black gutter above and below so the percentile stretch is not
            # dominated by padding.
            row_means = arr.mean(axis=1)
            band = np.where(row_means > row_means.max() * 0.6)[0]
            if band.size:
                arr = arr[band.min() : band.max() + 1]
            arr = _crop_to_text_columns(arr)
            geo_tag = f"{prep_name}_{span_top:.2f}-{span_bot:.2f}w{bar_width:.2f}"
            variants = _result_bar_variants(arr, geo_tag)

            # Collect every read, then take the best-scoring one. Stopping at
            # the first hit would let a marginal fuzzy match beat a clean
            # literal read later in the grid. psm 11 and 13 are here because 7
            # assumes a single line filling the image and 6 assumes a block; on
            # a short phrase in a wide box both tend to return a mostly-blank
            # line.
            for name, variant in variants:
                for scale in (6, 10):
                    scaled = variant.resize(
                        (variant.width * scale, variant.height * scale), Image.LANCZOS
                    )
                    for psm in (7, 6, 11, 13):
                        text = words_text(tesseract_words(scaled, psm=psm))
                        if not text:
                            continue
                        payload = _result_bar_payload(text)
                        normalized, score = roster_mod.normalize_result_fuzzy(payload)
                        if normalized and (best is None or score > best[0]):
                            best = (
                                score,
                                normalized,
                                f"{payload} [{name} x{scale} psm{psm}]",
                            )
                            if score >= 1.0:
                                return normalized, best[2]
    return (best[1], best[2]) if best else (None, None)


TITLE_WORDS = ("councilmember", "councilmembers", "council", "mayor", "member")
TITLE_FUZZY_CUTOFF = 0.72
TITLE_MIN_LEN = 5


def is_title_word(token: str) -> bool:
    """Whether an OCR'd word is the "Councilmember"/"Mayor" name prefix."""
    if len(token) < TITLE_MIN_LEN:
        return False
    return bool(
        difflib.get_close_matches(token, TITLE_WORDS, n=1, cutoff=TITLE_FUZZY_CUTOFF)
    )


def build_column_grid(lefts: list[int], min_pitch: int = 120) -> list[float]:
    """Collapse observed name x-positions into the board's column grid.

    Every member row is laid out on the same columns, so one x per column read
    off whichever rows parsed cleanly can be reused for the rows that did not.
    Positions within `min_pitch` of each other are the same column and are
    reduced to their median, which shrugs off the pixel or two of jitter
    between rows.
    """
    grid: list[float] = []
    cluster: list[int] = []
    for left in sorted(lefts):
        if cluster and left - cluster[-1] > min_pitch:
            grid.append(_median(cluster))
            cluster = []
        cluster.append(left)
    if cluster:
        grid.append(_median(cluster))
    return grid


def snap_to_grid(grid: list[float], left: float) -> float | None:
    """The grid column a word at `left` belongs to.

    A surname sits a fixed offset right of its own column's title and well left
    of the next column, so the nearest column at or left of it is its own.
    """
    if not grid:
        return None
    at_or_left = [x for x in grid if x <= left + 1]
    return max(at_or_left) if at_or_left else None


def find_name_entries(rows: list[list[dict]], era: roster_mod.Era) -> list[dict]:
    """Locate member names by matching roster surnames, not the OCR'd title.

    The "Councilmember"/"Mayor" prefix garbles constantly on compressed frames,
    so the roster dictionary is the anchor for *which* member a row is. The
    prefix is still what anchors the *column*, because the vote value below is
    left-aligned with the prefix rather than with the surname.

    The prefix is found by looking left for a word that reads like a title,
    instead of blindly taking `row[i - 1]`. Those are the same word on a clean
    row, but when a row absorbed the value line the immediately preceding word
    was the value; a gap check then rejected it, the column fell back to the
    surname's own left edge some 250px right of the truth, and both the value
    scan and the icon match went looking in the wrong place.

    A column grid is then derived from the entries that did find their title
    and every entry is snapped onto it, so one badly-read row inherits the
    geometry the rest of the board agrees on.
    """
    entries: list[dict] = []
    for row_index, row in enumerate(rows):
        for i, word in enumerate(row):
            token = squash(word["text"])
            if tally_label_for(token) or is_title_word(token):
                continue
            member = roster_mod.match_member(word["text"], era)
            if not member:
                continue
            title = None
            for j in range(i - 1, max(-1, i - 4), -1):
                if is_title_word(squash(row[j]["text"])):
                    title = row[j]
                    break
            entries.append(
                {
                    "member": member,
                    "raw": " ".join(
                        w["text"] for w in ([title] if title else []) + [word]
                    ),
                    "row_index": row_index,
                    "column_left": title["left"] if title else word["left"],
                    "column_anchor": "title" if title else "surname",
                    "surname_left": word["left"],
                    "top": word["top"],
                    "bottom": word["top"] + word["height"],
                    "height": word["height"],
                }
            )

    # Keep the leftmost hit per member per row band.
    deduped: dict[tuple[str, int], dict] = {}
    for entry in entries:
        key = (entry["member"].name, entry["row_index"])
        if key not in deduped or entry["column_left"] < deduped[key]["column_left"]:
            deduped[key] = entry
    kept = list(deduped.values())

    grid = build_column_grid(
        [e["column_left"] for e in kept if e["column_anchor"] == "title"]
    )
    for entry in kept:
        column_x = snap_to_grid(grid, entry["surname_left"])
        entry["column_x"] = column_x if column_x is not None else entry["column_left"]
        entry["column_grid"] = grid
    return kept


def find_vote_icons(board: Image.Image) -> list[dict]:
    """Locate and classify the colour-coded member icons on a board crop.

    Blobs are screened on shape before hue is even considered. The panel's
    green edge glow used to come back as two confident YES votes at hue 80.7
    with 596 and 473 pixels -- four pixels under the old size ceiling and
    seven tenths of a degree over the old YES floor -- and the left one landed
    close enough to the first name column to override a correct read of it.
    A person glyph is a roughly square filled block about 11x11; those
    artefacts are 3x150 slivers, so side length, aspect ratio and fill reject
    them without depending on a hue threshold at all.
    """
    rgb = np.asarray(board.convert("RGB"), dtype=np.float32)
    height, width, _ = rgb.shape
    high = rgb.max(axis=2)
    low = rgb.min(axis=2)
    mask = ((high - low) / np.maximum(high, 1.0) > 0.30) & (high > 60)
    mask[: int(ICON_REGION_TOP * height), :] = False

    # A vote board carries a handful of small glyphs. Anything with this much
    # colour is a photo or a chart, and flood-filling it would cost seconds.
    if mask.sum() > ICON_MASK_MAX_PIXELS:
        return []

    seen = np.zeros_like(mask)
    icons: list[dict] = []
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        stack = [(int(sy), int(sx))]
        seen[sy, sx] = True
        pixels: list[tuple[int, int]] = []
        while stack:
            y, x = stack.pop()
            pixels.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if not (ICON_MIN_PIXELS <= len(pixels) <= ICON_MAX_PIXELS):
            continue

        ys = [p[0] for p in pixels]
        xs = [p[1] for p in pixels]
        box_w = max(xs) - min(xs) + 1
        box_h = max(ys) - min(ys) + 1
        if not (ICON_MIN_SIDE <= box_w <= ICON_MAX_SIDE):
            continue
        if not (ICON_MIN_SIDE <= box_h <= ICON_MAX_SIDE):
            continue
        if not (ICON_MIN_ASPECT <= box_w / box_h <= ICON_MAX_ASPECT):
            continue
        if len(pixels) / (box_w * box_h) < ICON_MIN_FILL:
            continue

        mean = rgb[ys, xs].mean(axis=0)
        peak, trough = float(mean.max()), float(mean.min())
        if peak <= 0:
            continue
        hue = 0.0
        span = peak - trough
        if span > 0:
            red, green, blue = (float(c) for c in mean)
            if peak == red:
                hue = (60 * ((green - blue) / span)) % 360
            elif peak == green:
                hue = 60 * ((blue - red) / span) + 120
            else:
                hue = 60 * ((red - green) / span) + 240
        value = next(
            (name for lo, hi, name in ICON_HUE_CLASSES if lo <= hue < hi), None
        )
        if not value:
            continue
        icons.append(
            {
                "value": value,
                "hue": round(hue, 1),
                "pixels": len(pixels),
                "left": int(min(xs)),
                "right": int(max(xs)),
                "top": int(min(ys)),
                "bottom": int(max(ys)),
                "width": int(box_w),
                "height": int(box_h),
                "centre_y": (min(ys) + max(ys)) / 2,
            }
        )
    return icons


# Format A vote marks are 40x16 letter blocks to the right of each name, not
# the ~11x11 person glyphs Format B uses. Yea green sits at hue ~87, which is
# the dead zone between Format B's RECUSE and YES bands, so those marks must
# not go through find_vote_icons.
FORMAT_A_MARK_MIN_PIXELS = 400
FORMAT_A_MARK_MAX_PIXELS = 1200
FORMAT_A_MARK_MIN_W, FORMAT_A_MARK_MAX_W = 28, 52
FORMAT_A_MARK_MIN_H, FORMAT_A_MARK_MAX_H = 10, 24
FORMAT_A_MARK_MIN_ASPECT, FORMAT_A_MARK_MAX_ASPECT = 1.7, 4.0
FORMAT_A_MARK_MIN_FILL = 0.70
FORMAT_A_MARK_REGION_TOP = 0.28
FORMAT_A_HUE_CLASSES: tuple[tuple[float, float, str], ...] = (
    (0.0, 25.0, "NO"),
    (70.0, 100.0, "YES"),
    (185.0, 250.0, "ABSTAIN"),
    (345.0, 360.0, "NO"),
)

# Format C (mid-2010s): same coloured letter blocks, but the stack starts above
# Format A's 0.28 cutoff (first Y at ~y 95 on 360-tall) and the column sits
# farther right (~x 379 vs Format A's ~360).
FORMAT_C_MARK_REGION_TOP = 0.22
FORMAT_C_MARK_LEFT_MIN = 370


def _rgb_hue(mean: np.ndarray) -> tuple[float, float]:
    peak, trough = float(mean.max()), float(mean.min())
    span = peak - trough
    if span <= 0:
        return 0.0, 0.0
    red, green, blue = (float(c) for c in mean)
    if peak == red:
        hue = (60 * ((green - blue) / span)) % 360
    elif peak == green:
        hue = 60 * ((blue - red) / span) + 120
    else:
        hue = 60 * ((red - green) / span) + 240
    return hue, span


def _find_letter_block_marks(
    image: Image.Image, *, region_top: float
) -> list[dict]:
    """Locate coloured Yea/Nay/Abstain letter blocks on a white Voting Results slide."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    height, width, _ = rgb.shape
    high = rgb.max(axis=2)
    low = rgb.min(axis=2)
    sat = (high - low) / np.maximum(high, 1.0)
    mask = (sat > 0.25) & (high > 70)
    mask[: int(region_top * height), :] = False
    if mask.sum() > ICON_MASK_MAX_PIXELS:
        return []

    seen = np.zeros_like(mask)
    marks: list[dict] = []
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        stack = [(int(sy), int(sx))]
        seen[sy, sx] = True
        pixels: list[tuple[int, int]] = []
        while stack:
            y, x = stack.pop()
            pixels.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if not (FORMAT_A_MARK_MIN_PIXELS <= len(pixels) <= FORMAT_A_MARK_MAX_PIXELS):
            continue
        ys = [p[0] for p in pixels]
        xs = [p[1] for p in pixels]
        box_w = max(xs) - min(xs) + 1
        box_h = max(ys) - min(ys) + 1
        if not (FORMAT_A_MARK_MIN_W <= box_w <= FORMAT_A_MARK_MAX_W):
            continue
        if not (FORMAT_A_MARK_MIN_H <= box_h <= FORMAT_A_MARK_MAX_H):
            continue
        if not (FORMAT_A_MARK_MIN_ASPECT <= box_w / box_h <= FORMAT_A_MARK_MAX_ASPECT):
            continue
        if len(pixels) / (box_w * box_h) < FORMAT_A_MARK_MIN_FILL:
            continue
        mean = rgb[ys, xs].mean(axis=0)
        hue, span = _rgb_hue(mean)
        if span < 40:
            continue
        value = next(
            (name for lo, hi, name in FORMAT_A_HUE_CLASSES if lo <= hue < hi),
            None,
        )
        if not value:
            continue
        marks.append(
            {
                "value": value,
                "hue": round(hue, 1),
                "pixels": len(pixels),
                "left": int(min(xs)),
                "right": int(max(xs)),
                "top": int(min(ys)),
                "bottom": int(max(ys)),
                "width": int(box_w),
                "height": int(box_h),
                "centre_y": (min(ys) + max(ys)) / 2,
            }
        )
    return marks


def find_format_a_marks(image: Image.Image) -> list[dict]:
    """Locate the coloured Yea/Nay/Abstain letter blocks on a Format A slide."""
    return _find_letter_block_marks(image, region_top=FORMAT_A_MARK_REGION_TOP)


def find_format_c_marks(image: Image.Image) -> list[dict]:
    """Locate green Y/N letter blocks on a mid-2010s Format C Voting Results slide."""
    return _find_letter_block_marks(image, region_top=FORMAT_C_MARK_REGION_TOP)


def format_a_mark_for_entry(marks: list[dict], entry: dict) -> dict | None:
    """Match a Format A name to the letter block immediately right of it."""
    scale = OCR_UPSCALE
    surname_right = (entry["surname_left"] + 8) / scale
    centre_y = (entry["top"] + entry["height"] / 2) / scale
    tolerance = max(8.0, entry["height"] / scale)
    best = None
    for mark in marks:
        if abs(mark["centre_y"] - centre_y) > tolerance:
            continue
        if mark["left"] < surname_right:
            continue
        gap = mark["left"] - surname_right
        if best is None or gap < best[0]:
            best = (gap, mark)
    return best[1] if best else None


def icon_for_entry(icons: list[dict], entry: dict) -> dict | None:
    """Match a name to the icon immediately left of it on the same row.

    The gap is measured from the column grid rather than from the entry's own
    left edge, and it has a floor as well as a ceiling. The glyph sits 28-29
    board pixels left of its column on every row of every board measured, so
    a blob that is merely somewhere in the 70px to the left is not evidence.
    """
    scale = OCR_UPSCALE
    name_left = entry.get("column_x", entry["column_left"]) / scale
    centre_y = (entry["top"] + entry["height"] / 2) / scale
    tolerance = max(6.0, entry["height"] / scale)

    best = None
    for icon in icons:
        if abs(icon["centre_y"] - centre_y) > tolerance:
            continue
        gap = name_left - icon["left"]
        if not (ICON_MIN_LEFT_GAP <= gap <= ICON_MAX_LEFT_GAP):
            continue
        if best is None or gap < best[0]:
            best = (gap, icon)
    return best[1] if best else None


def reread_vote_value(
    prepped: Image.Image, entry: dict
) -> tuple[str | None, str | None, dict | None]:
    """OCR just the small box where a member's vote value should sit.

    Returns (value, raw_text, box). Every word the box yields is scored and the
    best-scoring one wins, rather than the first that happened to normalize --
    Tesseract emits fragments left of the real word often enough that
    first-past-the-post handed the vote to a stray glyph.
    """
    column = entry.get("column_x", entry["column_left"])
    left = max(0, int(column) - 30)
    top = entry["top"] + int(0.85 * entry["height"])
    box = (
        left,
        top,
        min(prepped.width, left + 200),
        min(prepped.height, entry["top"] + int(2.3 * entry["height"])),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return None, None, None
    sub = prepped.crop(box)
    sub = sub.resize((sub.width * 3, sub.height * 3), Image.LANCZOS)

    best: tuple[float, str, str] | None = None
    for psm in (7, 8, 6):
        for word in tesseract_words(sub, psm=psm):
            value, score = roster_mod.normalize_vote_scored(word["text"])
            if value and (best is None or score > best[0]):
                best = (score, value, word["text"])
        if best and best[0] >= 1.0:
            break
    if not best:
        return None, None, None
    return best[1], best[2], {
        "left": box[0], "top": box[1],
        "width": box[2] - box[0], "height": box[3] - box[1],
        "source": "reread",
    }


VOTE_SOURCE_BOTH = "both"
VOTE_SOURCE_OCR = "ocr"
VOTE_SOURCE_ICON = "icon"
VOTE_SOURCE_CONFLICT = "conflict"

# Fraction of the column pitch a value word may sit off its column and still
# belong to it. A fraction of the pitch, deliberately, rather than a multiple of
# the entry's own text height: the old `3 * entry["height"]` window shrank on
# exactly the rows that were parsed badly.
VALUE_COLUMN_FRACTION = 0.20


def _column_pitch(grid: list[float], fallback: float) -> float:
    if len(grid) >= 2:
        return _median([grid[i + 1] - grid[i] for i in range(len(grid) - 1)])
    return fallback


def read_value_for_entry(rows: list[list[dict]], entry: dict) -> tuple[str | None, str | None, float, dict | None]:
    """Find the vote word printed under one member's name.

    Returns (value, raw_text, score, box). Candidates come from the rows below
    the name *and* from the name's own row below the surname's baseline, because
    a row that absorbed the value line puts the value in the same row rather
    than a later one. Every candidate is scored and the best one wins; taking
    the first word in the window that happened to normalize is how a one- or
    two-character fragment beat the real word next to it.
    """
    grid = entry.get("column_grid") or []
    column = entry.get("column_x", entry["column_left"])
    tolerance = VALUE_COLUMN_FRACTION * _column_pitch(grid, 15 * max(entry["height"], 1))

    candidates: list[dict] = []
    own_row = rows[entry["row_index"]] if entry["row_index"] < len(rows) else []
    for word in own_row:
        if word["top"] >= entry["bottom"] - 0.2 * entry["height"]:
            candidates.append(word)
    for row in rows[entry["row_index"] + 1 :]:
        if min(w["top"] for w in row) > entry["bottom"] + 2.5 * entry["height"]:
            break
        candidates.extend(row)

    best: tuple[float, float, str, str, dict] | None = None
    for word in candidates:
        offset = abs(word["left"] - column)
        if offset > tolerance:
            continue
        value, score = roster_mod.normalize_vote_scored(word["text"])
        if not value:
            continue
        # Highest score first, then the word sitting closest to the column.
        rank = (score, -offset)
        if best is None or rank > (best[0], best[1]):
            box = {
                "left": word["left"], "top": word["top"],
                "width": word["width"], "height": word["height"],
                "conf": word["conf"], "source": "row_scan",
            }
            best = (score, -offset, value, word["text"], box)
    if best is None:
        return None, None, 0.0, None
    return best[2], best[3], best[0], best[4]


def parse_individual_votes(
    rows: list[list[dict]],
    era: roster_mod.Era,
    prepped: Image.Image | None = None,
    icons: list[dict] | None = None,
) -> dict:
    """Read each member's vote off both independent channels on the board.

    The coloured glyph and the printed word are produced by different parts of
    the slide and read by completely different code, so agreement between them
    is real evidence and disagreement is a real problem. The old code resolved
    a disagreement by overwriting the OCR value with the icon's and carried on,
    and only recorded the conflict when the OCR had produced something -- an
    icon supplying a vote for a name whose word could not be read at all left
    no trace, and looked exactly like a corroborated read.

    Nothing here infers a vote from the tally; an unreadable member stays
    unreadable.
    """
    votes: dict[str, str] = {}
    details: dict[str, dict] = {}
    unresolved: list[dict] = []
    conflicts: list[dict] = []

    for entry in find_name_entries(rows, era):
        name = entry["member"].name
        value, raw_value, score, value_box = read_value_for_entry(rows, entry)
        if value is None and prepped is not None:
            value, raw_value, value_box = reread_vote_value(prepped, entry)

        icon = icon_for_entry(icons, entry) if icons else None
        icon_value = icon["value"] if icon else None

        if value is not None and icon_value is not None:
            if value == icon_value:
                source = VOTE_SOURCE_BOTH
                final = value
            else:
                source = VOTE_SOURCE_CONFLICT
                # Keep the glyph's reading in the record -- it is the more
                # robust signal -- but the conflict is what decides the vote's
                # fate, in validate(), rather than being silently absorbed here.
                final = icon_value
        elif value is not None:
            source, final = VOTE_SOURCE_OCR, value
        elif icon_value is not None:
            source, final = VOTE_SOURCE_ICON, icon_value
        else:
            source, final = None, None

        if source == VOTE_SOURCE_CONFLICT:
            conflicts.append(
                {
                    "member": name,
                    "icon": icon_value,
                    "hue": icon["hue"],
                    "icon_box": {
                        "left": icon["left"], "top": icon.get("top"),
                        "width": icon.get("width"), "height": icon.get("height"),
                    },
                    "ocr": value,
                    "ocr_raw": raw_value,
                    "ocr_score": round(score, 3),
                    "ocr_box": value_box,
                }
            )

        details[name] = {
            "value": final,
            "source": source,
            "ocr_value": value,
            "ocr_raw": raw_value,
            "ocr_score": round(score, 3) if value else 0.0,
            "value_box": value_box,
            "icon_value": icon_value,
            "icon_hue": icon["hue"] if icon else None,
            "icon_box": (
                {
                    "left": icon["left"], "top": icon.get("top"),
                    "width": icon.get("width"), "height": icon.get("height"),
                }
                if icon
                else None
            ),
            "column_x": entry.get("column_x"),
            "column_anchor": entry.get("column_anchor"),
            "row_index": entry["row_index"],
        }

        if final:
            votes[name] = final
        else:
            unresolved.append(
                {"raw_name": entry["raw"], "member": name, "matched": True}
            )

    return {
        "individual_votes": votes,
        "vote_details": details,
        "unresolved": unresolved,
        "icon_conflicts": conflicts,
    }


def ocr_parse_board(image: Image.Image, era: roster_mod.Era) -> dict:
    board = crop_fractional(image, BOARD_BOX)
    prepped = prep_for_ocr(board)
    words, ocr_status = run_tesseract(prepped)
    rows = group_rows(words)
    result, result_raw = parse_result(rows)
    if result is None:
        result, result_raw = read_result_bar(board)
    tally, tally_problem = parse_tally_detail(rows)
    parsed = parse_individual_votes(rows, era, prepped, find_vote_icons(board))
    return {
        "parser": "tesseract_roster",
        "ocr_status": ocr_status,
        "vote_tally": tally,
        "tally_problem": tally_problem,
        "result": result,
        "result_raw": result_raw,
        "individual_votes": parsed["individual_votes"],
        "vote_details": parsed["vote_details"],
        "unresolved": parsed["unresolved"],
        "icon_conflicts": parsed["icon_conflicts"],
        "ocr_text": words_text(words),
    }


FORMAT_A_REVIEW_PROBLEM = (
    "Format A board requires GEMINI_API_KEY or manual review"
)


def read_format_a_result(image: Image.Image) -> tuple[str | None, str | None]:
    """Recover a Format A/C Motion Passes/Fails line when the full-frame OCR drops it.

    On late-2025 Format A boards the result often sits in the bottom band. On
    mid-2010s Format C slides it sits higher (~0.58–0.75), just above the
    agenda banner — bands that only start at 0.65 were swallowing the banner
    and rejecting the strip as "too long" agenda prose. Never invents an
    outcome from the tally. Agenda-banner prose in the same band is rejected
    unless the line clearly carries a Motion Passes/Fails style outcome.
    """
    width, height = image.size
    best: tuple[float, str, str] | None = None
    # Prefer the Format C mid-band first (short Motion Passes line), then the
    # lower Format A bands. Order matters only for which strip label we keep.
    bands = (
        (0.58, 0.72),
        (0.60, 0.75),
        (0.62, 0.78),
        (0.65, 0.82),
        (0.72, 0.98),
        (0.78, 1.0),
        (0.65, 0.90),
    )
    for top, bottom in bands:
        strip = image.crop((0, int(top * height), width, int(bottom * height)))
        prepped = ImageOps.autocontrast(strip.convert("L")).filter(ImageFilter.SHARPEN)
        for scale in (3, 5):
            scaled = prepped.resize(
                (prepped.width * scale, prepped.height * scale), Image.LANCZOS
            )
            for psm in (6, 7, 11):
                text = words_text(tesseract_words(scaled, psm=psm))
                if not text:
                    continue
                flat = squash(text)
                tokens = set(roster_mod.result_tokens(text))
                # Agenda banners in the lower third are long and often contain
                # the word "motion" (Consent Calendar boilerplate). The real
                # result bar is a short Motion Passes/Fails line.
                if len(roster_mod.result_tokens(text)) > 10:
                    continue
                if not tokens.intersection(
                    {"motion", "result", "passed", "passes", "failed", "fails", "fail", "carried", "tie", "tied"}
                ):
                    continue
                normalized, score = roster_mod.normalize_result_fuzzy(text)
                if normalized and (best is None or score > best[0]):
                    best = (score, normalized, f"{text.strip()} [a_strip_{top:.2f}-{bottom:.2f} x{scale} psm{psm}]")
                    if score >= 1.0:
                        return normalized, best[2]
    return (best[1], best[2]) if best else (None, None)


def result_from_mark_tally(tally: dict | None) -> str | None:
    """Infer passed/failed/tie from a complete letter-block mark tally.

    Used only when the Motion Passes/Fails (or Format A result) banner OCR
    fails. Does not invent member votes — only labels the already-counted
    ayes/noes outcome the same way the on-screen banner would.
    """
    if not tally:
        return None
    ayes = int(tally.get("ayes") or 0)
    noes = int(tally.get("noes") or 0)
    if ayes == 0 and noes == 0:
        return None
    if ayes == noes:
        return "tie"
    if ayes > noes:
        return "passed"
    return "failed"


# Back-compat alias used by tests and Format C call sites.
result_from_format_c_tally = result_from_mark_tally


def ocr_parse_format_a(image: Image.Image, era: roster_mod.Era) -> dict:
    """Parse a white Format A slide from names plus coloured letter blocks.

    Boxed tally digits on this layout OCR as Q/O/4, so the tally is counted
    from the classified marks rather than from those digits. A member with no
    mark stays unresolved; nothing is filled in from the printed totals.
    """
    return _ocr_parse_letter_block_slide(
        image,
        era,
        format_name=FORMAT_A,
        parser="tesseract_format_a_marks",
        find_marks=find_format_a_marks,
        empty_tally_problem="no Format A member marks read",
    )


def read_format_c_agenda_banner(image: Image.Image) -> str | None:
    """OCR the lower-third agenda/motion banner on a Format C slide."""
    width, height = image.size
    strip = image.crop((0, int(0.62 * height), width, height))
    prepped = ImageOps.autocontrast(strip.convert("L")).filter(ImageFilter.SHARPEN)
    scaled = prepped.resize(
        (prepped.width * 3, prepped.height * 3), Image.LANCZOS
    )
    text = words_text(tesseract_words(scaled, psm=6)).strip()
    if len(text) < 12:
        return None
    # Reject if the strip is mostly the Motion Passes banner with no agenda body.
    flat = squash(text)
    if "motionpasses" in flat or "motionfails" in flat:
        if len(roster_mod.result_tokens(text)) <= 4 and "consider" not in flat:
            # Try a slightly lower crop that skips the result banner.
            strip = image.crop((0, int(0.70 * height), width, height))
            prepped = ImageOps.autocontrast(strip.convert("L")).filter(ImageFilter.SHARPEN)
            scaled = prepped.resize(
                (prepped.width * 3, prepped.height * 3), Image.LANCZOS
            )
            text = words_text(tesseract_words(scaled, psm=6)).strip()
    return text or None


def ocr_parse_format_c(image: Image.Image, era: roster_mod.Era) -> dict:
    """Parse a mid-2010s Format C Voting Results slide (green Y column).

    Same letter-block approach as Format A, with a higher mark region so the
    first councilmember is not clipped. Also captures the lower-third agenda
    banner for transcript cross-check.
    """
    parsed = _ocr_parse_letter_block_slide(
        image,
        era,
        format_name=FORMAT_C,
        parser="tesseract_format_c_marks",
        find_marks=find_format_c_marks,
        empty_tally_problem="no Format C member marks read",
    )
    parsed["agenda_banner"] = read_format_c_agenda_banner(image)
    return parsed


def _ocr_parse_letter_block_slide(
    image: Image.Image,
    era: roster_mod.Era,
    *,
    format_name: str,
    parser: str,
    find_marks,
    empty_tally_problem: str,
) -> dict:
    words, ocr_status = run_tesseract(prep_format_a_for_ocr(image))
    rows = group_rows(words)
    result, result_raw = parse_result(rows)
    if result is None:
        result, result_raw = read_format_a_result(image)
    marks = find_marks(image)
    votes: dict[str, str] = {}
    details: dict[str, dict] = {}
    unresolved: list[dict] = []
    for entry in find_name_entries(rows, era):
        name = entry["member"].name
        mark = format_a_mark_for_entry(marks, entry)
        if mark is None:
            unresolved.append(
                {"raw_name": entry["raw"], "member": name, "matched": True}
            )
            details[name] = {
                "value": None,
                "source": None,
                "icon_value": None,
                "column_x": entry.get("column_x"),
                "row_index": entry["row_index"],
            }
            continue
        votes[name] = mark["value"]
        details[name] = {
            "value": mark["value"],
            "source": VOTE_SOURCE_ICON,
            "icon_value": mark["value"],
            "icon_hue": mark["hue"],
            "icon_box": {
                "left": mark["left"], "top": mark["top"],
                "width": mark["width"], "height": mark["height"],
            },
            "column_x": entry.get("column_x"),
            "row_index": entry["row_index"],
        }
    tally_map = {
        "YES": "ayes", "NO": "noes", "ABSTAIN": "abstentions", "RECUSE": "recused",
    }
    tally = {key: 0 for key in ("ayes", "noes", "abstentions", "recused")}
    for value in votes.values():
        tally[tally_map[value]] += 1
    vote_tally = tally if votes else None
    result_inferred = False
    if result is None and vote_tally:
        inferred = result_from_mark_tally(vote_tally)
        if inferred:
            result = inferred
            result_raw = (
                f"inferred from {format_name} mark tally "
                f"{vote_tally} [no result banner OCR]"
            )
            result_inferred = True
    payload = {
        "format": format_name,
        "parser": parser,
        "ocr_status": ocr_status,
        "vote_tally": vote_tally,
        "tally_problem": None if votes else empty_tally_problem,
        "result": result,
        "result_raw": result_raw,
        "individual_votes": votes,
        "vote_details": details,
        "vote_sources": {name: VOTE_SOURCE_ICON for name in votes},
        "unresolved": unresolved,
        "icon_conflicts": [],
        "ocr_text": words_text(words),
    }
    if result_inferred:
        payload["result_inferred_from_tally"] = True
    return payload


def consensus_pick(counts: Counter, total: int) -> dict:
    """Pick the winning read of one field and report how well supported it is.

    `Counter.most_common(1)` was used for this, which silently breaks a tie on
    insertion order -- the first frame that happened to be counted won -- and
    imposed no minimum, so a field read by one frame out of seven was reported
    with the same authority as one read by seven out of seven. A tie here
    resolves to no value at all and the caller blocks the vote.
    """
    if not counts:
        return {"value": None, "count": 0, "reads": 0, "total": total,
                "fraction": 0.0, "tied": False}
    ranked = counts.most_common()
    top_count = ranked[0][1]
    winners = [value for value, count in ranked if count == top_count]
    reads = sum(counts.values())
    return {
        "value": winners[0] if len(winners) == 1 else None,
        "count": top_count,
        "reads": reads,
        "total": total,
        "fraction": (top_count / total) if total else 0.0,
        "tied": len(winners) > 1,
        "candidates": sorted(winners) if len(winners) > 1 else None,
    }


def consensus_parse_format_a(group: list[dict], era: roster_mod.Era) -> dict:
    """Parse Format A marks from the sharpest frame; majority-vote the result.

    Format A member marks and the computed tally come from one sharp evidence
    frame so a blurry neighbour cannot invent a Nay. The result line is faint
    or cropped on some frames even when the marks are clear (late-2025
    rejects), so every cluster frame is OCR'd for the result and the majority
    outcome wins. If every frame still misses the banner, infer passed/failed
    from the mark tally only — never invent member votes.
    """
    return _consensus_parse_letter_block_slide(
        group,
        era,
        probe_key="_probe_a",
        parse_one=ocr_parse_format_a,
        consensus_parser="tesseract_format_a_marks_consensus",
    )


def consensus_parse_format_c(group: list[dict], era: roster_mod.Era) -> dict:
    """Parse Format C marks from the sharpest frame; majority-vote the result."""
    return _consensus_parse_letter_block_slide(
        group,
        era,
        probe_key="_probe_c",
        parse_one=ocr_parse_format_c,
        consensus_parser="tesseract_format_c_marks_consensus",
    )


def _consensus_parse_letter_block_slide(
    group: list[dict],
    era: roster_mod.Era,
    *,
    probe_key: str,
    parse_one,
    consensus_parser: str,
) -> dict:
    winner = pick_sharpest(group)
    if winner.get(probe_key) is not None:
        base = dict(winner[probe_key])
    else:
        with Image.open(winner["frame"]) as image:
            base = parse_one(image, era)
        winner[probe_key] = base

    reads: list[dict] = []
    for frame in group:
        read = frame.get(probe_key)
        if read is None:
            with Image.open(frame["frame"]) as image:
                read = parse_one(image, era)
            frame[probe_key] = read
        reads.append(read)

    total = len(reads)
    results = Counter(r["result"] for r in reads if r.get("result"))
    result_pick = consensus_pick(results, total)
    base = dict(base)
    base["parser"] = consensus_parser
    base["frames_merged"] = total
    base["result"] = result_pick["value"]
    base["result_agreement"] = f"{result_pick['count']}/{total}"
    base["result_consensus"] = result_pick
    if result_pick["value"]:
        base["result_raw"] = next(
            (
                r.get("result_raw")
                for r in reads
                if r.get("result") == result_pick["value"] and r.get("result_raw")
            ),
            base.get("result_raw"),
        )
    else:
        # Preserve any single-frame raw text for audit, but do not invent an
        # outcome when the cluster did not agree.
        if not base.get("result"):
            base["result_raw"] = next(
                (r.get("result_raw") for r in reads if r.get("result_raw")),
                base.get("result_raw"),
            )
    if not base.get("result") and result_pick["reads"] == 0:
        # Infer only when every frame missed the banner. A tied OCR disagreement
        # (passed vs failed) must stay unresolved — do not paper over it with
        # the mark tally.
        inferred = result_from_mark_tally(base.get("vote_tally"))
        if inferred:
            base["result"] = inferred
            base["result_raw"] = (
                f"inferred from mark tally {base.get('vote_tally')} "
                f"[no result banner consensus]"
            )
            base["result_inferred_from_tally"] = True
    return base


def consensus_parse(group: list[dict], era: roster_mod.Era) -> dict:
    """Merge the OCR reads of every frame showing the same board.

    A single 1 fps frame of a compressed slide often drops one member's value.
    The slide is static for several seconds, so the majority read per field
    across the cluster recovers what any one frame misses -- but only when
    there genuinely is a majority. The support for every field is reported
    structurally so `validate` can act on it, rather than only as a "3/5"
    string that nothing read.
    """
    reads = []
    for frame in group:
        read = frame.get("_probe")
        if read is None:
            with Image.open(frame["frame"]) as image:
                read = ocr_parse_board(image, era)
            frame["_probe"] = read
        reads.append(read)

    total = len(reads)
    tallies = Counter(
        tuple(r["vote_tally"][k] for k in TALLY_KEYS)
        for r in reads
        if r.get("vote_tally")
    )
    results = Counter(r["result"] for r in reads if r.get("result"))

    per_member: dict[str, Counter] = {}
    source_counts: dict[str, Counter] = {}
    for read in reads:
        for name, value in (read.get("individual_votes") or {}).items():
            per_member.setdefault(name, Counter())[value] += 1
        for name, detail in (read.get("vote_details") or {}).items():
            if detail.get("source"):
                source_counts.setdefault(name, Counter())[detail["source"]] += 1

    tally_pick = consensus_pick(tallies, total)
    result_pick = consensus_pick(results, total)
    member_picks = {
        name: consensus_pick(counts, total) for name, counts in sorted(per_member.items())
    }

    votes = {
        name: pick["value"] for name, pick in member_picks.items() if pick["value"]
    }
    unresolved = [
        {"member": u["member"], "raw_name": u.get("raw_name"), "matched": True}
        for read in reads
        for u in read.get("unresolved") or []
        if u.get("member") not in votes
    ]
    # A member whose reads tied is unreadable, not absent.
    unresolved += [
        {"member": name, "raw_name": None, "matched": True}
        for name, pick in member_picks.items()
        if pick["tied"]
    ]
    seen: set[str] = set()
    unresolved = [
        u for u in unresolved if not (u["member"] in seen or seen.add(u["member"]))
    ]
    # Never invent a YES/NO for a member we also marked unreadable.
    unreadable_names = {u["member"] for u in unresolved if u.get("member")}
    if unreadable_names:
        votes = {name: value for name, value in votes.items() if name not in unreadable_names}

    tally = (
        dict(zip(TALLY_KEYS, tally_pick["value"])) if tally_pick["value"] else None
    )

    # The strongest source seen for each member across the cluster. "conflict"
    # is sticky: if any frame saw the icon and the word disagree, that is the
    # fact about this board, not something a luckier frame overwrites.
    vote_sources: dict[str, str] = {}
    for name, counts in source_counts.items():
        if counts.get(VOTE_SOURCE_CONFLICT):
            vote_sources[name] = VOTE_SOURCE_CONFLICT
        elif counts.get(VOTE_SOURCE_BOTH):
            vote_sources[name] = VOTE_SOURCE_BOTH
        elif counts.get(VOTE_SOURCE_OCR) and counts.get(VOTE_SOURCE_ICON):
            # Corroborated across frames rather than within one frame.
            vote_sources[name] = VOTE_SOURCE_BOTH
        elif counts.get(VOTE_SOURCE_OCR):
            vote_sources[name] = VOTE_SOURCE_OCR
        else:
            vote_sources[name] = VOTE_SOURCE_ICON

    return {
        "parser": "tesseract_roster_consensus",
        "frames_merged": total,
        "ocr_failures": sum(
            1 for r in reads if r.get("ocr_status") not in (None, TESS_OK)
        ),
        "vote_tally": tally,
        "tally_agreement": f"{tally_pick['count']}/{total}",
        "tally_consensus": tally_pick,
        "tally_problem": next(
            (r.get("tally_problem") for r in reads if r.get("tally_problem")), None
        ),
        "result": result_pick["value"],
        "result_agreement": f"{result_pick['count']}/{total}",
        "result_consensus": result_pick,
        "result_raw": next((r.get("result_raw") for r in reads if r.get("result")), None),
        "individual_votes": votes,
        "vote_agreement": {
            name: f"{pick['count']}/{pick['reads']}" for name, pick in member_picks.items()
        },
        "vote_consensus": member_picks,
        "vote_sources": vote_sources,
        # One representative read per member, chosen to be a frame that agreed
        # with the consensus, so the recorded bounding boxes belong to the value
        # actually published rather than to whichever frame happened to be last.
        "vote_details": _representative_details(reads, votes),
        "unresolved": unresolved,
        "icon_conflicts": _dedupe_conflicts(
            [conflict for read in reads for conflict in read.get("icon_conflicts") or []]
        ),
        "ocr_text": next((r.get("ocr_text") for r in reads if r.get("ocr_text")), ""),
    }


def _representative_details(reads: list[dict], votes: dict[str, str]) -> dict[str, dict]:
    """Pick one per-member read to keep as the audit record for the vote.

    Preference goes to a frame that saw the consensus value on both channels,
    then to any frame that saw the consensus value, then to anything at all.
    """
    rank = {VOTE_SOURCE_BOTH: 3, VOTE_SOURCE_OCR: 2, VOTE_SOURCE_ICON: 2,
            VOTE_SOURCE_CONFLICT: 1, None: 0}
    chosen: dict[str, tuple[int, dict]] = {}
    for read in reads:
        for name, detail in (read.get("vote_details") or {}).items():
            agrees = 1 if detail.get("value") == votes.get(name) else 0
            score = agrees * 10 + rank.get(detail.get("source"), 0)
            if name not in chosen or score > chosen[name][0]:
                chosen[name] = (score, detail)
    return {name: detail for name, (_score, detail) in sorted(chosen.items())}


def _dedupe_conflicts(conflicts: list[dict]) -> list[dict]:
    """One entry per (member, icon, ocr) triple, with how many frames saw it."""
    merged: dict[tuple, dict] = {}
    for conflict in conflicts:
        key = (conflict["member"], conflict.get("icon"), conflict.get("ocr"))
        if key in merged:
            merged[key]["frames"] += 1
        else:
            merged[key] = {**conflict, "frames": 1}
    return sorted(merged.values(), key=lambda c: c["member"])


# --- vision parsing --------------------------------------------------------

def gemini_key() -> tuple[str | None, str | None]:
    for name in GEMINI_KEY_ENVS:
        value = os.environ.get(name)
        if value:
            return value, name
    return None, None


def vision_parse_board(
    image: Image.Image, era: roster_mod.Era, format_name: str = FORMAT_B
) -> dict:
    key, key_env = gemini_key()
    if not key:
        raise RuntimeError(
            "no vision API key; set GEMINI_API_KEY (never hardcode one)"
        )

    buffer = io.BytesIO()
    vision_image = image if format_name in BRIGHT_FORMATS else crop_fractional(image, OVERLAY_BOX)
    vision_image.save(buffer, format="PNG")
    prompt = VISION_PROMPT + (
        VISION_FORMAT_A_NOTE if format_name in BRIGHT_FORMATS else ""
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": base64.b64encode(buffer.getvalue()).decode(),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"vision call failed: {exc.code} {exc.read()[:300]!r}") from exc

    text = "".join(
        part.get("text", "")
        for part in body["candidates"][0]["content"]["parts"]
    )
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(text)

    votes: dict[str, str] = {}
    unresolved: list[dict] = []
    for raw_name, raw_value in (data.get("individual_votes") or {}).items():
        member = roster_mod.match_member(raw_name, era)
        value = roster_mod.normalize_vote(str(raw_value))
        if member and value:
            votes[member.name] = value
        else:
            unresolved.append(
                {"raw_name": raw_name, "raw_value": raw_value, "matched": bool(member)}
            )
    return {
        "format": format_name,
        "parser": f"gemini:{GEMINI_MODEL}",
        "parser_key_env": key_env,
        "vote_tally": {
            "ayes": int(data.get("ayes") or 0),
            "noes": int(data.get("noes") or 0),
            "abstentions": int(data.get("abstentions") or 0),
            "recused": int(data.get("recused") or 0),
        },
        "result": roster_mod.normalize_result(str(data.get("result") or "")),
        "result_raw": data.get("result"),
        "motion_text": data.get("motion_text"),
        "individual_votes": votes,
        "unresolved": unresolved,
    }


# --- validation ------------------------------------------------------------

VOTE_TO_TALLY = {
    "YES": "ayes",
    "NO": "noes",
    "ABSTAIN": "abstentions",
    "RECUSE": "recused",
}

VOTE_SOURCE_POLICIES = ("both", "agree", "any")
# What corroboration a member's vote needs. The blocking condition is
# disagreement between the two channels, not absence of one of them: measured
# on clip 14821 the glyph channel reads 53/53 member-votes correctly while
# whole-board OCR reads 22/53 exactly, so demanding both channels for every
# member throws out roughly 60% of correct votes. That is a far worse failure
# than the one it guards against, and it fails in the direction of publishing
# nothing rather than of being caught. "both" is kept as an opt-in audit mode.
VOTE_SOURCE_POLICY_DEFAULT = "agree"


def _channel_problems(parsed: dict, policy: str) -> list[str]:
    """Blocking problems from the icon channel disagreeing with the text channel.

    A disagreement used to be resolved by fiat -- the glyph overwrote the word
    and the run carried on. Two live examples on Sep 1 2026 alone: Kartsonis
    read RECUSE by glyph against YES by word, and Lewis read YES by glyph
    against NO by word. Either one silently changed a published vote.

    A member seen on only one channel is not that problem. It is one channel
    reading a value and the other reading nothing, which is missing evidence,
    not contradictory evidence, and the glyph alone is the stronger of the two
    reads anyway.
    """
    problems: list[str] = []
    conflicts = parsed.get("icon_conflicts") or []
    if conflicts and policy != "any":
        problems.append(
            "icon/OCR disagreement for "
            + ", ".join(
                f"{c['member']} (glyph {c.get('icon')} hue {c.get('hue')} vs "
                f"word {c.get('ocr')} from {c.get('ocr_raw')!r})"
                for c in conflicts
            )
        )

    if policy == "both":
        sources = parsed.get("vote_sources") or {}
        votes = parsed.get("individual_votes") or {}
        uncorroborated = sorted(
            f"{name} ({sources.get(name) or 'unknown'} only)"
            for name in votes
            if sources.get(name) not in (VOTE_SOURCE_BOTH,)
        )
        if uncorroborated:
            problems.append(
                "vote read from a single channel for: " + ", ".join(uncorroborated)
            )
    return problems


def _agreement_problems(parsed: dict) -> list[str]:
    """Blocking problems from a read that too few frames of the cluster support."""
    problems: list[str] = []

    result = parsed.get("result_consensus")
    if result and result.get("total"):
        reads = result.get("reads") or 0
        if result.get("tied"):
            problems.append(
                "result is a tie between "
                + " and ".join(result.get("candidates") or [])
                + f" across {result['total']} frames"
            )
        elif reads and result.get("count", 0) * 2 <= reads:
            problems.append(
                f"result {parsed.get('result')!r} read from only "
                f"{result['count']}/{reads} of the frames that read a result, "
                f"which is not a majority of them"
            )

    for name, pick in sorted((parsed.get("vote_consensus") or {}).items()):
        if pick.get("tied"):
            problems.append(
                f"{name}: frames split evenly between "
                + " and ".join(pick.get("candidates") or [])
            )
        elif pick.get("reads") and pick["count"] * 2 <= pick["reads"]:
            problems.append(
                f"{name}: winning read {pick['count']}/{pick['reads']} is not a "
                f"majority of the frames that read them"
            )
    return problems


def validate(
    parsed: dict,
    era: roster_mod.Era,
    partial_board: str = "absent",
    vote_source_policy: str = VOTE_SOURCE_POLICY_DEFAULT,
) -> tuple[list[str], list[str]]:
    """Return (blocking problems, roster members with no vote on the slide).

    Granicus omits a member entirely when they cast no vote, so a board smaller
    than the seated council is legitimate. That case is recorded as absentees
    rather than invented data; `--partial-board reject` makes it fatal instead.

    Every check the old version made was a multiset count: how many YES votes
    the slide claims against how many members were named YES. That is blind to
    *which* member cast which vote, so swapping two members' values on a real
    5-1-0-1 board produced no problems at all. The cross-check that catches a
    permutation is the per-member one between the two independent channels --
    the coloured glyph and the printed word are at different places on the
    slide and read by different code, so they cannot be permuted together.
    """
    problems: list[str] = []
    tally = parsed.get("vote_tally")
    votes = parsed.get("individual_votes") or {}

    if parsed.get("format_problem"):
        problems.append(parsed["format_problem"])
    if not tally:
        problems.append(
            "no tally read from the slide"
            + (f": {parsed['tally_problem']}" if parsed.get("tally_problem") else "")
        )
    if not parsed.get("result"):
        problems.append("result line did not normalize to passed/failed/tie")
    if not votes:
        problems.append("no individual votes read")

    if tally:
        counted = {key: 0 for key in VOTE_TO_TALLY.values()}
        for value in votes.values():
            key = VOTE_TO_TALLY.get(value)
            if key:
                counted[key] += 1
        for key, expected in counted.items():
            if int(tally.get(key, 0)) != expected:
                problems.append(
                    f"{key}: slide says {tally.get(key)} but {expected} members named"
                )
        # Abstentions and recusals are not votes against. Counting them in the
        # denominator rejected 3-2 with two recusals, and 3-0 with four
        # abstentions, both of which genuinely carry.
        decisive = int(tally.get("ayes", 0)) + int(tally.get("noes", 0))
        if decisive and parsed.get("result") == "passed" and int(tally.get("ayes", 0)) * 2 <= decisive:
            problems.append(
                f"result says passed but ayes ({tally.get('ayes')}) are not a "
                f"majority of the {decisive} votes for or against"
            )
        if decisive and parsed.get("result") == "failed" and int(tally.get("noes", 0)) * 2 <= decisive:
            problems.append(
                f"result says failed but noes ({tally.get('noes')}) are not a "
                f"majority of the {decisive} votes for or against"
            )

    problems.extend(_channel_problems(parsed, vote_source_policy))
    problems.extend(_agreement_problems(parsed))

    roster_names = {m.name for m in era.members}
    off_roster = sorted(set(votes) - roster_names)
    if off_roster:
        problems.append(
            f"name(s) not on the {era.key} roster: {', '.join(off_roster)}"
        )

    absent = sorted(roster_names - set(votes))
    if len(votes) > max(era.sizes):
        problems.append(
            f"{len(votes)} members named, era {era.key} seats at most {max(era.sizes)}"
        )
    elif len(votes) not in era.sizes:
        if partial_board == "reject":
            problems.append(
                f"{len(votes)} members named, era {era.key} expects {list(era.sizes)}"
            )

    unreadable = [
        u["member"] for u in parsed.get("unresolved") or [] if u.get("member") in roster_names
    ]
    if unreadable:
        problems.append(
            "vote value unreadable for: " + ", ".join(sorted(set(unreadable)))
        )
        # Never invent YES/NO for a member we could not read.
        unread_set = set(unreadable)
        cleaned = {name: value for name, value in votes.items() if name not in unread_set}
        if cleaned != votes:
            parsed["individual_votes"] = cleaned
            votes = cleaned
            absent = sorted(roster_names - set(votes))
    return problems, absent


# --- agenda binding --------------------------------------------------------

def is_non_item(title: str | None) -> bool:
    """Whether a cuepoint marks no substantive business.

    Tested against the heading only; see AGENDA_HEADING_CHARS for why the body
    cannot be allowed to vote on this.
    """
    return bool(AGENDA_NON_ITEM.search((title or "")[:AGENDA_HEADING_CHARS]))


def _meta_key(value) -> tuple[int, int, str]:
    """Numeric sort key for a Granicus meta id.

    Granicus emits several cuepoints on the same second, so this tie-break is
    what decides which of them a vote binds to. Compared as strings, '9' sorts
    above '451683' and `max()` returns the wrong agenda item entirely. Ids that
    are not purely numeric keep a deterministic slot after the numeric ones.
    """
    text = str(value)
    if text.isdigit():
        return (0, int(text), "")
    return (1, 0, text)


def _agenda_order(item: dict) -> tuple[float, tuple[int, int, str]]:
    return (item["time"], _meta_key(item.get("meta_id")))


def bind_agenda(
    agenda: list[dict], timestamp: float, board_last_seen: float | None = None
) -> dict | None:
    """The latest cuepoint at or before the vote. Kept for existing callers."""
    return bind_agenda_detail(agenda, timestamp, board_last_seen)["item"]


def bind_agenda_detail(
    agenda: list[dict],
    timestamp: float,
    board_last_seen: float | None = None,
    uncertainty: float = BINDING_UNCERTAINTY_SECONDS,
) -> dict:
    """Bind a vote to an agenda item, and say when that binding is ambiguous.

    Taking the latest cuepoint at or before the vote is right, and the vote's
    timestamp is already the first frame the board appeared on. What neither
    accounts for is that detection is sparse: `min(group)` can land seconds
    after the board really came up, and the clerk often advances the cuepoint
    while the result is still on screen. On Sep 1 2026 the board was visible
    from 6908 to 6930 with a cuepoint at 6910 titled "11. AGENCY AGENDAS - None
    Scheduled", so binding at 6908 gives the right item and binding three
    frames later gives a heading for nothing at all. Whether the answer is
    right then depends on which frame the detector happened to catch.

    So both candidates are recorded, and a cuepoint that advanced to real
    business while the board was up makes the binding ambiguous rather than
    quietly resolved. A cuepoint that only advanced to a non-item ("None
    Scheduled", a recess) is recorded but is not ambiguity: there is nothing it
    could plausibly be the item for.
    """
    before_candidates = [a for a in agenda if a["time"] <= timestamp]
    before = (
        max(before_candidates, key=_agenda_order) if before_candidates else None
    )

    during: list[dict] = []
    if board_last_seen is not None:
        during = sorted(
            (a for a in agenda if timestamp < a["time"] <= board_last_seen),
            key=_agenda_order,
        )

    substantive_during = [a for a in during if not is_non_item(a.get("title"))]
    problems: list[str] = []
    if substantive_during:
        problems.append(
            "agenda cuepoint advanced while the board was still on screen "
            f"(vote at {timestamp:.0f}s, board until {board_last_seen:.0f}s, "
            + "; ".join(
                f"{a['meta_id']} at {a['time']:.0f}s {str(a.get('title'))[:40]!r}"
                for a in substantive_during
            )
            + f"): could be that item or {(before or {}).get('meta_id')}"
        )
    if before is not None and is_non_item(before.get("title")):
        prior = [
            a
            for a in before_candidates
            if not is_non_item(a.get("title")) and a["time"] <= before["time"]
        ]
        alternative = max(prior, key=_agenda_order) if prior else None
        problems.append(
            f"bound to a non-substantive cuepoint {str(before.get('title'))[:50]!r}"
            + (
                f"; previous real item is {alternative['meta_id']} "
                f"{str(alternative.get('title'))[:40]!r}"
                if alternative
                else ""
            )
        )

    boundary = sorted(
        (a for a in agenda if abs(a["time"] - timestamp) <= uncertainty),
        key=lambda a: (a["time"], str(a.get("meta_id", ""))),
    )
    during_meta = {a["meta_id"] for a in substantive_during}
    boundary_only = [a for a in boundary if a["meta_id"] not in during_meta]
    if boundary_only:
        problems.append(
            f"board onset {timestamp:.2f}s is within {uncertainty:g}s of "
            + "; ".join(
                f"{a['meta_id']} at {a['time']}s "
                f"({a['time'] - timestamp:+.2f}s) {str(a.get('title'))[:40]!r}"
                for a in boundary_only
            )
            + f": the sample grid cannot resolve which side of the boundary "
            f"this board is on (bound to {(before or {}).get('meta_id')})"
        )

    return {
        "item": before,
        "before": before,
        "during": during,
        "boundary": boundary,
        "problems": problems,
    }


# --- clustering ------------------------------------------------------------

def cluster_detections(detections: list[dict]) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for det in sorted(detections, key=lambda d: d["video_timestamp"]):
        if clusters and det["video_timestamp"] - clusters[-1][-1]["video_timestamp"] <= CLUSTER_GAP_SECONDS:
            clusters[-1].append(det)
        else:
            clusters.append([det])
    return clusters


def tally_key_of(probe: dict) -> tuple[int, ...]:
    tally = probe.get("vote_tally") or {}
    return tuple(tally.get(k, -1) for k in TALLY_KEYS)


def board_present(probe: dict) -> bool:
    """Whether a frame is showing a vote board at all.

    A frame whose tally failed to read is still showing the board as long as
    the board's furniture is there. This is the signal votes are separated on,
    because it is the only one that answers the actual question: did the board
    leave the screen between these two frames?
    """
    if probe.get("vote_tally"):
        return True
    if probe.get("individual_votes"):
        return True
    text = probe.get("ocr_text") or ""
    flat = squash(text)
    if any(key in flat for key in DETECT_KEYWORDS):
        return True
    return count_label_hits([{"text": t} for t in text.split()], flat) >= 2


def stabilize_tally_keys(
    keys: list[tuple[int, ...]], min_run: int = TALLY_STABLE_FRAMES
) -> list[tuple[int, ...]]:
    """Absorb tally readings too short-lived to be a different board.

    A tally has to hold for `min_run` consecutive frames to count as a board of
    its own. One frame in the middle of a vote whose tally came back unreadable
    is a misread, not the start of a new vote -- grouping on runs of *equal*
    tally made that frame bisect the vote into two candidates, and both halves
    then re-expanded over the same neighbours so the sharpest-frame pick could
    return the same frame for both.
    """
    if not keys:
        return []
    runs: list[list] = []
    for index, key in enumerate(keys):
        if runs and runs[-1][0] == key:
            runs[-1][2] = index + 1
        else:
            runs.append([key, index, index + 1])

    stable = [
        run
        for run in runs
        if run[2] - run[1] >= min_run and any(k >= 0 for k in run[0])
    ]
    if not stable:
        # Nothing held long enough to be trusted; treat the span as one board.
        readable = [run[0] for run in runs if any(k >= 0 for k in run[0])]
        fill = readable[0] if readable else keys[0]
        return [fill] * len(keys)

    out: list[tuple[int, ...] | None] = [None] * len(keys)
    for key, start, end in stable:
        for index in range(start, end):
            out[index] = key
    # An unstable frame inherits from the nearest stable run, preferring the one
    # it follows, so a misread never opens a boundary of its own.
    last: tuple[int, ...] | None = None
    for index in range(len(out)):
        if out[index] is None:
            out[index] = last
        else:
            last = out[index]
    nxt: tuple[int, ...] | None = None
    for index in range(len(out) - 1, -1, -1):
        if out[index] is None:
            out[index] = nxt
        else:
            nxt = out[index]
    return [key for key in out]  # type: ignore[misc]


def group_by_presence(frames: list[dict]) -> list[list[dict]]:
    """Split a time-ordered, probed span of frames into one group per vote.

    Two votes are separate records when the board left the screen between them,
    or when a different tally held for long enough to be a different board. The
    old rule was runs of equal tally alone, which broke both ways: one bad frame
    split a single vote in two, and -- far worse -- two consecutive 7-0-0-0
    votes twenty seconds apart on a consent calendar collapsed into one record,
    silently deleting the second vote.
    """
    if not frames:
        return []

    # 1. Split on runs of frames with no board on them.
    spans: list[list[dict]] = []
    current: list[dict] = []
    absent_run = 0
    for frame in frames:
        if frame.get("_present"):
            if absent_run >= BOARD_ABSENT_RUN and current:
                spans.append(current)
                current = []
            absent_run = 0
            current.append(frame)
        else:
            absent_run += 1
    if current:
        spans.append(current)

    groups: list[list[dict]] = []
    for span in spans:
        stabilized = stabilize_tally_keys([f["_tally_key"] for f in span])
        # 2. Split each span where a *lasting* tally change happens, then merge
        #    non-adjacent runs of the same tally back together: the same board
        #    interrupted by a misread is one vote, not two.
        by_key: dict[tuple[int, ...], list[dict]] = {}
        order: list[tuple[int, ...]] = []
        for frame, key in zip(span, stabilized):
            frame["_stable_tally_key"] = key
            if key not in by_key:
                by_key[key] = []
                order.append(key)
            by_key[key].append(frame)
        position = {id(frame): index for index, frame in enumerate(span)}
        for key in order:
            members = sorted(by_key[key], key=lambda f: f["video_timestamp"])
            groups.append(members)
            # Contiguity is measured against the span, not against a fixed
            # number of seconds, so it holds at any sampling rate: if a frame
            # belonging to a different board sits between two of ours, this
            # group spans two boards and the caller needs to know.
            indices = sorted(position[id(frame)] for frame in members)
            if indices[-1] - indices[0] + 1 != len(indices):
                gap = max(
                    members[i + 1]["video_timestamp"] - members[i]["video_timestamp"]
                    for i in range(len(members) - 1)
                )
                members[0]["_non_contiguous"] = round(gap, 1)
    return sorted(groups, key=lambda g: min(f["video_timestamp"] for f in g))


def build_vote_groups(
    cluster: list[dict],
    frames: list[dict],
    era: roster_mod.Era,
    pad: float = CONSENSUS_PAD_SECONDS,
) -> list[list[dict]]:
    """Turn one time cluster of detections into one group of frames per vote.

    Every frame in the padded span is probed exactly once and assigned to
    exactly one group, which is what stops the old two-step (split by tally,
    then re-expand each half over its neighbours) from handing the same frame to
    two different votes.
    """
    if cluster and all(f.get("format") in BRIGHT_FORMATS for f in cluster):
        # Format B's presence/tally probe invokes its board crop, inversion,
        # four-column parser, and icon detector. None describe Formats A/C. The
        # detector has already identified these full-frame white boards, so
        # keep each time cluster intact for vision/manual review.
        return [sorted(cluster, key=lambda f: f["video_timestamp"])]

    low = min(f["video_timestamp"] for f in cluster) - pad
    high = max(f["video_timestamp"] for f in cluster) + pad
    detected = {f["frame"] for f in cluster}

    span: list[dict] = []
    for frame in frames:
        if not (low <= frame["video_timestamp"] <= high):
            continue
        merged = dict(frame)
        merged["_detected"] = frame["frame"] in detected
        span.append(merged)
    for frame in cluster:
        if frame["frame"] not in {f["frame"] for f in span}:
            span.append(dict(frame))
    span.sort(key=lambda f: f["video_timestamp"])

    for frame in span:
        if frame.get("_probe") is None:
            with Image.open(frame["frame"]) as image:
                frame["_probe"] = ocr_parse_board(image, era)
        frame["_tally_key"] = tally_key_of(frame["_probe"])
        frame["_present"] = board_present(frame["_probe"])

    groups = group_by_presence(span)
    # A group holding no detection at all is board furniture either side of the
    # real vote, not a vote of its own.
    return [g for g in groups if any(f.get("_detected") for f in g)] or groups


def split_cluster_by_tally(cluster: list[dict], era: roster_mod.Era) -> list[list[dict]]:
    """Deprecated: superseded by build_vote_groups. Kept for external callers."""
    for frame in cluster:
        if frame.get("_probe") is None:
            with Image.open(frame["frame"]) as image:
                frame["_probe"] = ocr_parse_board(image, era)
        frame["_tally_key"] = tally_key_of(frame["_probe"])
        frame["_present"] = board_present(frame["_probe"])
    return group_by_presence(cluster)


def expand_group(
    group: list[dict],
    frames: list[dict],
    era: roster_mod.Era,
    pad: float = CONSENSUS_PAD_SECONDS,
) -> list[dict]:
    """Add neighbouring frames that show the same tally.

    Detection only fires where Tesseract happened to catch both the title and
    the tally labels, but the slide is on screen continuously either side of
    those frames. Every extra read of the same board is another vote in the
    per-member majority, which is what recovers a value a single frame drops.
    Only frames whose tally matches exactly are admitted, so a neighbouring
    board for a different motion can never be folded in.
    """
    key = group[0].get("_tally_key")
    if not key or all(k < 0 for k in key):
        return group

    low = min(f["video_timestamp"] for f in group) - pad
    high = max(f["video_timestamp"] for f in group) + pad
    have = {f["frame"] for f in group}

    extra: list[dict] = []
    for frame in frames:
        if frame["frame"] in have or not (low <= frame["video_timestamp"] <= high):
            continue
        with Image.open(frame["frame"]) as image:
            probe = ocr_parse_board(image, era)
        tally = probe.get("vote_tally") or {}
        probe_key = tuple(
            tally.get(k, -1) for k in ("ayes", "noes", "abstentions", "recused")
        )
        if probe_key != key:
            continue
        merged = dict(frame)
        merged["_probe"] = probe
        merged["_tally_key"] = probe_key
        extra.append(merged)

    return sorted(group + extra, key=lambda f: f["video_timestamp"])


def pick_sharpest(group: list[dict]) -> dict:
    for frame in group:
        if "_sharpness" not in frame:
            with Image.open(frame["frame"]) as image:
                sharpness_image = (
                    image
                    if frame.get("format") in BRIGHT_FORMATS
                    else crop_fractional(image, BOARD_BOX)
                )
                frame["_sharpness"] = sharpness(sharpness_image)
    return max(group, key=lambda f: f["_sharpness"])


# Spoken outcome language used to double-check the on-screen Motion Passes/Fails
# line. Unanimous / carried language confirms a pass; fail language confirms a
# fail. Contradiction is a blocking problem; silence is recorded, not fatal.
_TRANSCRIPT_PASS_NEEDLES = (
    "motion carried",
    "motion passes",
    "motion passed",
    "that passes",
    "that motion carried",
    "unanimously",
)
_TRANSCRIPT_FAIL_NEEDLES = (
    "motion fails",
    "motion failed",
    "that fails",
    "that motion failed",
)


def transcript_double_check(
    clip: dict,
    timestamp: float,
    parsed: dict,
    agenda: dict | None,
) -> dict:
    """Cross-check slide result + agenda/motion against the ±30s transcript.

    Uses cached ASR/captions only (no fresh whisper) so detect stays offline-
    friendly after preprocess_asr. Missing transcript is noted, not fatal.
    """
    import audit_agenda_bindings as audit

    check: dict = {
        "status": "skipped",
        "problems": [],
        "result_match": None,
        "agenda_match": None,
        "source": None,
        "excerpt": None,
    }
    try:
        transcript = audit.get_transcript(
            clip, float(timestamp), cache_only=True, force_asr=False
        )
    except Exception as exc:  # noqa: BLE001
        check["status"] = "error"
        check["note"] = str(exc)[:200]
        return check

    text = (transcript.get("text") or "").strip()
    check["source"] = transcript.get("source")
    check["excerpt"] = text[:500] if text else None
    if not text:
        check["status"] = "no_transcript"
        check["note"] = transcript.get("note") or "empty transcript"
        return check

    lower = text.lower()
    spoken_pass = any(n in lower for n in _TRANSCRIPT_PASS_NEEDLES)
    spoken_fail = any(n in lower for n in _TRANSCRIPT_FAIL_NEEDLES)
    slide_result = parsed.get("result")
    if slide_result == "passed" and spoken_fail and not spoken_pass:
        check["result_match"] = "mismatch"
        check["problems"].append(
            "transcript says motion failed/fails but slide result is passed"
        )
    elif slide_result == "failed" and spoken_pass and not spoken_fail:
        check["result_match"] = "mismatch"
        check["problems"].append(
            "transcript says motion carried/passes but slide result is failed"
        )
    elif slide_result == "passed" and spoken_pass:
        check["result_match"] = "confirmed"
    elif slide_result == "failed" and spoken_fail:
        check["result_match"] = "confirmed"
    elif spoken_pass or spoken_fail:
        check["result_match"] = "ambiguous"
    else:
        check["result_match"] = "no_vote_language"

    # Agenda / motion: prefer keywords from the cuepoint title, then from the
    # Format C lower-third banner OCR when present.
    title = (agenda or {}).get("title") or ""
    banner = parsed.get("agenda_banner") or ""
    evidence: list[str] = []
    kws = audit.title_keywords(title) if title else []
    if not kws and banner:
        kws = audit.title_keywords(banner)
    pre_text = " ".join(
        str(c.get("text") or "")
        for c in (transcript.get("cues") or [])
        if float(c.get("start") or 0) <= float(timestamp) + 2
    ).lower() or lower
    hits = [w for w in kws if re.search(rf"\b{re.escape(w)}\b", pre_text)]
    code = audit.item_code(title) if title else audit.item_code(banner)
    code_hit = bool(code and code in audit.normalize_spoken_codes(text))
    if hits:
        evidence.append("keywords: " + ", ".join(hits[:8]))
    if code_hit:
        evidence.append(f"spoken item code {code}")
    if banner and hits:
        # Banner text overlapping spoken words is extra confirmation of motion.
        evidence.append("agenda banner keywords in transcript")

    if hits or code_hit:
        check["agenda_match"] = "confirmed"
    elif title or banner:
        # Soft signal only — cuepoint timing may still be right when ASR drops
        # the item number. Hard reject only when a rival item clearly wins.
        check["agenda_match"] = "weak"
        try:
            row = {
                "video_timestamp": timestamp,
                "meta_id": (agenda or {}).get("meta_id"),
                "agenda_item": title,
            }
            audit_row = audit.audit_vote(
                row, clip, cache_only=True, force_asr=False
            )
            if audit_row.get("verdict") == "mismatch":
                check["agenda_match"] = "mismatch"
                check["problems"].append(
                    f"transcript agenda mismatch: {audit_row.get('reason')}"
                )
            check["agenda_audit"] = {
                "verdict": audit_row.get("verdict"),
                "reason": audit_row.get("reason"),
            }
        except Exception as exc:  # noqa: BLE001
            check["agenda_audit_error"] = str(exc)[:200]
    else:
        check["agenda_match"] = "no_agenda"

    check["agenda_evidence"] = evidence
    if check["problems"]:
        check["status"] = "mismatch"
    elif check["result_match"] == "confirmed" and check["agenda_match"] == "confirmed":
        check["status"] = "confirmed"
    else:
        check["status"] = "partial"
    return check


# --- main ------------------------------------------------------------------

def slug(text: str, limit: int = 48) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_")
    return cleaned[:limit] or "item"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument(
        "--parser",
        choices=("auto", "vision", "ocr"),
        default="auto",
        help="auto uses the vision model only when GEMINI_API_KEY is set",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="OCR every frame instead of gating on the cheap numeric signature",
    )
    parser.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 4) - 2))
    parser.add_argument(
        "--partial-board",
        choices=("absent", "reject"),
        default="absent",
        help="how to treat a slide listing fewer members than the seated council",
    )
    parser.add_argument(
        "--keep-frames",
        action="store_true",
        help="keep the dense frame directory instead of deleting it after clustering",
    )
    parser.add_argument(
        "--out",
        help="write the vote JSON here instead of metadata/votes_{clip}.json, so a "
        "verification run cannot overwrite the file the publish stage reads",
    )
    parser.add_argument(
        "--frames-root",
        help="read frames from this directory instead of the newest layout "
        "find_work_dir picks. Needed when a clip has been extracted twice and "
        "the preferred root holds the smaller set",
    )
    parser.add_argument(
        "--crops-dir",
        help="write board/overlay crops here instead of crops/{clip}, so a "
        "verification run does not disturb the crops another stage is reading",
    )
    parser.add_argument(
        "--clear-crops",
        action="store_true",
        help="delete the clip's existing crops before writing new ones. The "
        "timestamp is part of the crop filename, so re-runs otherwise leave "
        "board_00_6907.jpg next to board_00_6909.jpg from a previous pass and "
        "nothing says which run each came from. OFF by default because other "
        "stages read these files in place.",
    )
    parser.add_argument(
        "--vote-source-policy",
        choices=VOTE_SOURCE_POLICIES,
        default=VOTE_SOURCE_POLICY_DEFAULT,
        help="how much corroboration a member's vote needs. agree: the coloured "
        "glyph and the printed word must not disagree, but one channel alone is "
        "enough (default). both: every member must be read on both channels -- "
        "an audit mode, not a production one, since board OCR reads well under "
        "half the values. any: legacy behaviour where the glyph wins a "
        "disagreement, though the conflict is still reported.",
    )
    parser.add_argument(
        "--allow-unverified-roster",
        action="store_true",
        help="run against a roster era flagged unverified. Off by default: the "
        "pre-turnover era holds a different council entirely, so validating a "
        "2026 vote against it attributes votes to members who were not seated.",
    )
    args = parser.parse_args()

    detect_started = time.time()
    disk_guard.require_space("detect:start")

    # Prefers frames.noindex/, falls back to the pre-rename frames/ so a clip
    # extracted before the bulk roots were excluded from Spotlight is still
    # readable in place rather than needing a re-extract.
    frames_root = (
        Path(args.frames_root)
        if args.frames_root
        else disk_guard.find_work_dir("frames", args.clip)
    )
    manifest_path = frames_root / "windows.json"
    try:
        frame_pairs, manifest = manifest_mod.load_window_frames(manifest_path)
    except manifest_mod.IncompleteManifest as exc:
        raise SystemExit(str(exc)) from exc

    catalog = json.loads(
        (disk_guard.work_dir("metadata") / f"clips_{args.year}.json").read_text()
    )
    clip = next(c for c in catalog["clips"] if c["clip_id"] == args.clip)
    # An undated clip used to fall back to January 1st of the requested year,
    # which for 2026 resolves to the pre-turnover era: a 2026 meeting would have
    # been validated against Chen / Kaji / Mattucci, none of whom were seated.
    # There is no safe guess for a meeting date, so there is no fallback.
    meeting_date = clip.get("date")
    if not meeting_date:
        raise SystemExit(
            f"clip {args.clip} has no date in metadata/clips_{args.year}.json. "
            f"Re-run catalog_granicus.py to date it; guessing the date picks the "
            f"roster era, and the wrong era attributes votes to the wrong council."
        )
    try:
        era = roster_mod.era_for(meeting_date)
    except roster_mod.UnknownRosterEra as exc:
        raise SystemExit(str(exc)) from exc
    if not era.verified and not args.allow_unverified_roster:
        raise SystemExit(
            f"roster era {era.key} is flagged unverified ({era.note}). "
            f"Pass --allow-unverified-roster to parse against it anyway."
        )
    print(
        f"clip {args.clip} ({meeting_date}) roster era {era.key}"
        f"{'' if era.verified else ' [UNVERIFIED]'}: "
        f"{len(era.members)} members, accepts {list(era.sizes)}"
    )

    key, key_env = gemini_key()
    mode = args.parser
    if mode == "auto":
        mode = "vision" if os.environ.get("GEMINI_API_KEY") else "ocr"
    if mode == "vision" and not key:
        print("no vision key available; falling back to OCR", file=sys.stderr)
        mode = "ocr"
    print(
        f"parser={mode}"
        + (f" (key from {key_env})" if mode == "vision" else "")
        + (" [GEMINI_API_KEY not set]" if not os.environ.get("GEMINI_API_KEY") else "")
    )

    frames = [
        {"frame": path, "video_timestamp": timestamp}
        for path, timestamp in frame_pairs
    ]
    # The fused extractor already ran this exact gate while the segments were
    # local and only wrote the frames that passed, so the manifest carries the
    # sampled count. Reporting it keeps frames_scanned comparable with runs made
    # before the gate moved upstream.
    sampled = manifest.get("frames_sampled_total") or len(frames)
    pre_gated = bool(re.match(r"(fused-gate|stream-gate)", manifest.get("pipeline") or ""))
    print(
        f"scanning {len(frames)} frames with {args.workers} workers"
        + (f" (pre-gated from {sampled} sampled)" if pre_gated else "")
    )

    t0 = time.time()
    detections: list[dict] = []
    gate_passed = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(detect_frame, f["frame"], args.force_ocr): f for f in frames
        }
        for future in concurrent.futures.as_completed(futures):
            record = future.result()
            if record["gate"]:
                gate_passed += 1
            if record["detected"]:
                merged = dict(futures[future])
                merged.update(record)
                detections.append(merged)
    scan_seconds = time.time() - t0
    print(
        f"detect: {gate_passed} frames passed the numeric gate, "
        f"{len(detections)} matched vote keywords in {scan_seconds:.1f}s"
    )

    ocr_failed = sum(
        1 for d in detections if d.get("ocr_status") not in (None, TESS_OK)
    )
    if ocr_failed:
        print(
            f"detect: WARNING {ocr_failed} frames failed or timed out in Tesseract "
            f"rather than reading as empty",
            file=sys.stderr,
        )

    t0 = time.time()
    clusters = cluster_detections(detections)
    # One pass per cluster: probe the padded span once and assign every frame to
    # exactly one vote. Splitting on tally and then re-expanding each half over
    # the same neighbours could give two candidates the same frames.
    groups: list[list[dict]] = []
    for cluster in clusters:
        groups.extend(build_vote_groups(cluster, frames, era))
    detected_in_groups = sum(
        1 for g in groups for f in g if f.get("_detected") or f.get("detected")
    )
    cluster_seconds = time.time() - t0
    print(
        f"cluster: {len(clusters)} time clusters -> {len(groups)} candidate votes "
        f"in {cluster_seconds:.1f}s; consensus widened from {detected_in_groups} "
        f"detected to {sum(len(g) for g in groups)} frames"
    )

    t0 = time.time()
    crops_dir = (
        Path(args.crops_dir)
        if args.crops_dir
        else disk_guard.work_dir("crops", args.clip)
    )
    crops_dir.mkdir(parents=True, exist_ok=True)
    if args.clear_crops:
        stale = sorted(crops_dir.glob("*.jpg"))
        for path in stale:
            path.unlink()
        print(f"cleared {len(stale)} stale crops from {crops_dir}")
    accepted: list[dict] = []
    rejected: list[dict] = []

    for seq, group in enumerate(groups):
        winner = pick_sharpest(group)
        format_name = winner.get("format") or FORMAT_B
        # The vote happens when the board first appears, not on whichever frame
        # happens to be sharpest. Binding on the later frame can jump the vote
        # to the next agenda item when the clerk advances the cuepoint while the
        # result is still on screen.
        timestamp = min(f["video_timestamp"] for f in group)
        if format_name == FORMAT_C:
            parsed = consensus_parse_format_c(group, era)
        elif format_name == FORMAT_A:
            parsed = consensus_parse_format_a(group, era)
        else:
            parsed = consensus_parse(group, era)

        if mode == "vision":
            try:
                with Image.open(winner["frame"]) as image:
                    vision = vision_parse_board(image, era, format_name)
                if format_name == FORMAT_B:
                    vision["ocr_consensus"] = {
                        "vote_tally": parsed["vote_tally"],
                        "result": parsed["result"],
                        "individual_votes": parsed["individual_votes"],
                    }
                parsed = vision
            except Exception as exc:  # noqa: BLE001 - never abort the run on the model
                print(f"  vision parse failed at {timestamp:.0f}s: {exc}", file=sys.stderr)
                parsed["parser_fallback_reason"] = str(exc)[:200]
                if format_name in BRIGHT_FORMATS:
                    parsed["format_problem"] = FORMAT_A_REVIEW_PROBLEM

        with Image.open(winner["frame"]) as image:
            audit_image = (
                image.copy()
                if format_name in BRIGHT_FORMATS
                else crop_fractional(image, OVERLAY_BOX)
            )
            audit_image.save(crops_dir / f"vote_{seq:02d}_{int(timestamp)}.jpg", quality=92)
            board_path = crops_dir / f"board_{seq:02d}_{int(timestamp)}.jpg"
            board_image = (
                image.copy()
                if format_name in BRIGHT_FORMATS
                else crop_fractional(image, BOARD_BOX)
            )
            board_image.save(board_path, quality=92)

        board_last_seen = max(f["video_timestamp"] for f in group)
        binding = bind_agenda_detail(clip["agenda"], timestamp, board_last_seen)
        agenda = binding["item"]
        problems, absent = validate(
            parsed, era, args.partial_board, args.vote_source_policy
        )
        problems.extend(binding["problems"])
        transcript_check = transcript_double_check(
            clip, timestamp, parsed, agenda
        )
        problems.extend(transcript_check.get("problems") or [])
        if not agenda:
            problems.append("no agenda cuepoint at or before the vote timestamp")
        non_contiguous = next(
            (f["_non_contiguous"] for f in group if f.get("_non_contiguous")), None
        )
        if non_contiguous:
            problems.append(
                f"frames backing this vote are not contiguous in time "
                f"({non_contiguous}s gap): they may span two boards"
            )

        candidate = {
            "sequence": seq,
            "vote_id": f"{args.clip}_{(agenda or {}).get('meta_id', 'na')}_{seq}",
            "video_timestamp": int(round(timestamp)),
            "board_last_seen": int(round(board_last_seen)),
            "frame_source": winner["frame"],
            "frame_timestamp": int(round(winner["video_timestamp"])),
            "frame_count_in_cluster": len(group),
            "format": format_name,
            "sharpness": round(winner.get("_sharpness", 0.0), 1),
            "board_crop": str(board_path),
            "agenda_item": (agenda or {}).get("title"),
            "meta_id": (agenda or {}).get("meta_id"),
            "agenda_time": (agenda or {}).get("time"),
            # Both sides of the binding, so a rejection for an ambiguous
            # cuepoint can be audited without re-running the stage.
            "agenda_candidates": {
                "before": (
                    {
                        "meta_id": binding["before"]["meta_id"],
                        "time": binding["before"]["time"],
                        "title": binding["before"].get("title"),
                    }
                    if binding["before"]
                    else None
                ),
                "during_board": [
                    {"meta_id": a["meta_id"], "time": a["time"], "title": a.get("title")}
                    for a in binding["during"]
                ],
                "boundary": [
                    {"meta_id": a["meta_id"], "time": a["time"], "title": a.get("title")}
                    for a in binding.get("boundary", [])
                ],
            },
            "absent_members": absent,
            "roster_complete": not absent,
            "parsed": parsed,
            "transcript_check": transcript_check,
            "problems": problems,
        }
        if problems:
            rejected.append(candidate)
            print(
                f"  REJECT t={timestamp:.0f}s "
                f"item={(candidate['agenda_item'] or '?')[:45]!r}: {problems[0]}"
            )
        else:
            accepted.append(candidate)
            tally = parsed["vote_tally"]
            note = f" absent={','.join(a.split()[-1] for a in absent)}" if absent else ""
            print(
                f"  ok     t={timestamp:.0f}s meta={candidate['meta_id']} "
                f"{tally['ayes']}-{tally['noes']}-{tally['abstentions']}-{tally['recused']} "
                f"{parsed['result']}{note} :: {(candidate['agenda_item'] or '')[:46]}"
            )

    parse_seconds = time.time() - t0

    out = (
        Path(args.out)
        if args.out
        else disk_guard.work_dir("metadata") / f"votes_{args.clip}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "clip_id": args.clip,
        "year": args.year,
        "date": meeting_date,
        "roster_era": era.key,
        "roster": [
            {"name": m.name, "district": m.district, "role": m.role} for m in era.members
        ],
        "parser_mode": mode,
        "partial_board_policy": args.partial_board,
        "vote_source_policy": args.vote_source_policy,
        # Whether the roster this was validated against is one we have confirmed.
        # Recording only the era key left a reader unable to tell a verified
        # council from the placeholder historical one.
        "roster_verified": era.verified,
        "roster_note": era.note,
        "gemini_api_key_present": bool(os.environ.get("GEMINI_API_KEY")),
        # frames_scanned counts the 1 fps frames the meeting was sampled at,
        # whether they were gated here or upstream in extract; frames_read is
        # how many JPEGs this stage actually had to open.
        "frames_scanned": sampled,
        "frames_read": len(frames),
        "frames_pre_gated": pre_gated,
        "frames_gated": gate_passed,
        "frames_detected": len(detections),
        # A frame Tesseract failed or timed out on is not a frame with no board
        # on it; keeping them apart is what stops a systematic OCR failure from
        # reading as "this meeting contains no votes".
        "frames_ocr_failed": ocr_failed,
        "tesseract": dict(TESS_STATS),
        "candidates": len(groups),
        "accepted": accepted,
        "rejected": rejected,
    }
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(
        f"wrote {out}: {len(accepted)} validated, {len(rejected)} rejected "
        f"by the tally/roster check"
    )

    freed = 0.0
    if not args.keep_frames:
        for window_dir in sorted(frames_root.glob("w*")):
            freed += disk_guard.purge(window_dir, "detect")
        print(f"deleted dense frames, reclaimed {freed:.2f} GiB")

    wall = time.time() - detect_started
    timing_path = merge_timing(
        args.clip,
        "detect",
        {
            "wall_seconds": round(wall, 2),
            "scan_seconds": round(scan_seconds, 2),
            "cluster_seconds": round(cluster_seconds, 2),
            "parse_seconds": round(parse_seconds, 2),
            "workers": args.workers,
            "parser_mode": mode,
            "frames_sampled": sampled,
            "frames_read": len(frames),
            "frames_pre_gated": pre_gated,
            "frames_gated": gate_passed,
            "frames_detected": len(detections),
            "frames_ocr_failed": ocr_failed,
            "tesseract_calls": TESS_STATS["calls"],
            "tesseract_timeouts": TESS_STATS["timeouts"],
            "tesseract_failures": TESS_STATS["failures"],
            "frames_per_second": round(len(frames) / scan_seconds, 1) if scan_seconds else 0.0,
            "candidates": len(groups),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "frames_gib_reclaimed": round(freed, 3),
        },
    )
    print(
        f"detect: {wall:.1f}s wall "
        f"(scan {scan_seconds:.1f}s, cluster {cluster_seconds:.1f}s, "
        f"parse {parse_seconds:.1f}s); wrote {timing_path}"
    )

    print(disk_guard.report("detect:done"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
