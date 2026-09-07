#!/usr/bin/env python3
"""Catalog Granicus council meeting clips into Passport metadata.

Scrapes the archive listing for a year's clips, then for each clip pulls the
player page to capture the HLS playlist, captions URL, and the agenda index
(cuepoint time + meta id + title). Output lands on the Passport as
`metadata/clips_{year}.json` so the extract step never needs the network twice.

    python3 pipeline/catalog_granicus.py --year 2026
    python3 pipeline/catalog_granicus.py --clip 14821
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard

BASE = "https://torrance.granicus.com"
LISTING_URL = f"{BASE}/ViewPublisher.php?view_id=8"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) torrance-vote-viewer/2026"

# Agenda sections that never carry a recorded roll-call vote.
NON_VOTABLE_PATTERNS = [
    r"CALL TO ORDER",
    r"ROLL CALL",
    r"FLAG SALUTE",
    r"PLEDGE OF ALLEGIANCE",
    r"INVOCATION",
    r"ORAL COMMUNICATIONS",
    r"PUBLIC (COMMENT|PARTICIPATION)",
    r"ADJOURN",
    r"RECESS",
    r"RECONVENE",
    r"CLOSED SESSION",
    r"CONFERENCE WITH (LEGAL COUNSEL|LABOR|REAL PROPERTY)",
    r"REAL PROPERTY - CONFERENCE",
    r"ANNOUNCEMENT",
    r"PRESENTATION",
    r"PROCLAMATION",
    r"COMMENDATION",
    r"REPORT OF THE CITY",
    r"^\s*BREAK\s*$",
]
NON_VOTABLE_RE = re.compile("|".join(NON_VOTABLE_PATTERNS), re.IGNORECASE)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def clean_title(raw: str) -> str:
    text = html.unescape(raw)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_votable(title: str) -> bool:
    return not NON_VOTABLE_RE.search(title or "")


def numeric_key(value: str | int | None) -> tuple[int, int, str]:
    """Numeric sort key for a Granicus meta id or clip id.

    Granicus does emit several cuepoints on the same second, so the tie-break
    decides their order. Comparing the raw string sorts "9" ahead of "451683";
    ids that are not purely numeric keep a deterministic slot at the end.
    """
    text = str(value)
    if text.isdigit():
        return (0, int(text), "")
    return (1, 0, text)


def parse_listing(page: str, year: int) -> list[dict]:
    """Pull the clips out of one year's collapsible panel."""
    panel_start = page.find(f'id="CollapsiblePanel1_{year}"')
    if panel_start < 0:
        raise SystemExit(f"no {year} panel found in archive listing")
    next_panel = re.search(r'id="CollapsiblePanel1_\d+"', page[panel_start + 10 :])
    panel_end = panel_start + 10 + next_panel.start() if next_panel else len(page)
    panel = page[panel_start:panel_end]

    clips: list[dict] = []
    for row in re.findall(r"<tr>(.*?)</tr>", panel, re.DOTALL):
        clip_match = re.search(r"clip_id=(\d+)", row)
        if not clip_match:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        name = clean_title(cells[0]) if cells else ""
        date_text = clean_title(cells[1]) if len(cells) > 1 else ""
        clips.append(
            {
                "clip_id": clip_match.group(1),
                "name": name,
                "date_text": date_text,
                "date": normalize_date(date_text),
                "player_url": f"{BASE}/player/clip/{clip_match.group(1)}?view_id=8&redirect=true",
                "agenda_url": f"{BASE}/AgendaViewer.php?view_id=8&clip_id={clip_match.group(1)}",
            }
        )
    # The listing repeats a clip when it has both agenda and minutes rows.
    seen: dict[str, dict] = {}
    for clip in clips:
        seen.setdefault(clip["clip_id"], clip)
    return sorted(seen.values(), key=lambda c: int(c["clip_id"]))


MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ],
        start=1,
    )
}


def normalize_date(date_text: str) -> str | None:
    match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", date_text or "")
    if not match:
        return None
    month = MONTHS.get(match.group(1).lower())
    if not month:
        return None
    return f"{match.group(3)}-{month:02d}-{int(match.group(2)):02d}"


