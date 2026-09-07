#!/usr/bin/env python3
"""Find likely vote-result moments from captions/ASR, then pull sample frames.

Used when detect finds nothing (older board formats, gate miss, etc.):

    .venv/bin/python pipeline/hunt_votes_from_transcript.py --clip 37 --year 2005
    .venv/bin/python pipeline/hunt_votes_from_transcript.py --clip 12849 --year 2016

Writes Passport scratch/vote_hunt_{clip}/ with:
  - hits.json (timestamps + cue text)
  - frame_{t}.jpg samples around each hit
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard
import review_server
import transcribe_window as asr_mod

USER_AGENT = asr_mod.USER_AGENT
REFERER = asr_mod.REFERER

VOTE_PATTERNS = [
    r"\bmotion\s+carried\b",
    r"\bmotion\s+passes\b",
    r"\bmotion\s+passed\b",
    r"\bmotion\s+fails\b",
    r"\bmotion\s+failed\b",
    r"\bmotion\s+is\s+adopted\b",
    r"\bmotion\s+is\s+approved\b",
    r"\bthat\s+motion\s+carries\b",
    r"\bthat\s+passes\b",
    r"\bso\s+ordered\b",
    r"\ball\s+in\s+favor\b",
    r"\ball\s+those\s+in\s+favor\b",
    r"\bayes\s+have\s+it\b",
    r"\bstart\s+voting\b",
    r"\bplease\s+vote\b",
    r"\bvoting\s+is\s+open\b",
    r"\bvoting\s+is\s+closed\b",
    # Bare "roll call" matches opening attendance; omit. Prefer clerk vote phrasing:
    r"\bclerk[,.]?\s+call\s+the\s+roll\b",
    r"\bunanimous(?:ly)?\b",
    r"\bwe(?:'ll| will)\s+take\s+a\s+(?:roll\s+call\s+)?vote\b",
    r"\bthe\s+vote\s+is\b",
    r"\bby\s+a\s+vote\s+of\b",
]
VOTE_RE = re.compile("|".join(VOTE_PATTERNS), re.I)


def load_clip(year: int, clip_id: str) -> dict:
    path = disk_guard.PASSPORT_ROOT / "metadata" / f"clips_{year}.json"
    data = json.loads(path.read_text())
    for clip in data.get("clips") or []:
        if str(clip.get("clip_id")) == str(clip_id):
            return clip
    raise SystemExit(f"clip {clip_id} not in {path}")


def load_caption_cues(clip: dict) -> list[dict]:
    url = clip.get("captions_url") or ""
    if not url:
        return []
    req = urllib.request.Request(url, headers={"User-Agent": "TorranceVoteHunt/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        cues = review_server.parse_vtt(raw)
        if cues:
            print(f"loaded {len(cues)} Granicus caption cues")
            return cues
        print("Granicus captions empty")
    except Exception as exc:  # noqa: BLE001
        print(f"captions fetch failed: {exc}", file=sys.stderr)
    return []


def load_asr_cues(clip: dict) -> list[dict]:
    """Whisper fallback when VTT is missing or has no vote-language hits."""
    # Short meetings: one ffmpeg+whisper pass from first agenda to end.
    duration = float(clip.get("duration") or 0)
    first = asr_mod.first_agenda_time(clip.get("agenda"))
    if duration and duration - first <= 45 * 60:
        print(
            f"ASR full meeting audio {first:.0f}s–{duration:.0f}s "
            f"(skip before first agenda)"
        )
        scratch = disk_guard.PASSPORT_ROOT / "scratch" / "asr"
        scratch.mkdir(parents=True, exist_ok=True)
        stem = f"{clip.get('clip_id')}_full_{int(first)}_{int(duration)}"
        wav = scratch / f"{stem}.wav"
        prefix = scratch / stem
        cache = (
            disk_guard.work_dir("metadata")
            / "asr_cache"
            / str(clip.get("clip_id"))
            / f"{int(first)}_{int(duration)}.json"
        )
        if cache.is_file():
            payload = json.loads(cache.read_text())
            return payload.get("cues") or []
        try:
            asr_mod.extract_wav(
                str(clip.get("hls_url") or ""),
                first,
                max(1.0, duration - first),
                wav,
            )
            raw = asr_mod.run_whisper(wav, prefix)
            cues = asr_mod._parse_whisper_json(raw, first)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps(
                    {
                        "available": bool(cues),
                        "source": "local_whisper",
                        "cues": cues,
                        "window": {"start": first, "end": duration},
                    },
                    indent=2,
                )
            )
            return cues
        finally:
            for path in (wav, Path(str(prefix) + ".json"), Path(str(prefix) + ".txt")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    print("ASR around votable agenda items (±90s)")
    agenda = [a for a in (clip.get("agenda") or []) if a.get("votable")]
    if not agenda:
        agenda = clip.get("agenda") or []
    all_cues: list[dict] = []
    seen = set()
    for item in agenda:
        t = float(item.get("time") or 0)
        try:
            local = asr_mod.transcribe_window(clip, t + 30, 90)
        except Exception as exc:  # noqa: BLE001
            print(f"  ASR fail near t={t}: {exc}", file=sys.stderr)
            continue
        for cue in local.get("cues") or []:
            key = (round(cue["start"], 1), cue["text"][:40])
            if key in seen:
                continue
            seen.add(key)
            all_cues.append(cue)
    all_cues.sort(key=lambda c: c["start"])
    return all_cues


def find_hits(cues: list[dict]) -> list[dict]:
    hits = []
    for cue in cues:
        text = str(cue.get("text") or "")
        if not VOTE_RE.search(text):
            continue
        hits.append(
            {
                "start": float(cue["start"]),
                "end": float(cue.get("end") or cue["start"]),
                "text": text.strip(),
            }
        )
    # Cluster hits within 8s
    clustered: list[dict] = []
    for hit in hits:
        if clustered and hit["start"] - clustered[-1]["start"] < 8:
            clustered[-1]["text"] += " | " + hit["text"]
            clustered[-1]["end"] = max(clustered[-1]["end"], hit["end"])
            continue
        clustered.append(dict(hit))
    return clustered


def load_cues(clip: dict, captions_only: bool = False) -> tuple[list[dict], str]:
    """Return (cues, source) where source is captions|asr|none.

    Non-empty Granicus VTTs are often commercial filler with zero vote
    language. Fall through to ASR unless --captions-only.
    """
    caption_cues = load_caption_cues(clip)
    if caption_cues and find_hits(caption_cues):
        return caption_cues, "captions"
    if caption_cues:
        print(
            f"captions had {len(caption_cues)} cues but 0 vote hits"
            + ("; skipping ASR" if captions_only else "; falling back to ASR")
        )
    if captions_only:
        print("captions-only: skipping ASR fallback")
        return caption_cues, ("captions" if caption_cues else "none")
    asr_cues = load_asr_cues(clip)
    if asr_cues:
        return asr_cues, "asr"
    return caption_cues, ("captions" if caption_cues else "none")


def grab_frame(hls_url: str, t: float, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        asr_mod.FFMPEG_BIN,
        "-y",
        "-user_agent",
        USER_AGENT,
        "-headers",
        f"Referer: {REFERER}\r\n",
        "-ss",
        f"{max(0.0, t):.3f}",
        "-i",
        hls_url,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not dest.is_file():
        raise RuntimeError((proc.stderr or "")[-500:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument(
        "--offsets",
        default="-2,0,2,5",
        help="comma seconds relative to hit start to grab frames",
    )
    parser.add_argument("--limit", type=int, default=12, help="max hit clusters")
    parser.add_argument(
        "--captions-only",
        action="store_true",
        help="use Granicus VTT only; do not fall back to Whisper ASR",
    )
    parser.add_argument(
        "--no-frames",
        action="store_true",
        help="record hit timestamps only; skip HLS frame grabs",
    )
    args = parser.parse_args()

    disk_guard.require_space("vote_hunt")
    clip = load_clip(args.year, args.clip)
    if not clip.get("hls_url"):
        raise SystemExit("clip has no hls_url")

    out_dir = disk_guard.PASSPORT_ROOT / "scratch" / f"vote_hunt_{args.clip}"
    out_dir.mkdir(parents=True, exist_ok=True)

    cues, cue_source = load_cues(clip, captions_only=args.captions_only)
    hits = find_hits(cues)[: args.limit]
    offsets = [float(x) for x in args.offsets.split(",") if x.strip()]

    print(f"cues={len(cues)} source={cue_source} vote_hits={len(hits)}")
    frames = []
    if args.no_frames:
        for i, hit in enumerate(hits):
            print(f"  hit {i} t={hit['start']:.1f}: {hit['text'][:100]}")
    else:
        for i, hit in enumerate(hits):
            print(f"  hit {i} t={hit['start']:.1f}: {hit['text'][:100]}")
            for off in offsets:
                t = max(0.0, hit["start"] + off)
                dest = out_dir / f"hit{i:02d}_t{int(t)}_off{int(off)}.jpg"
                try:
                    grab_frame(clip["hls_url"], t, dest)
                    frames.append({"hit": i, "t": t, "offset": off, "path": str(dest)})
                    print(f"    wrote {dest.name}")
                except Exception as exc:  # noqa: BLE001
                    print(f"    frame fail t={t}: {exc}", file=sys.stderr)

    # Heuristic tallies spoken in cue text (oral-era meetings have no board).
    tally_re = re.compile(
        r"\b(\d)\s*[-–to]+\s*(\d)(?:\s*[-–to]+\s*(\d))?\b",
        re.I,
    )
    for hit in hits:
        m = tally_re.search(hit["text"])
        if m:
            hit["spoken_tally"] = {
                "ayes": int(m.group(1)),
                "noes": int(m.group(2)),
                "abstentions": int(m.group(3) or 0),
            }

    payload = {
        "clip_id": args.clip,
        "year": args.year,
        "cue_count": len(cues),
        "cue_source": cue_source,
        "hits": hits,
        "frames": frames,
        "out_dir": str(out_dir),
        "board_ocr_note": (
            "2019–2023 sample audits found no Voting Results slides in gated "
            "frames; prefer transcript hits for oral roll-call meetings."
        ),
    }
    (out_dir / "hits.json").write_text(json.dumps(payload, indent=2))
    # Sidecar next to votes_*.json so the archive inventory can see hunt status.
    meta = disk_guard.work_dir("metadata")
    sidecar = {
        "clip_id": args.clip,
        "year": args.year,
        "source": "transcript_hunt",
        "cue_count": len(cues),
        "cue_source": cue_source,
        "vote_hits": len(hits),
        "hits": hits,
        "captions_only": args.captions_only,
    }
    (meta / f"votes_{args.clip}_transcript_hunt.json").write_text(
        json.dumps(sidecar, indent=2)
    )
    print(f"wrote {out_dir / 'hits.json'}")
    print(f"wrote {meta / f'votes_{args.clip}_transcript_hunt.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
