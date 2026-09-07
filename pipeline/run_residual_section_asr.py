#!/usr/bin/env python3
"""Section-end ASR hunts for residual empty board clips, then oral convert.

Default residual list is the 2024–2026 clips that still have zero accepted
board votes and no useful hunt hits. For each votable agenda section, Whisper
runs near the *end* of the section (where clerk result speech usually lands),
not only near the agenda cue start.

    .venv/bin/python pipeline/run_residual_section_asr.py
    .venv/bin/python pipeline/run_residual_section_asr.py --clips 14405,14718 --publish
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard
import hunt_votes_from_transcript as hunt
import oral_votes_from_hunt as oral
import transcribe_window as asr_mod

META = disk_guard.work_dir("metadata")
REPO = disk_guard.REPO_ROOT
PYTHON = REPO / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)

DEFAULT_RESIDUALS = [
    "14282",
    "14318",
    "14340",
    "14360",
    "14385",
    "14405",
    "14435",
    "14482",
    "14588",
    "14718",
]

# Re-export / mirror prepare_full_archive exclusions.
NON_COUNCIL_CLIPS = frozenset({"14588"})


def find_clip(clip_id: str) -> tuple[int, dict] | None:
    for year in range(2024, 2027):
        path = META / f"clips_{year}.json"
        if not path.is_file():
            continue
        for clip in json.loads(path.read_text()).get("clips") or []:
            if str(clip.get("clip_id")) == str(clip_id):
                return year, clip
    return None


def section_end_centers(clip: dict) -> list[tuple[dict, float, float, float]]:
    """Return (item, t0, t1, asr_center) for votable sections."""
    agenda = sorted(
        [a for a in (clip.get("agenda") or []) if a.get("time") is not None],
        key=lambda a: float(a["time"]),
    )
    out: list[tuple[dict, float, float, float]] = []
    for i, item in enumerate(agenda):
        if not item.get("votable"):
            continue
        title = str(item.get("title") or "")
        if hunt.VOTE_RE.search(title) and "CALL MEETING" in title.upper():
            continue
        t0 = float(item["time"])
        # Skip absurd cuepoints (bad catalog rows).
        if t0 > 80_000:
            continue
        t1 = float(agenda[i + 1]["time"]) if i + 1 < len(agenda) else t0 + 400
        if t1 - t0 < 5:
            # Degenerate adjacent cuepoints — still probe shortly after start.
            center = t0 + 40
        else:
            center = max(t0 + 30, t1 - 45)
        out.append((item, t0, t1, center))
    return out


def asr_section_ends(clip: dict, pad: float = 60.0) -> list[dict]:
    centers = section_end_centers(clip)
    all_cues: list[dict] = []
    seen: set[tuple[float, str]] = set()
    for item, t0, t1, center in centers:
        title = (item.get("title") or "")[:60]
        print(f"  section {t0:.0f}-{t1:.0f} center={center:.0f} {title}", flush=True)
        try:
            payload = asr_mod.transcribe_window(clip, center, pad)
        except Exception as exc:  # noqa: BLE001
            print(f"    ASR fail: {exc}", file=sys.stderr)
            continue
        for cue in payload.get("cues") or []:
            key = (round(float(cue["start"]), 1), str(cue.get("text") or "")[:40])
            if key in seen:
                continue
            seen.add(key)
            all_cues.append(cue)
    all_cues.sort(key=lambda c: c["start"])
    return all_cues


def write_hunt(clip_id: str, year: int, cues: list[dict], cue_source: str) -> dict:
    hits = hunt.find_hits(cues)
    sidecar = {
        "clip_id": str(clip_id),
        "year": int(year),
        "source": "transcript_hunt",
        "cue_count": len(cues),
        "cue_source": cue_source,
        "vote_hits": len(hits),
        "hits": hits,
        "captions_only": False,
        "hunt_mode": "section_end",
    }
    path = META / f"votes_{clip_id}_transcript_hunt.json"
    path.write_text(json.dumps(sidecar, indent=2) + "\n")
    scratch = disk_guard.PASSPORT_ROOT / "scratch" / f"vote_hunt_{clip_id}"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "hits.json").write_text(
        json.dumps({**sidecar, "out_dir": str(scratch)}, indent=2) + "\n"
    )
    return sidecar


def has_board_accepted(clip_id: str) -> bool:
    path = META / f"votes_{clip_id}.json"
    if not path.is_file():
        return False
    data = json.loads(path.read_text())
    for c in data.get("accepted") or []:
        if c.get("board_crop") or (c.get("format") or "") in (
            "A",
            "B",
            "C",
            "format_a",
            "format_b",
            "format_c",
        ):
            return True
    return False


def publish_clip(clip_id: str) -> int:
    path = META / f"votes_{clip_id}.json"
    if not path.is_file():
        return 1
    data = json.loads(path.read_text())
    n = len(data.get("accepted") or []) + len(data.get("rejected") or [])
    if n <= 0:
        print(f"  publish skip {clip_id}: no candidates")
        return 0
    cmd = [str(PYTHON), str(REPO / "pipeline" / "publish_votes.py"), "--input", str(path)]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout[-400:], file=sys.stderr)
        print(proc.stderr[-400:], file=sys.stderr)
        return proc.returncode
    for line in proc.stdout.splitlines():
        if line.startswith("votes:") or line.startswith("verification:"):
            print(f"  {line}")
    return 0


def process_clip(clip_id: str, pad: float, publish: bool, dry_run: bool) -> dict:
    if str(clip_id) in NON_COUNCIL_CLIPS:
        if not dry_run:
            vp = META / f"votes_{clip_id}.json"
            data = json.loads(vp.read_text()) if vp.is_file() else {"clip_id": clip_id}
            data["coverage_status"] = {
                "status": "excluded",
                "reason": "non_council_civil_service",
                "note": "Torrance Civil Service Commission — not City Council.",
            }
            vp.parent.mkdir(parents=True, exist_ok=True)
            vp.write_text(json.dumps(data, indent=2) + "\n")
        return {
            "clip_id": clip_id,
            "skipped": "non_council_civil_service",
        }
    found = find_clip(clip_id)
    if not found:
        return {"clip_id": clip_id, "error": "not_in_catalog"}
    year, clip = found
    if not clip.get("hls_url"):
        return {"clip_id": clip_id, "year": year, "error": "no_hls"}
    if has_board_accepted(clip_id):
        return {"clip_id": clip_id, "year": year, "skipped": "has_board_accepted"}

    print(f"\n=== {clip.get('date')} clip={clip_id} year={year} ===", flush=True)
    centers = section_end_centers(clip)
    if not centers:
        reason = "no_votable_sections"
        if not dry_run:
            vp = META / f"votes_{clip_id}.json"
            data = json.loads(vp.read_text()) if vp.is_file() else {"clip_id": clip_id, "year": year}
            data["coverage_status"] = {
                "status": "empty",
                "reason": reason,
                "hunt_mode": "section_end",
            }
            vp.write_text(json.dumps(data, indent=2) + "\n")
        return {"clip_id": clip_id, "year": year, "reason": reason}

    if dry_run:
        return {
            "clip_id": clip_id,
            "year": year,
            "date": clip.get("date"),
            "sections": len(centers),
            "dry_run": True,
        }

    cues = asr_section_ends(clip, pad=pad)
    sidecar = write_hunt(clip_id, year, cues, "asr_section_end")
    print(f"  cues={len(cues)} vote_hits={sidecar['vote_hits']}", flush=True)

    summary = oral.convert_clip(clip_id, year, dry_run=False)
    result = {
        "clip_id": clip_id,
        "year": year,
        "date": clip.get("date"),
        "sections": len(centers),
        "cues": len(cues),
        "vote_hits": sidecar["vote_hits"],
        "oral_events": summary.get("events"),
        "oral_accepted": summary.get("accepted"),
        "oral_empty_reason": summary.get("oral_empty_reason"),
        "skipped": summary.get("skipped"),
    }
    # Refresh coverage_status on votes file.
    vp = META / f"votes_{clip_id}.json"
    if vp.is_file():
        data = json.loads(vp.read_text())
        if summary.get("skipped"):
            data["coverage_status"] = {
                "status": "board_present",
                "reason": summary.get("skipped"),
                "hunt_mode": "section_end",
                "vote_hits": sidecar["vote_hits"],
            }
        elif int(summary.get("accepted") or 0) > 0:
            data["coverage_status"] = {
                "status": "oral_from_section_end",
                "reason": None,
                "hunt_mode": "section_end",
                "vote_hits": sidecar["vote_hits"],
                "oral_accepted": summary.get("accepted"),
            }
            if "oral_empty_reason" in data:
                del data["oral_empty_reason"]
        else:
            data["coverage_status"] = {
                "status": "empty",
                "reason": summary.get("oral_empty_reason") or "no_attributable_speech",
                "hunt_mode": "section_end",
                "vote_hits": sidecar["vote_hits"],
                "cues": len(cues),
            }
            if summary.get("oral_empty_reason"):
                data["oral_empty_reason"] = summary["oral_empty_reason"]
        vp.write_text(json.dumps(data, indent=2) + "\n")

    if publish and int(summary.get("accepted") or 0) > 0 and not summary.get("skipped"):
        result["publish_rc"] = publish_clip(clip_id)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clips", default=",".join(DEFAULT_RESIDUALS))
    parser.add_argument("--pad", type=float, default=60.0)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    disk_guard.require_space("vote_hunt")
    clips = [c.strip() for c in args.clips.split(",") if c.strip()]
    print(
        f"residual section-end ASR: {len(clips)} clips "
        f"pad={args.pad} publish={args.publish} dry_run={args.dry_run}"
    )
    results = []
    for clip_id in clips:
        results.append(process_clip(clip_id, args.pad, args.publish, args.dry_run))

    out = META / "residual_section_asr_summary.json"
    out.write_text(json.dumps({"results": results}, indent=2) + "\n")
    ok = sum(1 for r in results if int(r.get("oral_accepted") or 0) > 0)
    empty = sum(1 for r in results if r.get("oral_empty_reason") or r.get("reason"))
    err = sum(1 for r in results if r.get("error"))
    print(
        f"\ndone oral_ok={ok} emptyish={empty} errors={err} "
        f"summary={out}"
    )
    return 1 if err else 0


if __name__ == "__main__":
    raise SystemExit(main())
