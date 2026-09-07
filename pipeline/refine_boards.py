#!/usr/bin/env python3
"""Re-extract every detected vote board at the maximum quality Granicus serves.

Detect samples the meeting at 1 fps and writes JPEG, so the board it parses is a
frame chosen for when it landed rather than for how clean it is, re-compressed a
second time on the way to disk. This stage goes back to the video for the handful
of timestamps detect already confirmed and pulls them again losslessly.

Three things change, in decreasing order of how much they turned out to matter:

  * Lossless PNG, so the ~8 pixel vote values are not asked to survive a second
    generation of JPEG on top of the h264 they arrived in.
  * Keyframes. Granicus encodes one I-frame every 2.002 s and 59 P-frames after
    it, at 2.0 Mbps for 1280x720. On a static slide the encoder spends almost
    nothing on those P-frames, so the I-frame is measurably the cleanest picture
    of the board available. 1 fps sampling hits one by luck.
  * Several frames per board rather than one, so a caller can vote across them.

It does NOT change resolution, because there is nothing to change it to: the
master playlist advertises a single 1280x720 variant and the source MP4 behind
it is itself 1280x720 (see refine_report_*.json for the ffprobe evidence). The
variant selection below still picks the largest rendition on offer, so a future
Granicus ladder would be used without touching this file.

Reads detect's output, never writes to it. Existing frames/, crops/ and
metadata/votes_*.json are inputs only; everything new lands in crops_hq/ and
metadata/refine_*.json on the Passport.

    python3 pipeline/refine_boards.py --clip 14821
    python3 pipeline/refine_boards.py --clip 14821 --frames 8 --keep-segments
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bounded_proc
import disk_guard
from PIL import Image

# Same CloudFront-friendly identity the extract stage uses; the CDN in front of
# archive-stream.granicus.com refuses anything that looks automated.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
REFERER = "https://torrance.granicus.com/"
SEGMENT_TIMEOUT = 45
SEGMENT_RETRIES = 3
DOWNLOAD_WORKERS = 6

# Fractional bounds of the VoteCast panel inside the frame, copied from detect so
# a refined crop is pixel-comparable with the one detect wrote. Kept as literals
# rather than imported: this stage must keep working on last month's output if
# detect retunes its boxes, and a silent shift would invalidate a comparison.
BOARD_BOX = (0.115, 0.200, 0.890, 0.660)
OVERLAY_BOX = (0.100, 0.100, 0.900, 0.890)

# Seconds either side of the confirmed board span to also sample. The board is on
# screen continuously, so this only widens the pool of clean frames to choose
# from; it never reaches a different motion.
SPAN_PAD = 1.0
# Frames kept per board after ranking. Enough for a majority vote across frames
# without turning a meeting into gigabytes of PNG.
FRAMES_PER_BOARD = 6
# Non-keyframes are sampled this often inside the window. I-frames are always
# taken regardless.
SAMPLE_EVERY_N = 10
# Extra segments pulled either side of the computed span, to cover the skew
# between accumulated EXTINF time and real transport-stream PTS.
SEGMENT_MARGIN = 1

# Detect's own numeric gate, applied to the refined board crop so this stage
# cannot disagree with detect about whether a frame shows a board. Widening the
# window to catch clean frames also catches the camera shot either side of the
# slide, and those must never reach the OCR comparison.
GATE_BOARD_DARK = 0.45
GATE_BOARD_SAT = 18.0
# A frame that passes the gate can still be a cross-fade, where the slide is
# composited over the camera image: measured on clip 14821 one such frame scored
# 2148 on sharpness against ~187 for the settled board. Frames of a genuinely
# static slide sit within ~1 grey level of each other, so anything this far from
# the median of the window is a transition and is dropped.
STABLE_MAX_DEVIATION = 8.0
MIN_FRAMES_FOR_MEDIAN = 3

# Wall-clock allowance for the PNG decode, as a multiple of the media duration the
# board's playlist covers. A board window is a handful of segments, but PNG at
# compression_level 1 writes far more bytes per frame than the JPEG pipe in
# extract does, and it writes them to the Passport, so the multiplier is looser
# than extract's. Derived rather than constant for the same reason: a bound tight
# enough to catch a hang on a 4-second board would kill a legitimately long one.
PNG_DECODE_MULTIPLIER = 20.0
# Floor, because a board window is short enough that the multiplier alone would
# leave ffmpeg less time than process start and HLS parse take.
PNG_DECODE_FLOOR = 180.0

# Granicus emits one I-frame every 2.002 s. On a static slide the P-frames after
# it carry almost no residual and decode to within ~1 grey level of that
# I-frame, so several frames from one interval are near-duplicates and a
# majority vote across them is a majority of one measurement. Selection
# therefore spreads across intervals before it takes a second frame from any.
KEYFRAME_INTERVAL = 2.002

REFINE_VERSION = "refine-hq-v1"


# --- http ------------------------------------------------------------------

def http_get(url: str, retries: int = SEGMENT_RETRIES) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Referer": REFERER}
        )
        try:
            with urllib.request.urlopen(request, timeout=SEGMENT_TIMEOUT) as response:
                return response.read()
        except (urllib.error.URLError, OSError) as exc:
            last = exc
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} tries: {url} ({last})")


# --- playlists -------------------------------------------------------------

def master_variants(hls_url: str) -> tuple[list[dict], str]:
    """Parse the master playlist into its variants, largest first.

    Granicus serves `playlist.m3u8` as a real master even when it holds a single
    variant, so this is how the resolution ceiling is measured rather than
    assumed. Returns the variants and the absolute URL of the best one.
    """
    body = http_get(hls_url).decode("utf-8", errors="replace")
    base = hls_url.rsplit("/", 1)[0]

    if "#EXT-X-STREAM-INF" not in body:
        # Already a media playlist; it is its own only rendition.
        return [], hls_url

    variants: list[dict] = []
    attrs: dict | None = None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF:"):
            spec = line.split(":", 1)[1]
            bandwidth = re.search(r"BANDWIDTH=(\d+)", spec)
            resolution = re.search(r"RESOLUTION=(\d+)x(\d+)", spec)
            codecs = re.search(r'CODECS="([^"]*)"', spec)
            attrs = {
                "bandwidth": int(bandwidth.group(1)) if bandwidth else 0,
                "width": int(resolution.group(1)) if resolution else 0,
                "height": int(resolution.group(2)) if resolution else 0,
                "codecs": codecs.group(1) if codecs else "",
            }
        elif line and not line.startswith("#") and attrs is not None:
            attrs["uri"] = line if line.startswith("http") else f"{base}/{line}"
            variants.append(attrs)
            attrs = None

    if not variants:
        raise RuntimeError(f"master playlist at {hls_url} listed no variants")
    variants.sort(key=lambda v: (v["width"] * v["height"], v["bandwidth"]), reverse=True)
    return variants, variants[0]["uri"]


def load_chunklist(chunk_url: str) -> tuple[str, list[str], list[float]]:
    """Return (segment base url, segment names, cumulative start seconds)."""
    body = http_get(chunk_url).decode("utf-8", errors="replace")
    seg_base = chunk_url.rsplit("/", 1)[0]

    names: list[str] = []
    starts: list[float] = []
    clock = 0.0
    pending: float | None = None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            pending = float(line.split(":", 1)[1].rstrip(","))
        elif line and not line.startswith("#"):
            names.append(line)
            starts.append(clock)
            clock += pending if pending is not None else 0.0
            pending = None
    if not names:
        raise RuntimeError(f"no segments in {chunk_url}")
    return seg_base, names, starts


def segment_span(
    starts: list[float], begin: float, end: float, margin: int = SEGMENT_MARGIN
) -> range:
    """Inclusive segment index range covering [begin, end] in video seconds.

    `starts` comes from accumulating EXTINF durations, which is not quite the
    same clock as the timestamps inside the transport stream: measured on clip
    14821 the real PTS of segment 12965 runs 0.76 s ahead of its accumulated
    start. `margin` extra segments on each side absorb that skew, and the exact
    window is then cut by real PTS once the frames are decoded.
    """
    first = 0
    for index, start in enumerate(starts):
        if start <= begin:
            first = index
        else:
            break
    last = first
    for index in range(first, len(starts)):
        last = index
        if starts[index] >= end:
            break
    return range(max(0, first - margin), min(last + margin, len(starts) - 1) + 1)


def write_local_playlist(
    path: Path, names: list[str], starts: list[float], indexes: range
) -> None:
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-TARGETDURATION:4",
        f"#EXT-X-MEDIA-SEQUENCE:{indexes.start}",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]
    for index in indexes:
        nxt = starts[index + 1] if index + 1 < len(starts) else starts[index] + 2.0
        lines.append(f"#EXTINF:{nxt - starts[index]:.3f},")
        lines.append(names[index])
    lines.append("#EXT-X-ENDLIST")
    path.write_text("\n".join(lines) + "\n")


# --- segments --------------------------------------------------------------

def index_existing_segments(clip_root: Path) -> dict[str, Path]:
    """Find any media_*.ts the extract stage already left on the Passport.

    Extract deletes its segments unless run with --keep-segments, so this is
    usually empty, but when it is not a whole meeting's refine costs no
    download at all.
    """
    found: dict[str, Path] = {}
    if not clip_root.exists():
        return found
    for path in clip_root.rglob("*.ts"):
        found.setdefault(path.name, path)
    return found


def stage_segments(
    seg_base: str,
    names: list[str],
    indexes: range,
    dest: Path,
    existing: dict[str, Path],
) -> tuple[int, int, int]:
    """Make every segment for a window present in `dest`.

    Returns (bytes downloaded, segments reused, segments fetched). A segment
    already on the Passport is hardlinked rather than copied, so reuse is free
    in both bytes and space.
    """
    dest.mkdir(parents=True, exist_ok=True)
    reused = 0
    todo: list[int] = []
    for index in indexes:
        name = names[index]
        target = dest / name
        if target.exists():
            reused += 1
            continue
        source = existing.get(name)
        if source is not None:
            try:
                target.hardlink_to(source)
                reused += 1
                continue
            except OSError:
                shutil.copyfile(source, target)
                reused += 1
                continue
        todo.append(index)

    if not todo:
        return 0, reused, 0

    def grab(index: int) -> int:
        name = names[index]
        data = http_get(f"{seg_base}/{name}")
        tmp = dest / f".{name}.part"
        tmp.write_bytes(data)
        tmp.rename(dest / name)
        return len(data)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(DOWNLOAD_WORKERS, len(todo))
    ) as pool:
        sizes = list(pool.map(grab, todo))
    return sum(sizes), reused, len(todo)


# --- decode ----------------------------------------------------------------

SHOWINFO = re.compile(r"n:\s*(\d+).*?pts_time:\s*([0-9.]+).*?type:([IPB])")


def extract_png_frames(
    playlist: Path,
    begin: float,
    end: float,
    scratch: Path,
    sample_every: int = SAMPLE_EVERY_N,
) -> list[dict]:
    """Decode one board window to lossless PNG, keeping I-frames and a sample.

    The local playlist holds only the handful of segments covering the board, so
    it is decoded end to end with no seeking at all. That matters: `-ss` and
    `-t` as output options trim *after* the filter graph, so `showinfo` would
    describe frames that never reach disk and every PNG would carry the wrong
    timestamp. Selecting inside the graph and cutting the window afterwards in
    Python keeps the two in lockstep by construction.

    Granicus' segments carry true meeting PTS, and `-copyts` stops ffmpeg from
    rebasing them to zero the way it does by default, so `showinfo`'s pts_time
    is the absolute video timestamp and needs no playlist offset added to it.
    Without it the window below silently matches nothing.

    The decode is bounded off the media duration the playlist covers and its
    process group is killed if that bound fires. A timeout raises rather than
    returning the PNGs written so far: this stage picks the cleanest frames of a
    board out of the pool it decoded, so a truncated pool silently degrades the
    board that gets published instead of failing.
    """
    scratch.mkdir(parents=True, exist_ok=True)
    for stale in scratch.glob("hq_*.png"):
        stale.unlink()

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "info",
        "-copyts",
        "-allowed_extensions", "ALL",
        "-i", str(playlist),
        "-vf", f"select='eq(pict_type\\,I)+not(mod(n\\,{sample_every}))',showinfo",
        "-vsync", "0",
        "-compression_level", "1",
        str(scratch / "hq_%04d.png"),
    ]
    label = f"ffmpeg png {playlist.name}"
    timeout = bounded_proc.bound_from_work(
        bounded_proc.playlist_media_seconds(playlist),
        multiplier=PNG_DECODE_MULTIPLIER,
        floor=PNG_DECODE_FLOOR,
    )
    bounded_proc.note_bound(label, f"{timeout:.0f}s for the PNG decode")
    proc = bounded_proc.run_bounded(cmd, timeout=timeout, label=label, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-600:]}")

    meta = [
        {"pts": float(m.group(2)), "pict_type": m.group(3)}
        for m in (SHOWINFO.search(line) for line in proc.stderr.splitlines())
        if m
    ]
    files = sorted(scratch.glob("hq_*.png"))
    if len(meta) != len(files):
        raise RuntimeError(
            f"showinfo reported {len(meta)} frames but {len(files)} PNGs were "
            f"written; refusing to mislabel frame timestamps"
        )

    frames = []
    for path, info in zip(files, meta):
        if not (begin <= info["pts"] <= end):
            path.unlink()
            continue
        frames.append(
            {
                "path": path,
                "video_timestamp": round(info["pts"], 3),
                "pict_type": info["pict_type"],
            }
        )
    return frames


# --- image helpers ---------------------------------------------------------

def crop_fractional(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    width, height = image.size
    return image.crop(
        (int(box[0] * width), int(box[1] * height), int(box[2] * width), int(box[3] * height))
    )


def sharpness(image: Image.Image) -> float:
    """Variance of the Laplacian, the same measure detect ranks frames by."""
    import numpy as np

    gray = np.asarray(image.convert("L"), dtype=np.float32)
    lap = (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    return float(lap.var())


def board_gate_stats(board: Image.Image) -> tuple[float, float]:
    """Dark fraction and mean saturation of a board crop, as detect measures them."""
    import numpy as np

    arr = np.asarray(board.convert("RGB"), dtype=np.float32)
    dark = float((arr.mean(axis=2) < 40).mean())
    sat = float((arr.max(axis=2) - arr.min(axis=2)).mean())
    return dark, sat


def shows_board(board: Image.Image) -> bool:
    dark, sat = board_gate_stats(board)
    return dark >= GATE_BOARD_DARK and sat <= GATE_BOARD_SAT


def drop_transitions(frames: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split gated frames into the settled slide and any cross-fade frames.

    The reference is the per-pixel median of the window, which is the settled
    board as long as most frames show it. Deviation is measured in grey levels
    so the threshold means the same thing on every board.
    """
    import numpy as np

    if len(frames) < MIN_FRAMES_FOR_MEDIAN:
        for frame in frames:
            frame["deviation"] = 0.0
        return frames, []

    stack = np.stack(
        [np.asarray(f["_board"].convert("L"), dtype=np.float32) for f in frames]
    )
    median = np.median(stack, axis=0)
    keep, dropped = [], []
    for frame, layer in zip(frames, stack):
        frame["deviation"] = round(float(np.abs(layer - median).mean()), 3)
        (keep if frame["deviation"] <= STABLE_MAX_DEVIATION else dropped).append(frame)
    return keep, dropped


