#!/usr/bin/env python3
"""Audit vote→agenda bindings using ±30s spoken transcript.

For each detect candidate, load (or generate) the review ASR/Granicus window and
score the bound agenda item against nearby cuepoints. Typical signal:

  "I will take a motion to waive further reading…"
  "Your Honor, that motion carried unanimously."   ← vote
  "Moving on to item five, council committee…"     ← next item

So a board that ends exactly when the next cuepoint fires is often still the
*previous* item — the transcript settles it.

    .venv/bin/python pipeline/audit_agenda_bindings.py
    .venv/bin/python pipeline/audit_agenda_bindings.py --cache-only
    .venv/bin/python pipeline/audit_agenda_bindings.py --clip 14632

Writes Passport metadata/agenda_binding_audit.json. Optionally marks undecided
review decisions as needs_review when the transcript disagrees with the bind.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard
import review_server
import transcribe_window as asr_mod

PAD = 30.0
AUDIT_PATH = disk_guard.PASSPORT_ROOT / "metadata" / "agenda_binding_audit.json"

STOPWORDS = frozenset(
    """
    a an the and or of to for in on at by from with after before about into over
    further reading resolutions ordinances number title motion waive approve
    adopt accept file city council item items meeting meetings matter matters
    discussion consider considered staff report public works community
    development services manager commission board none scheduled honor
    announcements announcement withdrawn deferred supplemental
    """.split()
)

ORDINALS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
}


def item_code(title: str) -> str | None:
    """Leading agenda code: '4', '10A', '8C', …"""
    m = re.match(r"^\s*([0-9]+[A-Za-z]?)\b", title or "")
    return m.group(1).upper() if m else None


def title_keywords(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    out = set()
    for w in words:
        if w in STOPWORDS or len(w) < 4:
            continue
        if w.isdigit():
            continue
        out.add(w)
    return out


def normalize_spoken_codes(text: str) -> set[str]:
    """Item codes mentioned in speech: 'item four', 'item 4', 'item 10A'."""
    found: set[str] = set()
    lower = text.lower()
    for word, num in ORDINALS.items():
        if re.search(rf"\bitem\s+{word}\b", lower):
            found.add(num)
        if re.search(rf"\bmoving on to (?:item\s+)?{word}\b", lower):
            found.add(num)
    for m in re.finditer(r"\bitem\s+([0-9]+[A-Za-z]?)\b", text, re.I):
        found.add(m.group(1).upper())
    for m in re.finditer(
        r"\bmoving on to (?:item\s+)?([0-9]+[A-Za-z]?)\b", text, re.I
    ):
        found.add(m.group(1).upper())
    return found


def _codes_in_text(text: str) -> list[str]:
    ordered: list[str] = []
    lower = text.lower()
    for m in re.finditer(
        r"\bitem\s+([0-9]+[A-Za-z]?|one|two|three|four|five|six|seven|"
        r"eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen)\b",
        lower,
    ):
        tok = m.group(1)
        ordered.append(ORDINALS.get(tok, tok.upper()))
    return ordered


_POST_VOTE_SPLIT = re.compile(
    r"(motion\s+carried|motion\s+passes|motion\s+passed|motion\s+fails|"
    r"that\s+motion\s+carries|unanimously\b|thank\s+you[,.]?\s+item)",
    re.I,
)


def codes_before_after(cues: list[dict], t: float) -> tuple[set[str], set[str]]:
    """Item codes spoken before vs at/after the vote.

    A single cue often contains both the result and the clerk opening the next
    item ("…carried unanimously thank you item 9e…"). Text after that split
    counts as after-vote even when cue.start is still slightly before t.
    """
    before: set[str] = set()
    after: set[str] = set()
    for cue in cues:
        text = str(cue.get("text") or "")
        start = float(cue.get("start") or 0)
        if start >= t:
            after.update(_codes_in_text(text))
            continue
        m = _POST_VOTE_SPLIT.search(text)
        if m:
            before.update(_codes_in_text(text[: m.start()]))
            after.update(_codes_in_text(text[m.start() :]))
        else:
            before.update(_codes_in_text(text))
    return before, after


def transition_codes_after(cues: list[dict], t: float, grace: float = 2.0) -> set[str]:
    """Codes introduced as the *next* item at/after the vote instant."""
    found: set[str] = set()
    for cue in cues:
        start = float(cue.get("start") or 0)
        text = str(cue.get("text") or "")
        m = _POST_VOTE_SPLIT.search(text)
        if start >= t:
            post = text
        elif m:
            post = text[m.start() :]
        else:
            continue
        if start > t + 30:
            continue
        lower_post = post.lower()
        is_transition = (
            "moving on" in lower_post
            or "next item" in lower_post
            or "staff presentation" in lower_post
            or re.search(r"\bthank you[,.]?\s+item\b", lower_post)
            or re.search(r"\bitem\s+[0-9]+[a-z]?\s+from the\b", lower_post)
            or re.search(r"\bitem\s+[0-9]+[a-z]?\s+is a\b", lower_post)
            or re.search(r"\bunanimously\b.*\bitem\b", lower_post)
        )
        if is_transition:
            found.update(_codes_in_text(post))
    return found


def vote_language_present(text: str) -> bool:
    lower = text.lower()
    needles = (
        "motion carried",
        "motion passes",
        "motion passed",
        "motion fails",
        "motion failed",
        "all in favor",
        "start voting",
        "please vote",
        "voting is open",
        "that passes",
        " unanimously",
    )
    return any(n in lower for n in needles)


def neighbor_items(clip: dict, t: float, bound_meta: str | None) -> list[dict]:
    """Agenda rows near the vote, including bound + immediate neighbors."""
    agenda = clip.get("agenda") or []
    rows: list[dict] = []
    before = None
    after = None
    for item in agenda:
        try:
            item_t = float(item.get("time") or 0)
        except (TypeError, ValueError):
            continue
        row = {
            "meta_id": str(item.get("meta_id") or ""),
            "time": item_t,
            "title": item.get("title") or "",
            "votable": bool(item.get("votable")),
            "code": item_code(item.get("title") or ""),
        }
        if bound_meta and row["meta_id"] == str(bound_meta):
            rows.append(row)
        if item_t < t - 0.05:
            before = row
        elif abs(item_t - t) <= PAD + 5:
            if row not in rows:
                rows.append(row)
        elif item_t > t and after is None:
            after = row
    if before and before["meta_id"] not in {r["meta_id"] for r in rows}:
        rows.append(before)
    if after and after["meta_id"] not in {r["meta_id"] for r in rows}:
        rows.append(after)
    for item in agenda:
        try:
            item_t = float(item.get("time") or 0)
        except (TypeError, ValueError):
            continue
        if abs(item_t - t) <= 2.5:
            row = {
                "meta_id": str(item.get("meta_id") or ""),
                "time": item_t,
                "title": item.get("title") or "",
                "votable": bool(item.get("votable")),
                "code": item_code(item.get("title") or ""),
            }
            if row["meta_id"] not in {r["meta_id"] for r in rows}:
                rows.append(row)
    rows.sort(key=lambda r: (r["time"], r["meta_id"]))
    return rows


def last_item_code_before(cues: list[dict], t: float) -> str | None:
    """Most recently spoken item code in the pre-result portion of the window."""
    last: str | None = None
    for cue in cues:
        start = float(cue.get("start") or 0)
        if start >= t:
            break
        text = str(cue.get("text") or "")
        m = _POST_VOTE_SPLIT.search(text)
        chunk = text[: m.start()] if m else text
        ordered = _codes_in_text(chunk)
        if ordered:
            last = ordered[-1]
    return last


def score_candidate(
    item: dict,
    *,
    transcript: str,
    cues: list[dict],
    t: float,
    codes_before: set[str],
    codes_after: set[str],
    transition_after: set[str],
    last_code_before: str | None,
) -> tuple[float, list[str]]:
    score = 0.0
    evidence: list[str] = []
    code = item.get("code")
    title = item.get("title") or ""
    item_t = float(item.get("time") or 0)

    if code and code in codes_before:
        score += 3.0
        evidence.append(f"spoken item {code} before vote")
    elif code and code in codes_after and code not in codes_before:
        score -= 3.0
        evidence.append(f"spoken item {code} only after vote (likely next)")

    if code and last_code_before and code == last_code_before:
        score += 2.5
        evidence.append(f"last item code before vote is {code}")
    elif code and last_code_before and code != last_code_before and code in codes_before:
        score -= 1.5
        evidence.append(f"earlier item {code} superseded by {last_code_before}")

    if code and code in transition_after:
        score -= 4.0
        evidence.append(f"transition to item {code} at/after vote (likely next)")

    if item_t <= t + 0.5:
        score += 1.0
        evidence.append("cuepoint at/before vote")
    else:
        score -= 0.5

    kws = title_keywords(title)
    if kws:
        pre_text = " ".join(
            str(c.get("text") or "")
            for c in cues
            if float(c.get("start") or 0) <= t + 2
        ).lower()
        hits = [w for w in kws if re.search(rf"\b{re.escape(w)}\b", pre_text)]
        if hits:
            score += min(3.0, 0.7 * len(hits))
            evidence.append("keywords: " + ", ".join(hits[:6]))

    compact = re.sub(r"^\s*[0-9]+[A-Za-z]?\.\s*", "", title)
    compact = re.sub(r"\s+", " ", compact).strip()
    if len(compact) >= 20:
        head = compact[:40].lower()
        pre_text = " ".join(
            str(c.get("text") or "")
            for c in cues
            if float(c.get("start") or 0) <= t + 2
        ).lower()
        if head.split(",")[0] and head.split(",")[0] in pre_text:
            score += 2.0
            evidence.append("title phrase overlap")

    return score, evidence


def get_transcript(
    clip: dict, t: float, *, cache_only: bool, force_asr: bool
) -> dict:
    """Return {cues, source, text, start, end, note}."""
    start, end, first = asr_mod.clamped_audio_window(t, PAD, clip.get("agenda"))
    clip_id = str(clip.get("clip_id") or "")

    # Granicus first when nonempty.
    url = clip.get("captions_url") or ""
    if url:
        req = urllib.request.Request(url, headers={"User-Agent": "TorranceAgendaAudit/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            all_cues = review_server.parse_vtt(raw)
            window = [
                c for c in all_cues if c["end"] >= start and c["start"] <= end
            ]
            if window:
                text = " ".join(c["text"] for c in window)
                return {
                    "cues": window,
                    "source": "granicus",
                    "text": text,
                    "start": start,
                    "end": end,
                    "note": None,
                }
        except (urllib.error.URLError, TimeoutError, OSError):
            pass

    cached = asr_mod.load_cached(clip_id, start, end)
    if cached and cached.get("cues"):
        cues = cached["cues"]
        return {
            "cues": cues,
            "source": "local_whisper",
            "text": " ".join(c["text"] for c in cues),
            "start": start,
            "end": end,
            "note": None,
        }

    if cache_only:
        return {
            "cues": [],
            "source": "none",
            "text": "",
            "start": start,
            "end": end,
            "note": "transcript not cached yet",
        }

    if force_asr or not cache_only:
        try:
            local = asr_mod.transcribe_window(clip, t, PAD)
            cues = local.get("cues") or []
            return {
                "cues": cues,
                "source": "local_whisper",
                "text": " ".join(c["text"] for c in cues),
                "start": start,
                "end": end,
                "note": local.get("note"),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "cues": [],
                "source": "none",
                "text": "",
                "start": start,
                "end": end,
                "note": f"ASR failed: {exc}",
            }

    return {
        "cues": [],
        "source": "none",
        "text": "",
        "start": start,
        "end": end,
        "note": "no transcript",
    }


def audit_vote(
    row: dict,
    clip: dict,
    *,
    cache_only: bool,
    force_asr: bool,
) -> dict:
    t = float(row.get("video_timestamp") or 0)
    bound_meta = str(row.get("meta_id") or "") or None
    bound_title = row.get("agenda_item") or ""
    transcript = get_transcript(clip, t, cache_only=cache_only, force_asr=force_asr)

    result = {
        "vote_id": row.get("vote_id"),
        "clip_id": row.get("clip_id"),
        "date": row.get("date"),
        "t": t,
        "bound_meta_id": bound_meta,
        "bound_title": bound_title,
        "detect_status": row.get("detect_status"),
        "problems": row.get("problems") or [],
        "transcript_source": transcript["source"],
        "window": {"start": transcript["start"], "end": transcript["end"]},
        "transcript_excerpt": (transcript["text"] or "")[:600],
    }

    if not bound_meta and not bound_title:
        result["verdict"] = "no_binding"
        result["reason"] = "no agenda item bound"
        return result

    if not transcript["text"].strip():
        result["verdict"] = "no_transcript"
        result["reason"] = transcript.get("note") or "empty transcript"
        return result

    spoken_codes = normalize_spoken_codes(transcript["text"])
    codes_before, codes_after = codes_before_after(transcript["cues"], t)
    transitions = transition_codes_after(transcript["cues"], t)
    last_code = last_item_code_before(transcript["cues"], t)
    candidates = neighbor_items(clip, t, bound_meta)
    scored = []
    for item in candidates:
        sc, ev = score_candidate(
            item,
            transcript=transcript["text"],
            cues=transcript["cues"],
            t=t,
            codes_before=codes_before,
            codes_after=codes_after,
            transition_after=transitions,
            last_code_before=last_code,
        )
        scored.append(
            {
                "meta_id": item["meta_id"],
                "code": item.get("code"),
                "time": item["time"],
                "title": item["title"],
                "score": round(sc, 2),
                "evidence": ev,
                "is_bound": item["meta_id"] == bound_meta,
            }
        )
    scored.sort(key=lambda s: (-s["score"], s["time"]))
    result["candidates"] = scored
    result["spoken_codes"] = sorted(spoken_codes)
    result["codes_before_vote"] = sorted(codes_before)
    result["codes_after_vote"] = sorted(codes_after)
    result["last_code_before_vote"] = last_code
    result["transition_after_vote"] = sorted(transitions)
    result["vote_language"] = vote_language_present(transcript["text"])

    bound_score = next((s for s in scored if s["is_bound"]), None)
    best = scored[0] if scored else None

    if not best:
        result["verdict"] = "ambiguous"
        result["reason"] = "no nearby agenda candidates"
        return result

    bound_sc = bound_score["score"] if bound_score else -99
    # Strong confirm: bound wins, or tied at top with vote language / spoken code.
    if bound_score and bound_score["meta_id"] == best["meta_id"] and bound_sc >= 1.5:
        result["verdict"] = "confirmed"
        result["reason"] = "; ".join(bound_score["evidence"] or ["bound scored highest"])
        return result

    if (
        bound_score
        and best["score"] - bound_sc < 1.25
        and bound_sc >= 0.5
        and result["vote_language"]
    ):
        result["verdict"] = "confirmed"
        result["reason"] = "bound competitive with vote language in window"
        return result

    # Transition to rival at vote time while bound is previous ⇒ confirm bound.
    rival_code = best.get("code")
    bound_code = item_code(bound_title)
    if (
        bound_score
        and rival_code
        and rival_code in transitions
        and bound_code
        and bound_code not in transitions
        and float(best["time"]) >= t - 0.5
    ):
        result["verdict"] = "confirmed"
        result["reason"] = (
            f"transcript moves on to item {rival_code} at/after vote; "
            f"bound {bound_code} is the item that was voted"
        )
        return result

    if best["meta_id"] != bound_meta and best["score"] >= bound_sc + 1.5 and best["score"] >= 2.0:
        result["verdict"] = "mismatch"
        result["suggested_meta_id"] = best["meta_id"]
        result["suggested_title"] = best["title"]
        result["reason"] = (
            f"transcript favors {best.get('code') or best['meta_id']} "
            f"(score {best['score']}) over bound "
            f"{bound_code or bound_meta} (score {bound_sc})"
        )
        return result

    result["verdict"] = "ambiguous"
    result["reason"] = (
        f"bound score {bound_sc}; best {best.get('code') or best['meta_id']} "
        f"score {best['score']}"
    )
    return result


def mark_review_decisions(audits: list[dict], *, write: bool) -> int:
    """Flag undecided mismatches/ambiguous-with-problems for human review."""
    if not write:
        return 0
    payload = review_server.load_decisions()
    decisions = payload.setdefault("decisions", {})
    marked = 0
    for row in audits:
        if row.get("verdict") not in ("mismatch", "ambiguous"):
            continue
        vote_id = row.get("vote_id")
        if not vote_id:
            continue
        existing = decisions.get(vote_id)
        if existing and existing.get("status") in ("accepted", "rejected"):
            continue
        if row["verdict"] == "ambiguous" and not row.get("problems"):
            continue
        note = f"transcript audit: {row['verdict']} — {row.get('reason')}"
        decisions[vote_id] = {
            "status": "needs_review",
            "note": note[:500],
            "source_file": "agenda_binding_audit",
            "clip_id": row.get("clip_id"),
        }
        marked += 1
    if marked:
        review_server.save_decisions(payload)
    return marked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", help="only this clip_id")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="do not call whisper; leave no_transcript when cache miss",
    )
    parser.add_argument(
        "--mark-review",
        action="store_true",
        help="write needs_review into review_decisions.json for mismatches",
    )
    args = parser.parse_args()

    if not disk_guard.passport_available():
        print("Passport not mounted", file=sys.stderr)
        return 1

    candidates = review_server.load_candidates()
    index = review_server.load_clip_index()
    if args.clip:
        candidates = [c for c in candidates if str(c.get("clip_id")) == args.clip]

    # Dedupe by vote_id (same vote can appear in multiple detect JSON files).
    by_id: dict[str, dict] = {}
    for row in candidates:
        vid = str(row.get("vote_id") or "")
        if not vid:
            continue
        prev = by_id.get(vid)
        if not prev or (
            prev.get("detect_status") != "accepted"
            and row.get("detect_status") == "accepted"
        ):
            by_id[vid] = row
    rows = list(by_id.values())
    rows.sort(
        key=lambda c: (
            c.get("date") or "",
            c.get("clip_id") or "",
            float(c.get("video_timestamp") or 0),
        )
    )
    if args.limit:
        rows = rows[: args.limit]

    print(f"auditing {len(rows)} votes…", flush=True)
    audits: list[dict] = []
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        clip = index.get(str(row.get("clip_id")))
        if not clip:
            audits.append(
                {
                    "vote_id": row.get("vote_id"),
                    "clip_id": row.get("clip_id"),
                    "verdict": "no_transcript",
                    "reason": "clip not in catalog",
                }
            )
            continue
        result = audit_vote(
            row, clip, cache_only=args.cache_only, force_asr=not args.cache_only
        )
        audits.append(result)
        if i % 25 == 0 or result.get("verdict") in ("mismatch",):
            print(
                f"  [{i}/{len(rows)}] {result.get('vote_id')} → {result.get('verdict')}"
                f" ({result.get('reason', '')[:80]})",
                flush=True,
            )

    counts = Counter(a.get("verdict") for a in audits)
    marked = mark_review_decisions(audits, write=args.mark_review)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pad_seconds": PAD,
        "counts": dict(counts),
        "marked_needs_review": marked,
        "audits": audits,
    }
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = AUDIT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(AUDIT_PATH)

    elapsed = time.time() - t0
    print(f"counts: {dict(counts)}")
    print(f"marked needs_review: {marked}")
    print(f"wrote {AUDIT_PATH} in {elapsed/60:.1f}m")

    # Print mismatches for immediate attention.
    mismatches = [a for a in audits if a.get("verdict") == "mismatch"]
    if mismatches:
        print(f"\n{len(mismatches)} mismatches:")
        for a in mismatches[:30]:
            print(
                f"  {a.get('vote_id')} t={a.get('t')} bound={a.get('bound_title', '')[:50]}"
            )
            print(f"    → suggest: {a.get('suggested_title', '')[:70]}")
            print(f"    {a.get('reason')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
