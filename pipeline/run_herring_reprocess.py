#!/usr/bin/env python3
"""Re-extract + re-detect clips that failed under archive-pre-2024 with Herring roster.

Reads metadata/reprocess_herring_queue.json (or rebuilds the all-reject set).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard

REPO = disk_guard.REPO_ROOT
META = disk_guard.work_dir("metadata")
PYTHON = REPO / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)
QUEUE = META / "reprocess_herring_queue.json"


def rebuild_queue() -> list[dict]:
    clips: list[dict] = []
    for year in (2016, 2017, 2018):
        cat = json.loads((META / f"clips_{year}.json").read_text())
        for c in cat["clips"]:
            date = c.get("date") or ""
            if date < "2016-07-01" or date > "2018-12-31":
                continue
            votable = sum(1 for a in (c.get("agenda") or []) if a.get("votable"))
            if not votable:
                continue
            path = META / f"votes_{c['clip_id']}.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            accepted = len(data.get("accepted") or [])
            rejected = len(data.get("rejected") or [])
            candidates = data.get("candidates") or (accepted + rejected)
            if candidates > 0 and accepted == 0:
                clips.append(
                    {
                        "clip_id": str(c["clip_id"]),
                        "year": year,
                        "date": date,
                        "rejected": rejected,
                    }
                )
    QUEUE.write_text(json.dumps({"clips": clips}, indent=2))
    return clips


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rebuild-queue", action="store_true")
    parser.add_argument("--from-clip", type=str, default=None)
    parser.add_argument("--skip-extract", action="store_true")
    args = parser.parse_args()

    if args.rebuild_queue or not QUEUE.is_file():
        clips = rebuild_queue()
    else:
        clips = json.loads(QUEUE.read_text()).get("clips") or []

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

    print(f"herring reprocess: {len(clips)} clips", flush=True)
    ok = fail = skip = 0
    for i, item in enumerate(clips, 1):
        clip_id = str(item["clip_id"])
        year = int(item["year"])
        # Skip if a prior run already recovered accepts
        votes_path = META / f"votes_{clip_id}.json"
        if votes_path.exists():
            data = json.loads(votes_path.read_text())
            if len(data.get("accepted") or []) > 0 and data.get("roster_era") == "2016-furey-herring":
                print(f"[{i}/{len(clips)}] skip already recovered {clip_id}", flush=True)
                skip += 1
                continue

        if not args.skip_extract:
            extract_cmd = [
                str(PYTHON),
                str(REPO / "pipeline" / "extract_vote_windows.py"),
                "--clip",
                clip_id,
                "--year",
                str(year),
            ]
            print(f"[{i}/{len(clips)}] {' '.join(extract_cmd)}", flush=True)
            if not args.dry_run:
                disk_guard.require_space(f"herring_extract_{clip_id}")
                proc = subprocess.run(extract_cmd, cwd=str(REPO))
                if proc.returncode != 0:
                    fail += 1
                    print(f"  EXTRACT FAILED exit={proc.returncode}", file=sys.stderr)
                    continue

        detect_cmd = [
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
        print(f"[{i}/{len(clips)}] {' '.join(detect_cmd)}", flush=True)
        if args.dry_run:
            continue
        disk_guard.require_space(f"herring_detect_{clip_id}")
        proc = subprocess.run(detect_cmd, cwd=str(REPO))
        if proc.returncode == 0:
            ok += 1
        else:
            fail += 1
            print(f"  DETECT FAILED exit={proc.returncode}", file=sys.stderr)

    print(f"done ok={ok} fail={fail} skip={skip} dry_run={args.dry_run}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
