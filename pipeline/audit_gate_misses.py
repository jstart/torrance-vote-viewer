#!/usr/bin/env python3
"""Audit gated frames that fail Voting Results keyword detect.

After extract, samples frames that pass the color gate, OCRs them, and reports
why detect_frame rejects them. Used for 2019–2023 zero-candidate diagnosis.

    .venv/bin/python pipeline/audit_gate_misses.py --clip 13504 --year 2019
    .venv/bin/python pipeline/audit_gate_misses.py --clip 13504 --year 2019 --save-samples 20
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard
import detect_and_parse_votes as detect

REPO = disk_guard.REPO_ROOT


def list_frame_paths(clip_id: str) -> list[Path]:
    root = disk_guard.work_dir("frames", clip_id)
    paths = sorted(root.rglob("*.jpg"))
    return [p for p in paths if "board" not in p.name]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--sample", type=int, default=80, help="max gated frames to OCR")
    parser.add_argument("--save-samples", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    frames = list_frame_paths(args.clip)
    if not frames:
        print(f"no frames for clip {args.clip}", file=sys.stderr)
        return 1

    gated: list[tuple[Path, dict]] = []
    for path in frames:
        stats = detect.frame_stats(str(path))
        fmt = detect.frame_format(stats)
        if fmt is not None:
            gated.append((path, {"stats": stats, "format": fmt}))

    print(
        f"clip {args.clip}: {len(frames)} frames on disk, {len(gated)} pass color gate"
    )
    if not gated:
        return 0

    rng = random.Random(args.seed)
    sample = gated if len(gated) <= args.sample else rng.sample(gated, args.sample)

    out_dir = disk_guard.PASSPORT_ROOT / "scratch" / f"gate_audit_{args.clip}"
    out_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = out_dir / "samples"
    if args.save_samples:
        samples_dir.mkdir(parents=True, exist_ok=True)

    title_hits = 0
    detected = 0
    formats = Counter()
    keyword_snippets: list[str] = []
    flat_tokens = Counter()
    rows: list[dict] = []

    for i, (path, meta) in enumerate(sample):
        record = detect.detect_frame(str(path))
        formats[record.get("format")] += 1
        signals = record.get("signals") or {}
        if signals.get("title"):
            title_hits += 1
        if record.get("detected"):
            detected += 1
        text = (record.get("ocr_text") or "")[:240]
        flat = detect.squash(text)
        # Collect interesting tokens that might be alternate titles
        for token in (
            "voting",
            "vote",
            "result",
            "results",
            "motion",
            "passed",
            "failed",
            "carried",
            "aye",
            "nay",
            "yes",
            "no",
            "council",
            "roll",
            "call",
        ):
            if token in flat:
                flat_tokens[token] += 1
        row = {
            "frame": str(path),
            "format": record.get("format"),
            "detected": record.get("detected"),
            "signals": signals,
            "ocr_text": text,
        }
        rows.append(row)
        if signals.get("title") or record.get("detected"):
            keyword_snippets.append(text)
        if args.save_samples and i < args.save_samples:
            dest = samples_dir / f"{i:03d}_{path.name}"
            dest.write_bytes(path.read_bytes())

    summary = {
        "clip_id": args.clip,
        "year": args.year,
        "frames_on_disk": len(frames),
        "frames_gated": len(gated),
        "sampled": len(sample),
        "title_hits": title_hits,
        "detected": detected,
        "formats": dict(formats),
        "flat_token_hits": dict(flat_tokens),
        "detect_keywords": list(detect.DETECT_KEYWORDS),
        "sample_ocr_with_title_or_detect": keyword_snippets[:20],
        "sample_ocr_first_10": [r["ocr_text"] for r in rows[:10]],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "rows.json").write_text(json.dumps(rows, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
