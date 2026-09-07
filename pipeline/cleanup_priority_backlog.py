#!/usr/bin/env python3
"""One-shot P0–P3 cleanup: unpublish bad site rows, taxonomy residuals, notes.

    .venv/bin/python pipeline/cleanup_priority_backlog.py
    .venv/bin/python pipeline/cleanup_priority_backlog.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard
import publish_votes as pub

REPO = disk_guard.REPO_ROOT
META = disk_guard.work_dir("metadata")
CONSOLIDATED = REPO / "data" / "torrance_votes_smart_consolidated.json"

P0_IDS = {
    "14286_379056_9",
    "13410_279391_1",
    "14319_380979_9",
    "14595_416987_5",
}

NON_VOTABLE_AGENDA = re.compile(
    r"none\s+scheduled|\brecess\b|\breconvene\b|close\s+public\s+hearing",
    re.I,
)

RESIDUAL_EMPTY = [
    "14282",
    "14318",
    "14340",
    "14360",
    "14385",
    "14435",
    "14482",
]
NON_COUNCIL_CLIPS = frozenset({"14588"})
ORAL_DEDUPE_MEETINGS = frozenset({"14718", "14405"})


def backup(data: dict) -> Path:
    dest = (
        REPO
        / "data"
        / "backup"
        / f"backup_before_priority_cleanup_{time.strftime('%Y%m%d_%H%M%S')}.json"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data))
    return dest


def is_oral(vote: dict) -> bool:
    parser = str(vote.get("parser") or "")
    return parser in ("oral_asr_unanimous", "oral_asr_clerk") or any(
        "oral attribution" in str(p) for p in (vote.get("problems") or [])
    )


def remove_reason(vote: dict) -> str | None:
    vid = vote.get("id") or vote.get("vote_id")
    if vid in P0_IDS:
        return "p0_known_bad"
    if NON_VOTABLE_AGENDA.search(str(vote.get("agenda_item") or "")):
        return "non_votable_agenda"
    invented = pub.unreadable_members_still_voted(
        vote.get("problems") or [], vote.get("individual_votes") or {}
    )
    if invented:
        return f"unreadable_invented:{','.join(invented)}"
    if (
        not is_oral(vote)
        and vote.get("verification") == "needs_review"
        and len(vote.get("individual_votes") or {}) == 0
    ):
        return "empty_individual_votes"
    return None


def recount_meetings(data: dict) -> None:
    by_meet: dict[str, list[dict]] = defaultdict(list)
    for vote in data.get("votes") or []:
        by_meet[str(vote.get("meeting_id"))].append(vote)
    meetings = data.setdefault("meetings", {})
    for mid, meeting in list(meetings.items()):
        votes = by_meet.get(str(mid), [])
        meeting["total_votes"] = len(votes)
        meeting["passed_votes"] = sum(1 for v in votes if v.get("result") == "passed")
        meeting["failed_votes"] = sum(1 for v in votes if v.get("result") == "failed")
        meeting["tie_votes"] = sum(1 for v in votes if v.get("result") == "tie")
        meeting["needs_review_votes"] = sum(
            1 for v in votes if v.get("verification") == "needs_review"
        )
        if not votes and meeting.get("source") != pub.SOURCE:
            # Leave granicus meetings even at 0 so republish can refill; drop
            # orphan import stubs with no votes.
            if meeting.get("verification") == "unverified" or not meeting.get("source"):
                del meetings[mid]


def oral_dedupe_ids(votes: list[dict]) -> set[str]:
    """Keep earlier oral vote when same meeting+meta within 120s and same tally."""
    drop: set[str] = set()
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for vote in votes:
        if not is_oral(vote):
            continue
        mid = str(vote.get("meeting_id") or "")
        if mid not in ORAL_DEDUPE_MEETINGS:
            continue
        meta = str(vote.get("meta_id") or "")
        groups[(mid, meta)].append(vote)
    for group in groups.values():
        group.sort(key=lambda v: int(v.get("video_timestamp") or 0))
        for prev, cur in zip(group, group[1:]):
            dt = abs(
                int(cur.get("video_timestamp") or 0)
                - int(prev.get("video_timestamp") or 0)
            )
            if dt > 120:
                continue
            if prev.get("vote_tally") == cur.get("vote_tally") and prev.get(
                "result"
            ) == cur.get("result"):
                drop.add(str(cur.get("id") or cur.get("vote_id")))
    return drop


def classify_residual(clip_id: str, data: dict) -> dict:
    existing = data.get("coverage_status") or {}
    if clip_id in NON_COUNCIL_CLIPS:
        return {
            "status": "excluded",
            "reason": "non_council_civil_service",
            "hunt_mode": existing.get("hunt_mode"),
            "note": "Torrance Civil Service Commission — not City Council.",
        }
    if clip_id == "14340":
        return {
            "status": "empty",
            "reason": "no_votable_sections",
            "hunt_mode": existing.get("hunt_mode"),
        }
    # Heuristic from agenda titles in clips catalogs.
    year = data.get("year")
    agenda = []
    for y in ([year] if year else range(2024, 2027)):
        path = META / f"clips_{y}.json"
        if not path.is_file():
            continue
        for clip in json.loads(path.read_text()).get("clips") or []:
            if str(clip.get("clip_id")) == str(clip_id):
                agenda = clip.get("agenda") or []
                break
    titles = " ".join(str(a.get("title") or "") for a in agenda).lower()
    if any(
        key in titles
        for key in (
            "public employee",
            "closed session",
            "closed hearing",
            "discipline/dismissal",
            "performance evaluation",
            "conference with legal",
        )
    ):
        reason = "closed_or_personnel_session"
    else:
        reason = "no_public_vote_speech"
    return {
        "status": "empty",
        "reason": reason,
        "hunt_mode": existing.get("hunt_mode") or "section_end",
        "vote_hits": (existing.get("vote_hits") or 0),
        "note": "No further ASR scheduled; classify rather than keep hunting.",
    }


def repair_passport_unreadable(report: dict) -> None:
    """Strip invented member rows from passport candidates that still invent."""
    repaired = []
    for path in META.glob("votes_*.json"):
        if "_transcript" in path.name or "_review" in path.name or "queue" in path.name:
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        changed = False
        for group in ("accepted", "rejected"):
            for cand in data.get(group) or []:
                parsed = cand.get("parsed") or {}
                votes = dict(parsed.get("individual_votes") or {})
                invented = pub.unreadable_members_still_voted(
                    cand.get("problems") or [], votes
                )
                if not invented:
                    # Also parse problem text on nested parsed problems
                    invented = pub.unreadable_members_still_voted(
                        parsed.get("problems") or cand.get("problems") or [], votes
                    )
                if not invented:
                    continue
                for name in invented:
                    votes.pop(name, None)
                parsed["individual_votes"] = votes
                cand["parsed"] = parsed
                changed = True
                repaired.append(
                    {
                        "file": path.name,
                        "vote_id": cand.get("vote_id"),
                        "stripped": invented,
                    }
                )
        if changed:
            path.write_text(json.dumps(data, indent=2) + "\n")
    report["passport_stripped"] = repaired


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = json.loads(CONSOLIDATED.read_text())
    before = len(data.get("votes") or [])
    removed: list[dict] = []
    kept: list[dict] = []

    dedupe_drop = oral_dedupe_ids(data.get("votes") or [])

    for vote in data.get("votes") or []:
        vid = str(vote.get("id") or vote.get("vote_id"))
        reason = remove_reason(vote)
        if not reason and vid in dedupe_drop:
            reason = "oral_near_duplicate"
        if reason:
            removed.append({"id": vid, "reason": reason, "meeting_id": vote.get("meeting_id")})
            continue
        kept.append(vote)

    data["votes"] = kept
    recount_meetings(data)
    data["total_votes"] = len(kept)
    data["total_meetings"] = len(data.get("meetings") or {})

    metadata = data.setdefault("metadata", {})
    metadata["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    metadata["total_votes"] = data["total_votes"]
    metadata["total_meetings"] = data["total_meetings"]
    metadata["years_included"] = sorted(
        {v["year"] for v in kept if v.get("year")}
    )
    metadata["coverage_notes"] = {
        "year_2020": (
            "Sparse on purpose: COVID Zoom-era meetings often lack Voting Results "
            "boards and have few usable transcript hunts. Site count is expected "
            "to stay low until/unless oral ASR is expanded for 2020."
        ),
        "priority_cleanup": time.strftime("%Y-%m-%d"),
    }
    metadata["priority_cleanup"] = {
        "removed": len(removed),
        "before": before,
        "after": len(kept),
    }

    residual_updates = {}
    for clip_id in list(RESIDUAL_EMPTY) + list(NON_COUNCIL_CLIPS):
        path = META / f"votes_{clip_id}.json"
        if not path.is_file():
            residual_updates[clip_id] = {"error": "missing"}
            continue
        payload = json.loads(path.read_text())
        payload["coverage_status"] = classify_residual(clip_id, payload)
        residual_updates[clip_id] = payload["coverage_status"]
        if not args.dry_run:
            path.write_text(json.dumps(payload, indent=2) + "\n")

    report = {
        "before": before,
        "after": len(kept),
        "removed": removed,
        "removed_by_reason": {},
        "residuals": residual_updates,
        "oral_dedupe_ids": sorted(dedupe_drop),
    }
    for row in removed:
        report["removed_by_reason"][row["reason"]] = (
            report["removed_by_reason"].get(row["reason"], 0) + 1
        )

    if not args.dry_run:
        saved = backup(data)
        CONSOLIDATED.write_text(json.dumps(data, indent=2) + "\n")
        repair_passport_unreadable(report)
        report_path = META / "cleanup_priority_backlog_report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"backup {saved}")
        print(f"wrote {CONSOLIDATED} votes {before}->{len(kept)}")
        print(f"report {report_path}")
    else:
        print(f"[dry-run] would remove {len(removed)} of {before}")
    print("by reason:", report["removed_by_reason"])
    print("oral dedupe", sorted(dedupe_drop))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
