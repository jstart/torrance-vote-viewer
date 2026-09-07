#!/usr/bin/env python3
"""Publish detected votes into the data file the viewer actually reads.

Takes the output of detect_and_parse_votes.py (a per-clip JSON with `accepted`
and `rejected` candidate lists) and does two things:

  1. Copies each published vote's board crop into `frame_images/<year>/` under a
     name derived from its vote_id, so `frame_path` in the JSON resolves to a
     real file. Only board crops are copied - never anything out of `frames/`,
     which holds tens of thousands of full-resolution stills.

  2. Merges the votes and their meeting into
     `data/torrance_votes_smart_consolidated.json`, keyed on vote_id, after
     taking a timestamped backup. Re-running updates in place.

Accepted candidates with no problems are published `verified`. Rejected
candidates and anything carrying a problem are published `needs_review`, because
a vote the detector could not fully read is still a vote that happened — except:

  - non-votable agenda binds (recess / reconvene / close public hearing / none
    scheduled): skipped entirely (timestamp-to-agenda join slipped)
  - board candidates with zero individual votes: skipped (nothing to show)
  - unreadable-member inventions (member listed as unreadable but still assigned
    a YES/NO): skipped until re-detect omits that member

Oral ASR attributions always publish as `needs_review`.

Records this script did not write are left alone; in particular no pre-existing
`verification` value is ever changed.

    python3 pipeline/publish_votes.py
    python3 pipeline/publish_votes.py --input /path/to/votes_14821.json --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = disk_guard.PASSPORT_ROOT / "metadata" / "votes_14821.json"
CONSOLIDATED_RELPATH = Path("data") / "torrance_votes_smart_consolidated.json"

# Marks the records this script owns, so a re-run may overwrite them while
# leaving the 2024-2025 import untouched.
SOURCE = "granicus_frame"
ORAL_PROBLEM = "oral attribution from clerk speech; not board OCR"

# An agenda item that only exists to say nothing was scheduled, or to mark a
# break in the meeting, can never be the subject of a vote. A vote bound to one
# means the detector's timestamp-to-agenda join slipped.
NON_VOTABLE_TITLE = re.compile(
    r"none\s+scheduled|\brecess\b|\breconvene\b|close\s+public\s+hearing",
    re.IGNORECASE,
)
UNREADABLE_MEMBER_RE = re.compile(
    r"vote value unreadable for:\s*(.+)$", re.IGNORECASE
)

# Known bad bindings, confirmed against the agenda, that the guard would
# otherwise only be able to flag. Keyed by (clip_id, video_timestamp).
#
# The 14821 entry no longer fires: the detector was fixed on 2026-09-04 to bind
# this vote to 451763 itself. It is kept because it still applies when an older
# detect output is republished, e.g. metadata/votes_14821_baseline.json.
BINDING_CORRECTIONS = {
    ("14821", 18822): {
        "meta_id": "451763",
        "agenda_item": "10A. Accept and File Economic Development Update",
    },
}

RESULT_WORDS = (("tie", "tie"), ("fail", "failed"), ("pass", "passed"))


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def agenda_item_text(value) -> str:
    """Flatten an agenda item to a plain string.

    The 2024-2025 import stores this as either a string or a
    {number, description, ...} object; the viewer has to special-case both. New
    records are always strings.
    """
    if isinstance(value, dict):
        for key in ("description", "title", "number"):
            if value.get(key):
                return str(value[key]).strip()
        return ""
    return str(value or "").strip()


def normalize_result(parsed: dict) -> tuple[str | None, list[str]]:
    """Reduce a parsed result line to passed / failed / tie.

    Returns None plus a problem when the line cannot be reduced, rather than
    guessing from the tally: a board whose result line was unreadable is exactly
    the kind of record a human needs to look at.
    """
    for field in ("result", "result_raw"):
        text = str(parsed.get(field) or "").lower()
        for needle, normalized in RESULT_WORDS:
            if needle in text:
                return normalized, []
    return None, ["result could not be normalized to passed/failed/tie"]


def is_non_votable_title(title: str | None) -> bool:
    return bool(NON_VOTABLE_TITLE.search(str(title or "")))


def resolve_binding(clip_id: str, candidate: dict) -> dict:
    """Decide which agenda item a vote belongs to.

    Returns the fields to publish plus any guard problem. A known-bad binding is
    corrected and annotated; an unknown non-votable bind is flagged and later
    skipped by should_skip_publish (guessing the real item is worse).
    """
    original_item = agenda_item_text(candidate.get("agenda_item"))
    original_meta = candidate.get("meta_id")
    binding = {
        "agenda_item": original_item,
        "meta_id": str(original_meta) if original_meta is not None else None,
        "problems": [],
        "extra": {},
        "non_votable": False,
    }

    if not is_non_votable_title(original_item):
        return binding

    correction = BINDING_CORRECTIONS.get((clip_id, int(candidate["video_timestamp"])))
    if not correction:
        binding["non_votable"] = True
        binding["problems"].append(
            f'agenda binding is a non-votable item ("{original_item}"); '
            "the vote's true agenda item is unknown"
        )
        return binding

    binding["agenda_item"] = correction["agenda_item"]
    binding["meta_id"] = correction["meta_id"]
    binding["extra"] = {
        "binding_corrected": True,
        "binding_note": (
            f'Detector bound this vote to "{original_item}", which is not a votable '
            f'item. Re-bound to "{correction["agenda_item"]}" '
            f'(meta_id {correction["meta_id"]}).'
        ),
        "original_agenda_item": original_item,
        "original_meta_id": str(original_meta) if original_meta is not None else None,
    }
    return binding


def unreadable_members_still_voted(problems: list, individual_votes: dict) -> list[str]:
    """Members flagged unreadable who still have a YES/NO/ABSTAIN/RECUSE row."""
    bad: list[str] = []
    for problem in problems or []:
        match = UNREADABLE_MEMBER_RE.search(str(problem))
        if not match:
            continue
        for raw in re.split(r",\s*", match.group(1).strip()):
            name = raw.strip()
            if name and name in (individual_votes or {}):
                bad.append(name)
    return sorted(set(bad))


def should_skip_publish(record: dict, *, non_votable: bool = False) -> str | None:
    """Return a skip reason, or None if the record may be merged into the site."""
    if non_votable or is_non_votable_title(record.get("agenda_item")):
        return "non_votable_agenda_bind"
    parser = str(record.get("parser") or "")
    is_oral = (
        parser in ("oral_asr_unanimous", "oral_asr_clerk")
        or any("oral attribution" in str(p) for p in (record.get("problems") or []))
    )
    individuals = record.get("individual_votes") or {}
    if not is_oral and len(individuals) == 0:
        return "empty_individual_votes"
    invented = unreadable_members_still_voted(
        record.get("problems") or [], individuals
    )
    if invented:
        return f"unreadable_member_invented:{','.join(invented)}"
    return None


def build_vote_record(candidate: dict, results: dict, accepted: bool, frame_relpath: str) -> dict:
    """Shape one candidate into the vote object the viewer renders."""
    clip_id = str(results["clip_id"])
    parsed = candidate["parsed"]
    binding = resolve_binding(clip_id, candidate)
    result, result_problems = normalize_result(parsed)

    problems = list(candidate.get("problems") or [])
    if any("normalize" in problem for problem in problems):
        # The detector already reported the unreadable result line in its own words.
        result_problems = []
    for extra in binding["problems"] + result_problems:
        if extra not in problems:
            problems.append(extra)

    meta_id = binding["meta_id"]
    player_url = f"https://torrance.granicus.com/player/clip/{clip_id}"
    tally = parsed.get("vote_tally") or {}

    record = {
        "id": candidate["vote_id"],
        "vote_id": candidate["vote_id"],
        "meeting_id": clip_id,
        "agenda_item": binding["agenda_item"],
        "meta_id": meta_id,
        "video_timestamp": int(candidate["video_timestamp"]),
        "timestamp": int(candidate["video_timestamp"]),
        "timestamp_estimated": False,
        # The viewer sorts a meeting's votes by frame_number and labels the still
        # with it. These clips have no meeting-wide frame numbering, so leave it
        # null (the sort is stable, and votes are merged in timestamp order).
        "frame_number": None,
        "frame_path": frame_relpath,
        "frame_available": False,
        "vote_tally": {
            "ayes": int(tally.get("ayes") or 0),
            "noes": int(tally.get("noes") or 0),
            "abstentions": int(tally.get("abstentions") or 0),
            "recused": int(tally.get("recused") or 0),
        },
        "result": result,
        "result_raw": parsed.get("result_raw"),
        "motion_text": "",
        "individual_votes": {
            name: str(choice).upper() for name, choice in (parsed.get("individual_votes") or {}).items()
        },
        "absent_members": list(candidate.get("absent_members") or []),
        "roster_complete": bool(candidate.get("roster_complete")),
        "roster_era": results.get("roster_era"),
        "year": int(results.get("year") or str(results.get("date", ""))[:4]),
        "verification": "verified" if accepted and not problems else "needs_review",
        "problems": problems,
        "detect_status": "accepted" if accepted else "rejected",
        "sequence": candidate.get("sequence"),
        "frame_count_in_cluster": candidate.get("frame_count_in_cluster"),
        "sharpness": candidate.get("sharpness"),
        "parser": parsed.get("parser"),
        # Kept so a reviewer can see what the board actually said without
        # re-running OCR.
        "ocr_text": parsed.get("ocr_text"),
        "video_url": player_url,
        "agenda_url": f"https://torrance.granicus.com/GeneratedAgendaViewer.php?view_id=8&clip_id={clip_id}",
        "source": SOURCE,
    }
    # Oral ASR attributions are never board-verified, even if problem list is empty.
    if (
        parsed.get("source") == "oral_asr"
        or parsed.get("parser") in ("oral_asr_unanimous", "oral_asr_clerk")
        or candidate.get("vote_source_policy") == "oral_asr"
        or candidate.get("format") == "oral"
    ):
        record["verification"] = "needs_review"
        if ORAL_PROBLEM not in record["problems"]:
            record["problems"] = list(record["problems"]) + [ORAL_PROBLEM]
    record.update(binding["extra"])
    record["_non_votable"] = bool(binding.get("non_votable"))
    return record


def build_meeting_record(results: dict, votes: list[dict]) -> dict:
    clip_id = str(results["clip_id"])
    year = str(results.get("year") or "")
    return {
        "id": clip_id,
        "title": f"City Council Meeting {clip_id}{f' ({year})' if year else ''}",
        "date": results.get("date"),
        "video_url": f"https://torrance.granicus.com/player/clip/{clip_id}",
        "agenda_url": f"https://torrance.granicus.com/GeneratedAgendaViewer.php?view_id=8&clip_id={clip_id}",
        "total_votes": len(votes),
        "passed_votes": sum(1 for v in votes if v["result"] == "passed"),
        "failed_votes": sum(1 for v in votes if v["result"] == "failed"),
        "tie_votes": sum(1 for v in votes if v["result"] == "tie"),
        "needs_review_votes": sum(1 for v in votes if v["verification"] == "needs_review"),
        "summary": meeting_summary_text(results, votes),
        "year": year,
        "roster_era": results.get("roster_era"),
        # The meeting itself was rebuilt from the Granicus video, so it is
        # verified. Votes inside it carry their own verification state.
        "verification": "verified",
        "source": SOURCE,
    }


def meeting_summary_text(results: dict, votes: list[dict]) -> str:
    verified = sum(1 for v in votes if v["verification"] == "verified")
    review = len(votes) - verified
    text = (
        f"City Council meeting of {results.get('date')}, rebuilt from the Granicus video. "
        f"{len(votes)} vote board{'s' if len(votes) != 1 else ''} captured across "
        f"{results.get('frames_scanned', 0):,} scanned frames: {verified} verified"
    )
    if review:
        text += f" and {review} flagged for human review"
    return text + "."


def build_meeting_summary(results: dict, votes: list[dict]) -> dict:
    """Optional card the viewer shows above a meeting's vote list."""
    aspects = []
    verified = [v for v in votes if v["verification"] == "verified"]
    review = [v for v in votes if v["verification"] == "needs_review"]
    if verified:
        aspects.append(f"{len(verified)} votes read off the on-screen vote board")
    if review:
        aspects.append(f"{len(review)} votes flagged for human review")
    if any(v.get("binding_corrected") for v in votes):
        aspects.append("One agenda-item binding corrected at publish time")

    return {
        "summary": meeting_summary_text(results, votes),
        "unique_aspects": aspects,
        "key_items": [v["agenda_item"] for v in verified if v["agenda_item"]],
        "generated_by": "pipeline/publish_votes.py",
    }


