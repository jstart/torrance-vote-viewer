#!/usr/bin/env python3
"""Write validated votes to the 2026 staging file and copy the winning frames.

Deliberately self-contained: it re-derives every record from the detector's
output and re-runs the roster and tally checks itself rather than trusting the
`accepted` flag, so a bad record cannot reach the staging file just because an
upstream stage said it was fine. Nothing here touches the consolidated dataset.

    python3 pipeline/publish_staging.py --clip 14821

Output:
  data/2026_verified_votes.json
  frame_images/2026/{clip_id}/vote_{vote_id}.jpg
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard
import roster as roster_mod

REPO = Path(__file__).resolve().parent.parent
STAGING_PATH = REPO / "data" / "2026_verified_votes.json"
PASSPORT = Path("/Volumes/Black Passport/torrance-vote-viewer")

# Region of the 1280x720 frame holding the whole VoteCast overlay.
OVERLAY_BOX = (0.100, 0.100, 0.900, 0.890)

ALLOWED_VOTES = ("YES", "NO", "ABSTAIN", "RECUSE")
TALLY_KEYS = {"YES": "ayes", "NO": "noes", "ABSTAIN": "abstentions", "RECUSE": "recused"}


def crop_overlay(image: Image.Image) -> Image.Image:
    width, height = image.size
    return image.crop(
        (
            int(OVERLAY_BOX[0] * width),
            int(OVERLAY_BOX[1] * height),
            int(OVERLAY_BOX[2] * width),
            int(OVERLAY_BOX[3] * height),
        )
    )


def recheck(candidate: dict, era: roster_mod.Era) -> list[str]:
    """Re-run the acceptance rules independently of the detector."""
    parsed = candidate.get("parsed") or {}
    tally = parsed.get("vote_tally") or {}
    votes = parsed.get("individual_votes") or {}
    problems: list[str] = []

    if parsed.get("result") not in ("passed", "failed", "tie"):
        problems.append(f"result {parsed.get('result')!r} is not passed/failed/tie")

    roster_names = {m.name for m in era.members}
    for name, value in sorted(votes.items()):
        if name not in roster_names:
            problems.append(f"{name} is not on the {era.key} roster")
        if value not in ALLOWED_VOTES:
            problems.append(f"{name} has vote value {value!r}")

    counted = dict.fromkeys(TALLY_KEYS.values(), 0)
    for value in votes.values():
        if value in TALLY_KEYS:
            counted[TALLY_KEYS[value]] += 1
    for key, expected in counted.items():
        if int(tally.get(key, -1)) != expected:
            problems.append(f"{key}: slide says {tally.get(key)}, {expected} members named")

    if not candidate.get("meta_id"):
        problems.append("no agenda cuepoint bound")
    if not str(candidate.get("agenda_item") or "").strip():
        problems.append("empty agenda item")
    if not isinstance(candidate.get("video_timestamp"), int):
        problems.append("video_timestamp is not an integer second offset")
    return problems


def build_record(candidate: dict, clip: dict, era: roster_mod.Era, frame: dict) -> dict:
    parsed = candidate["parsed"]
    meta_id = str(candidate["meta_id"])
    player = f"https://torrance.granicus.com/player/clip/{clip['clip_id']}?view_id=8"
    return {
        "id": candidate["vote_id"],
        "meeting_id": str(clip["clip_id"]),
        "meeting_date": clip.get("date"),
        "agenda_item": str(candidate["agenda_item"]),
        "meta_id": meta_id,
        "video_timestamp": int(candidate["video_timestamp"]),
        "timestamp_estimated": False,
        "result": parsed["result"],
        "vote_tally": {
            "ayes": int(parsed["vote_tally"]["ayes"]),
            "noes": int(parsed["vote_tally"]["noes"]),
            "abstentions": int(parsed["vote_tally"]["abstentions"]),
            "recused": int(parsed["vote_tally"]["recused"]),
        },
        "individual_votes": dict(sorted(parsed["individual_votes"].items())),
        "absent_members": sorted(candidate.get("absent_members") or []),
        "roster_complete": bool(candidate.get("roster_complete")),
        "roster_era": era.key,
        "verification": "verified",
        "source": "granicus_frame",
        "parser": parsed.get("parser"),
        "frames_merged": parsed.get("frames_merged"),
        "tally_agreement": parsed.get("tally_agreement"),
        "result_agreement": parsed.get("result_agreement"),
        "frame_path": frame["path"],
        "frame_available": True,
        "frame_width": frame["width"],
        "frame_height": frame["height"],
        "frame_timestamp": candidate.get("frame_timestamp"),
        "board_last_seen": candidate.get("board_last_seen"),
        "year": int(str(clip.get("date") or "2026")[:4]),
        "video_url": f"{player}&meta_id={meta_id}",
        "agenda_url": clip.get("agenda_url"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--out", type=Path, default=STAGING_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    disk_guard.require_space("publish")

    results = json.loads((PASSPORT / "metadata" / f"votes_{args.clip}.json").read_text())
    catalog = json.loads((PASSPORT / "metadata" / f"clips_{args.year}.json").read_text())
    clip = next(c for c in catalog["clips"] if c["clip_id"] == args.clip)
    era = roster_mod.era_for(results["date"])

    frame_dir = REPO / "frame_images" / str(args.year) / str(args.clip)
    frame_dir.mkdir(parents=True, exist_ok=True)

    votes: list[dict] = []
    blocked: list[dict] = []
    for candidate in results["accepted"]:
        problems = recheck(candidate, era)
        if problems:
            blocked.append({"vote_id": candidate["vote_id"], "problems": problems})
            print(f"  BLOCKED {candidate['vote_id']}: {problems[0]}", file=sys.stderr)
            continue

        source = Path(candidate["frame_source"])
        if not source.exists():
            blocked.append(
                {"vote_id": candidate["vote_id"], "problems": [f"missing frame {source}"]}
            )
            print(f"  BLOCKED {candidate['vote_id']}: winning frame is gone", file=sys.stderr)
            continue

        dest = frame_dir / f"vote_{candidate['vote_id']}.jpg"
        with Image.open(source) as image:
            out = crop_overlay(image)
            if not args.dry_run:
                out.save(dest, format="JPEG", quality=92, optimize=True)
            size = out.size
        frame = {
            "path": str(dest.relative_to(REPO)),
            "width": size[0],
            "height": size[1],
        }
        votes.append(build_record(candidate, clip, era, frame))

    votes.sort(key=lambda v: v["video_timestamp"])

    meeting = {
        "id": str(clip["clip_id"]),
        "date": clip.get("date"),
        "title": f"Torrance City Council Meeting {clip.get('date')}",
        "video_url": f"https://torrance.granicus.com/player/clip/{clip['clip_id']}?view_id=8",
        "agenda_url": clip.get("agenda_url"),
        "verification": "verified",
        "source": "granicus_frame",
        "roster_era": era.key,
        "councilmembers": [
            {"name": m.name, "district": m.district, "role": m.role} for m in era.members
        ],
        "total_votes": len(votes),
        "passed_votes": sum(1 for v in votes if v["result"] == "passed"),
        "failed_votes": sum(1 for v in votes if v["result"] == "failed"),
        "tie_votes": sum(1 for v in votes if v["result"] == "tie"),
        "scan": {
            "frames_scanned": results.get("frames_scanned"),
            "sampling_fps": 1.0,
            "coverage": "whole clip, 0s to end of video",
            "parser_mode": results.get("parser_mode"),
            "gemini_api_key_present": results.get("gemini_api_key_present"),
        },
    }

    audit_path = PASSPORT / "metadata" / f"vote_events_{args.clip}.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        meeting["scan"]["result_boards_on_video"] = audit["result_boards"]
        meeting["scan"]["result_boards_captured"] = len(votes)
        # A vote whose result panel never aired cannot be recovered by any
        # parser, so it is recorded rather than silently absent.
        meeting["scan"]["votes_with_no_result_board_broadcast"] = [
            {"in_progress_start": e["start"], "in_progress_end": e["end"]}
            for e in audit.get("unbroadcast_votes", [])
        ]

    existing = {"votes": [], "meetings": {}}
    if args.out.exists():
        existing = json.loads(args.out.read_text())
    by_id = {v["id"]: v for v in existing.get("votes", [])}
    for vote in votes:
        by_id[vote["id"]] = vote
    meetings = existing.get("meetings", {})
    meetings[meeting["id"]] = meeting

    payload = {
        "schema": "torrance-vote-viewer/staging-votes/1",
        "note": (
            "Verified 2026 votes read from Granicus VoteCast result frames. "
            "Staging only: not merged into data/torrance_votes_smart_consolidated.json."
        ),
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "votes": sorted(by_id.values(), key=lambda v: (v["meeting_id"], v["video_timestamp"])),
        "meetings": dict(sorted(meetings.items())),
        "total_votes": len(by_id),
        "total_meetings": len(meetings),
        "blocked_at_publish": blocked,
        "rejected_by_detector": {
            meeting["id"]: [
                {
                    "video_timestamp": r["video_timestamp"],
                    "agenda_item": r.get("agenda_item"),
                    "problems": r["problems"],
                }
                for r in results.get("rejected", [])
            ]
        },
    }

    print(f"clip {args.clip}: {len(votes)} published, {len(blocked)} blocked at publish")
    for vote in votes:
        tally = vote["vote_tally"]
        print(
            f"  {vote['id']} t={vote['video_timestamp']}s "
            f"{tally['ayes']}-{tally['noes']}-{tally['abstentions']}-{tally['recused']} "
            f"{vote['result']} -> {vote['frame_path']}"
        )

    if args.dry_run:
        print(f"[dry-run] would write {args.out}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2))
    print(f"wrote {args.out}: {len(by_id)} votes, {len(meetings)} meetings")
    print(disk_guard.report("publish"))
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
