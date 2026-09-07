#!/usr/bin/env python3
"""Extract and gate 1 fps frames for the votable chapter windows of one clip.

The full meeting is ~7 hours, so nothing downloads the whole MP4. Instead this
reads the HLS chunklist, works out exactly which 2-second segments cover each
votable agenda window, pulls only those segments to the Passport in parallel,
and decodes them locally. Local decode is roughly 100x faster than letting
ffmpeg seek into the remote playlist for every window.

Sampled frames never become files. One ffmpeg pass per window streams the
full-resolution JPEGs back over a pipe and this stage consumes them one at a
time: a cheap numeric gate (dark fraction and saturation, needing no text
legibility) runs on a draft decode of the bytes in hand, the exact gate confirms
any survivor on the full-resolution pixels, and only the confirmed frames plus
their consensus halo are ever written. A 7-hour meeting lands a few dozen
detection frames instead of the ~26,000 files the frame-per-JPEG design
produced, which is what stops Spotlight and the endpoint security agent from
being handed tens of thousands of create/close events per meeting.

Memory is bounded by the halo, not the clip: a deque of a few frames supplies
the lookbehind a gate hit needs, so a 7-hour window costs the same as a
5-minute one.

Windows run concurrently behind a global cap on in-flight CDN sockets, and every
window checks free space on both volumes before and after it runs.

    python3 pipeline/extract_vote_windows.py --clip 14821
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import inspect
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bounded_proc
import disk_guard
import detect_and_parse_votes as detect
from detect_and_parse_votes import (
    frame_stats_image,
    merge_timing,
    passes_gate,
    passes_gate_relaxed,
)
from PIL import Image

# CloudFront in front of archive-stream.granicus.com rejects non-browser agents.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
REFERER = "https://torrance.granicus.com/"
DOWNLOAD_WORKERS = 8
# The CDN throttles hard after a few hundred megabytes, so retries stay cheap:
# a stuck window should cost seconds, not hours, and the run moves on.
SEGMENT_TIMEOUT = 45
SEGMENT_RETRIES = 3

# Windows run in parallel, so the per-window worker count is no longer the real
# concurrency. This caps total in-flight requests across every window at once.
WINDOW_WORKERS = 3
MAX_SOCKETS = 24
MIN_SOCKETS = 4
THROTTLE_CODES = {403, 429, 500, 502, 503, 504}

# Cheap gate tier: a draft (DCT-scaled) decode of the full-resolution JPEG
# already in memory. 320x180 is the 1/4 scale of the 1280x720 source, so
# libjpeg reaches it without a second ffmpeg output, a re-encode, or a file.
# The gate's crops are fractional, so it reads the same picture regions here.
GATE_DRAFT = (320, 180)
# Downscaling moves the gate statistics, so the cheap tier screens with a
# widened threshold and the real gate re-runs on the full-resolution bytes that
# survive. Measured over 2,852 frames of clip 14821 (every one of the 661 gate
# hits, the 800 nearest misses and 1,500 random frames): the draft tier reads at
# most 0.0069 lower on the dark fractions and never higher on saturation where
# it could flip a real hit, versus 0.046 and 2.05 for the 270p re-encoded tier
# this replaces -- the draft is more faithful because it is the same
# entropy-coded data, not a second encode. The margins are left at the wider
# values the old tier needed, so they now clear the worst observed deviation by
# ~9x. Widen them, never narrow them.
GATE_MARGIN_DARK = 0.06
GATE_MARGIN_SAT = 4.0

# Bounds on the ffmpeg that decodes a window. Two of them, because they catch
# different failures and neither is sufficient alone.
#
# The stall timeout is the one that does the real work. Once ffmpeg is running it
# emits a frame every few milliseconds, so silence this long means it is wedged
# on a read -- a Passport that stopped responding, a segment it cannot get past
# -- not that it is being slow. It is charged only for time this process spends
# blocked waiting for bytes, never for the time the gate spends on frames it has
# already been handed, which is why it does not need to scale with the window.
DECODE_STALL_TIMEOUT = 120.0
# The deadline is the backstop for the failure the stall timeout cannot see: a
# process making real but useless progress forever, which is what the ffmpeg pair
# that ran for five and a half hours was doing. It has to scale, because window
# extraction time legitimately varies with window duration -- a constant tight
# enough to catch a hang would kill valid long windows, and one loose enough to
# be safe would not have caught that run for hours. Local decode of staged
# segments runs at roughly 100x realtime, so 2.5x the media duration is a ~250x
# margin over the work and still bounds a 15-minute window at under 40 minutes.
DECODE_DEADLINE_MULTIPLIER = 2.5
# Floor for the deadline: process start, HLS parse and a cold Passport dominate a
# short window, and 2.5x a 20-second window is not a bound, it is a coin flip.
DECODE_DEADLINE_FLOOR = 180.0


def _consensus_pad_seconds(default: float = 4.0) -> float:
    """How far either side of a vote cluster detect reads neighbouring frames.

    Detect merges the OCR of every frame showing the same board, and widens each
    cluster by a few seconds to pick up reads the detector itself missed. Those
    neighbours are frames the gate rejected, so dropping them here would quietly
    shrink that consensus. The pad is read back off detect rather than copied,
    so the two stages cannot drift apart.
    """
    try:
        pad = inspect.signature(detect.expand_group).parameters["pad"].default
        return float(pad)
    except (AttributeError, KeyError, TypeError, ValueError):
        return default


# Keep a second of slack beyond what detect asks for, so a small change there
# does not silently start losing consensus frames here.
GATE_HALO_SECONDS = _consensus_pad_seconds() + 1.0

PIPELINE_VERSION = "stream-gate-v3"
# Manifests whose frames are already a gated selection rather than every sampled
# frame. Resume trusts a sidecar only if it names one of these, so a manifest
# from some future scheme is re-extracted instead of silently half-read.
# v3 adds the Format A bright-slide gate (480x360 white boards); v2 manifests
# must not be resumed on old-format clips or white slides are silently skipped.
PRE_GATED_PIPELINES = (PIPELINE_VERSION,)


class CdnLimiter:
    """Global cap on in-flight segment requests, with throttle backoff.

    Running three windows at once multiplies DOWNLOAD_WORKERS, and the CDN
    starts refusing or stalling requests well before the pipeline would notice.
    The cap shrinks on any throttle or timeout and recovers only after a long
    run of clean responses, so a bad patch costs throughput instead of failing
    the window.
    """

    def __init__(self, ceiling: int = MAX_SOCKETS, floor: int = MIN_SOCKETS) -> None:
        self.ceiling = max(1, ceiling)
        self.floor = max(1, min(floor, self.ceiling))
        self._limit = self.ceiling
        self._active = 0
        self._streak = 0
        self._cond = threading.Condition()
        self.throttle_events = 0
        self.low_water = self._limit

    @property
    def limit(self) -> int:
        with self._cond:
            return self._limit

    @contextlib.contextmanager
    def slot(self):
        with self._cond:
            while self._active >= self._limit:
                self._cond.wait(timeout=1.0)
            self._active += 1
        try:
            yield
        finally:
            with self._cond:
                self._active -= 1
                self._cond.notify()

    def penalize(self, reason: str) -> float:
        """Shrink the cap and report how long the caller should wait."""
        with self._cond:
            self.throttle_events += 1
            self._streak = 0
            before = self._limit
            self._limit = max(self.floor, self._limit - 4)
            self.low_water = min(self.low_water, self._limit)
            self._cond.notify_all()
            shrank = self._limit < before
        if shrank:
            print(
                f"  cdn backoff: {reason}; socket cap {before} -> {self._limit}",
                file=sys.stderr,
            )
        return 2.0 if shrank else 1.0

    def reward(self) -> None:
        with self._cond:
            self._streak += 1
            if self._streak >= 64 and self._limit < self.ceiling:
                self._limit += 1
                self._streak = 0
                self._cond.notify()


LIMITER = CdnLimiter()


def _retry_after(exc: urllib.error.HTTPError) -> float:
    try:
        return float(exc.headers.get("Retry-After") or 0)
    except (TypeError, ValueError):
        return 0.0


def http_get(url: str, retries: int = SEGMENT_RETRIES, timeout: int = SEGMENT_TIMEOUT) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Referer": REFERER}
        )
        try:
            with LIMITER.slot():
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = resp.read()
            LIMITER.reward()
            return data
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in THROTTLE_CODES:
                wait = LIMITER.penalize(f"HTTP {exc.code}")
                time.sleep(max(wait, _retry_after(exc), 1.0 * (attempt + 1)))
            else:
                time.sleep(1.0 * (attempt + 1))
        except (urllib.error.URLError, OSError) as exc:
            # A timeout under load is the CDN throttling us, not a dead link.
            last = exc
            wait = LIMITER.penalize(str(exc)[:60])
            time.sleep(max(wait, 1.0 * (attempt + 1)))
    raise RuntimeError(f"GET failed after {retries} tries: {url} ({last})")


def load_chunklist(hls_url: str) -> tuple[str, list[str], list[float]]:
    """Return (segment base url, segment names, cumulative start times)."""
    master = http_get(hls_url).decode("utf-8", errors="replace")
    base = hls_url.rsplit("/", 1)[0]

    chunk_url = hls_url
    if "#EXT-X-STREAM-INF" in master:
        variants = [
            line.strip()
            for line in master.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not variants:
            raise RuntimeError(f"no variant playlist in {hls_url}")
        chunk_url = variants[0] if variants[0].startswith("http") else f"{base}/{variants[0]}"

    chunklist = http_get(chunk_url).decode("utf-8", errors="replace")
    seg_base = chunk_url.rsplit("/", 1)[0]

    names: list[str] = []
    starts: list[float] = []
    clock = 0.0
    pending: float | None = None
    for line in chunklist.splitlines():
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


def segment_span(starts: list[float], total: float, begin: float, end: float) -> tuple[int, int]:
    """Inclusive segment index range covering [begin, end] in video seconds."""
    first = 0
    for idx, start in enumerate(starts):
        if start <= begin:
            first = idx
        else:
            break
    last = first
    for idx in range(first, len(starts)):
        last = idx
        if starts[idx] >= end:
            break
    return first, min(last, len(starts) - 1)


def votable_ranges(agenda: list[dict], lead: int, duration: float) -> list[dict]:
    """Merge each votable cuepoint's [start - lead, next start] into ranges."""
    raw: list[dict] = []
    for i, item in enumerate(agenda):
        if not item.get("votable"):
            continue
        end = agenda[i + 1]["time"] if i + 1 < len(agenda) else duration
        raw.append(
            {
                "begin": max(0.0, item["time"] - lead),
                "end": float(min(end, duration)),
                "meta_ids": [item["meta_id"]],
            }
        )
    raw.sort(key=lambda r: r["begin"])

    merged: list[dict] = []
    for rng in raw:
        if merged and rng["begin"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], rng["end"])
            merged[-1]["meta_ids"].extend(rng["meta_ids"])
        else:
            merged.append(dict(rng))
    return merged