def publish_frames(votes: list[dict], candidates: dict, frame_dir: Path, dry_run: bool) -> dict:
    """Copy board crops into the repo and set frame_available from what landed.

    frame_available is only ever true for a file this function can see on disk,
    so the viewer's "No frame image on file" placeholder stays honest.
    """
    counts = {"copied": 0, "unchanged": 0, "missing_source": 0}
    if not dry_run:
        frame_dir.mkdir(parents=True, exist_ok=True)

    for vote in votes:
        crop = candidates[vote["id"]].get("board_crop")
        if not crop:
            # Oral ASR votes have no board crop; publish text-only.
            counts["missing_source"] += 1
            vote["frame_available"] = False
            continue
        source = Path(crop)
        dest = frame_dir / Path(vote["frame_path"]).name

        if not source.is_file():
            counts["missing_source"] += 1
            print(f"  ! board crop missing, publishing without image: {source}")
            continue

        # Compare contents, not size: a detect re-run regenerates the crops, and
        # a new crop of the same board can land on the same byte count.
        if dest.is_file() and file_digest(dest) == file_digest(source):
            counts["unchanged"] += 1
        elif dry_run:
            counts["copied"] += 1
        else:
            shutil.copy2(source, dest)
            counts["copied"] += 1

        vote["frame_available"] = dry_run or (dest.is_file() and dest.stat().st_size > 0)

    return counts