def select_diverse(frames: list[dict], limit: int) -> list[dict]:
    """Pick up to `limit` frames, spreading across keyframe intervals first.

    Frames sharing a keyframe interval are near-copies of the same I-frame, so
    taking two of them buys no independent read. This walks one frame from each
    interval in time order before it comes back for seconds, preferring the
    I-frame within an interval and falling back to the sharpest.
    """
    if not frames:
        return []

    base = min(f["video_timestamp"] for f in frames)
    groups: dict[int, list[dict]] = {}
    for frame in frames:
        index = int((frame["video_timestamp"] - base) / KEYFRAME_INTERVAL)
        frame["interval"] = index
        groups.setdefault(index, []).append(frame)

    for members in groups.values():
        members.sort(key=lambda f: (f["pict_type"] != "I", -f["sharpness"]))

    picked: list[dict] = []
    depth = 0
    while len(picked) < limit:
        added = False
        for index in sorted(groups):
            if depth < len(groups[index]):
                picked.append(groups[index][depth])
                added = True
                if len(picked) >= limit:
                    break
        if not added:
            break
        depth += 1

    picked.sort(key=lambda f: f["video_timestamp"])
    return picked


# --- one board -------------------------------------------------------------

def refine_board(
    board: dict,
    seg_base: str,
    names: list[str],
    starts: list[float],
    segments_dir: Path,
    existing: dict[str, Path],
    out_dir: Path,
    scratch_root: Path,
    frames_per_board: int,
    span_pad: float,
    sample_every: int,
    write_jpeg_twin: bool,
    force: bool,
) -> dict:
    sequence = board["sequence"]
    begin = float(board["begin"]) - span_pad
    end = float(board["end"]) + span_pad
    stem = f"board_{sequence:02d}_{int(round(board['begin']))}"

    manifest_path = out_dir / f"{stem}.json"
    if manifest_path.exists() and not force:
        try:
            done = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            done = None
        if done and done.get("refine_version") == REFINE_VERSION:
            if all(Path(f["board_png"]).exists() for f in done.get("frames", [])):
                done["reused"] = True
                done["bytes_downloaded"] = 0
                return done

    t_start = time.time()
    indexes = segment_span(starts, begin, end)
    downloaded, reused, fetched = stage_segments(
        seg_base, names, indexes, segments_dir, existing
    )
    t_download = time.time() - t_start

    playlist = segments_dir / f"refine_{sequence:02d}.m3u8"
    write_local_playlist(playlist, names, starts, indexes)

    scratch = scratch_root / f"b{sequence:02d}"
    t0 = time.time()
    try:
        frames = extract_png_frames(playlist, begin, end, scratch, sample_every)
        t_decode = time.time() - t0

        if not frames:
            raise RuntimeError(f"no frames decoded for board {sequence}")

        t0 = time.time()
        for frame in frames:
            with Image.open(frame["path"]) as image:
                frame["_board"] = crop_fractional(image, BOARD_BOX).copy()
                frame["_overlay"] = crop_fractional(image, OVERLAY_BOX).copy()
                frame["_full_size"] = image.size
            frame["sharpness"] = sharpness(frame["_board"])
            dark, sat = board_gate_stats(frame["_board"])
            frame["dark_fraction"] = round(dark, 3)
            frame["saturation"] = round(sat, 2)

        # Widening the window to find clean frames also reaches the camera shot
        # either side of the slide and the cross-fade between them. Both would
        # otherwise be saved as "the board" and quietly poison any comparison.
        on_board = [f for f in frames if shows_board(f["_board"])]
        off_board = len(frames) - len(on_board)
        on_board, faded = drop_transitions(on_board)
        if not on_board:
            raise RuntimeError(
                f"board {sequence}: none of {len(frames)} decoded frames in "
                f"{begin:.1f}-{end:.1f}s show a settled board"
            )

        keep = select_diverse(on_board, frames_per_board)
        intervals = len({f["interval"] for f in keep})

        out_dir.mkdir(parents=True, exist_ok=True)
        for stale in out_dir.glob(f"{stem}_f*"):
            stale.unlink()

        records = []
        for rank, frame in enumerate(keep):
            base = f"{stem}_f{rank}_{frame['pict_type']}"
            board_png = out_dir / f"{base}_board.png"
            overlay_png = out_dir / f"{base}_overlay.png"
            frame["_board"].save(board_png, format="PNG", optimize=True)
            frame["_overlay"].save(overlay_png, format="PNG", optimize=True)
            record = {
                "rank": rank,
                "video_timestamp": frame["video_timestamp"],
                "pict_type": frame["pict_type"],
                "keyframe_interval": frame["interval"],
                "sharpness": round(frame["sharpness"], 1),
                "dark_fraction": frame["dark_fraction"],
                "saturation": frame["saturation"],
                "deviation_from_median": frame["deviation"],
                "board_png": str(board_png),
                "overlay_png": str(overlay_png),
                "board_size": list(frame["_board"].size),
                "source_frame_size": list(frame["_full_size"]),
            }
            if write_jpeg_twin:
                # Same pixels, encoded the way detect encodes them. This exists
                # only so a caller can measure what the JPEG step alone costs;
                # nothing downstream should read it as the good copy.
                twin = out_dir / f"{base}_board_q92.jpg"
                frame["_board"].save(twin, format="JPEG", quality=92)
                record["board_jpeg_q92"] = str(twin)
            records.append(record)
        t_write = time.time() - t0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    record = {
        "refine_version": REFINE_VERSION,
        "sequence": sequence,
        "vote_id": board.get("vote_id"),
        "video_timestamp": board["begin"],
        "board_last_seen": board["end"],
        "window": [round(begin, 2), round(end, 2)],
        "detect_status": board.get("status"),
        "detect_tally": board.get("tally"),
        "detect_result": board.get("result"),
        "detect_board_crop": board.get("board_crop"),
        "segments": [names[i] for i in indexes],
        "segments_reused": reused,
        "segments_fetched": fetched,
        "bytes_downloaded": downloaded,
        "frames_decoded": len(frames),
        "keyframes_decoded": sum(1 for f in frames if f["pict_type"] == "I"),
        "frames_off_board": off_board,
        "frames_faded": len(faded),
        "frames_on_board": len(on_board),
        "frames_kept": len(records),
        # How many independent pictures of this board the kept frames really
        # represent. Frames sharing an interval are near-copies, so this is the
        # honest ceiling on what cross-frame consensus can do.
        "distinct_keyframe_intervals": intervals,
        "frames": records,
        "reused": False,
        "timing": {
            "download": round(t_download, 2),
            "decode": round(t_decode, 2),
            "write": round(t_write, 2),
            "total": round(time.time() - t_start, 2),
        },
    }
    manifest_path.write_text(json.dumps(record, indent=2))
    return record


