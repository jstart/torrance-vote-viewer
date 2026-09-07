"""Local ASR for review when Granicus captions.vtt is empty.

Extracts a short mono WAV from the clip HLS playlist with ffmpeg (browser
User-Agent / Referer — Granicus CDN rejects bare clients), then runs
whisper-cli. Audio never starts before the first agenda cuepoint — the same
pre-meeting skip the extract path uses when it refuses to pull media before
the agenda begins.

Caches JSON on the Passport under metadata/asr_cache/ so review reloads are
instant. Never publishes to the viewer.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
REFERER = "https://torrance.granicus.com/"

DEFAULT_MODEL = Path.home() / ".cache" / "whisper" / "ggml-large-v3-turbo.bin"
WHISPER_BIN = os.environ.get("WHISPER_CLI", "whisper-cli")
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")

_ASR_LOCK = threading.Lock()


def first_agenda_time(agenda: list[dict] | None) -> float:
    """Earliest agenda cuepoint time; 0 if the catalog has none."""
    times: list[float] = []
    for item in agenda or []:
        try:
            times.append(float(item.get("time") or 0))
        except (TypeError, ValueError):
            continue
    return min(times) if times else 0.0


def clamped_audio_window(
    t: float, pad: float, agenda: list[dict] | None
) -> tuple[float, float, float]:
    """Return (start, end, first_agenda) with start >= first agenda cuepoint."""
    first = first_agenda_time(agenda)
    start = max(float(first), float(t) - float(pad))
    end = float(t) + float(pad)
    if end <= start:
        end = start + max(1.0, float(pad))
    return start, end, first


def _cache_dir(clip_id: str) -> Path:
    path = disk_guard.work_dir("metadata") / "asr_cache" / str(clip_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path(clip_id: str, start: float, end: float) -> Path:
    return _cache_dir(clip_id) / f"{int(start)}_{int(end)}.json"


def _scratch_dir() -> Path:
    path = disk_guard.PASSPORT_ROOT / "scratch" / "asr"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_cached(clip_id: str, start: float, end: float) -> dict | None:
    path = _cache_path(clip_id, start, end)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _whisper_model() -> Path:
    env = os.environ.get("WHISPER_MODEL")
    if env:
        return Path(env)
    return DEFAULT_MODEL


def extract_wav(hls_url: str, start: float, duration: float, dest: Path) -> None:
    """Pull mono 16 kHz PCM from HLS for [start, start+duration]."""
    if not hls_url:
        raise RuntimeError("clip has no hls_url")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-user_agent",
        USER_AGENT,
        "-headers",
        f"Referer: {REFERER}\r\n",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        hls_url,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(dest),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=max(120, int(duration * 8) + 60),
    )
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 1000:
        tail = (proc.stderr or "")[-800:]
        raise RuntimeError(f"ffmpeg audio extract failed: {tail}")


def _parse_whisper_json(payload: dict, origin: float) -> list[dict]:
    cues: list[dict] = []
    for seg in payload.get("transcription") or []:
        offsets = seg.get("offsets") or {}
        try:
            rel_start = float(offsets.get("from") or 0) / 1000.0
            rel_end = float(offsets.get("to") or 0) / 1000.0
        except (TypeError, ValueError):
            continue
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        cues.append(
            {
                "start": round(origin + rel_start, 3),
                "end": round(origin + rel_end, 3),
                "text": text,
            }
        )
    return cues


def run_whisper(wav_path: Path, out_prefix: Path) -> list[dict]:
    model = _whisper_model()
    if not model.is_file():
        raise RuntimeError(f"whisper model not found: {model}")
    if not shutil.which(WHISPER_BIN) and not Path(WHISPER_BIN).is_file():
        raise RuntimeError(f"whisper-cli not found: {WHISPER_BIN}")

    cmd = [
        WHISPER_BIN,
        "-m",
        str(model),
        "-f",
        str(wav_path),
        "-l",
        "en",
        "-np",
        "-oj",
        "-of",
        str(out_prefix),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    json_path = Path(str(out_prefix) + ".json")
    if proc.returncode != 0 or not json_path.is_file():
        tail = (proc.stderr or proc.stdout or "")[-800:]
        raise RuntimeError(f"whisper-cli failed: {tail}")
    payload = json.loads(json_path.read_text())
    return payload


def transcribe_window(
    clip: dict,
    t: float,
    pad: float = 30.0,
    *,
    force: bool = False,
) -> dict:
    """ASR [max(first_agenda, t-pad), t+pad]. Returns cue payload for review UI."""
    clip_id = str(clip.get("clip_id") or "")
    start, end, first = clamped_audio_window(t, pad, clip.get("agenda"))
    duration = max(0.5, end - start)

    if not force:
        cached = load_cached(clip_id, start, end)
        if cached:
            return cached

    if not disk_guard.passport_available():
        raise RuntimeError("Passport not mounted; cannot cache ASR output")

    with _ASR_LOCK:
        if not force:
            cached = load_cached(clip_id, start, end)
            if cached:
                return cached

        scratch = _scratch_dir()
        stem = f"{clip_id}_{int(start)}_{int(end)}"
        wav_path = scratch / f"{stem}.wav"
        out_prefix = scratch / stem
        try:
            extract_wav(str(clip.get("hls_url") or ""), start, duration, wav_path)
            payload = run_whisper(wav_path, out_prefix)
            cues = _parse_whisper_json(payload, start)
        finally:
            for path in (wav_path, Path(str(out_prefix) + ".json"), Path(str(out_prefix) + ".txt")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

        result = {
            "available": bool(cues),
            "source": "local_whisper",
            "model": str(_whisper_model().name),
            "clip_id": clip_id,
            "window": {"start": start, "end": end},
            "first_agenda_time": first,
            "skipped_before_agenda": start > (t - pad) and first > 0,
            "cue_count": len(cues),
            "cues": cues,
            "note": None
            if cues
            else "Local whisper returned no speech in this window",
        }
        cache_path = _cache_path(clip_id, start, end)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2, sort_keys=True))
        tmp.replace(cache_path)
        return result