def prune_stale_votes(data: dict, clip_id: str, incoming: set[str]) -> list[dict]:
    """Drop votes this script published for a clip that the detector no longer reports.

    A detect re-run can renumber a clip's vote ids - it rebinds an agenda item and
    the meta_id embedded in the id moves with it - so merging on id alone would
    leave the old record behind as a phantom vote. Only records this script owns,
    for this clip, are ever dropped.
    """
    existing = data.setdefault("votes", [])
    stale = [
        vote for vote in existing
        if vote.get("source") == SOURCE
        and vote.get("meeting_id") == clip_id
        and vote.get("id") not in incoming
    ]
    if stale:
        stale_ids = {vote["id"] for vote in stale}
        data["votes"] = [vote for vote in existing if vote.get("id") not in stale_ids]
        for vote in stale:
            print(f"  - dropping stale published vote {vote['id']} (no longer detected)")
    return stale


def prune_frames(frame_dir: Path, clip_id: str, incoming: set[str], dry_run: bool) -> int:
    """Delete board crops left behind by a previous publish of the same clip."""
    if not frame_dir.is_dir():
        return 0

    removed = 0
    for image in sorted(frame_dir.glob(f"{clip_id}_*.jpg")):
        if image.stem in incoming:
            continue
        print(f"  - removing orphaned image {image.name}")
        if not dry_run:
            image.unlink()
        removed += 1
    return removed