def chunk_ranges(ranges: list[dict], max_window: int) -> list[dict]:
    """Split long ranges so the disk guard runs often and reruns stay cheap."""
    out: list[dict] = []
    for rng in ranges:
        begin, end = rng["begin"], rng["end"]
        while begin < end:
            stop = min(end, begin + max_window)
            out.append({"begin": begin, "end": stop, "meta_ids": rng["meta_ids"]})
            begin = stop
    return out


def download_segments(
    seg_base: str, names: list[str], indexes: range, dest: Path
) -> tuple[int, list[int]]:
    """Fetch the segments for one window, returning (bytes, failed indexes)."""
    dest.mkdir(parents=True, exist_ok=True)

    def grab(idx: int) -> tuple[int, int | None]:
        try:
            data = http_get(f"{seg_base}/{names[idx]}")
        except RuntimeError:
            return 0, idx
        tmp = dest / f".{names[idx]}.part"
        tmp.write_bytes(data)
        tmp.rename(dest / names[idx])
        return len(data), None

    total = 0
    todo = [i for i in indexes if not (dest / names[i]).exists()]
    # Archive-era Granicus streams drop individual .ts segments under load.
    # Extra passes with fewer workers recover most "1 of 452 missing" failures
    # without failing the whole window.
    for attempt in range(5):
        if not todo:
            break
        if attempt:
            time.sleep(min(8.0, 1.5 * attempt))
        workers = DOWNLOAD_WORKERS if attempt == 0 else max(1, 4 - attempt)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(grab, todo))
        total += sum(size for size, _ in outcomes)
        todo = [idx for _, idx in outcomes if idx is not None]
    return total, todo


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
    for idx in indexes:
        nxt = starts[idx + 1] if idx + 1 < len(starts) else starts[idx] + 2.0
        lines.append(f"#EXTINF:{nxt - starts[idx]:.3f},")
        lines.append(names[idx])
    lines.append("#EXT-X-ENDLIST")
    path.write_text("\n".join(lines) + "\n")


