#!/usr/bin/env python3
"""Batch oral convert for meetings with transcript-hunt hits and no board votes.

    .venv/bin/python pipeline/run_oral_convert_queue.py --years 2019-2023 --dry-run
    .venv/bin/python pipeline/run_oral_convert_queue.py --years 2018-2024 --after-date 2018-05-01
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_granicus as catalog
import disk_guard
import oral_votes_from_hunt as oral

META = disk_guard.work_dir("metadata")


def queue_clips(years: set[int], after_date: str | None) -> list[dict]:
    out: list[dict] = []
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
            cid = str(clip["clip_id"])
            hunt = META / f"votes_{cid}_transcript_hunt.json"
            if not hunt.is_file():
                continue
            try:
                hits = int(json.loads(hunt.read_text()).get("vote_hits") or 0)
            except (OSError, ValueError):
                hits = 0
            if hits <= 0:
                continue
            out.append({"clip_id": cid, "year": year, "date": date, "hits": hits})
    out.sort(key=lambda c: (c["year"], c.get("date") or "", int(c["clip_id"])))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", default="2019-2023")
    parser.add_argument("--after-date", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-clip", default=None)
    args = parser.parse_args()

    years = set(catalog.parse_years_arg(args.years))
    queue = queue_clips(years, args.after_date)
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

    print(
        f"oral convert queue: {len(queue)} clips ({args.years}"
        + (f" after {args.after_date}" if args.after_date else "")
        + f") dry_run={args.dry_run}"
    )
    ok = skip = fail = empty = 0
    total_events = 0
    for i, item in enumerate(queue, 1):
        try:
            summary = oral.convert_clip(
                item["clip_id"], int(item["year"]), dry_run=args.dry_run
            )
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"[{i}/{len(queue)}] FAIL {item['clip_id']}: {exc}", flush=True)
            continue
        if summary.get("skipped"):
            skip += 1
            print(
                f"[{i}/{len(queue)}] skip {item['clip_id']} "
                f"{summary.get('skipped')} board_acc={summary.get('board_accepted')}",
                flush=True,
            )
            continue
        n = int(summary.get("accepted") or 0)
        total_events += n
        if n == 0:
            empty += 1
        else:
            ok += 1
        absentees = summary.get("absentees") or []
        print(
            f"[{i}/{len(queue)}] {item.get('date')} {item['clip_id']} "
            f"era={summary.get('era')} events={n} absent={absentees}",
            flush=True,
        )
    print(
        f"done ok={ok} empty={empty} skip={skip} fail={fail} "
        f"oral_votes={total_events} dry_run={args.dry_run}"
    )
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