def merge_votes(data: dict, votes: list[dict]) -> dict:
    """Merge on vote id, keeping this clip's votes contiguous and in video order.

    The viewer sorts a meeting's votes by frame_number, which these records leave
    null, so their order in the file is the order they render in.
    """
    counts = {"added": 0, "updated": 0, "skipped": 0}
    existing = data.setdefault("votes", [])
    index = {v.get("id"): v for v in existing if v.get("id")}

    publishable = []
    for vote in sorted(votes, key=lambda v: v["video_timestamp"]):
        previous = index.get(vote["id"])
        if previous is None:
            counts["added"] += 1
        elif previous.get("source") != SOURCE:
            # Something else already claims this id. Publishing over it would
            # change a record's verification, which is not ours to do.
            print(
                f"  ! {vote['id']} already exists and was not published by this "
                f"script (verification={previous.get('verification')!r}); left alone"
            )
            counts["skipped"] += 1
            continue
        else:
            counts["updated"] += 1
        publishable.append(vote)

    # Splice the block back in where it already sat, so the legacy import keeps
    # the order it has always had.
    ids = {vote["id"] for vote in publishable}
    kept = [vote for vote in existing if vote.get("id") not in ids]
    first = next((i for i, v in enumerate(existing) if v.get("id") in ids), None)
    position = len(kept) if first is None else sum(1 for v in existing[:first] if v.get("id") not in ids)
    data["votes"] = kept[:position] + publishable + kept[position:]

    return counts


