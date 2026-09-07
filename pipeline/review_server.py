#!/usr/bin/env python3
"""Local review UI for unpublished detect JSON on the Passport.

Serves review.html and exposes Passport board crops so a human can confirm
that the agenda item, vote frame, and parsed results match — without copying
bulk media into the git repo or touching GitHub Pages.

    .venv/bin/python pipeline/review_server.py
    open http://127.0.0.1:8765/

Decisions land on the Passport at metadata/review_decisions.json. This server
never calls publish_votes.py.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard

REPO_ROOT = disk_guard.REPO_ROOT
PASSPORT = disk_guard.PASSPORT_ROOT
META = PASSPORT / "metadata"
DECISIONS_PATH = META / "review_decisions.json"
STATIC_FILES = {
    "/": REPO_ROOT / "review.html",
    "/review.html": REPO_ROOT / "review.html",
    "/review.js": REPO_ROOT / "review.js",
    "/review.css": REPO_ROOT / "review.css",
}

# Only serve images that live under these Passport trees.
ALLOWED_IMAGE_ROOTS = (
    PASSPORT / "crops",
    PASSPORT / "crops_hq",
    PASSPORT / "frames.noindex",
    PASSPORT / "scratch",
)

DEFAULT_CONTEXT_PAD = 30
CAPTION_CACHE_TTL_S = 3600
_CAPTION_CACHE: dict[str, tuple[float, dict]] = {}
_CLIP_INDEX: dict[str, dict] | None = None
_TS_RE = re.compile(
    r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\s*-->\s*"
    r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?"
)


def load_decisions() -> dict:
    if not DECISIONS_PATH.exists():
        return {"decisions": {}}
    return json.loads(DECISIONS_PATH.read_text())


def save_decisions(payload: dict) -> None:
    META.mkdir(parents=True, exist_ok=True)
    tmp = DECISIONS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(DECISIONS_PATH)


def iter_vote_files() -> list[Path]:
    if not META.exists():
        return []
    files = []
    for path in sorted(META.glob("votes_*.json")):
        name = path.name
        # Skip experimental duplicates when a canonical file exists, but still
        # surface uniquely named review outputs and verified-only files.
        if name.endswith("_baseline.json"):
            continue
        files.append(path)
    return files


def candidate_from_record(
    record: dict,
    *,
    clip_id: str,
    year: int | None,
    date: str | None,
    roster_era: str | None,
    source_file: str,
    detect_status: str,
) -> dict:
    parsed = record.get("parsed") or {}
    tally = parsed.get("vote_tally") or {}
    return {
        "vote_id": record.get("vote_id"),
        "clip_id": clip_id,
        "year": year,
        "date": date,
        "roster_era": roster_era,
        "source_file": source_file,
        "detect_status": detect_status,
        "sequence": record.get("sequence"),
        "format": record.get("format"),
        "video_timestamp": record.get("video_timestamp"),
        "board_last_seen": record.get("board_last_seen"),
        "agenda_item": record.get("agenda_item"),
        "meta_id": record.get("meta_id"),
        "agenda_time": record.get("agenda_time"),
        "board_crop": record.get("board_crop"),
        "frame_source": record.get("frame_source"),
        "result": parsed.get("result"),
        "result_raw": parsed.get("result_raw"),
        "vote_tally": tally,
        "individual_votes": parsed.get("individual_votes") or {},
        "absent_members": record.get("absent_members") or [],
        "problems": record.get("problems") or [],
        "parser": parsed.get("parser"),
    }


def load_candidates() -> list[dict]:
    out: list[dict] = []
    for path in iter_vote_files():
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        clip_id = str(data.get("clip_id") or "")
        year = data.get("year")
        date = data.get("date")
        roster_era = data.get("roster_era")
        for status, key in (("accepted", "accepted"), ("rejected", "rejected")):
            for record in data.get(key) or []:
                out.append(
                    candidate_from_record(
                        record,
                        clip_id=clip_id,
                        year=year,
                        date=date,
                        roster_era=roster_era,
                        source_file=path.name,
                        detect_status=status,
                    )
                )
    out.sort(
        key=lambda c: (
            -(c.get("year") or 0),
            c.get("date") or "",
            c.get("clip_id") or "",
            c.get("sequence") if c.get("sequence") is not None else 999,
        )
    )
    return out


def safe_image_path(raw: str) -> Path | None:
    if not raw:
        return None
    path = Path(raw).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for root in ALLOWED_IMAGE_ROOTS:
        try:
            resolved.relative_to(root.resolve())
            return resolved if resolved.is_file() else None
        except ValueError:
            continue
    return None


def _vtt_clock_to_seconds(
    hours: str | None, minutes: str, seconds: str, millis: str | None
) -> float:
    h = int(hours or 0)
    m = int(minutes)
    s = int(seconds)
    ms = int((millis or "0").ljust(3, "0")[:3])
    return h * 3600 + m * 60 + s + ms / 1000.0


def parse_vtt(text: str) -> list[dict]:
    """Parse WEBVTT into cue dicts with start/end seconds and text."""
    cues: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = [ln.strip("\ufeff") for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        # Drop optional cue identifier line preceding the timestamp.
        ts_line = lines[0]
        payload_start = 1
        if "-->" not in ts_line and len(lines) > 1 and "-->" in lines[1]:
            ts_line = lines[1]
            payload_start = 2
        match = _TS_RE.search(ts_line)
        if not match:
            continue
        start = _vtt_clock_to_seconds(
            match.group(1), match.group(2), match.group(3), match.group(4)
        )
        end = _vtt_clock_to_seconds(
            match.group(5), match.group(6), match.group(7), match.group(8)
        )
        body = " ".join(lines[payload_start:]).strip()
        if not body:
            continue
        cues.append({"start": start, "end": end, "text": body})
    return cues


def load_clip_index() -> dict[str, dict]:
    global _CLIP_INDEX
    if _CLIP_INDEX is not None:
        return _CLIP_INDEX
    index: dict[str, dict] = {}
    if not META.exists():
        _CLIP_INDEX = index
        return index
    for path in sorted(META.glob("clips_*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for clip in data.get("clips") or []:
            clip_id = str(clip.get("clip_id") or "")
            if clip_id:
                index[clip_id] = clip
    _CLIP_INDEX = index
    return index


def fetch_caption_cues(clip: dict) -> dict:
    """Return caption cues for a clip, caching empty and nonempty results."""
    clip_id = str(clip.get("clip_id") or "")
    url = clip.get("captions_url") or ""
    now = time.time()
    cached = _CAPTION_CACHE.get(clip_id)
    if cached and now - cached[0] < CAPTION_CACHE_TTL_S:
        return cached[1]

    result = {
        "available": False,
        "source_url": url or None,
        "cue_count": 0,
        "cues": [],
        "note": None,
    }
    if not url:
        result["note"] = "No captions URL in catalog"
        _CAPTION_CACHE[clip_id] = (now, result)
        return result

    req = urllib.request.Request(url, headers={"User-Agent": "TorranceVoteReview/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result["note"] = f"Failed to fetch captions: {exc}"
        _CAPTION_CACHE[clip_id] = (now, result)
        return result

    cues = parse_vtt(raw)
    if not cues:
        result["note"] = "Granicus captions file is empty for this meeting"
        _CAPTION_CACHE[clip_id] = (now, result)
        return result

    result["available"] = True
    result["cue_count"] = len(cues)
    result["cues"] = cues
    _CAPTION_CACHE[clip_id] = (now, result)
    return result


def agenda_window(clip: dict, t: float, pad: float, bound_meta_id: str | None) -> list[dict]:
    """Agenda cuepoints in [t-pad, t+pad], plus neighbors and the bound item."""
    agenda = clip.get("agenda") or []
    start = max(0.0, t - pad)
    end = t + pad

    def row_for(item: dict, **flags) -> dict:
        try:
            item_t = float(item.get("time") or 0)
        except (TypeError, ValueError):
            item_t = 0.0
        return {
            "time": item_t,
            "meta_id": item.get("meta_id"),
            "title": item.get("title") or "",
            "votable": bool(item.get("votable")),
            "bound": str(item.get("meta_id") or "") == str(bound_meta_id or ""),
            "delta": round(item_t - t, 1),
            **flags,
        }

    in_window: list[dict] = []
    before = None
    after = None
    bound_item = None
    for item in agenda:
        try:
            item_t = float(item.get("time") or 0)
        except (TypeError, ValueError):
            continue
        if bound_meta_id and str(item.get("meta_id") or "") == str(bound_meta_id):
            bound_item = item
        if item_t < start:
            before = item
        elif start <= item_t <= end:
            in_window.append(row_for(item))
        elif item_t > end and after is None:
            after = item

    out: list[dict] = []
    seen: set[str] = set()

    def add(row: dict) -> None:
        key = str(row.get("meta_id") or "") + "@" + str(row.get("time"))
        if key in seen:
            return
        seen.add(key)
        out.append(row)

    if before:
        add(row_for(before, preceding=True))
    for row in in_window:
        add(row)
    if after:
        add(row_for(after, following=True))
    if bound_item:
        try:
            bound_t = float(bound_item.get("time") or 0)
        except (TypeError, ValueError):
            bound_t = 0.0
        if not (start <= bound_t <= end):
            add(row_for(bound_item, outside_window=True))

    out.sort(key=lambda r: (r.get("time") or 0, str(r.get("meta_id") or "")))
    return out


def build_context(
    clip_id: str,
    t: float,
    pad: float = DEFAULT_CONTEXT_PAD,
    bound_meta_id: str | None = None,
    *,
    asr: bool = False,
) -> dict:
    clip = load_clip_index().get(str(clip_id))
    if not clip:
        return {
            "ok": False,
            "error": f"clip {clip_id} not found in catalog",
            "clip_id": clip_id,
            "t": t,
            "pad": pad,
        }

    import transcribe_window as asr_mod

    audio_start, audio_end, first_agenda = asr_mod.clamped_audio_window(
        t, pad, clip.get("agenda")
    )
    # Display window matches the audio window (may start later than t-pad when
    # the vote is near the top of the meeting).
    start, end = audio_start, audio_end
    captions = fetch_caption_cues(clip)
    source = "granicus"
    note = captions.get("note")
    window_cues = [
        c
        for c in captions.get("cues") or []
        if c["end"] >= start and c["start"] <= end
    ]
    asr_status = None
    skipped_before_agenda = start > max(0.0, t - pad) and first_agenda > 0

    if captions.get("available") and window_cues:
        pass
    else:
        # Prefer Passport cache; optionally run whisper when Granicus is empty.
        cached = asr_mod.load_cached(str(clip_id), start, end)
        if cached and cached.get("cues"):
            window_cues = cached["cues"]
            source = "local_whisper"
            note = cached.get("note")
            asr_status = "cached"
            skipped_before_agenda = bool(cached.get("skipped_before_agenda"))
        elif asr:
            try:
                local = asr_mod.transcribe_window(clip, t, pad)
                window_cues = local.get("cues") or []
                source = "local_whisper"
                note = local.get("note")
                asr_status = "generated"
                skipped_before_agenda = bool(local.get("skipped_before_agenda"))
            except Exception as exc:  # noqa: BLE001 — surface to the review UI
                note = f"Local ASR failed: {exc}"
                asr_status = "error"
                source = "none"
        else:
            asr_status = "missing"
            if not note:
                note = "Granicus captions empty — local ASR not loaded yet"
            source = "none"

    if len(window_cues) > 200:
        window_cues = window_cues[:200]

    return {
        "ok": True,
        "clip_id": clip_id,
        "t": t,
        "pad": pad,
        "window": {"start": start, "end": end},
        "first_agenda_time": first_agenda,
        "skipped_before_agenda": skipped_before_agenda,
        "bound_meta_id": bound_meta_id,
        "agenda": agenda_window(clip, t, pad, bound_meta_id),
        "captions": {
            "available": bool(window_cues),
            "source": source,
            "source_url": captions.get("source_url"),
            "note": note,
            "asr_status": asr_status,
            "total_cues": len(window_cues),
            "cues": window_cues,
        },
        "video_url": (
            f"https://torrance.granicus.com/player/clip/{clip_id}"
            f"?view_id=8&t={max(0, int(start))}"
        ),
    }


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "TorranceReview/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: object) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in STATIC_FILES:
            file_path = STATIC_FILES[path]
            if not file_path.exists():
                self._send(404, b"missing static file", "text/plain")
                return
            data = file_path.read_bytes()
            ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self._send(200, data, ctype)
            return

        if path == "/api/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "passport": disk_guard.passport_available(),
                    "metadata": str(META),
                    "decisions": str(DECISIONS_PATH),
                },
            )
            return

        if path == "/api/candidates":
            decisions = load_decisions().get("decisions") or {}
            rows = load_candidates()
            year = (qs.get("year") or [None])[0]
            clip = (qs.get("clip") or [None])[0]
            fmt = (qs.get("format") or [None])[0]
            status = (qs.get("detect_status") or [None])[0]
            review = (qs.get("review") or [None])[0]
            filtered = []
            for row in rows:
                if year and str(row.get("year")) != str(year):
                    continue
                if clip and str(row.get("clip_id")) != str(clip):
                    continue
                if fmt and str(row.get("format") or "").upper() != fmt.upper():
                    continue
                if status and row.get("detect_status") != status:
                    continue
                decision = decisions.get(row["vote_id"]) if row.get("vote_id") else None
                row = dict(row)
                row["decision"] = decision
                if review == "undecided" and decision:
                    continue
                if review in ("accepted", "needs_review", "rejected"):
                    if not decision or decision.get("status") != review:
                        continue
                filtered.append(row)
            self._send_json(
                200,
                {
                    "count": len(filtered),
                    "total": len(rows),
                    "candidates": filtered,
                },
            )
            return

        if path == "/api/decisions":
            self._send_json(200, load_decisions())
            return

        if path == "/api/image":
            raw = (qs.get("path") or [""])[0]
            image_path = safe_image_path(raw)
            if image_path is None:
                self._send(404, b"image not found or not allowed", "text/plain")
                return
            data = image_path.read_bytes()
            ctype = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
            self._send(200, data, ctype)
            return

        if path == "/api/context":
            clip = (qs.get("clip") or [""])[0].strip()
            try:
                t = float((qs.get("t") or ["0"])[0])
            except ValueError:
                self._send_json(400, {"ok": False, "error": "t must be a number"})
                return
            try:
                pad = float((qs.get("pad") or [str(DEFAULT_CONTEXT_PAD)])[0])
            except ValueError:
                self._send_json(400, {"ok": False, "error": "pad must be a number"})
                return
            pad = max(5.0, min(pad, 180.0))
            meta_id = (qs.get("meta_id") or [None])[0]
            asr_flag = (qs.get("asr") or ["0"])[0].strip().lower() in (
                "1",
                "true",
                "yes",
            )
            if not clip:
                self._send_json(400, {"ok": False, "error": "clip required"})
                return
            self._send_json(
                200, build_context(clip, t, pad, meta_id, asr=asr_flag)
            )
            return

        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/decisions":
            self._send(404, b"not found", "text/plain")
            return
        try:
            body = self._read_json()
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid json"})
            return
        vote_id = str(body.get("vote_id") or "").strip()
        status = str(body.get("status") or "").strip()
        note = str(body.get("note") or "").strip()
        if not vote_id or status not in ("accepted", "needs_review", "rejected", "clear"):
            self._send_json(
                400,
                {
                    "error": "vote_id and status "
                    "(accepted|needs_review|rejected|clear) required"
                },
            )
            return
        payload = load_decisions()
        decisions = payload.setdefault("decisions", {})
        if status == "clear":
            decisions.pop(vote_id, None)
        else:
            decisions[vote_id] = {
                "status": status,
                "note": note,
                "source_file": body.get("source_file"),
                "clip_id": body.get("clip_id"),
            }
        save_decisions(payload)
        self._send_json(200, {"ok": True, "decision": decisions.get(vote_id)})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if not disk_guard.passport_available():
        print("warning: Passport not mounted; candidate list may be empty", file=sys.stderr)

    httpd = ThreadingHTTPServer((args.host, args.port), ReviewHandler)
    print(f"review server on http://{args.host}:{args.port}/")
    print(f"decisions -> {DECISIONS_PATH}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
