"""Shared disk checks and Passport work-root layout for the 2026 vote pipeline.

Internal disk is chronically near full, so every extraction command must call
`require_space()` before it writes anything and after it finishes. All video,
dense frames and OCR scratch live on the Passport; the repo only receives small
JSON plus the selected JPG per vote.

The bulk roots carry a ".noindex" suffix so Spotlight and the endpoint security
agent skip them without having to disable indexing for the whole volume; see
NOINDEX_KINDS.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

GIB = 1024 ** 3

PASSPORT_ROOT = Path("/Volumes/Black Passport/torrance-vote-viewer")
INTERNAL_MOUNT = Path("/System/Volumes/Data")

MIN_INTERNAL_GIB = 15
MIN_PASSPORT_GIB = 20

REPO_ROOT = Path(__file__).resolve().parent.parent


class DiskGuardError(RuntimeError):
    """Raised when free space is too low to safely continue."""


@dataclass(frozen=True)
class Usage:
    mount: str
    total_gib: float
    used_gib: float
    free_gib: float

    def __str__(self) -> str:
        return (
            f"{self.mount}: {self.free_gib:.1f} GiB free "
            f"({self.used_gib:.1f}/{self.total_gib:.1f} GiB used)"
        )


def usage(path: Path | str) -> Usage:
    try:
        st = shutil.disk_usage(str(path))
    except OSError:
        # An unmounted or briefly-disconnected volume reports as zero free, which
        # makes require_space() abort instead of crashing mid-extraction.
        return Usage(mount=f"{path} (unavailable)", total_gib=0.0, used_gib=0.0, free_gib=0.0)
    return Usage(
        mount=str(path),
        total_gib=st.total / GIB,
        used_gib=st.used / GIB,
        free_gib=st.free / GIB,
    )


def internal_usage() -> Usage:
    return usage(INTERNAL_MOUNT)


def passport_usage() -> Usage:
    return usage(PASSPORT_ROOT if PASSPORT_ROOT.exists() else PASSPORT_ROOT.parent)


def passport_available() -> bool:
    return PASSPORT_ROOT.parent.is_dir() and os.path.ismount(str(PASSPORT_ROOT.parent))


def require_space(stage: str = "pipeline") -> tuple[Usage, Usage]:
    """Abort the caller unless both volumes have headroom.

    Returns the two usage snapshots so callers can log peak numbers.
    """
    internal = internal_usage()
    if internal.free_gib < MIN_INTERNAL_GIB:
        raise DiskGuardError(
            f"[{stage}] internal disk has only {internal.free_gib:.1f} GiB free, "
            f"need >= {MIN_INTERNAL_GIB} GiB"
        )

    if not passport_available():
        raise DiskGuardError(
            f"[{stage}] Passport not mounted at {PASSPORT_ROOT.parent}"
        )

    passport = passport_usage()
    if passport.free_gib < MIN_PASSPORT_GIB:
        raise DiskGuardError(
            f"[{stage}] Passport has only {passport.free_gib:.1f} GiB free, "
            f"need >= {MIN_PASSPORT_GIB} GiB"
        )

    return internal, passport


def report(stage: str) -> str:
    internal, passport = internal_usage(), passport_usage()
    return f"[{stage}] {internal} | {passport}"


# --- Passport layout -------------------------------------------------------

WORK_KINDS = frozenset({"raw", "frames", "crops", "logs", "metadata"})

# Spotlight skips any directory whose name ends in ".noindex", and so does the
# CrowdStrike file-analysis path that follows it. Only the two bulk kinds get
# the suffix: raw segments and sampled frames are the only directories that
# ever hold thousands of files, and mdworker waking on each one is what
# saturates the endpoint agent. crops / logs / metadata stay indexed because
# they are small and worth being able to search.
#
# The Passport also holds unrelated user data (campaign_finance, dashboard),
# so indexing is left enabled for the volume as a whole and excluded per
# directory instead.
NOINDEX_KINDS = frozenset({"raw", "frames"})


def work_root(kind: str) -> Path:
    """Root directory new output of this kind is written to."""
    if kind not in WORK_KINDS:
        raise ValueError(f"unknown work dir kind: {kind}")
    name = f"{kind}.noindex" if kind in NOINDEX_KINDS else kind
    return PASSPORT_ROOT / name


def legacy_work_root(kind: str) -> Path:
    """Pre-.noindex root, still holding data earlier runs produced."""
    if kind not in WORK_KINDS:
        raise ValueError(f"unknown work dir kind: {kind}")
    return PASSPORT_ROOT / kind


def work_dir(kind: str, clip_id: str | int | None = None) -> Path:
    """Return (and create) the Passport directory new output goes to.

    The mount check lives here rather than in the callers because this is the
    only place bulk output directories get created. A Passport that unmounts
    mid-run would otherwise let a whole window of frames land on the near-full
    boot disk before the next require_space() call noticed.
    """
    if not passport_available():
        raise DiskGuardError(
            f"[work_dir] Passport not mounted at {PASSPORT_ROOT.parent}; "
            f"refusing to create {kind} output on the internal disk"
        )
    path = work_root(kind)
    if clip_id is not None:
        path = path / str(clip_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_work_dir(kind: str, clip_id: str | int | None = None) -> Path:
    """Locate existing data of this kind, newest layout first.

    Read paths go through here so that renaming the bulk roots does not orphan
    what earlier runs already produced. A clip extracted before the rename is
    still found under the legacy root and can be read in place, which matters
    because those frame directories are inputs to other stages. Nothing is
    created; the preferred path is returned when neither exists so callers can
    report a single canonical location in their error message.
    """
    preferred = work_root(kind)
    legacy = legacy_work_root(kind)
    if clip_id is not None:
        preferred = preferred / str(clip_id)
        legacy = legacy / str(clip_id)
    if preferred.exists():
        return preferred
    if legacy.exists():
        return legacy
    return preferred


def dir_size_gib(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total / GIB


def purge(path: Path, stage: str = "purge") -> float:
    """Delete a Passport scratch directory, returning the GiB reclaimed.

    This is the only destructive primitive in the pipeline, so containment is
    checked on the resolved path. A plain string prefix test would accept both
    a sibling root that merely starts with the same characters
    ("torrance-vote-viewer-OTHER") and any "../" walk back out of the volume.
    """
    root = PASSPORT_ROOT.resolve()
    try:
        resolved = Path(path).resolve()
        relative = resolved.relative_to(root)
    except (OSError, ValueError):
        raise DiskGuardError(
            f"[{stage}] refusing to purge outside Passport: {path}"
        ) from None
    if relative == Path("."):
        raise DiskGuardError(
            f"[{stage}] refusing to purge the Passport root itself: {path}"
        )
    freed = dir_size_gib(resolved)
    shutil.rmtree(resolved, ignore_errors=True)
    return freed


if __name__ == "__main__":
    print(report("disk_guard"))
    try:
        require_space("disk_guard")
        print("OK: both volumes have headroom")
    except DiskGuardError as exc:
        raise SystemExit(str(exc))
