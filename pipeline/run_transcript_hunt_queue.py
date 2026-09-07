#!/usr/bin/env python3
"""Batch transcript vote-hunts for years without Voting Results boards.

Sample audits of 2019 / 2021 / 2023 found the bright gate filled with
closed-session splash cards and agenda decks; OCR never saw "Voting Results".
Those meetings are oral / roll-call — use caption (or ASR) cues instead.

    .venv/bin/python pipeline/run_transcript_hunt_queue.py --years 2019-2023 --captions-only --no-frames
    .venv/bin/python pipeline/run_transcript_hunt_queue.py --years 2018-2023 --after-date 2018-05-01 --no-frames --workers 3
    .venv/bin/python pipeline/run_transcript_hunt_queue.py --queue metadata/reprocess_2024_asr_zeros.json --no-frames
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_granicus as catalog
import disk_guard
from prepare_full_archive import CLOSED_SESSION_SKIPS

REPO = disk_guard.REPO_ROOT
META = disk_guard.work_dir("metadata")
PYTHON = REPO / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)


def votable_clips(years: set[int], after_date: str | None = None) -> list[dict]:
    clips: list[dict] = []
    for year in sorted(years):
        path = META / f"clips_{year}.json"
        if not path.is_file():
            continue
        for clip in json.loads(path.read_text()).get("clips") or []:
            votable = sum(1 for a in (clip.get("agenda") or []) if a.get("votable"))
            if not votable:
                continue
            date = str(clip.get("date") or "")
            if after_date and date and date < after_date:
                continue
            clips.append(
                {
                    "clip_id": str(clip["clip_id"]),
                    "year": year,
                    "date": clip.get("date"),
                }
            )
    clips.sort(key=lambda c: (c["year"], c.get("date") or "", int(c["clip_id"])))
    return clips


def load_queue_file(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    clips = payload.get("clips") if isinstance(payload, dict) else payload
    out: list[dict] = []
    for item in clips or []:
        out.append(
            {
                "clip_id": str(item.get("clip_id") or item.get("clip")),
                "year": int(item["year"]),
                "date": item.get("date"),
            }
        )
    return out


def should_skip(clip_id: str, skip_existing: bool) -> tuple[bool, str]:
    if clip_id in CLOSED_SESSION_SKIPS:
        return True, "closed-session"
    if not skip_existing:
        return False, ""
    sidecar = META / f"votes_{clip_id}_transcript_hunt.json"
    if not sidecar.is_file():
        return False, ""
    try:
        prior = json.loads(sidecar.read_text())
    except (OSError, ValueError):
        prior = {}
    hits = int(prior.get("vote_hits") or 0)
    source = str(prior.get("cue_source") or "")
    # Older sidecars omit cue_source; any positive hit count is enough to skip.
    if hits > 0:
        return True, f"existing hits={hits} source={source or 'unknown'}"
    return False, f"retry prior empty hunt hits=0 source={source or '?'}"


def hunt_one(item: dict, captions_only: bool, no_frames: bool) -> tuple[str, int]:
    clip_id = item["clip_id"]
    year = int(item["year"])
    cmd = [
        str(PYTHON),
        str(REPO / "pipeline" / "hunt_votes_from_transcript.py"),
        "--clip",
        clip_id,
        "--year",
        str(year),
    ]
    if captions_only:
        cmd.append("--captions-only")
    if no_frames:
        cmd.append("--no-frames")
    print(f"START {clip_id} {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO))
    return clip_id, proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", default="2019-2023")
    parser.add_argument(
        "--after-date",
        default=None,
        help="only clips on/after this ISO date (e.g. 2018-05-01 for oral era)",
    )
    parser.add_argument(
        "--queue",
        default=None,
        help="optional JSON queue with clips[{clip_id,year}] instead of year scan",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--from-clip", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--captions-only", action="store_true")
    parser.add_argument("--no-frames", action="store_true")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="skip clips that already have a transcript hunt with vote hits",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="parallel Whisper hunts (keep low; disk/CPU heavy)",
    )
    args = parser.parse_args()

    if args.queue:
        queue = load_queue_file(Path(args.queue))
        label = args.queue
    else:
        years = set(catalog.parse_years_arg(args.years))
        queue = votable_clips(years, after_date=args.after_date)
        label = args.years + (f" after {args.after_date}" if args.after_date else "")
    if args.from_clip:
        clipped = []
        seen = False
        for item in queue:
            if str(item["clip_id"]) == str(args.from_clip):
                seen = True
            if seen:
                clipped.append(item)
        queue = clipped
    if args.limit:
        queue = queue[: args.limit]

    print(f"transcript hunt queue: {len(queue)} clips ({label}) workers={args.workers}")
    work: list[dict] = []
    ok = fail = skip = 0
    for i, item in enumerate(queue, 1):
        clip_id = item["clip_id"]
        skip_it, reason = should_skip(clip_id, args.skip_existing)
        if skip_it:
            print(f"[{i}/{len(queue)}] skip {reason} {clip_id}")
            skip += 1
            continue
        if reason.startswith("retry"):
            print(f"[{i}/{len(queue)}] {reason} {clip_id}")
        if args.dry_run:
            print(f"[{i}/{len(queue)}] dry-run {clip_id}")
            continue
        work.append(item)

    if args.dry_run:
        print(f"done ok={ok} fail={fail} skip={skip} dry_run=True")
        return 0

    workers = max(1, int(args.workers))
    if workers == 1:
        for i, item in enumerate(work, 1):
            clip_id, rc = hunt_one(item, args.captions_only, args.no_frames)
            if rc == 0:
                ok += 1
            else:
                fail += 1
                print(f"  FAILED {clip_id} exit={rc}", file=sys.stderr)
            print(f"progress {i}/{len(work)} ok={ok} fail={fail}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(hunt_one, item, args.captions_only, args.no_frames): item
                for item in work
            }
            done = 0
            for fut in as_completed(futures):
                clip_id, rc = fut.result()
                done += 1
                if rc == 0:
                    ok += 1
                else:
                    fail += 1
                    print(f"  FAILED {clip_id} exit={rc}", file=sys.stderr)
                print(f"progress {done}/{len(work)} ok={ok} fail={fail}", flush=True)

    print(f"done ok={ok} fail={fail} skip={skip} dry_run={args.dry_run}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