# --- input -----------------------------------------------------------------

def boards_from_detect(payload: dict) -> list[dict]:
    """Flatten detect's accepted and rejected candidates into refine targets.

    Rejected candidates are exactly the ones worth re-reading, so both lists are
    taken; `status` is carried through so a caller can tell them apart.
    """
    boards: list[dict] = []
    for status in ("accepted", "rejected"):
        for candidate in payload.get(status) or []:
            parsed = candidate.get("parsed") or {}
            begin = candidate.get("video_timestamp")
            if begin is None:
                continue
            end = candidate.get("board_last_seen", begin)
            boards.append(
                {
                    "sequence": candidate.get("sequence", len(boards)),
                    "vote_id": candidate.get("vote_id"),
                    "begin": float(begin),
                    "end": float(max(end, begin)),
                    "status": status,
                    "tally": parsed.get("vote_tally"),
                    "result": parsed.get("result"),
                    "board_crop": candidate.get("board_crop"),
                    "problems": candidate.get("problems") or [],
                }
            )
    boards.sort(key=lambda b: b["sequence"])
    return boards


# --- main ------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument(
        "--input",
        default=None,
        help="detect output JSON; defaults to metadata/votes_{clip}.json on the Passport",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="output directory; defaults to crops_hq/{clip} on the Passport",
    )
    parser.add_argument(
        "--frames", type=int, default=FRAMES_PER_BOARD,
        help="lossless frames to keep per board, for cross-frame consensus",
    )
    parser.add_argument(
        "--span-pad", type=float, default=SPAN_PAD,
        help="seconds either side of the confirmed board span to also sample",
    )
    parser.add_argument(
        "--sample-every", type=int, default=SAMPLE_EVERY_N,
        help="also take every Nth non-key frame inside the window",
    )
    parser.add_argument(
        "--no-jpeg-twin", dest="jpeg_twin", action="store_false",
        help="skip the q92 JPEG copy written alongside each PNG for A/B testing",
    )
    parser.add_argument(
        "--keep-segments", action="store_true",
        help="leave the .ts segments on the Passport so a rerun costs no download",
    )
    parser.add_argument(
        "--force", action="store_true", help="re-extract boards that already have output"
    )
    parser.add_argument("--only", type=int, action="append", default=[],
                        help="refine just these sequence numbers; repeatable")
    args = parser.parse_args()

    started = time.time()
    disk_guard.require_space("refine:start")
    print(disk_guard.report("refine:start"))

    metadata = disk_guard.work_dir("metadata")
    input_path = Path(args.input) if args.input else metadata / f"votes_{args.clip}.json"
    if not input_path.is_absolute():
        candidate = disk_guard.PASSPORT_ROOT / input_path
        input_path = candidate if candidate.exists() else input_path
    if not input_path.exists():
        raise SystemExit(f"missing detect output {input_path}")
    payload = json.loads(input_path.read_text())

    boards = boards_from_detect(payload)
    if args.only:
        boards = [b for b in boards if b["sequence"] in set(args.only)]
    if not boards:
        raise SystemExit(f"no vote candidates in {input_path}")

    catalog_path = metadata / f"clips_{args.year}.json"
    if not catalog_path.exists():
        raise SystemExit(f"missing catalog {catalog_path}")
    catalog = json.loads(catalog_path.read_text())
    clip = next((c for c in catalog["clips"] if c["clip_id"] == args.clip), None)
    if clip is None:
        raise SystemExit(f"clip {args.clip} not in {catalog_path}")
    if not clip.get("hls_url"):
        raise SystemExit(f"clip {args.clip} has no HLS url")

    variants, chunk_url = master_variants(clip["hls_url"])
    if variants:
        print(f"master playlist lists {len(variants)} rendition(s):")
        for index, variant in enumerate(variants):
            marker = " <- using (largest)" if index == 0 else ""
            print(
                f"  {variant['width']}x{variant['height']} "
                f"{variant['bandwidth'] / 1e6:.2f} Mbps {variant['codecs']}{marker}"
            )
    else:
        print(f"{clip['hls_url']} is already a media playlist; single rendition")

    seg_base, names, starts = load_chunklist(chunk_url)
    print(f"chunklist: {len(names)} segments, ~{(starts[-1] + 2.0) / 3600:.2f} h")

    out_dir = Path(args.out) if args.out else disk_guard.PASSPORT_ROOT / "crops_hq" / args.clip
    out_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = disk_guard.PASSPORT_ROOT / "raw_hq" / args.clip
    scratch_root = disk_guard.PASSPORT_ROOT / "scratch" / f"refine_{args.clip}"

    existing = index_existing_segments(disk_guard.PASSPORT_ROOT / "raw" / args.clip)
    print(
        f"refining {len(boards)} boards -> {out_dir}"
        + (f"; {len(existing)} segments already on the Passport" if existing else "")
    )

    records: list[dict] = []
    failures: list[dict] = []
    for board in boards:
        disk_guard.require_space(f"refine:b{board['sequence']:02d}")
        try:
            record = refine_board(
                board, seg_base, names, starts, segments_dir, existing, out_dir,
                scratch_root, args.frames, args.span_pad, args.sample_every,
                args.jpeg_twin, args.force,
            )
        except Exception as exc:  # noqa: BLE001 - one bad board must not sink the run
            failures.append({"sequence": board["sequence"], "error": str(exc)})
            print(f"  board {board['sequence']:02d} FAILED: {exc}", file=sys.stderr)
            continue
        records.append(record)
        timing = record.get("timing") or {}
        print(
            f"  board {record['sequence']:02d} t={record['video_timestamp']:.0f}s "
            f"[{record['detect_status']}] "
            f"{record['segments_fetched']} fetched / {record['segments_reused']} reused, "
            f"{record['bytes_downloaded'] / 1e6:.1f} MB, "
            f"{record['frames_decoded']} decoded "
            f"({record['keyframes_decoded']} key, -{record['frames_off_board']} off-board"
            f", -{record['frames_faded']} fading) -> {record['frames_kept']} kept "
            f"across {record['distinct_keyframe_intervals']} intervals "
            f"in {timing.get('total', 0.0):.1f}s"
            + ("  (reused)" if record.get("reused") else "")
        )

    if not args.keep_segments:
        freed = disk_guard.dir_size_gib(segments_dir)
        shutil.rmtree(segments_dir, ignore_errors=True)
        print(f"removed staged segments, reclaimed {freed:.3f} GiB")
    shutil.rmtree(scratch_root, ignore_errors=True)

    wall = time.time() - started
    total_bytes = sum(r["bytes_downloaded"] for r in records)
    kept = sum(r["frames_kept"] for r in records)

    # A --only run must not turn the report into a one-board file: the next
    # stage reads it as the inventory of every refined board for the clip. This
    # merges by sequence the way extract does with windows.json, so the record
    # list is cumulative while the counters below describe just this run.
    report_path = metadata / f"refine_{args.clip}.json"
    merged: dict[int, dict] = {}
    if report_path.exists():
        try:
            previous = json.loads(report_path.read_text())
        except json.JSONDecodeError:
            previous = {}
        for old in previous.get("records") or []:
            if all(Path(f["board_png"]).exists() for f in old.get("frames", [])):
                merged[old["sequence"]] = old
    for fresh in records:
        merged[fresh["sequence"]] = fresh
    inventory = [merged[key] for key in sorted(merged)]

    report = {
        "refine_version": REFINE_VERSION,
        "clip_id": args.clip,
        "year": args.year,
        "date": payload.get("date"),
        "input": str(input_path),
        "out_dir": str(out_dir),
        "hls_url": clip["hls_url"],
        "renditions": variants,
        "rendition_used": variants[0] if variants else None,
        "resolution_ceiling": (
            f"{variants[0]['width']}x{variants[0]['height']}" if variants else "unknown"
        ),
        "boards": len(inventory),
        "boards_this_run": len(records),
        "boards_selected": sorted(args.only) or None,
        "boards_failed": failures,
        "frames_kept": sum(r["frames_kept"] for r in inventory),
        "frames_kept_this_run": kept,
        "frames_per_board": args.frames,
        "span_pad": args.span_pad,
        "bytes_downloaded": total_bytes,
        "mb_downloaded": round(total_bytes / 1e6, 2),
        "output_gib": round(disk_guard.dir_size_gib(out_dir), 4),
        "wall_seconds": round(wall, 2),
        "seconds_per_board": round(wall / max(1, len(records)), 2),
        "records": inventory,
    }
    report_path.write_text(json.dumps(report, indent=2, default=str))

    print(
        f"\nrefine: {len(records)} boards, {kept} lossless frames, "
        f"{total_bytes / 1e6:.1f} MB downloaded, {report['output_gib'] * 1024:.0f} MiB written, "
        f"{wall:.1f}s wall ({report['seconds_per_board']:.1f}s/board)"
    )
    print(f"wrote {report_path}")
    print(disk_guard.report("refine:done"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
