#!/usr/bin/env python3
"""Extract + detect a list of gap clips from a JSON queue file.

    .venv/bin/python pipeline/run_gap_queue.py --queue metadata/reprocess_2024_gaps.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard
from prepare_full_archive import CLOSED_SESSION_SKIPS

REPO = disk_guard.REPO_ROOT
PYTHON = REPO / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)

PROTECTED = frozenset({"14798", "14817", "14821"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True, help="JSON with clips:[{clip_id,year}]")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--from-clip", default=None)
    args = parser.parse_args()

    queue_path = Path(args.queue)
    if not queue_path.is_file():
        queue_path = disk_guard.work_dir("metadata") / args.queue
    clips = json.loads(queue_path.read_text()).get("clips") or []
    if args.from_clip:
        clipped = []
        seen = False
        for item in clips:
            if str(item["clip_id"]) == str(args.from_clip):
                seen = True
            if seen:
                clipped.append(item)
        clips = clipped
    if args.limit:
        clips = clips[: args.limit]

    print(f"gap queue: {len(clips)} from {queue_path}")
    ok = fail = skip = 0
    for i, item in enumerate(clips, 1):
        clip_id = str(item["clip_id"])
        year = int(item["year"])
        if clip_id in CLOSED_SESSION_SKIPS or clip_id in PROTECTED:
            print(f"[{i}/{len(clips)}] skip protected/closed {clip_id}")
            skip += 1
            continue
        if not args.skip_extract:
            cmd = [
                str(PYTHON),
                str(REPO / "pipeline" / "extract_vote_windows.py"),
                "--clip",
                clip_id,
                "--year",
                str(year),
            ]
            print(f"[{i}/{len(clips)}] {' '.join(cmd)}", flush=True)
            if not args.dry_run:
                disk_guard.require_space(f"gap_extract_{clip_id}")
                proc = subprocess.run(cmd, cwd=str(REPO))
                if proc.returncode != 0:
                    fail += 1
                    print(f"  EXTRACT FAILED", file=sys.stderr)
                    continue
        cmd = [
            str(PYTHON),
            str(REPO / "pipeline" / "detect_and_parse_votes.py"),
            "--clip",
            clip_id,
            "--year",
            str(year),
            "--parser",
            "ocr",
            "--allow-unverified-roster",
            "--clear-crops",
        ]
        print(f"[{i}/{len(clips)}] {' '.join(cmd)}", flush=True)
        if args.dry_run:
            continue
        disk_guard.require_space(f"gap_detect_{clip_id}")
        proc = subprocess.run(cmd, cwd=str(REPO))
        if proc.returncode == 0:
            ok += 1
        else:
            fail += 1
            print(f"  DETECT FAILED", file=sys.stderr)
    print(f"done ok={ok} fail={fail} skip={skip}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
