#!/usr/bin/env python3
"""Precompute ±30s local-whisper transcripts for review candidates.

Granicus captions.vtt is empty for most Torrance meetings. The review UI can
ASR on demand, but serial per-card transcription is too slow for a full queue.
This walks every detect candidate, skips windows that already have Granicus
cues or an asr_cache hit, and writes Passport metadata/asr_cache/{clip}/*.json.

Audio windows are clamped to the first agenda cuepoint (same skip as extract).

    .venv/bin/python pipeline/preprocess_asr.py
    .venv/bin/python pipeline/preprocess_asr.py --limit 5
    .venv/bin/python pipeline/preprocess_asr.py --clip 14632
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard
import review_server
import transcribe_window as asr_mod

PAD = 30.0


def granicus_has_cues(clip: dict) -> bool:
    url = clip.get("captions_url") or ""
    if not url:
        return False
    req = urllib.request.Request(url, headers={"User-Agent": "TorranceAsrPreprocess/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    return bool(review_server.parse_vtt(raw))


def unique_windows(
    candidates: list[dict], clip_filter: str | None
) -> list[tuple[str, float, float, float, dict]]:
    """Return (clip_id, t, start, end, clip) unique by (clip, start, end)."""
    index = review_server.load_clip_index()
    seen: set[tuple[str, int, int]] = set()
    out: list[tuple[str, float, float, float, dict]] = []
    for row in candidates:
        clip_id = str(row.get("clip_id") or "")
        if clip_filter and clip_id != clip_filter:
            continue
        clip = index.get(clip_id)
        if not clip or not clip.get("hls_url"):
            continue
        try:
            t = float(row.get("video_timestamp") or 0)
        except (TypeError, ValueError):
            continue
        start, end, _ = asr_mod.clamped_audio_window(t, PAD, clip.get("agenda"))
        key = (clip_id, int(start), int(end))
        if key in seen:
            continue
        seen.add(key)
        out.append((clip_id, t, start, end, clip))
    out.sort(key=lambda x: (x[0], x[2]))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", help="only this clip_id")
    parser.add_argument("--limit", type=int, default=0, help="max windows to process")
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-run even when asr_cache exists",
    )
    parser.add_argument(
        "--skip-caption-check",
        action="store_true",
        help="do not probe Granicus VTT (treat all as needing ASR)",
    )
    args = parser.parse_args()

    if not disk_guard.passport_available():
        print("Passport not mounted", file=sys.stderr)
        return 1

    candidates = review_server.load_candidates()
    windows = unique_windows(candidates, args.clip)
    print(f"unique vote windows: {len(windows)}")

    caption_ok: dict[str, bool] = {}
    done = skipped = failed = 0
    t0 = time.time()

    for i, (clip_id, t, start, end, clip) in enumerate(windows, 1):
        if args.limit and done >= args.limit:
            break

        if not args.skip_caption_check:
            if clip_id not in caption_ok:
                caption_ok[clip_id] = granicus_has_cues(clip)
                print(
                    f"  captions {clip_id}: "
                    f"{'granicus ok — skip ASR' if caption_ok[clip_id] else 'empty — will ASR'}"
                )
            if caption_ok[clip_id]:
                skipped += 1
                continue

        cached = asr_mod.load_cached(clip_id, start, end)
        if cached and not args.force:
            skipped += 1
            continue

        label = f"[{i}/{len(windows)}] clip {clip_id} t={t:.0f} window={int(start)}-{int(end)}"
        print(f"{label} …", flush=True)
        try:
            result = asr_mod.transcribe_window(clip, t, PAD, force=args.force)
            n = len(result.get("cues") or [])
            print(f"  -> {n} cues ({result.get('source')})", flush=True)
            done += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL: {exc}", file=sys.stderr, flush=True)
            failed += 1

    elapsed = time.time() - t0
    print(
        f"done: generated={done} skipped={skipped} failed={failed} "
        f"elapsed={elapsed/60:.1f}m"
    )
    return 1 if failed and not done else 0


if __name__ == "__main__":
    raise SystemExit(main())
