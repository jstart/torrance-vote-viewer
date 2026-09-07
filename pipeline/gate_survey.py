#!/usr/bin/env python3
"""One-off audit: how well does the cheap numeric gate separate vote slides?

Computes the gate statistics for every extracted frame of a clip and reports the
distribution, so the OCR pass can be trusted not to be silently skipping boards.

    python3 pipeline/gate_survey.py --clip 14821
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_guard
import manifest as manifest_io
from detect_and_parse_votes import frame_stats, passes_gate


def probe(item: tuple[str, float]) -> dict:
    path, timestamp = item
    stats = frame_stats(path)
    stats["frame"] = path
    stats["video_timestamp"] = timestamp
    stats["gate"] = passes_gate(stats)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    # This survey exists to prove the gate is not silently skipping boards, so it
    # is the last place that should quietly probe fewer frames than the clip has.
    frames, _ = manifest_io.load_window_frames(
        disk_guard.find_work_dir("frames", args.clip) / "windows.json"
    )
    print(f"probing {len(frames)} frames")

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(probe, frames, chunksize=32))

    rows.sort(key=lambda r: r["video_timestamp"])
    out = disk_guard.work_dir("metadata") / f"gate_survey_{args.clip}.json"
    out.write_text(json.dumps(rows))

    passed = [r for r in rows if r["gate"]]
    print(f"gate passed: {len(passed)} / {len(rows)}")

    # Near misses: dark enough to plausibly be a slide but rejected by the gate.
    near = [
        r
        for r in rows
        if not r["gate"]
        and (r["board_dark_fraction"] >= 0.30 or r["inner_dark_fraction"] >= 0.45)
    ]
    print(f"near misses (dark but rejected): {len(near)}")
    for r in sorted(near, key=lambda r: -r["board_dark_fraction"])[:25]:
        print(
            f"  t={r['video_timestamp']:>8.0f} boardDark={r['board_dark_fraction']:.3f} "
            f"boardSat={r['board_saturation']:.1f} innerDark={r['inner_dark_fraction']:.3f} "
            f"innerSat={r['inner_saturation']:.1f}"
        )

    runs: list[list[float]] = []
    for r in passed:
        if runs and r["video_timestamp"] - runs[-1][-1] <= 30:
            runs[-1].append(r["video_timestamp"])
        else:
            runs.append([r["video_timestamp"]])
    print(f"gate-passing frames form {len(runs)} time clusters:")
    for run in runs:
        print(f"  {run[0]:.0f}-{run[-1]:.0f}s ({len(run)} frames)")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
