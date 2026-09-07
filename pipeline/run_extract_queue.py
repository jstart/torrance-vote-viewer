#!/usr/bin/env python3
"""Run extract_vote_windows.py for clips in the full-archive extract queue.

Reads Passport metadata/full_archive_extract_queue.json (from
prepare_full_archive.py). Skips known closed-session clips. Resume is the
extract default — already-complete windows are cheap.

    .venv/bin/python pipeline/run_extract_queue.py --dry-run
    .venv/bin/python pipeline/run_extract_queue.py --limit 3
    .venv/bin/python pipeline/run_extract_queue.py --year 2023
    .venv/bin/python pipeline/run_extract_queue.py --years 2016-2026
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_granicus as catalog
import disk_guard
from prepare_full_archive import CLOSED_SESSION_SKIPS, QUEUE_PATH

REPO = disk_guard.REPO_ROOT
PYTHON = REPO / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument(
        "--years",
        type=str,
        default=None,
        help="year list/ranges, e.g. 2016-2026 (overrides --year)",
    )
    parser.add_argument(
        "--from-clip",
        type=str,
        default=None,
        help="skip queue entries until this clip_id (inclusive)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="pass --no-resume to extract_vote_windows.py",
    )
    args = parser.parse_args()

    if not QUEUE_PATH.is_file():
        print(
            f"missing {QUEUE_PATH}\n"
            "Run: .venv/bin/python pipeline/prepare_full_archive.py --years 2016-2026",
            file=sys.stderr,
        )
        return 1

    payload = json.loads(QUEUE_PATH.read_text())
    queue = payload.get("extract_queue") or []
    if args.years:
        years = set(catalog.parse_years_arg(args.years))
        queue = [q for q in queue if int(q["year"]) in years]
    elif args.year:
        queue = [q for q in queue if int(q["year"]) == args.year]
    if args.from_clip:
        clipped = []
        seen = False
        for q in queue:
            if str(q["clip_id"]) == str(args.from_clip):
                seen = True
            if seen:
                clipped.append(q)
        queue = clipped
    if args.limit:
        queue = queue[: args.limit]

    print(f"extract queue: {len(queue)} clips")
    ok = fail = skip = 0
    for i, item in enumerate(queue, 1):
        clip_id = str(item["clip_id"])
        year = int(item["year"])
        if clip_id in CLOSED_SESSION_SKIPS:
            print(f"[{i}/{len(queue)}] skip closed-session {clip_id}")
            skip += 1
            continue
        cmd = [
            str(PYTHON),
            str(REPO / "pipeline" / "extract_vote_windows.py"),
            "--clip",
            clip_id,
            "--year",
            str(year),
        ]
        if args.no_resume:
            cmd.append("--no-resume")
        print(f"[{i}/{len(queue)}] {' '.join(cmd)}", flush=True)
        if args.dry_run:
            continue
        disk_guard.require_space(f"extract_queue_{clip_id}")
        proc = subprocess.run(cmd, cwd=str(REPO))
        if proc.returncode == 0:
            ok += 1
        else:
            fail += 1
            print(f"  FAILED exit={proc.returncode}", file=sys.stderr)

    print(f"done ok={ok} fail={fail} skip={skip} dry_run={args.dry_run}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
