#!/usr/bin/env python3
"""Re-parse existing board crops and rewrite votes_{clip}.json accepted/rejected.

Faster than full extract+detect when crops already exist (e.g. after a Format C
result-line fix). Does not touch dense frames.

    .venv/bin/python pipeline/reparse_vote_crops.py --clips 13176,13220
    .venv/bin/python pipeline/reparse_vote_crops.py --herring-all-reject
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import detect_and_parse_votes as detect
import disk_guard
import roster as roster_mod
from PIL import Image

META = disk_guard.work_dir("metadata")


def herring_all_reject_clips() -> list[str]:
    clips: list[str] = []
    for year in (2016, 2017, 2018):
        cat = json.loads((META / f"clips_{year}.json").read_text())
        for c in cat["clips"]:
            date = c.get("date") or ""
            if date < "2016-07-01" or date > "2018-12-31":
                continue
            path = META / f"votes_{c['clip_id']}.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            if len(data.get("accepted") or []) == 0 and len(data.get("rejected") or []) > 0:
                clips.append(str(c["clip_id"]))
    return clips


def reparse_clip(clip_id: str, dry_run: bool = False) -> dict:
    path = META / f"votes_{clip_id}.json"
    data = json.loads(path.read_text())
    date = data.get("date") or ""
    era = roster_mod.era_for(date)
    candidates = list(data.get("accepted") or []) + list(data.get("rejected") or [])
    accepted: list[dict] = []
    rejected: list[dict] = []

    for cand in candidates:
        crop = cand.get("board_crop")
        if not crop or not Path(crop).is_file():
            rejected.append(cand)
            continue
        with Image.open(crop) as image:
            fmt = detect.classify_bright_format(image)
            if fmt == detect.FORMAT_C:
                parsed = detect.ocr_parse_format_c(image, era)
            elif fmt == detect.FORMAT_A:
                parsed = detect.ocr_parse_format_a(image, era)
            else:
                # Keep prior parse if we cannot re-classify
                parsed = cand.get("parsed") or {}
                rejected.append({**cand, "problems": ["reparse: unrecognized format"]})
                continue

        problems, absent = detect.validate(parsed, era)
        cand = {
            **cand,
            "format": parsed.get("format") or cand.get("format"),
            "parsed": parsed,
            "absent_members": absent,
            "roster_complete": not absent,
            "problems": problems,
        }
        if problems:
            rejected.append(cand)
        else:
            # Drop problems key for accepted
            cand.pop("problems", None)
            accepted.append(cand)

    summary = {
        "clip_id": clip_id,
        "date": date,
        "era": era.key,
        "before_accepted": len(data.get("accepted") or []),
        "before_rejected": len(data.get("rejected") or []),
        "after_accepted": len(accepted),
        "after_rejected": len(rejected),
    }
    print(
        f"clip {clip_id} ({date}) {era.key}: "
        f"{summary['before_accepted']}→{summary['after_accepted']} accepted, "
        f"{summary['before_rejected']}→{summary['after_rejected']} rejected",
        flush=True,
    )
    if dry_run:
        return summary

    data["accepted"] = accepted
    data["rejected"] = rejected
    data["candidates"] = len(accepted) + len(rejected)
    data["roster_era"] = era.key
    data["roster_verified"] = era.verified
    data["roster_note"] = era.note
    data["reparsed_from_crops"] = True
    path.write_text(json.dumps(data, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clips", default="", help="comma clip ids")
    parser.add_argument("--herring-all-reject", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    clips: list[str] = []
    if args.herring_all_reject:
        clips.extend(herring_all_reject_clips())
    if args.clips:
        clips.extend(c.strip() for c in args.clips.split(",") if c.strip())
    # unique preserve order
    seen = set()
    ordered = []
    for c in clips:
        if c not in seen:
            seen.add(c)
            ordered.append(c)

    if not ordered:
        print("no clips", file=sys.stderr)
        return 1

    ok = improved = 0
    for clip_id in ordered:
        try:
            summary = reparse_clip(clip_id, dry_run=args.dry_run)
            ok += 1
            if summary["after_accepted"] > summary["before_accepted"]:
                improved += 1
        except Exception as exc:  # noqa: BLE001
            print(f"clip {clip_id} FAILED: {exc}", file=sys.stderr)
    print(f"done clips={ok} improved={improved} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