def frame_timestamp(ordinal: int, playlist_t0: float, fps: float) -> float:
    """Absolute video timestamp of the Nth frame ffmpeg emitted for a window.

    The local playlist starts at a known segment boundary, so frame N sits at
    playlist_t0 + (N-1)/fps. That is a real video timestamp, not an estimate
    derived from a frame index over the whole meeting.
    """
    return playlist_t0 + (ordinal - 1) / fps


def frame_records(
    out_dir: Path, playlist_t0: float, fps: float, window: dict, prune: bool
) -> list[dict]:
    """Map each frame file on disk to an absolute video timestamp."""
    records = []
    for frame in sorted(out_dir.glob("f_*.jpg")):
        ordinal = int(re.search(r"f_(\d+)", frame.name).group(1))
        timestamp = frame_timestamp(ordinal, playlist_t0, fps)
        if timestamp < window["begin"] - 1 or timestamp > window["end"] + 1:
            if prune:
                frame.unlink()
            continue
        records.append({"frame": str(frame), "video_timestamp": round(timestamp, 2)})
    return records


# --- decode ----------------------------------------------------------------

# Seconds of media a local playlist covers, the size of the work every decode
# bound below is scaled off. Lives in bounded_proc because refine_boards derives
# its own ffmpeg bound from the same measurement.
playlist_media_seconds = bounded_proc.playlist_media_seconds


def iter_window_jpegs(
    playlist: Path,
    fps: float,
    *,
    media_seconds: float | None = None,
    stall_timeout: float = DECODE_STALL_TIMEOUT,
    deadline_multiplier: float = DECODE_DEADLINE_MULTIPLIER,
    label: str | None = None,
):
    """Yield (ordinal, jpeg_bytes) as ffmpeg emits them, holding no history.

    Splitting on the SOI/EOI markers is safe because JPEG byte-stuffs any 0xFF
    inside entropy-coded data, and ffmpeg's mjpeg output carries no EXIF
    thumbnail that could embed a nested image.

    The generator is the whole point of this stage: the caller sees one frame at
    a time and decides immediately whether to keep it, so neither the frames nor
    a per-frame file for them ever exists. Consuming it in a `with closing(...)`
    or a for-loop that runs to completion is required, otherwise ffmpeg is left
    holding a full pipe; `finally` covers early exit.

    A `timeout=` argument has nothing to attach to here -- ffmpeg is alive across
    hundreds of reads with gate work between them -- so the bound is a stall
    timeout plus an overall deadline scaled off the media duration, and the kill
    goes to the whole process group. See `bounded_proc.stream_bounded`.

    A bound that fires raises `bounded_proc.ProcessTimeout` **through** this
    generator; it never returns the frames collected so far. Downstream a
    truncated window is indistinguishable from a window that genuinely held no
    vote board, so a partial result that looked successful would be a missing
    council vote in published data.
    """
    # -allowed_extensions is a private option of the HLS demuxer and ffmpeg
    # fails outright when it is handed to any other one, so it is only passed
    # for a playlist. That also lets this be pointed at a plain container,
    # which is how the timestamp mapping gets tested against a clip whose
    # gate-passing seconds are known.
    source = ["-i", str(playlist)]
    if playlist.suffix.lower() in {".m3u8", ".m3u"}:
        source = ["-allowed_extensions", "ALL"] + source

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        *source,
        "-vf", f"fps={fps}",
        "-q:v", "2",
        "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
    ]

    if media_seconds is None:
        media_seconds = playlist_media_seconds(playlist)
    deadline = bounded_proc.bound_from_work(
        media_seconds,
        multiplier=deadline_multiplier,
        floor=DECODE_DEADLINE_FLOOR,
    )
    label = label or f"ffmpeg decode {playlist.name}"
    bounded_proc.note_bound(
        label,
        f"{deadline:.0f}s deadline for "
        + (f"{media_seconds:.0f}s of media at {deadline_multiplier:g}x"
           if media_seconds else "unmeasured media (floor only)")
        + f", {stall_timeout:.0f}s stall",
    )

    with bounded_proc.stream_bounded(
        cmd, label=label, stall_timeout=stall_timeout, deadline=deadline
    ) as stream:
        buf = bytearray()
        ordinal = 0
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                break
            buf += chunk
            while True:
                start = buf.find(b"\xff\xd8")
                if start < 0:
                    break
                end = buf.find(b"\xff\xd9", start + 2)
                if end < 0:
                    break
                ordinal += 1
                yield ordinal, bytes(buf[start : end + 2])
                # Drop the frame from the buffer as soon as it is handed over,
                # so the buffer stays at one frame rather than one window.
                del buf[: end + 2]
        # Inside the `with`, so a non-zero exit raises before the consumer's
        # for-loop can end normally and let it treat the window as finished.
        stream.finish()


# --- gate ------------------------------------------------------------------