def parse_player(clip_id: str, page: str) -> dict:
    hls = None
    hls_match = re.search(r'src="(https://archive-stream\.granicus\.com/[^"]+\.m3u8)"', page)
    if hls_match:
        hls = hls_match.group(1)

    captions = None
    cap_match = re.search(r'src="(/videos/\d+/captions\.vtt)"', page)
    if cap_match:
        captions = BASE + cap_match.group(1)

    cuepoints: list[dict] = []
    cue_match = re.search(r"cuepoints:\s*(\[.*?\])", page, re.DOTALL)
    if cue_match:
        cuepoints = json.loads(cue_match.group(1))

    # Agenda titles live in .index-point divs carrying time + data-id attributes.
    index_points: list[dict] = []
    pattern = re.compile(
        r'<div\s+class="index-point[^"]*".*?time="(\d+)".*?data-id="(\d+)".*?>(.*?)</div>',
        re.DOTALL,
    )
    for match in pattern.finditer(page):
        time_s, meta_id, body = match.groups()
        index_points.append(
            {
                "time": int(time_s),
                "meta_id": meta_id,
                "title": clean_title(body),
            }
        )
    index_points.sort(key=lambda p: (p["time"], numeric_key(p["meta_id"])))

    by_meta = {p["meta_id"]: p for p in index_points}
    agenda: list[dict] = []
    for cue in cuepoints:
        if cue.get("type") != "Agenda":
            continue
        meta_id = str(cue.get("id"))
        point = by_meta.get(meta_id, {})
        title = point.get("title", "")
        agenda.append(
            {
                "meta_id": meta_id,
                "time": float(cue["time"]),
                "title": title,
                "votable": is_votable(title),
                "meta_url": f"{BASE}/MetaViewer.php?meta_id={meta_id}",
            }
        )
    agenda.sort(key=lambda a: (a["time"], numeric_key(a["meta_id"])))

    duration = None
    dur_match = re.search(r"duration:\s*(\d+)", page)
    if dur_match:
        duration = int(dur_match.group(1))

    return {
        "clip_id": clip_id,
        "hls_url": hls,
        "captions_url": captions,
        "duration": duration,
        "cuepoint_count": len(cuepoints),
        "index_point_count": len(index_points),
        "agenda": agenda,
        "unmatched_cuepoints": [
            c["meta_id"] for c in agenda if not c["title"]
        ],
    }


def catalog_clip(clip_id: str, base: dict | None = None) -> dict:
    player_url = (base or {}).get(
        "player_url", f"{BASE}/player/clip/{clip_id}?view_id=8&redirect=true"
    )
    record = dict(base or {"clip_id": clip_id, "player_url": player_url})
    record.update(parse_player(clip_id, fetch(player_url)))
    return record


# The published site data is generated by publish_votes.py; a catalog written
# there would silently replace what the frontend loads.
PROTECTED_DIR = disk_guard.REPO_ROOT / "data"


def resolve_out_path(raw: Path | None, year: int) -> Path:
    """Pick the catalog path, refusing to write over the published site data."""
    if raw is None:
        return disk_guard.work_dir("metadata") / f"clips_{year}.json"
    out = Path(raw).expanduser()
    resolved = out.resolve()
    try:
        resolved.relative_to(PROTECTED_DIR.resolve())
    except ValueError:
        return resolved
    raise SystemExit(
        f"refusing --out {out}: {PROTECTED_DIR} holds the published site data. "
        "Write the catalog to the Passport metadata dir or another path."
    )


