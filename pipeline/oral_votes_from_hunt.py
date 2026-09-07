#!/usr/bin/env python3
"""Convert transcript-hunt hits into oral-attributed vote candidates.

Oral / no-board meetings (mid-2018 through early 2024) have no Voting Results
slides. Whisper hunts find clerk phrases like "Start voting, please" /
"motion carried unanimously". This script attributes member votes from clerk
outcome formulas:

  - unanimous / carried (of present)
  - named absentees excluded
  - named "voting no" / "abstaining" exceptions (needs_review)

Contested numeric tallies and roll-call readings are never invented.

    .venv/bin/python pipeline/oral_votes_from_hunt.py --clip 13552 --year 2019
    .venv/bin/python pipeline/oral_votes_from_hunt.py --clip 13552 --year 2019 --dry-run

Writes/merges Passport metadata/votes_{clip}.json. Oral candidates always carry
a problem note so publish_votes.py emits verification=needs_review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import detect_and_parse_votes as detect
import disk_guard
import roster as roster_mod

META = disk_guard.work_dir("metadata")

ORAL_PROBLEM = "oral attribution from clerk speech; not board OCR"
ORAL_EXCEPTION_PROBLEM = "oral clerk exceptions: named no/abstain from speech"
START_RE = re.compile(r"\bstart\s+voting\b|\bplease\s+vote\b|\bvoting\s+is\s+open\b", re.I)
PASS_RE = re.compile(
    r"\bmotion\s+carr(?:ied|ies)\b|\bmotion\s+pass(?:ed|es)\b|"
    r"\bthat\s+motion\s+carr(?:ied|ies)\b|\bunanimous(?:ly)?\b",
    re.I,
)
FAIL_RE = re.compile(r"\bmotion\s+fail(?:ed|s)\b|\bmotion\s+is\s+defeated\b", re.I)
UNANIMOUS_RE = re.compile(r"\bunanimous(?:ly)?\b", re.I)
# Numeric contested tallies — refuse. Named no/abstain is handled separately.
TALLY_RE = re.compile(r"\b\d\s*[-–to]+\s*\d\b", re.I)
NAMED_NO_HINT = re.compile(r"\bvoting\s+no\b|\bvotes?\s+no\b", re.I)
NAMED_ABS_HINT = re.compile(r"\babstain(?:ed|ing|s)?\b", re.I)
RECUSE_HINT = re.compile(r"\brecus(?:e|ed|ing)\b", re.I)
ABSENT_RE = re.compile(
    r"(?:council\s*members?|councilmembers?|mayor)\s+"
    r"([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+)?)"
    r"\s+absent",
    re.I,
)
ABSENT_CLAUSE_RE = re.compile(
    r"(?:council\s*members?|councilmembers?|mayor).{0,60}\babsent\b",
    re.I,
)
# Capture the name list before "voting no" / "abstaining".
NO_CLAUSE_RE = re.compile(
    r"(?:council\s*members?|councilmembers?|mayor)\s+"
    r"(.+?)\s+vot(?:es?|ing)\s+no\b",
    re.I,
)
ABSTAIN_CLAUSE_RE = re.compile(
    r"(?:council\s*members?|councilmembers?|mayor)\s+"
    r"(.+?)\s+abstain(?:ed|ing|s)?\b",
    re.I,
)
ATTENDANCE_ONLY_RE = re.compile(
    r"\b(?:may we have a |ask for a |call the meeting.*?)"
    r"roll\s+call\b|\broll\s+call\s*,?\s*please\b",
    re.I,
)
NON_VOTABLE_TITLE = re.compile(
    r"none\s+scheduled|\brecess\b|\breconvene\b|close\s+public\s+hearing",
    re.I,
)
# Common Whisper mangling → roster surname keys.
ASR_SURNAME_FIX = {
    "matuci": "mattucci",
    "matucci": "mattucci",  # one-t ASR vs roster Mattucci
    "matici": "mattucci",
    "matuki": "mattucci",
    "metici": "mattucci",
    "maducci": "mattucci",
    "hearing": "herring",
    "harring": "herring",
    "chin": "chen",
    "griffith": "griffiths",
    "fury": "furey",
    "currie": "furey",
    "theory": "furey",
    "goodridge": "goodrich",
}


def load_clip(year: int, clip_id: str) -> dict:
    path = META / f"clips_{year}.json"
    data = json.loads(path.read_text())
    for clip in data.get("clips") or []:
        if str(clip.get("clip_id")) == str(clip_id):
            return clip
    raise SystemExit(f"clip {clip_id} not in {path}")


def load_hunt(clip_id: str) -> dict:
    path = META / f"votes_{clip_id}_transcript_hunt.json"
    if not path.is_file():
        raise SystemExit(f"missing hunt sidecar {path}")
    return json.loads(path.read_text())


def is_attendance_only(text: str, start: float) -> bool:
    """Opening roll call / attendance — not a substantive vote."""
    if ATTENDANCE_ONLY_RE.search(text) and not PASS_RE.search(text) and not START_RE.search(text):
        return True
    if start < 400 and "roll call" in text.lower() and not PASS_RE.search(text):
        return True
    return False


def _normalize_token(token: str) -> str:
    key = re.sub(r"\s+", " ", token.strip().lower())
    key = re.split(r"[-–—,/]", key)[0].strip()
    # Strip possessive: griffith's → griffith
    key = re.sub(r"'s\b", "", key)
    key = key.strip()
    return key


def _resolve_member_token(token: str, era: roster_mod.Era) -> str | None:
    """Map a spoken name/surname token onto a roster full name."""
    surnames = era.by_surname()
    aliases = {k.lower(): v for k, v in (era.aliases or {}).items()}
    key = _normalize_token(token)
    if not key:
        return None
    surname = key.rsplit(" ", 1)[-1]
    surname = ASR_SURNAME_FIX.get(surname, surname)
    token_fixed = ASR_SURNAME_FIX.get(key, key)
    if key in aliases:
        return aliases[key]
    if token_fixed in aliases:
        return aliases[token_fixed]
    if surname in aliases:
        return aliases[surname]
    if surname in surnames:
        return surnames[surname].name
    full = {n.lower(): n for n in (m.name for m in era.members)}
    if key in full:
        return full[key]
    if token_fixed in full:
        return full[token_fixed]
    return None


def _split_name_list(chunk: str) -> list[str]:
    """Split 'Griffiths and Mattucci' / 'Chen, Mattucci' into tokens."""
    chunk = re.sub(r"\s+", " ", chunk.strip())
    # Drop leading filler the regex sometimes swallows.
    chunk = re.sub(r"^(?:with\s+)?", "", chunk, flags=re.I)
    parts = re.split(r"\s+and\s+|,\s*", chunk, flags=re.I)
    return [p.strip() for p in parts if p.strip() and p.strip().lower() not in {"with", "a", "the"}]


def match_absent_names(text: str, era: roster_mod.Era) -> list[str]:
    """Map spoken absentee phrases onto roster full names."""
    found: list[str] = []
    for m in ABSENT_RE.finditer(text):
        name = _resolve_member_token(m.group(1), era)
        if name and name not in found:
            found.append(name)
    return found


def parse_named_exceptions(text: str, era: roster_mod.Era) -> tuple[dict[str, str], list[str]]:
    """Return ({full_name: NO|ABSTAIN}, unresolved_raw_tokens)."""
    exceptions: dict[str, str] = {}
    unresolved: list[str] = []

    def absorb(clause_re: re.Pattern[str], value: str) -> None:
        for m in clause_re.finditer(text):
            for part in _split_name_list(m.group(1)):
                name = _resolve_member_token(part, era)
                if name:
                    # NO wins over ABSTAIN if both said (shouldn't happen).
                    if name not in exceptions or value == "NO":
                        exceptions[name] = value
                else:
                    unresolved.append(part)

    absorb(NO_CLAUSE_RE, "NO")
    absorb(ABSTAIN_CLAUSE_RE, "ABSTAIN")
    return exceptions, unresolved


def spoken_absentee_unresolved(text: str, era: roster_mod.Era) -> bool:
    """True when clerk named an on-roster absentee we failed to map.

    Ghost names for members who already left office (e.g. 'Herring absent'
    after resignation) are ignored so unanimous-of-present still attributes.
    """
    if not ABSENT_CLAUSE_RE.search(text):
        return False
    if match_absent_names(text, era):
        return False
    surnames = set(era.by_surname())
    alias_keys = {k.lower() for k in (era.aliases or {})}
    for m in ABSENT_RE.finditer(text):
        raw = _normalize_token(m.group(1))
        surname = ASR_SURNAME_FIX.get(raw.rsplit(" ", 1)[-1], raw.rsplit(" ", 1)[-1])
        if surname in surnames or surname in alias_keys:
            return True
    return False


def classify_outcome(text: str) -> str | None:
    """Return passed/failed for clerk outcome formulas (incl. named exceptions)."""
    if TALLY_RE.search(text):
        return None  # contested numeric tally — do not invent members
    if RECUSE_HINT.search(text) and not NAMED_NO_HINT.search(text) and not NAMED_ABS_HINT.search(text):
        # Recusal without a clear carried/unanimous formula — refuse for now.
        if not (PASS_RE.search(text) or "carried" in text.lower() or "carries" in text.lower()):
            return None
    if FAIL_RE.search(text) and not PASS_RE.search(text):
        # Failures without a clear unanimous-fail formula — refuse.
        return None
    if PASS_RE.search(text) or "carried" in text.lower() or "carries" in text.lower():
        return "passed"
    if UNANIMOUS_RE.search(text):
        return "passed"
    return None


def cluster_events(hits: list[dict], era: roster_mod.Era | None = None) -> list[dict]:
    """Group start-voting + nearby outcome hits into vote events."""
    usable = []
    for hit in hits:
        text = str(hit.get("text") or "")
        start = float(hit.get("start") or 0)
        if is_attendance_only(text, start):
            continue
        usable.append({"start": start, "end": float(hit.get("end") or start), "text": text})

    events: list[dict] = []
    i = 0
    while i < len(usable):
        h = usable[i]
        has_start = bool(START_RE.search(h["text"]))
        outcome = classify_outcome(h["text"])
        texts = [h["text"]]
        t0, t1 = h["start"], h["end"]
        j = i + 1
        # Pull following hits within 45s into the same event.
        while j < len(usable) and usable[j]["start"] - t0 < 45:
            nxt = usable[j]
            texts.append(nxt["text"])
            t1 = max(t1, nxt["end"])
            has_start = has_start or bool(START_RE.search(nxt["text"]))
            if outcome is None:
                outcome = classify_outcome(nxt["text"])
            j += 1
        blob = " | ".join(texts)
        if outcome is None:
            outcome = classify_outcome(blob)
        if outcome is None:
            i = j if j > i + 1 else i + 1
            continue
        # Prefer events that look like a vote cycle (start + outcome) or a clear
        # carried/unanimous line even without "start voting".
        if (
            not has_start
            and not UNANIMOUS_RE.search(blob)
            and "carried" not in blob.lower()
            and "carries" not in blob.lower()
        ):
            i = j if j > i + 1 else i + 1
            continue
        if era is not None and spoken_absentee_unresolved(blob, era):
            i = j if j > i + 1 else i + 1
            continue
        # Named no/abstain with unresolved on-roster-looking tokens → refuse.
        if era is not None and (NAMED_NO_HINT.search(blob) or NAMED_ABS_HINT.search(blob)):
            exceptions, unresolved = parse_named_exceptions(blob, era)
            if (NAMED_NO_HINT.search(blob) or NAMED_ABS_HINT.search(blob)) and not exceptions:
                i = j if j > i + 1 else i + 1
                continue
            if unresolved:
                # If any unresolved token looks like it should have matched, skip.
                surnames = set(era.by_surname())
                alias_keys = {k.lower() for k in (era.aliases or {})}
                bad = False
                for tok in unresolved:
                    sur = ASR_SURNAME_FIX.get(
                        _normalize_token(tok).rsplit(" ", 1)[-1],
                        _normalize_token(tok).rsplit(" ", 1)[-1],
                    )
                    if sur in surnames or sur in alias_keys or len(sur) >= 4:
                        bad = True
                        break
                if bad:
                    i = j if j > i + 1 else i + 1
                    continue
        events.append(
            {
                "start": t0,
                "end": t1,
                "text": blob,
                "result": outcome,
                "has_start": has_start,
            }
        )
        i = j if j > i + 1 else i + 1

    # De-dupe events within 25s (keep first).
    deduped: list[dict] = []
    for ev in events:
        if deduped and ev["start"] - deduped[-1]["start"] < 25:
            # merge text
            deduped[-1]["text"] += " | " + ev["text"]
            deduped[-1]["end"] = max(deduped[-1]["end"], ev["end"])
            continue
        deduped.append(ev)
    return deduped


def build_candidate(
    *,
    clip_id: str,
    seq: int,
    event: dict,
    era: roster_mod.Era,
    agenda: list[dict],
) -> dict | None:
    absent = match_absent_names(event["text"], era)
    exceptions, unresolved = parse_named_exceptions(event["text"], era)
    if unresolved and (NAMED_NO_HINT.search(event["text"]) or NAMED_ABS_HINT.search(event["text"])):
        return None
    if (NAMED_NO_HINT.search(event["text"]) or NAMED_ABS_HINT.search(event["text"])) and not exceptions:
        return None

    present = [m.name for m in era.members if m.name not in absent]
    votes: dict[str, str] = {name: "YES" if event["result"] == "passed" else "NO" for name in present}
    for name, value in exceptions.items():
        if name in absent:
            continue
        if name not in votes:
            # Named exception for someone not on era roster — refuse.
            return None
        votes[name] = value

    tally = {"ayes": 0, "noes": 0, "abstentions": 0, "recused": 0}
    for value in votes.values():
        if value == "YES":
            tally["ayes"] += 1
        elif value == "NO":
            tally["noes"] += 1
        elif value == "ABSTAIN":
            tally["abstentions"] += 1
        elif value == "RECUSE":
            tally["recused"] += 1

    binding = detect.bind_agenda_detail(agenda, event["start"], event["end"])
    agenda_item = binding.get("item") or {}
    title = str((agenda_item or {}).get("title") or "")
    if title and NON_VOTABLE_TITLE.search(title):
        return None
    problems = [ORAL_PROBLEM]
    problems.extend(binding.get("problems") or [])
    if exceptions:
        problems.append(ORAL_EXCEPTION_PROBLEM)
    if not agenda_item:
        problems.append("no agenda cuepoint at or before the vote timestamp")

    parser = "oral_asr_clerk" if exceptions else "oral_asr_unanimous"
    parsed = {
        "format": "oral",
        "parser": parser,
        "ocr_status": "n/a",
        "vote_tally": tally,
        "tally_problem": None,
        "result": event["result"],
        "result_raw": event["text"][:240],
        "individual_votes": votes,
        "vote_details": {},
        "vote_sources": {name: "oral_asr" for name in votes},
        "unresolved": [],
        "icon_conflicts": [],
        "ocr_text": event["text"],
        "source": "oral_asr",
    }
    return {
        "sequence": seq,
        "vote_id": f"{clip_id}_{(agenda_item or {}).get('meta_id', 'na')}_oral_{seq}",
        "video_timestamp": int(round(event["start"])),
        "board_last_seen": int(round(event["end"])),
        "frame_source": None,
        "frame_timestamp": int(round(event["start"])),
        "frame_count_in_cluster": 0,
        "format": "oral",
        "sharpness": 0.0,
        "board_crop": None,
        "agenda_item": (agenda_item or {}).get("title"),
        "meta_id": (agenda_item or {}).get("meta_id"),
        "agenda_time": (agenda_item or {}).get("time"),
        "agenda_candidates": {
            "before": (
                {
                    "meta_id": binding["before"]["meta_id"],
                    "time": binding["before"]["time"],
                    "title": binding["before"].get("title"),
                }
                if binding.get("before")
                else None
            ),
            "during_board": [],
            "boundary": [],
        },
        "absent_members": absent,
        "roster_complete": not absent and not exceptions,
        "parsed": parsed,
        "problems": problems,
        "vote_source_policy": "oral_asr",
    }


def empty_reason_for(hunt: dict, events: list[dict], hits: list[dict]) -> str | None:
    """Explain why hunt hits produced zero oral vote events."""
    if events:
        return None
    raw_hits = hits or hunt.get("hits") or []
    if not raw_hits:
        return "no_hunt_hits"
    if all(
        is_attendance_only(str(h.get("text") or ""), float(h.get("start") or 0))
        for h in raw_hits
    ):
        return "attendance_roll_call_only"
    if any(TALLY_RE.search(str(h.get("text") or "")) for h in raw_hits):
        return "contested_speech_not_attributed"
    if any(
        NAMED_NO_HINT.search(str(h.get("text") or "")) or NAMED_ABS_HINT.search(str(h.get("text") or ""))
        for h in raw_hits
    ):
        return "named_exceptions_unresolved"
    if any(PASS_RE.search(str(h.get("text") or "")) for h in raw_hits):
        return "outcome_speech_not_clustered"
    return "no_attributable_unanimous_events"


def _is_oral_candidate(c: dict) -> bool:
    parser = (c.get("parsed") or {}).get("parser")
    return (
        c.get("format") == "oral"
        or parser in ("oral_asr_unanimous", "oral_asr_clerk")
        or (c.get("parsed") or {}).get("source") == "oral_asr"
    )


def convert_clip(clip_id: str, year: int, dry_run: bool = False) -> dict:
    clip = load_clip(year, clip_id)
    hunt = load_hunt(clip_id)
    date = str(clip.get("date") or hunt.get("date") or f"{year}-01-01")
    era = roster_mod.era_for(date)
    hits = hunt.get("hits") or []
    events = cluster_events(hits, era=era)
    agenda = clip.get("agenda") or []

    existing_path = META / f"votes_{clip_id}.json"
    existing = json.loads(existing_path.read_text()) if existing_path.is_file() else None
    # Treat any non-oral accepted with a board_crop as board OCR.
    board_accepted = [
        c
        for c in (existing or {}).get("accepted") or []
        if c.get("board_crop") or (c.get("format") or "") in ("A", "B", "C", "format_a", "format_b", "format_c")
    ]
    if board_accepted:
        return {
            "clip_id": clip_id,
            "skipped": "has_board_accepted",
            "board_accepted": len(board_accepted),
            "events": len(events),
        }

    candidates = []
    for i, ev in enumerate(events):
        cand = build_candidate(
            clip_id=clip_id, seq=i, event=ev, era=era, agenda=agenda
        )
        if cand is not None:
            candidates.append(cand)
    # Keep non-oral rejected for audit; replace oral accepted.
    prior_rejected = [
        c for c in (existing or {}).get("rejected") or [] if not _is_oral_candidate(c)
    ]
    reason = empty_reason_for(hunt, events, hits)
    oral_convert = {
        "hunt_hits": int(hunt.get("vote_hits") or len(hits)),
        "events": len(events),
        "cue_source": hunt.get("cue_source"),
    }
    if reason:
        oral_convert["oral_empty_reason"] = reason
    payload = {
        "clip_id": str(clip_id),
        "year": int(year),
        "date": date,
        "roster_era": era.key,
        "roster_verified": era.verified,
        "roster_note": era.note,
        "roster": [m.name for m in era.members],
        "parser_mode": "oral_asr",
        "vote_source_policy": "oral_asr",
        "partial_board_policy": "absent",
        "frames_scanned": (existing or {}).get("frames_scanned") or 0,
        "frames_detected": (existing or {}).get("frames_detected") or 0,
        "candidates": len(candidates),
        "accepted": candidates,
        "rejected": prior_rejected,
        "oral_convert": oral_convert,
    }
    if reason:
        payload["oral_empty_reason"] = reason
    summary = {
        "clip_id": clip_id,
        "date": date,
        "era": era.key,
        "events": len(events),
        "accepted": len(candidates),
        "oral_empty_reason": reason,
        "absentees": sorted(
            {a for c in candidates for a in (c.get("absent_members") or [])}
        ),
        "exceptions": sorted(
            {
                f"{name}:{val}"
                for c in candidates
                for name, val in ((c.get("parsed") or {}).get("individual_votes") or {}).items()
                if val in ("NO", "ABSTAIN", "RECUSE")
            }
        ),
        "dry_run": dry_run,
    }
    if dry_run:
        summary["sample"] = [
            {
                "t": c["video_timestamp"],
                "result": c["parsed"]["result"],
                "tally": c["parsed"]["vote_tally"],
                "absent": c["absent_members"],
                "item": (c.get("agenda_item") or "")[:60],
            }
            for c in candidates[:5]
        ]
        return summary

    existing_path.write_text(json.dumps(payload, indent=2))
    summary["wrote"] = str(existing_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    disk_guard.require_space("oral_convert")
    summary = convert_clip(args.clip, args.year, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
