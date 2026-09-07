#!/usr/bin/env python3
"""Prepare a full-archive parse of every Torrance Granicus council meeting.

Granicus listing panels cover 2005–present (~774 clips). This script:

  1. Discovers years on the live listing
  2. Optionally catalogs any missing/partial years into Passport clips_YYYY.json
  3. Writes an inventory + extract/detect queue (what is ready vs already done)

It does **not** run extract or detect — those are still per-clip and heavy.
Use the queue JSON to drive batch extract next.

    .venv/bin/python pipeline/prepare_full_archive.py
    .venv/bin/python pipeline/prepare_full_archive.py --catalog-missing
    .venv/bin/python pipeline/prepare_full_archive.py --catalog-all

Closed-session clips with zero votable cuepoints are listed but not queued.
Known closed-session skips (14676, 14693, 14721) stay excluded from extract.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_granicus as catalog
import disk_guard

META = disk_guard.PASSPORT_ROOT / "metadata"
INVENTORY_PATH = META / "full_archive_inventory.json"
QUEUE_PATH = META / "full_archive_extract_queue.json"

# Confirmed closed-session / non-votable meetings — never extract.
CLOSED_SESSION_SKIPS = frozenset({"14676", "14693", "14721"})
# Not City Council (Civil Service, etc.) — exclude from council coverage queues.
NON_COUNCIL_CLIPS = frozenset({"14588"})


def frames_root_for(clip_id: str) -> Path:
    """Prefer .noindex layout; fall back to legacy frames/."""
    for kind in ("frames",):
        noindex = disk_guard.work_root(kind) / str(clip_id)
        legacy = disk_guard.legacy_work_root(kind) / str(clip_id)
        if (noindex / "windows.json").is_file():
            return noindex
        if (legacy / "windows.json").is_file():
            return legacy
    return disk_guard.work_root("frames") / str(clip_id)


def detect_outputs(clip_id: str) -> list[str]:
    if not META.exists():
        return []
    return sorted(p.name for p in META.glob(f"votes_{clip_id}*.json"))


def clip_status(clip: dict, year: int) -> dict:
    clip_id = str(clip.get("clip_id") or "")
    agenda = clip.get("agenda") or []
    votable = sum(1 for a in agenda if a.get("votable"))
    frames = frames_root_for(clip_id)
    windows = frames / "windows.json"
    extracted = False
    gated_frames = 0
    if windows.is_file():
        try:
            w = json.loads(windows.read_text())
            gated_frames = int(w.get("kept_frames") or w.get("gated_frames") or 0)
            if not gated_frames:
                # windows.json shape varies; count frame entries if present
                for key in ("windows", "frames"):
                    if isinstance(w.get(key), list):
                        gated_frames = max(gated_frames, len(w[key]))
            # Manifest alone is not enough — frames may have been cleaned after
            # a prior detect. Require at least one JPEG on disk.
            has_jpeg = next(frames.rglob("*.jpg"), None) is not None
            extracted = bool(has_jpeg)
            if not has_jpeg:
                gated_frames = 0
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            extracted = False

    detects = detect_outputs(clip_id)
    skip_reason = None
    if clip_id in CLOSED_SESSION_SKIPS:
        skip_reason = "known_closed_session_skip"
    elif clip_id in NON_COUNCIL_CLIPS:
        skip_reason = "non_council_civil_service"
    elif votable == 0:
        skip_reason = "zero_votable_cuepoints"
    elif not clip.get("hls_url"):
        skip_reason = "no_hls_url"

    return {
        "clip_id": clip_id,
        "year": year,
        "date": clip.get("date"),
        "name": clip.get("name"),
        "agenda_count": len(agenda),
        "votable_count": votable,
        "hls": bool(clip.get("hls_url")),
        "captions_url": bool(clip.get("captions_url")),
        "extracted": extracted,
        "frames_dir": str(frames) if extracted else None,
        "detect_files": detects,
        "detected": bool(detects),
        "skip_reason": skip_reason,
        "queue_extract": skip_reason is None and not extracted,
        "queue_detect": skip_reason is None and extracted and not detects,
    }


def load_year_catalog(year: int) -> list[dict]:
    path = META / f"clips_{year}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [c for c in (data.get("clips") or []) if isinstance(c, dict)]


def build_inventory(years: list[int]) -> dict:
    clips_out: list[dict] = []
    for year in years:
        for clip in load_year_catalog(year):
            # Only count fully catalogued clips (player fetch done).
            if "agenda" not in clip and not clip.get("hls_url"):
                continue
            clips_out.append(clip_status(clip, year))

    by_year: dict[str, dict] = {}
    for row in clips_out:
        y = str(row["year"])
        bucket = by_year.setdefault(
            y,
            {
                "catalogued": 0,
                "votable_meetings": 0,
                "extracted": 0,
                "detected": 0,
                "queue_extract": 0,
                "queue_detect": 0,
                "skipped": 0,
            },
        )
        bucket["catalogued"] += 1
        if row["skip_reason"]:
            bucket["skipped"] += 1
        else:
            bucket["votable_meetings"] += 1
        if row["extracted"]:
            bucket["extracted"] += 1
        if row["detected"]:
            bucket["detected"] += 1
        if row["queue_extract"]:
            bucket["queue_extract"] += 1
        if row["queue_detect"]:
            bucket["queue_detect"] += 1

    extract_queue = [
        {"clip_id": r["clip_id"], "year": r["year"], "date": r["date"]}
        for r in clips_out
        if r["queue_extract"]
    ]
    detect_queue = [
        {"clip_id": r["clip_id"], "year": r["year"], "date": r["date"]}
        for r in clips_out
        if r["queue_detect"]
    ]
    extract_queue.sort(key=lambda r: (r["year"], r["date"] or "", int(r["clip_id"])))
    detect_queue.sort(key=lambda r: (r["year"], r["date"] or "", int(r["clip_id"])))

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "granicus_years": years,
        "closed_session_skips": sorted(CLOSED_SESSION_SKIPS),
        "non_council_clips": sorted(NON_COUNCIL_CLIPS),
        "totals": {
            "catalogued_clips": len(clips_out),
            "queue_extract": len(extract_queue),
            "queue_detect": len(detect_queue),
            "extracted": sum(1 for r in clips_out if r["extracted"]),
            "detected": sum(1 for r in clips_out if r["detected"]),
            "skipped": sum(1 for r in clips_out if r["skip_reason"]),
        },
        "by_year": dict(sorted(by_year.items())),
        "clips": clips_out,
        "extract_queue": extract_queue,
        "detect_queue": detect_queue,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog-missing",
        action="store_true",
        help="catalog any Granicus year that has no clips_YYYY.json yet",
    )
    parser.add_argument(
        "--catalog-all",
        action="store_true",
        help="re-catalog every year on the listing (slow; merges into existing)",
    )
    parser.add_argument(
        "--years",
        type=str,
        default=None,
        help="limit catalog/inventory to these years (e.g. 2005-2010)",
    )
    args = parser.parse_args()

    if not disk_guard.passport_available():
        print("Passport not mounted", file=sys.stderr)
        return 1

    disk_guard.require_space("prepare_full_archive")
    listing = catalog.fetch(catalog.LISTING_URL)
    available = catalog.discover_years(listing)
    years = (
        catalog.parse_years_arg(args.years) if args.years else list(available)
    )
    for y in years:
        if y not in available:
            print(f"warning: {y} not on listing", file=sys.stderr)

    print(f"Granicus years: {available}")
    print(f"scope: {years}")

    if args.catalog_all:
        for year in years:
            print(f"\n=== catalog {year} ===", flush=True)
            catalog.catalog_year(year, listing_html=listing)
    elif args.catalog_missing:
        for year in years:
            path = META / f"clips_{year}.json"
            existing = load_year_catalog(year)
            # Treat as missing if file absent or no clip has agenda/hls yet.
            complete = any(c.get("hls_url") or "agenda" in c for c in existing)
            if path.exists() and complete:
                print(f"year {year}: catalog present ({len(existing)} clips)")
                continue
            print(f"\n=== catalog missing {year} ===", flush=True)
            catalog.catalog_year(year, listing_html=listing)

    inventory = build_inventory(years)
    write_json(INVENTORY_PATH, inventory)
    write_json(
        QUEUE_PATH,
        {
            "generated_at": inventory["generated_at"],
            "extract_queue": inventory["extract_queue"],
            "detect_queue": inventory["detect_queue"],
            "totals": inventory["totals"],
        },
    )

    print("\n=== inventory ===")
    print(json.dumps(inventory["totals"], indent=2))
    print("by year:")
    for y, bucket in inventory["by_year"].items():
        print(
            f"  {y}: catalogued={bucket['catalogued']} "
            f"votable={bucket['votable_meetings']} "
            f"extracted={bucket['extracted']} detected={bucket['detected']} "
            f"queue_extract={bucket['queue_extract']} "
            f"queue_detect={bucket['queue_detect']} skipped={bucket['skipped']}"
        )
    print(f"\nwrote {INVENTORY_PATH}")
    print(f"wrote {QUEUE_PATH}")
    print(disk_guard.report("prepare_full_archive"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
