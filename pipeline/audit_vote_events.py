#!/usr/bin/env python3
"""Enumerate every VoteCast panel in a clip and label it result vs in-progress.

The detector only reports the boards it could parse. This answers the different
question a reviewer actually needs answered before trusting a meeting: how many
times did the vote panel appear at all, and was each appearance captured?

Torrance shows a "Voting in Progress" roster panel while members press their
buttons, then swaps it for the "Voting Results" board. Both share the same dark
desaturated signature, so counting them separately shows whether a missing vote
is a parser failure or a vote whose result was simply never broadcast.

    python3 pipeline/audit_vote_events.py --clip 14821

Writes metadata/vote_events_{clip}.json on the Passport.
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
from detect_and_parse_votes import detect_frame, frame_stats

# The VoteCast panel fills the frame with a near-black, near-grey board. These
# bounds are deliberately looser than the detector's gate so the audit cannot
# inherit the detector's blind spots.
PANEL_DARK_MIN = 0.72
PANEL_SAT_MAX = 15.0
EVENT_GAP_SECONDS = 30.0


def classify(item: tuple[str, float]) -> dict:
    path, timestamp = item
    record = detect_frame(path, force_ocr=True)
    text = record.get("ocr_text") or ""
    if record["detected"]:
        kind = "result"
    elif "oting in Progress" in text or "oting In Progress" in text:
        kind = "in_progress"
    else:
        kind = "other"
    return {"video_timestamp": timestamp, "kind": kind, "frame": path}


def panel_candidate(item: tuple[str, float]) -> dict | None:
    path, timestamp = item
    stats = frame_stats(path)
    if stats["board_dark_fraction"] < PANEL_DARK_MIN or stats["board_saturation"] > PANEL_SAT_MAX:
        return None
    return {"frame": path, "video_timestamp": timestamp}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    # The whole point of this audit is to answer "was every appearance of the
    # panel captured", so it must refuse a manifest that cannot account for its
    # own frames rather than auditing the subset that happens to be present.
    try:
        frames, _ = manifest_io.load_window_frames(
            disk_guard.find_work_dir("frames", args.clip) / "windows.json"
        )
    except manifest_io.IncompleteManifest as exc:
        raise SystemExit(str(exc)) from exc
    if not frames:
        raise SystemExit(
            f"no frames on disk for clip {args.clip}; re-run extract_vote_windows.py"
        )
    print(f"auditing {len(frames)} frames")

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        candidates = [c for c in pool.map(panel_candidate, frames, chunksize=32) if c]
    print(f"{len(candidates)} frames carry the VoteCast panel signature")

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(
            pool.map(
                classify,
                [(c["frame"], c["video_timestamp"]) for c in candidates],
                chunksize=4,
            )
        )
    rows.sort(key=lambda r: r["video_timestamp"])

    events: list[dict] = []
    for row in rows:
        if row["kind"] == "other":
            continue
        if (
            events
            and events[-1]["kind"] == row["kind"]
            and row["video_timestamp"] - events[-1]["end"] <= EVENT_GAP_SECONDS
        ):
            events[-1]["end"] = row["video_timestamp"]
            events[-1]["frames"] += 1
        else:
            events.append(
                {
                    "kind": row["kind"],
                    "start": row["video_timestamp"],
                    "end": row["video_timestamp"],
                    "frames": 1,
                }
            )

    # An in-progress panel with no result panel close behind it is a vote whose
    # outcome the stream never showed, which no amount of parsing can recover.
    unbroadcast: list[dict] = []
    for index, event in enumerate(events):
        if event["kind"] != "in_progress":
            continue
        follower = events[index + 1] if index + 1 < len(events) else None
        if not follower or follower["kind"] != "result" or follower["start"] - event["end"] > 60:
            unbroadcast.append(event)

    results = [e for e in events if e["kind"] == "result"]
    print(f"vote panels: {len(results)} result boards, "
          f"{len([e for e in events if e['kind'] == 'in_progress'])} in-progress boards")
    for event in events:
        print(f"  {event['kind']:11s} {event['start']:.0f}-{event['end']:.0f}s ({event['frames']} frames)")
    if unbroadcast:
        print(f"{len(unbroadcast)} vote(s) had no result board broadcast:")
        for event in unbroadcast:
            print(f"  in-progress at {event['start']:.0f}-{event['end']:.0f}s, result never shown")

    payload = {
        "clip_id": args.clip,
        "frames_audited": len(frames),
        "panel_frames": len(candidates),
        "result_boards": len(results),
        "events": events,
        "unbroadcast_votes": unbroadcast,
    }
    out = disk_guard.work_dir("metadata") / f"vote_events_{args.clip}.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