def load_catalog(out: Path, year: int) -> list[dict]:
    """Return the clips already catalogued at `out`.

    A partial run (`--clip X`) has to merge into this rather than replace it,
    otherwise every other clip loses the hls_url and agenda that the extract
    step depends on having fetched exactly once.
    """
    if not out.exists():
        return []
    try:
        payload = json.loads(out.read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit(
            f"existing catalog {out} could not be read ({exc}); refusing to "
            "overwrite it. Move it aside if it is genuinely corrupt."
        )
    if not isinstance(payload, dict):
        raise SystemExit(f"existing catalog {out} is not a JSON object")
    existing_year = payload.get("year")
    if existing_year is not None and int(existing_year) != int(year):
        raise SystemExit(
            f"existing catalog {out} is for year {existing_year}, not {year}; "
            "refusing to mix years in one file"
        )
    clips = payload.get("clips") or []
    if not isinstance(clips, list):
        raise SystemExit(f"existing catalog {out} has a non-list 'clips'")
    return [c for c in clips if isinstance(c, dict) and c.get("clip_id")]


def merge_clips(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """Overlay freshly fetched clips onto the previously catalogued ones."""
    merged = {str(c["clip_id"]): c for c in existing}
    for clip in fresh:
        merged[str(clip["clip_id"])] = clip
    return [merged[k] for k in sorted(merged, key=numeric_key)]


def write_json_atomic(path: Path, payload: dict) -> None:
    """Write via a sibling temp file so a crash cannot truncate the catalog."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def discover_years(listing_html: str | None = None) -> list[int]:
    """Year panels present on the Granicus archive listing."""
    page = listing_html if listing_html is not None else fetch(LISTING_URL)
    years = sorted({int(y) for y in re.findall(r'id="CollapsiblePanel1_(\d{4})"', page)})
    if not years:
        raise SystemExit("no CollapsiblePanel1_YYYY panels found on Granicus listing")
    return years


def catalog_year(
    year: int,
    *,
    clip_ids: list[str] | None = None,
    out: Path | None = None,
    listing_html: str | None = None,
) -> Path:
    """Fetch player pages for one year and write/merge metadata/clips_{year}.json."""
    out_path = resolve_out_path(out, year)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_catalog(out_path, year)

    page = listing_html if listing_html is not None else fetch(LISTING_URL)
    listing = parse_listing(page, year)
    if clip_ids:
        wanted = set(clip_ids)
        listing = [c for c in listing if c["clip_id"] in wanted]
        missing = wanted - {c["clip_id"] for c in listing}
        for clip_id in sorted(missing):
            listing.append({"clip_id": clip_id})

    clips = []
    for base in listing:
        clip = catalog_clip(base["clip_id"], base)
        votable = sum(1 for a in clip["agenda"] if a["votable"])
        print(
            f"clip {clip['clip_id']} {clip.get('date') or '?'}: "
            f"{len(clip['agenda'])} agenda cuepoints, {votable} votable, "
            f"hls={'yes' if clip['hls_url'] else 'NO'} "
            f"captions={'yes' if clip['captions_url'] else 'NO'}"
        )
        if clip["unmatched_cuepoints"]:
            print(
                f"  warning: {len(clip['unmatched_cuepoints'])} cuepoints had no "
                f"index-point title: {clip['unmatched_cuepoints']}"
            )
        clips.append(clip)

    merged = merge_clips(existing, clips)
    payload = {
        "year": year,
        "source": LISTING_URL,
        "clips": merged,
    }
    write_json_atomic(out_path, payload)
    kept = len(merged) - len(clips)
    print(
        f"wrote {out_path} ({len(clips)} fetched, {kept} preserved from earlier runs)"
    )
    return out_path


def parse_years_arg(raw: str) -> list[int]:
    """Parse '2005-2010,2015,2020-2022' into a sorted unique year list."""
    years: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
            if end < start:
                start, end = end, start
            years.update(range(start, end + 1))
        else:
            years.add(int(part))
    return sorted(years)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=None, help="single year (default: 2026)")
    parser.add_argument(
        "--years",
        type=str,
        default=None,
        help="year list/ranges, e.g. 2005-2010,2015",
    )
    parser.add_argument(
        "--all-years",
        action="store_true",
        help="catalog every year panel on the Granicus listing",
    )
    parser.add_argument(
        "--clip",
        action="append",
        default=[],
        help="restrict to specific clip id(s); repeatable (single --year only)",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    for clip_id in args.clip:
        if not str(clip_id).isdigit():
            parser.error(f"--clip expects a numeric clip id, got {clip_id!r}")

    modes = sum(bool(x) for x in (args.year, args.years, args.all_years))
    if modes > 1:
        parser.error("use only one of --year, --years, --all-years")
    if args.clip and (args.years or args.all_years):
        parser.error("--clip only works with a single --year")

    disk_guard.require_space("catalog")

    listing_html = fetch(LISTING_URL)
    available = discover_years(listing_html)

    if args.all_years:
        years = available
    elif args.years:
        years = parse_years_arg(args.years)
        unknown = [y for y in years if y not in available]
        if unknown:
            parser.error(
                f"years not on Granicus listing: {unknown}; available={available}"
            )
    else:
        years = [args.year if args.year is not None else 2026]
        for y in years:
            if y not in available:
                print(
                    f"warning: year {y} has no listing panel; "
                    f"available={available}",
                    file=sys.stderr,
                )

    print(f"cataloging years: {years}")
    for year in years:
        print(f"\n=== year {year} ===")
        catalog_year(
            year,
            clip_ids=args.clip or None,
            out=args.out if len(years) == 1 else None,
            listing_html=listing_html,
        )
    print(disk_guard.report("catalog"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