def draft_decode(image: Image.Image, target_height: int) -> None:
    """Ask libjpeg for the cheapest DCT reduction at or above `target_height`.

    `Image.draft` picks the largest reduction whose output still covers the box
    it is given, on both axes, so passing a fixed box silently does nothing on a
    source smaller than that box: 1280x720 asked for 320x180 reduces by 1/4 as
    intended, but 480x360 asked for the same box cannot, and returns full size --
    the cheap tier becomes a full decode on exactly the clips that already
    decode slowest per useful pixel. Sizing the box from this frame's own
    dimensions asks for a scale factor rather than a resolution, so each source
    lands on the cheapest reduction that still clears `target_height`.
    """
    if not target_height or image.height <= target_height:
        return
    reduction = 1
    while reduction < 8 and image.height // (reduction * 2) >= target_height:
        reduction *= 2
    image.draft("RGB", (image.width // reduction, image.height // reduction))


def gate_payload(
    payload: bytes, margins: tuple[float, float], draft: tuple[int, int]
) -> tuple[bool, bool]:
    """Two-tier gate run entirely on one in-memory JPEG.

    Returns (nominated_by_cheap_tier, confirmed_by_full_gate) so the caller can
    still report how selective the cheap tier was, which is the number that
    says whether the draft margins are too wide.

    libjpeg can scale by 1/2, 1/4 or 1/8 during entropy decode, so `draft`
    gives the cheap tier for free from the bytes already in hand: measured over
    2,852 frames of clip 14821 a 320x180 draft decode is 11.5x faster than the
    full decode and reads at most 0.007 low on the dark fractions where it could
    flip a real hit -- well inside GATE_MARGIN_DARK, and 6x more faithful than
    the separately encoded 270p tier this replaces, because it is the same
    entropy-coded data rather than a re-encode.

    Whatever the cheap tier nominates is then confirmed by the exact gate on the
    full-resolution pixels, so the accepted set is identical to gating every
    frame at full resolution -- which is what keeps this comparable with every
    earlier run.
    """
    with Image.open(io.BytesIO(payload)) as image:
        draft_decode(image, draft[1])
        cheap = frame_stats_image(image)
    if not passes_gate_relaxed(cheap, *margins):
        return False, False
    with Image.open(io.BytesIO(payload)) as image:
        return True, passes_gate(frame_stats_image(image))


def gate_window_stream(
    playlist: Path,
    out_dir: Path,
    fps: float,
    playlist_t0: float,
    window: dict,
    halo: int = 0,
    margins: tuple[float, float] = (GATE_MARGIN_DARK, GATE_MARGIN_SAT),
    draft: tuple[int, int] = GATE_DRAFT,
    full_gate: bool = False,
    stall_timeout: float = DECODE_STALL_TIMEOUT,
    deadline_multiplier: float = DECODE_DEADLINE_MULTIPLIER,
) -> dict:
    """Stream one window through the gate, writing only the frames worth keeping.

    Memory is bounded by `halo`, not by the length of the window: a deque of the
    last `halo + 1` frames supplies the lookbehind a hit needs, and a countdown
    supplies the lookahead, so a 7-hour clip costs the same as a 5-minute one.

    Frames outside the window's own span are skipped before the gate, exactly as
    the previous version dropped them before gating, so the sampled count and
    the accepted set both stay comparable.

    Returning at all means the decode ran to EOF and ffmpeg exited zero: every
    other outcome leaves through an exception from `iter_window_jpegs`. The
    returned `complete` flag makes that checkable by the caller rather than
    merely true, because the frames on disk after a killed decode are a partial
    set that nothing downstream can distinguish from a window with no vote in it.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("f_*.jpg"):
        stale.unlink()

    ring: deque[tuple[int, bytes]] = deque(maxlen=max(1, halo + 1))
    pending = 0
    sampled = 0
    candidates = 0
    hits: list[int] = []
    written: list[int] = []
    seen: set[int] = set()

    def keep_frame(ordinal: int, payload: bytes) -> None:
        if ordinal in seen:
            return
        (out_dir / f"f_{ordinal:05d}.jpg").write_bytes(payload)
        seen.add(ordinal)
        written.append(ordinal)

    # The bound scales off the media the playlist covers; a plain container has
    # no EXTINF tags to read, so the window's own span stands in as the size of
    # the work being asked for.
    media_seconds = playlist_media_seconds(playlist)
    if media_seconds is None:
        media_seconds = max(0.0, window["end"] - window["begin"])
    index = window.get("index")
    label = f"ffmpeg decode w{index:03d}" if isinstance(index, int) else "ffmpeg decode"

    frames = iter_window_jpegs(
        playlist,
        fps,
        media_seconds=media_seconds,
        stall_timeout=stall_timeout,
        deadline_multiplier=deadline_multiplier,
        label=label,
    )
    for ordinal, payload in frames:
        timestamp = frame_timestamp(ordinal, playlist_t0, fps)
        if not (window["begin"] - 1 <= timestamp <= window["end"] + 1):
            continue
        sampled += 1
        ring.append((ordinal, payload))

        if full_gate:
            with Image.open(io.BytesIO(payload)) as image:
                hit = passes_gate(frame_stats_image(image))
            candidates += 1
        else:
            nominated, hit = gate_payload(payload, margins, draft)
            candidates += int(nominated)

        if hit:
            hits.append(ordinal)
            for buf_ordinal, buf_payload in ring:
                keep_frame(buf_ordinal, buf_payload)
            pending = halo
        elif pending:
            keep_frame(ordinal, payload)
            pending -= 1

    return {
        "sampled": sampled,
        "candidates": candidates,
        "hits": hits,
        "written": sorted(written),
        "ring_frames": len(ring),
        # Reached only after ffmpeg hit EOF and exited zero. See the docstring.
        "complete": True,
    }


# --- one window ------------------------------------------------------------

def legacy_records(out_dir: Path, playlist_t0: float, fps: float, window: dict) -> list[dict]:
    """Frames left by the pre-gate-tier extractor, which wrote every frame."""
    return frame_records(out_dir, playlist_t0, fps, window, prune=False)


class WindowFailure(RuntimeError):
    """One window could not be extracted. A `RuntimeError` so existing callers catch it.

    `frames_invalidated` is the field that matters. It says whether this run had
    already begun replacing the window's frames when it failed. If it had, what
    is on disk now is a partial set, and any earlier manifest entry describing
    that window as complete has become a lie: carrying it forward would publish a
    truncated window as a finished one, with however many votes fell in the
    missing part silently absent. Nothing downstream can tell the difference
    between that and a window that genuinely held no vote board, which is why
    this is a data-integrity flag and not a diagnostic.
    """

    def __init__(
        self,
        message: str,
        *,
        index: int,
        frames_invalidated: bool = False,
        kind: str = "error",
    ) -> None:
        super().__init__(message)
        self.index = index
        self.frames_invalidated = frames_invalidated
        self.kind = kind


def _span_matches(record: dict, window: dict, playlist_t0: float) -> bool:
    """Resume is only valid if this disk record is the same window we would extract.

    Frames are timestamped from playlist_t0. Reusing a directory after --lead or
    the agenda changed relabels every frame with a new origin, which can shift
    timestamps by tens of seconds while still looking like a 95% complete set.
    """
    try:
        return (
            abs(float(record.get("begin")) - window["begin"]) <= 0.5
            and abs(float(record.get("end")) - window["end"]) <= 0.5
            and abs(float(record.get("playlist_t0")) - playlist_t0) <= 0.05
        )
    except (TypeError, ValueError):
        return False


def extract_window(
    window: dict,
    seg_base: str,
    names: list[str],
    starts: list[float],
    raw_root: Path,
    frames_root: Path,
    fps: float,
    keep_segments: bool,
    resume: bool = True,
    draft: tuple[int, int] = GATE_DRAFT,
    full_gate: bool = False,
    margins: tuple[float, float] = (GATE_MARGIN_DARK, GATE_MARGIN_SAT),
    halo_seconds: float = GATE_HALO_SECONDS,
    stall_timeout: float = DECODE_STALL_TIMEOUT,
    deadline_multiplier: float = DECODE_DEADLINE_MULTIPLIER,
) -> dict:
    stage = f"extract:w{window['index']:03d}"
    disk_guard.require_space(stage)

    first, last = segment_span(starts, starts[-1], window["begin"], window["end"])
    indexes = range(first, last + 1)
    playlist_t0 = starts[first]
    out_dir = frames_root / f"w{window['index']:03d}"
    record_path = frames_root / "records" / f"w{window['index']:03d}.json"
    # Concurrent windows share the boundary segment between them, so each window
    # owns its own segment directory. One duplicated 2-second download is much
    # cheaper than reference-counting deletes across threads.
    raw_dir = raw_root / f"w{window['index']:03d}"

    base = {
        "index": window["index"],
        "begin": round(window["begin"], 2),
        "end": round(window["end"], 2),
        "meta_ids": sorted(set(window["meta_ids"])),
        "segment_first": first,
        "segment_last": last,
        "playlist_t0": round(playlist_t0, 3),
        "failed_segments": [],
    }

    if resume:
        done = None
        if record_path.exists():
            try:
                done = json.loads(record_path.read_text())
            except json.JSONDecodeError:
                done = None
        if done and done.get("pipeline") in PRE_GATED_PIPELINES:
            existing = [f for f in done.get("frames", []) if Path(f["frame"]).exists()]
            if (
                len(existing) == len(done.get("frames", []))
                and _span_matches(done, window, playlist_t0)
            ):
                done["frames"] = existing
                done["bytes_downloaded"] = 0
                done["resumed"] = True
                done["timing"] = {"download": 0.0, "decode_gate": 0.0, "total": 0.0}
                return done
        # A clip extracted before the gate tier existed has every frame on disk.
        # Reusing it keeps a completed meeting from being re-downloaded, and
        # keeps this stage from deleting a fixture another stage is reading.
        # Only when the stored span matches: otherwise the filenames get
        # relabelled against a new playlist_t0 and votes bind to the wrong item.
        legacy = legacy_records(out_dir, playlist_t0, fps, window)
        expected = (window["end"] - window["begin"]) * fps
        if legacy and len(legacy) >= 0.95 * expected:
            prior = None
            prior_path = frames_root / "windows.json"
            if prior_path.exists():
                try:
                    prior_manifest = json.loads(prior_path.read_text())
                    prior = next(
                        (
                            w
                            for w in prior_manifest.get("windows") or []
                            if w.get("index") == window["index"]
                        ),
                        None,
                    )
                except json.JSONDecodeError:
                    prior = None
            if prior and _span_matches(prior, window, playlist_t0):
                return {
                    **base,
                    "bytes_downloaded": 0,
                    "resumed": True,
                    "pipeline": "legacy-full-frames",
                    "frame_count": len(legacy),
                    "frames": legacy,
                    "frames_sampled": len(legacy),
                    "frames_gated": None,
                    "gate_candidates": None,
                    "timing": {"download": 0.0, "decode_gate": 0.0, "total": 0.0},
                }

    t_start = time.time()
    downloaded, failed = download_segments(seg_base, names, indexes, raw_dir)
    t_download = time.time() - t_start
    if failed:
        if not keep_segments:
            shutil.rmtree(raw_dir, ignore_errors=True)
        # Nothing has touched this window's frames yet, so whatever an earlier run
        # left is still complete and still resumable.
        raise WindowFailure(
            f"window {window['index']} missing {len(failed)} of {len(indexes)} segments "
            f"(first failure media index {failed[0]})",
            index=window["index"],
            frames_invalidated=False,
            kind="download",
        )
    disk_guard.require_space(f"{stage}:downloaded")

    playlist = raw_dir / f"window_{window['index']:03d}.m3u8"
    write_local_playlist(playlist, names, starts, indexes)

    # Committing to re-extract. The gate is about to delete this window's frames
    # and write a new set, so from here until the new record lands, anything on
    # disk is a partial set -- and the sidecar claiming otherwise goes first.
    # That ordering is what stops a later resume from reading a stale sidecar and
    # reporting a truncated window as already done, including when this process
    # dies in a way that runs no cleanup at all.
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.unlink(missing_ok=True)

    # Decode and gate are one pass now: frames are consumed as ffmpeg produces
    # them, so the two costs cannot be separated and are reported together.
    t0 = time.time()
    try:
        gate = gate_window_stream(
            playlist, out_dir, fps, playlist_t0, window,
            halo=max(0, round(halo_seconds * fps)),
            margins=margins, draft=draft, full_gate=full_gate,
            stall_timeout=stall_timeout, deadline_multiplier=deadline_multiplier,
        )
        if not gate.get("complete"):
            raise RuntimeError("decode did not run to completion")
    except Exception as exc:  # noqa: BLE001 - re-raised; see WindowFailure
        # A bound that fired killed ffmpeg part-way through the window, so the
        # frames written so far are a truncated selection. Discarding them is what
        # keeps the legacy-resume heuristic -- 95% of the expected frames present
        # on disk counts as a finished window -- from ever being satisfied by the
        # wreckage of a killed run.
        partial = list(out_dir.glob("f_*.jpg"))
        for frame in partial:
            frame.unlink(missing_ok=True)
        if not keep_segments:
            shutil.rmtree(raw_dir, ignore_errors=True)
        raise WindowFailure(
            f"window {window['index']}: {exc}"
            + (f" [{len(partial)} partial frames discarded]" if partial else ""),
            index=window["index"],
            frames_invalidated=True,
            kind=getattr(exc, "kind", "error"),
        ) from exc
    t_decode_gate = time.time() - t0

    # ffmpeg can exit zero on a short window (a truncated segment, a playlist that
    # ends early), and that shortfall reaches detect as "fewer frames to look at"
    # with nothing to distinguish it from a quiet stretch of the meeting. Not
    # fatal, because the final window of a clip is legitimately short, but it is
    # the one number worth reading if a vote goes missing.
    frames_expected = round((window["end"] - window["begin"]) * fps)
    if frames_expected and gate["sampled"] < 0.9 * frames_expected:
        print(
            f"  window {window['index']:03d} SHORT: sampled {gate['sampled']} frames "
            f"where ~{frames_expected} were expected for a "
            f"{window['end'] - window['begin']:.0f}s window at {fps:g} fps; "
            f"ffmpeg exited 0, so this is a short source, not a timeout",
            file=sys.stderr,
        )

    records = [
        {
            "frame": str(out_dir / f"f_{n:05d}.jpg"),
            "video_timestamp": round(frame_timestamp(n, playlist_t0, fps), 2),
        }
        for n in gate["written"]
    ]

    if not keep_segments:
        shutil.rmtree(raw_dir, ignore_errors=True)

    disk_guard.require_space(f"{stage}:post")
    record = {
        **base,
        "bytes_downloaded": downloaded,
        "resumed": False,
        "pipeline": PIPELINE_VERSION,
        "gate_draft": list(draft),
        "frame_count": len(records),
        "frames": records,
        "frames_sampled": gate["sampled"],
        "frames_expected": frames_expected,
        "frames_gated": len(gate["hits"]),
        "frames_halo": len(records) - len(gate["hits"]),
        "gate_candidates": gate["candidates"],
        "gate_halo_seconds": halo_seconds,
        # Frames held in memory at once. This is the halo window, not the
        # window length, and is the number to watch if a clip ever grows.
        "gate_ring_frames": gate["ring_frames"],
        "timing": {
            "download": round(t_download, 2),
            "decode_gate": round(t_decode_gate, 2),
            "total": round(time.time() - t_start, 2),
        },
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2))
    return record


# --- reporting -------------------------------------------------------------

def merge_window_records(
    previous: list[dict], results: list[dict], failures: list[dict]
) -> list[dict]:
    """Combine this run's windows with the manifest already on disk.

    The merge exists because a coverage run adds windows to whatever the votable
    run produced, and detect reads one manifest that must name every extracted
    frame.

    The subtraction is the part that matters. A window this run began
    re-extracting and then failed has a partial frame set on disk now, so the
    entry describing the old complete set has stopped being true. Detect reads
    the manifest and silently skips frames that are missing, so carrying that
    entry forward would publish a truncated window as a finished one, and a
    truncated window is indistinguishable from a stretch of meeting where nobody
    voted. Dropping it turns a silent data loss into a window the next run has to
    redo.
    """
    invalidated = {f["index"] for f in failures if f.get("frames_invalidated")}
    merged: dict[int, dict] = {
        window["index"]: window
        for window in previous
        if window["index"] not in invalidated
    }
    for record in results:
        merged[record["index"]] = record
    return [merged[i] for i in sorted(merged)]


def summary_table(records: list[dict]) -> str:
    # Decode and gate are a single streaming pass now, so they share a column.
    head = (
        f"{'window':>7} {'span (s)':>15} {'MB':>7} {'dl s':>7} {'dec+gate s':>11} "
        f"{'total s':>8} {'MB/s':>6} {'fr/s':>6} {'sampled':>8} {'kept':>5}"
    )
    lines = [head, "-" * len(head)]
    for r in sorted(records, key=lambda r: r["index"]):
        t = r.get("timing") or {}
        total = t.get("total") or 0.0
        mb = r["bytes_downloaded"] / 1e6
        sampled = r.get("frames_sampled") or 0
        lines.append(
            f"{'w%03d' % r['index']:>7} "
            f"{f'{r["begin"]:.0f}-{r["end"]:.0f}':>15} "
            f"{mb:>7.1f} {t.get('download', 0.0):>7.1f} "
            f"{t.get('decode_gate', 0.0):>11.1f} {total:>8.1f} "
            f"{(mb / total if total else 0):>6.2f} "
            f"{(sampled / total if total else 0):>6.1f} "
            f"{sampled:>8} {r['frame_count']:>5}"
            + ("  (resumed)" if r.get("resumed") else "")
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument(
        "--lead", type=int, default=60, help="seconds of pre-roll before each chapter"
    )
    parser.add_argument(
        "--max-window",
        type=int,
        default=900,
        help="split merged ranges into pieces this long",
    )
    parser.add_argument("--keep-segments", action="store_true")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="re-download and re-decode windows that already have frames",
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="stop after N windows (debugging)"
    )
    parser.add_argument(
        "--window-workers",
        type=int,
        default=WINDOW_WORKERS,
        help="windows to extract concurrently; download is network bound and "
        "decode is CPU bound, so they overlap well",
    )
    parser.add_argument(
        "--max-sockets",
        type=int,
        default=MAX_SOCKETS,
        help="hard cap on in-flight CDN requests across all windows",
    )
    parser.add_argument(
        "--gate-draft-height",
        type=int,
        default=GATE_DRAFT[1],
        help="height of the draft decode used for the cheap gate tier; 0 gates "
        "every frame at full resolution instead",
    )
    parser.add_argument(
        "--gate-halo",
        type=float,
        default=GATE_HALO_SECONDS,
        help="seconds of frames to keep either side of every gate hit, so the "
        "detect stage can still widen a vote cluster onto its neighbours",
    )
    parser.add_argument(
        "--gate-margin-dark",
        type=float,
        default=GATE_MARGIN_DARK,
        help="how far below the real dark-fraction thresholds the gate tier may "
        "still nominate a frame; widen to be safer, never narrow",
    )
    parser.add_argument(
        "--gate-margin-sat",
        type=float,
        default=GATE_MARGIN_SAT,
        help="same, for the saturation thresholds",
    )
    parser.add_argument(
        "--decode-stall-timeout",
        type=float,
        default=DECODE_STALL_TIMEOUT,
        help="kill the window's ffmpeg if it produces no output for this many "
        "seconds; measures inactivity, so it does not scale with the window",
    )
    parser.add_argument(
        "--decode-deadline-multiplier",
        type=float,
        default=DECODE_DEADLINE_MULTIPLIER,
        help="overall ffmpeg deadline as a multiple of the media duration the "
        f"window covers, with a {DECODE_DEADLINE_FLOOR:.0f}s floor; catches a "
        "decode that makes real but endless progress",
    )
    parser.add_argument(
        "--cover",
        action="append",
        default=[],
        metavar="BEGIN-END",
        help=(
            "extract an explicit second range instead of the votable cuepoint "
            "windows; repeatable. Used to audit the stretches the votable "
            "filter skips, so 'no vote there' is a measurement not an assumption."
        ),
    )
    args = parser.parse_args()

    global LIMITER
    LIMITER = CdnLimiter(args.max_sockets)

    cover_ranges: list[tuple[float, float]] = []
    for spec in args.cover:
        begin, _, end = spec.partition("-")
        try:
            cover_ranges.append((float(begin), float(end)))
        except ValueError:
            raise SystemExit(f"bad --cover range {spec!r}; expected BEGIN-END in seconds")

    run_started = time.time()
    internal0, passport0 = disk_guard.require_space("extract:start")
    print(disk_guard.report("extract:start"))

    catalog_path = disk_guard.work_dir("metadata") / f"clips_{args.year}.json"
    if not catalog_path.exists():
        raise SystemExit(f"missing catalog {catalog_path}; run catalog_granicus.py first")
    catalog = json.loads(catalog_path.read_text())
    clips = {c["clip_id"]: c for c in catalog["clips"]}
    if args.clip not in clips:
        raise SystemExit(f"clip {args.clip} not in {catalog_path}")
    clip = clips[args.clip]
    if not clip.get("hls_url"):
        raise SystemExit(f"clip {args.clip} has no HLS url")

    t0 = time.time()
    seg_base, names, starts = load_chunklist(clip["hls_url"])
    chunklist_seconds = time.time() - t0
    duration = starts[-1] + 2.0
    print(f"clip {args.clip}: {len(names)} segments, ~{duration/3600:.2f} h")

    ranges = votable_ranges(clip["agenda"], args.lead, duration)
    votable_window_count = len(chunk_ranges(ranges, args.max_window))
    if cover_ranges:
        ranges = [
            {
                "begin": max(0.0, begin),
                "end": min(float(end), duration),
                "meta_ids": ["coverage"],
            }
            for begin, end in cover_ranges
        ]
    windows = chunk_ranges(ranges, args.max_window)
    for i, window in enumerate(windows):
        # Coverage windows are numbered above the votable ones so both sets can
        # live side by side in frames/{clip}/ without clobbering each other.
        window["index"] = (1000 + i) if cover_ranges else i
    if args.limit:
        windows = windows[: args.limit]

    covered = sum(w["end"] - w["begin"] for w in windows)
    print(
        f"{len(ranges)} {'explicit coverage' if cover_ranges else 'merged votable'} "
        f"ranges -> {len(windows)} windows, "
        f"{covered/3600:.2f} h of video, ~{int(covered*args.fps)} frames at {args.fps} fps"
    )
    # Only the height selects the DCT reduction; the width is carried for
    # reporting, so derive it at the 16:9 of the source rather than assuming 2:1
    # and printing a resolution that is never decoded.
    draft = (
        (round(args.gate_draft_height * 16 / 9), args.gate_draft_height)
        if args.gate_draft_height
        else GATE_DRAFT
    )
    print(
        f"{args.window_workers} windows at a time, {DOWNLOAD_WORKERS} downloads each, "
        f"socket cap {args.max_sockets}; cheap gate tier "
        + (
            f"draft decode to {draft[0]}x{draft[1]}"
            if args.gate_draft_height
            else "disabled (full-resolution gate on every frame)"
        )
        + f", keeping +/-{args.gate_halo:.0f}s around each gate hit"
    )
    print(
        f"decode bounds: {args.decode_stall_timeout:.0f}s without output, or "
        f"{args.decode_deadline_multiplier:g}x the media duration overall "
        f"(floor {DECODE_DEADLINE_FLOOR:.0f}s); either one kills ffmpeg's whole "
        f"process group and fails the window rather than keeping partial frames"
    )

    raw_root = disk_guard.work_dir("raw", args.clip)
    frames_root = disk_guard.work_dir("frames", args.clip)

    results: list[dict] = []
    failures: list[dict] = []
    peak_passport_used = passport0.used_gib
    min_internal_free = internal0.free_gib
    disk_error: disk_guard.DiskGuardError | None = None
    lock = threading.Lock()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, args.window_workers)
    ) as pool:
        futures = {
            pool.submit(
                extract_window,
                window, seg_base, names, starts, raw_root, frames_root, args.fps,
                args.keep_segments, not args.no_resume, draft,
                not args.gate_draft_height,
                (args.gate_margin_dark, args.gate_margin_sat),
                args.gate_halo,
                stall_timeout=args.decode_stall_timeout,
                deadline_multiplier=args.decode_deadline_multiplier,
            ): window
            for window in windows
        }
        for future in concurrent.futures.as_completed(futures):
            window = futures[future]
            try:
                record = future.result()
            except disk_guard.DiskGuardError as exc:
                disk_error = exc
                for pending in futures:
                    pending.cancel()
                continue
            except concurrent.futures.CancelledError:
                continue
            except Exception as exc:  # noqa: BLE001 - one bad window must not sink the run
                invalidated = bool(getattr(exc, "frames_invalidated", False))
                failures.append({
                    "index": window["index"],
                    "error": str(exc),
                    "kind": getattr(exc, "kind", "error"),
                    # Read below, where the manifest is merged.
                    "frames_invalidated": invalidated,
                })
                print(
                    f"  window {window['index']:03d} FAILED: {exc}"
                    + ("; its frames on disk are now partial and any earlier "
                       "manifest entry for it is being dropped" if invalidated else ""),
                    file=sys.stderr,
                )
                continue
            with lock:
                results.append(record)
                internal = disk_guard.internal_usage()
                passport = disk_guard.passport_usage()
                peak_passport_used = max(peak_passport_used, passport.used_gib)
                min_internal_free = min(min_internal_free, internal.free_gib)
                timing = record.get("timing") or {}
                print(
                    f"  window {record['index']:03d} "
                    f"{record['begin']:.0f}-{record['end']:.0f}s "
                    f"segs {record['segment_first']}-{record['segment_last']} "
                    f"{record['bytes_downloaded']/1e6:.0f} MB -> "
                    f"{record.get('frames_sampled') or 0} sampled, "
                    f"{record['frame_count']} kept "
                    f"in {timing.get('total', 0.0):.1f}s"
                    + (" (resumed)" if record.get("resumed") else "")
                )

    if disk_error is not None:
        raise disk_error

    out = frames_root / "windows.json"
    # A coverage run adds windows to whatever the votable run already produced;
    # the detect stage reads one manifest and must see every extracted frame.
    previous = json.loads(out.read_text()).get("windows", []) if out.exists() else []
    results = merge_window_records(previous, results, failures)

    wall = time.time() - run_started
    total_bytes = sum(r["bytes_downloaded"] for r in results)
    total_sampled = sum(r.get("frames_sampled") or 0 for r in results)
    window_seconds = sum((r.get("timing") or {}).get("total", 0.0) for r in results)

    manifest = {
        "clip_id": args.clip,
        "year": args.year,
        "date": clip.get("date"),
        "hls_url": clip["hls_url"],
        "duration": round(duration, 2),
        "fps": args.fps,
        "lead": args.lead,
        "pipeline": PIPELINE_VERSION,
        "gate_draft": list(draft) if args.gate_draft_height else None,
        "windows": results,
        "window_total": max(len(windows), votable_window_count),
        "failed_windows": failures,
        # False means at least one window is missing from `windows` on purpose.
        # A consumer that reads this manifest as the inventory of the meeting must
        # check it, or it is reading an incomplete meeting as a complete one.
        "complete": not failures,
        "frame_total": sum(r["frame_count"] for r in results),
        "frames_sampled_total": total_sampled,
        "frames_gate_hits_total": sum(r.get("frames_gated") or 0 for r in results),
        "frames_gib": round(disk_guard.dir_size_gib(frames_root), 3),
        "peak_passport_used_gib": round(peak_passport_used, 2),
        "min_internal_free_gib": round(min_internal_free, 2),
    }
    out.write_text(json.dumps(manifest, indent=2))
    print(
        f"wrote {out}: {manifest['frame_total']} gated frames of "
        f"{total_sampled} sampled, {manifest['frames_gib']} GiB"
    )

    fresh = [r for r in results if not r.get("resumed")]
    if fresh:
        print()
        print(summary_table(fresh))
    timing = {
        "wall_seconds": round(wall, 2),
        "chunklist_seconds": round(chunklist_seconds, 2),
        "window_seconds_sum": round(window_seconds, 2),
        "concurrency_speedup": round(window_seconds / wall, 2) if wall else 0.0,
        "window_workers": args.window_workers,
        "download_workers": DOWNLOAD_WORKERS,
        "socket_cap": args.max_sockets,
        "socket_low_water": LIMITER.low_water,
        "cdn_throttle_events": LIMITER.throttle_events,
        "gate_draft": list(draft) if args.gate_draft_height else None,
        "gate_margins": [args.gate_margin_dark, args.gate_margin_sat],
        "gate_halo_seconds": args.gate_halo,
        "gate_candidates": sum(r.get("gate_candidates") or 0 for r in fresh),
        "frames_gate_hits": sum(r.get("frames_gated") or 0 for r in fresh),
        # Frames resident in memory at the high-water mark of any window. Flat
        # in the length of the clip by construction; watch it anyway.
        "gate_ring_frames_max": max(
            (r.get("gate_ring_frames") or 0 for r in fresh), default=0
        ),
        "windows_extracted": len(fresh),
        "windows_resumed": len(results) - len(fresh),
        "windows_failed": len(failures),
        "windows_timed_out": sum(
            1 for f in failures if f.get("kind") in {"stall", "deadline", "exit", "timeout"}
        ),
        "decode_stall_timeout": args.decode_stall_timeout,
        "decode_deadline_multiplier": args.decode_deadline_multiplier,
        "bytes_downloaded": total_bytes,
        "mb_downloaded": round(total_bytes / 1e6, 1),
        "mb_per_second": round(total_bytes / 1e6 / wall, 2) if wall else 0.0,
        "frames_sampled": total_sampled,
        "frames_written": manifest["frame_total"],
        "frames_per_second": round(total_sampled / wall, 1) if wall else 0.0,
        "frames_gib_on_disk": manifest["frames_gib"],
        "download_seconds_sum": round(
            sum((r.get("timing") or {}).get("download", 0.0) for r in results), 2
        ),
        # Decode and gate are one streaming pass; they cannot be separated.
        "decode_gate_seconds_sum": round(
            sum((r.get("timing") or {}).get("decode_gate", 0.0) for r in results), 2
        ),
        "per_window": [
            {
                "index": r["index"],
                "seconds": (r.get("timing") or {}).get("total", 0.0),
                "download_seconds": (r.get("timing") or {}).get("download", 0.0),
                "decode_gate_seconds": (r.get("timing") or {}).get("decode_gate", 0.0),
                "mb": round(r["bytes_downloaded"] / 1e6, 1),
                "frames_sampled": r.get("frames_sampled"),
                "frames_written": r["frame_count"],
            }
            for r in sorted(fresh, key=lambda r: r["index"])
        ],
    }
    timing_path = merge_timing(args.clip, "extract", timing)
    print(
        f"\nextract: {wall:.1f}s wall, {total_bytes/1e6:.0f} MB at "
        f"{timing['mb_per_second']:.2f} MB/s, {total_sampled} frames sampled at "
        f"{timing['frames_per_second']:.1f} frames/s, "
        f"{timing['concurrency_speedup']:.2f}x from {args.window_workers} windows in parallel"
    )
    if LIMITER.throttle_events:
        print(
            f"cdn: {LIMITER.throttle_events} throttle/timeout events, "
            f"socket cap fell to {LIMITER.low_water}",
            file=sys.stderr,
        )
    print(f"wrote {timing_path}")

    if failures:
        print(
            f"{len(failures)} of {len(windows)} windows failed; rerun the same command "
            f"to resume the rest",
            file=sys.stderr,
        )
    print(disk_guard.report("extract:done"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