def merge_meeting(data: dict, meeting: dict) -> str:
    meetings = data.setdefault("meetings", {})
    previous = meetings.get(meeting["id"])
    prev_source = (previous or {}).get("source")
    # Take over legacy import rows (no source / pre-pipeline). Never overwrite a
    # meeting owned by a different publisher.
    if previous and prev_source and prev_source != SOURCE:
        print(
            f"  ! meeting {meeting['id']} already exists and was not published by "
            f"this script (verification={previous.get('verification')!r}); left alone"
        )
        return "skipped"

    meetings[meeting["id"]] = meeting
    return "updated" if previous else "added"


def refresh_councilmembers(data: dict, votes: list[dict]) -> list[str]:
    """Register the names that voted and recount only those members.

    Stats for names this clip does not touch are left byte-identical, so a
    publish can never silently restate the legacy councilmembers' totals.
    """
    names = sorted({name for vote in votes for name in vote["individual_votes"]})
    roster = data.setdefault("councilmembers", [])
    added = [name for name in names if name not in roster]
    roster.extend(added)

    stats = data.setdefault("councilmember_stats", {})
    for name in names:
        choices = [
            v["individual_votes"][name]
            for v in data.get("votes", [])
            if name in (v.get("individual_votes") or {})
        ]
        stats[name] = {
            "total_votes": len(choices),
            "yes_votes": choices.count("YES"),
            "no_votes": choices.count("NO"),
            "abstentions": choices.count("ABSTAIN"),
            "recused": choices.count("RECUSE"),
        }

    return added


