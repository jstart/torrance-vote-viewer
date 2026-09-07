#!/usr/bin/env python3
"""Publish every votes_*.json listed in a queue file into the consolidated viewer data.

    .venv/bin/python pipeline/publish_queue.py --queue metadata/publish_furey_queue.json
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
PYTHON = REPO / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
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

    print(f"publish queue: {len(clips)}")
    ok = fail = 0
    for i, item in enumerate(clips, 1):
        path = Path(item.get("path") or disk_guard.work_dir("metadata") / f"votes_{item['clip_id']}.json")
        cmd = [
            str(PYTHON),
            str(REPO / "pipeline" / "publish_votes.py"),
            "--input",
            str(path),
        ]
        if args.dry_run:
            cmd.append("--dry-run")
        print(f"[{i}/{len(clips)}] {item.get('date')} {item['clip_id']} acc={item.get('accepted')}", flush=True)
        proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
        if proc.returncode != 0:
            fail += 1
            print(proc.stdout[-500:], file=sys.stderr)
            print(proc.stderr[-500:], file=sys.stderr)
            print(f"  FAILED", file=sys.stderr)
        else:
            ok += 1
            # short summary line
            for line in proc.stdout.splitlines():
                if line.startswith("votes:") or line.startswith("verification:"):
                    print(f"  {line}")
    print(f"done ok={ok} fail={fail} dry_run={args.dry_run}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
