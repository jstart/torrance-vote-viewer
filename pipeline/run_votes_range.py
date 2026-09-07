#!/usr/bin/env python3
"""Extract then detect every votable meeting from a year range (default 2016–today).

Rebuilds the Passport inventory for the range, then for each clip still needing
frames: extract_vote_windows → detect_and_parse_votes. Clips that already have
frames but no votes_*.json go straight to detect.

    .venv/bin/python pipeline/run_votes_range.py --years 2016-2026 --dry-run
    .venv/bin/python pipeline/run_votes_range.py --years 2016-2026
    .venv/bin/python pipeline/run_votes_range.py --years 2016-2026 --limit 2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_granicus as catalog
import disk_guard
import prepare_full_archive as prep
import roster as roster_mod

REPO = disk_guard.REPO_ROOT
PYTHON = REPO / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)

LOG_DIR = disk_guard.PASSPORT_ROOT / "logs"
META = disk_guard.PASSPORT_ROOT / "metadata"

# Published / hand-verified detect outputs — never overwrite canonical votes_*.json.
# Re-extract of frames is allowed; detect must use a non-canonical --out or skip.
DETECT_PROTECT = frozenset({"14798", "14817", "14821"})


def needs_unverified(date: str | None) -> bool:
    if not date:
        return True
    try:
        return not roster_mod.era_for(date).verified
    except roster_mod.UnknownRosterEra:
        return True


def has_canonical_detect(clip_id: str) -> bool:
    return (META / f"votes_{clip_id}.json").is_file()


def rebuild_inventory(years: list[int]) -> dict:
    inventory = prep.build_inventory(years)
    prep.write_json(prep.INVENTORY_PATH, inventory)
    prep.write_json(
        prep.QUEUE_PATH,
        {
            "generated_at": inventory["generated_at"],
            "extract_queue": inventory["extract_queue"],
            "detect_queue": inventory["detect_queue"],
            "totals": inventory["totals"],
            "years": years,
        },
    )
    return inventory


def run_cmd(cmd: list[str], *, dry_run: bool) -> int:
    print("  $ " + " ".join(cmd), flush=True)
    if dry_run:
        return 0
    disk_guard.require_space(f"votes_range_{cmd[cmd.index('--clip') + 1]}")
    return subprocess.run(cmd, cwd=str(REPO)).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years",
        type=str,
        default="2016-2026",
        help="year list/ranges (default 2016-2026)",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="only run extract_vote_windows; skip detect",
    )
    parser.add_argument(
        "--detect-only",
        action="store_true",
        help="only run detect on the current detect_queue",
    )
    parser.add_argument(
        "--parser",
        choices=("auto", "vision", "ocr"),
        default="ocr",
    )
    parser.add_argument(
        "--from-clip",
        type=str,
        default=None,
        help="skip until this clip_id (inclusive) in the combined work list",
    )
    parser.add_argument(
        "--force-detect",
        action="store_true",
        help="re-run detect even when metadata/votes_{clip}.json already exists "
        "(still never overwrites protected published clips 14798/14817/14821)",
    )
    args = parser.parse_args()
    if args.extract_only and args.detect_only:
        parser.error("use only one of --extract-only / --detect-only")

    if not disk_guard.passport_available():
        print("Passport not mounted", file=sys.stderr)
        return 1

    years = catalog.parse_years_arg(args.years)
    print(f"scope years={years}")
    inventory = rebuild_inventory(years)
    print("inventory totals:", json.dumps(inventory["totals"]))
    for y, bucket in inventory["by_year"].items():
        if int(y) not in years:
            continue
        print(
            f"  {y}: votable={bucket['votable_meetings']} "
            f"extracted={bucket['extracted']} detected={bucket['detected']} "
            f"q_extract={bucket['queue_extract']} q_detect={bucket['queue_detect']} "
            f"skipped={bucket['skipped']}"
        )

    # Combined work list: extract-needed first (chrono), then detect-only.
    extract_ids = {str(q["clip_id"]) for q in inventory["extract_queue"]}
    work: list[dict] = []
    for q in inventory["extract_queue"]:
        work.append({**q, "need_extract": True, "need_detect": not args.extract_only})
    if not args.extract_only:
        for q in inventory["detect_queue"]:
            if str(q["clip_id"]) in extract_ids:
                continue
            work.append({**q, "need_extract": False, "need_detect": True})

    if args.detect_only:
        work = [w for w in work if w["need_detect"] and not w["need_extract"]]
        # Also include detect_queue explicitly rebuilt
        work = [
            {**q, "need_extract": False, "need_detect": True}
            for q in inventory["detect_queue"]
        ]

    if args.from_clip:
        clipped = []
        seen = False
        for w in work:
            if str(w["clip_id"]) == str(args.from_clip):
                seen = True
            if seen:
                clipped.append(w)
        work = clipped
    if args.limit:
        work = work[: args.limit]

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"votes_range_{years[0]}_{years[-1]}_{time.strftime('%Y%m%d_%H%M%S')}.log"
    print(f"work items: {len(work)}")
    print(f"log: {log_path}")

    ok = fail = skip = 0
    with log_path.open("a") as log:
        for i, item in enumerate(work, 1):
            clip_id = str(item["clip_id"])
            year = int(item["year"])
            date = item.get("date")
            if clip_id in prep.CLOSED_SESSION_SKIPS:
                msg = f"[{i}/{len(work)}] skip closed-session {clip_id}"
                print(msg, flush=True)
                log.write(msg + "\n")
                skip += 1
                continue

            print(
                f"[{i}/{len(work)}] clip={clip_id} year={year} date={date} "
                f"extract={item['need_extract']} detect={item['need_detect']}",
                flush=True,
            )
            log.write(
                f"{time.strftime('%H:%M:%S')} clip={clip_id} "
                f"extract={item['need_extract']} detect={item['need_detect']}\n"
            )
            log.flush()

            if item["need_extract"]:
                extract_ok = False
                for attempt in range(1, 4):
                    cmd = [
                        str(PYTHON),
                        str(REPO / "pipeline" / "extract_vote_windows.py"),
                        "--clip",
                        clip_id,
                        "--year",
                        str(year),
                    ]
                    # Later attempts: fewer CDN sockets so archive streams drop
                    # fewer individual segments under concurrency.
                    if attempt > 1:
                        cmd.extend(["--max-sockets", "8", "--window-workers", "1"])
                        print(f"  extract retry {attempt}/3", flush=True)
                        log.write(f"  extract retry {attempt}/3\n")
                    rc = run_cmd(cmd, dry_run=args.dry_run)
                    if rc == 0:
                        extract_ok = True
                        break
                if not extract_ok:
                    # Partial frames may still be on disk from successful windows.
                    frames_root = prep.frames_root_for(clip_id)
                    has_frames = next(frames_root.rglob("*.jpg"), None) is not None
                    print(
                        f"  EXTRACT FAILED after retries"
                        + ("; continuing to detect on partial frames" if has_frames else ""),
                        file=sys.stderr,
                    )
                    log.write(
                        "  EXTRACT FAILED after retries"
                        + ("; partial detect\n" if has_frames else "\n")
                    )
                    if not has_frames:
                        fail += 1
                        continue
                    # Fall through to detect with whatever windows succeeded.

            if item["need_detect"]:
                if clip_id in DETECT_PROTECT:
                    msg = (
                        f"  skip detect {clip_id}: protected published clip "
                        f"(re-extract frames only; never overwrite votes_{clip_id}.json)"
                    )
                    print(msg, flush=True)
                    log.write(msg + "\n")
                elif has_canonical_detect(clip_id) and not args.force_detect:
                    msg = f"  skip detect {clip_id}: votes_{clip_id}.json already exists"
                    print(msg, flush=True)
                    log.write(msg + "\n")
                else:
                    cmd = [
                        str(PYTHON),
                        str(REPO / "pipeline" / "detect_and_parse_votes.py"),
                        "--clip",
                        clip_id,
                        "--year",
                        str(year),
                        "--parser",
                        args.parser,
                    ]
                    if needs_unverified(date):
                        cmd.append("--allow-unverified-roster")
                    rc = run_cmd(cmd, dry_run=args.dry_run)
                    if rc != 0:
                        fail += 1
                        print(f"  DETECT FAILED exit={rc}", file=sys.stderr)
                        log.write(f"  DETECT FAILED exit={rc}\n")
                        continue

            ok += 1
            log.write("  ok\n")
            log.flush()

    print(f"done ok={ok} fail={fail} skip={skip} dry_run={args.dry_run}")
    print(f"log: {log_path}")
    # Refresh inventory so queues reflect progress.
    if not args.dry_run:
        rebuild_inventory(years)
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