def backup(path: Path) -> Path:
    destination = path.parent / "backup" / f"backup_before_publish_votes_{time.strftime('%Y%m%d_%H%M%S')}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="detect_and_parse_votes.py output JSON")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--dry-run", action="store_true", help="report what would change and write nothing")
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"no detect output at {args.input}")

    consolidated = args.repo_root / CONSOLIDATED_RELPATH
    if not consolidated.is_file():
        raise SystemExit(f"no consolidated data file at {consolidated}")

    print(disk_guard.report("publish:pre"))

    results = json.loads(args.input.read_text())
    clip_id = str(results["clip_id"])
    year = str(results.get("year") or str(results.get("date", ""))[:4])
    frame_reldir = Path("frame_images") / year

    candidates = {}
    votes = []
    skipped = []
    for accepted, group in ((True, "accepted"), (False, "rejected")):
        for candidate in results.get(group) or []:
            frame_relpath = str(frame_reldir / f"{candidate['vote_id']}.jpg")
            vote = build_vote_record(candidate, results, accepted, frame_relpath)
            reason = should_skip_publish(
                vote, non_votable=bool(vote.pop("_non_votable", False))
            )
            if reason:
                skipped.append({"id": vote["id"], "reason": reason})
                print(f"  skip {vote['id']}: {reason}")
                continue
            candidates[vote["id"]] = candidate
            votes.append(vote)

    if not votes and not skipped:
        raise SystemExit(f"{args.input} has no accepted or rejected candidates")
    if not votes:
        print(
            f"{args.input}: all {len(skipped)} candidate(s) skipped "
            f"({', '.join(sorted({s['reason'] for s in skipped}))})"
        )
        # Still prune stale published votes for this clip when everything is skipped.
        data = json.loads(consolidated.read_text())
        stale = prune_stale_votes(data, clip_id, set())
        if stale and not args.dry_run:
            saved = backup(consolidated)
            data["total_votes"] = len(data["votes"])
            data["total_meetings"] = len(data["meetings"])
            metadata = data.setdefault("metadata", {})
            metadata["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            metadata["total_votes"] = data["total_votes"]
            consolidated.write_text(json.dumps(data, indent=2) + "\n")
            print(f"dropped {len(stale)} stale vote(s); backed up to {saved.relative_to(args.repo_root)}")
        elif stale:
            print(f"[dry-run] would drop {len(stale)} stale vote(s)")
        return 0

    votes.sort(key=lambda v: v["video_timestamp"])

    incoming = {vote["id"] for vote in votes}
    frame_dir = args.repo_root / frame_reldir
    frames = publish_frames(votes, candidates, frame_dir, args.dry_run)
    frames["orphans_removed"] = prune_frames(frame_dir, clip_id, incoming, args.dry_run)
    meeting = build_meeting_record(results, votes)

    data = json.loads(consolidated.read_text())
    stale = prune_stale_votes(data, clip_id, incoming)
    vote_counts = merge_votes(data, votes)
    vote_counts["dropped"] = len(stale)
    meeting_state = merge_meeting(data, meeting)
    new_names = refresh_councilmembers(data, votes)

    summaries = data.setdefault("meeting_summaries", {})
    previous_summary = summaries.get(clip_id)
    if not previous_summary or previous_summary.get("generated_by") == "pipeline/publish_votes.py":
        summaries[clip_id] = build_meeting_summary(results, votes)

    data["total_votes"] = len(data["votes"])
    data["total_meetings"] = len(data["meetings"])
    metadata = data.setdefault("metadata", {})
    metadata["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    metadata["total_votes"] = data["total_votes"]
    metadata["total_meetings"] = data["total_meetings"]
    metadata["years_included"] = sorted({v["year"] for v in data["votes"] if v.get("year")})
    metadata["last_publish"] = {"clip_id": clip_id, "input": str(args.input), "votes": len(votes)}

    print(f"\nclip {clip_id} ({results.get('date')}, roster era {results.get('roster_era')})")
    for vote in votes:
        tally = vote["vote_tally"]
        print(
            f"  {vote['id']:<18} t={vote['video_timestamp']:<6} "
            f"{tally['ayes']}-{tally['noes']}-{tally['abstentions']}-{tally['recused']} "
            f"{str(vote['result']):<8} {vote['verification']:<12} "
            f"image={'yes' if vote['frame_available'] else 'NO'}  {vote['agenda_item'][:60]}"
        )
        for problem in vote["problems"]:
            print(f"      - {problem}")
        if vote.get("binding_corrected"):
            print(f"      * {vote['binding_note']}")

    flagged = [v for v in votes if any("non-votable item" in p for p in v["problems"])]
    print(
        f"\nagenda-binding guard: {len(BINDING_CORRECTIONS)} known correction(s) available, "
        f"{sum(1 for v in votes if v.get('binding_corrected'))} applied, "
        f"{len(flagged)} unrecognized non-votable binding(s) flagged for review"
    )
    print(
        f"votes: {vote_counts['added']} added, {vote_counts['updated']} updated, "
        f"{vote_counts['dropped']} dropped, {vote_counts['skipped']} skipped  |  "
        f"meeting {meeting['id']}: {meeting_state}"
    )
    print(
        f"frames -> {frame_reldir}/: {frames['copied']} copied, {frames['unchanged']} unchanged, "
        f"{frames['orphans_removed']} orphan(s) removed, {frames['missing_source']} source(s) missing"
    )
    if new_names:
        print(f"councilmembers registered: {', '.join(new_names)}")
    print(
        f"verification: {sum(1 for v in votes if v['verification'] == 'verified')} verified, "
        f"{sum(1 for v in votes if v['verification'] == 'needs_review')} needs_review"
    )

    if args.dry_run:
        print(f"\n[dry-run] {consolidated} not written")
    else:
        saved = backup(consolidated)
        consolidated.write_text(json.dumps(data, indent=2) + "\n")
        print(f"\nbacked up to {saved.relative_to(args.repo_root)}")
        print(f"wrote {consolidated.relative_to(args.repo_root)}: {data['total_votes']} votes, {data['total_meetings']} meetings")

    print(disk_guard.report("publish:post"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
