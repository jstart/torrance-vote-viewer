#!/usr/bin/env python3
"""Reading windows.json without turning a failed extraction into a quiet zero.

Every consumer of the extract manifest was written the same way:

    frames = [f for w in manifest["windows"] for f in w["frames"]
              if Path(f["frame"]).exists()]

The `exists()` filter is the problem. It was added so a partly-swept frame
directory would not crash the stage, and the cost of that is that a window whose
frames are gone contributes nothing and says nothing. Fewer frames read means
fewer boards detected, which reaches the published data as a council vote that
simply is not there -- there is no signal anywhere in the output distinguishing it
from a stretch of meeting where nobody voted.

`load_window_frames` reads the same manifest and refuses the same silence:
`complete: false` or a window whose frames are missing from disk is an error with
the window numbers in it, not a shorter list.
"""

from __future__ import annotations

import json
from pathlib import Path


class IncompleteManifest(RuntimeError):
    """The manifest does not describe a whole clip, or its frames are not there."""


def load_window_frames(
    manifest_path: Path,
    *,
    require_complete: bool = True,
) -> tuple[list[tuple[str, float]], dict]:
    """Return ([(frame_path, video_timestamp)], manifest) or raise.

    Set `require_complete=False` only to inspect a clip that is knowingly
    mid-extraction, and never on a path that feeds published vote data.
    """
    if not manifest_path.exists():
        raise IncompleteManifest(
            f"missing {manifest_path}; run extract_vote_windows.py first"
        )
    manifest = json.loads(manifest_path.read_text())

    failed = manifest.get("failed_windows") or []
    # `complete` is absent from manifests written before it existed, so its
    # absence falls back to the failure list rather than being read as False.
    complete = manifest.get("complete")
    if complete is None:
        complete = not failed
    if require_complete and not complete:
        listed = ", ".join(
            "w{}: {}".format(entry.get("index"), entry.get("kind", "error"))
            for entry in failed[:5]
        )
        raise IncompleteManifest(
            f"{manifest_path} covers an incomplete extraction: "
            f"{len(failed)} window(s) failed"
            + (f" ({listed})" if listed else "")
            + ". Re-run extract_vote_windows.py for this clip; reading it now "
            "would report those windows as containing no votes."
        )

    frames: list[tuple[str, float]] = []
    missing: dict[int, int] = {}
    for window in manifest.get("windows", []):
        index = window.get("index", -1)
        for frame in window.get("frames", []):
            if Path(frame["frame"]).exists():
                frames.append((frame["frame"], frame["video_timestamp"]))
            else:
                missing[index] = missing.get(index, 0) + 1
    if missing:
        detail = ", ".join(f"w{idx:03d}: {n}" for idx, n in sorted(missing.items()))
        raise IncompleteManifest(
            f"{manifest_path} lists frames that are not on disk ({detail}). "
            f"Those windows would silently contribute no boards. Re-run "
            f"extract_vote_windows.py for this clip."
        )
    return frames, manifest
