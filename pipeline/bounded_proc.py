#!/usr/bin/env python3
"""Wall-clock bounds and process-group kills for every subprocess this pipeline spawns.

Two ffmpeg processes encoding a synthetic test clip once ran for five and a half
hours at ~850% combined CPU before being killed by hand. Nothing timed out and
nothing errored: an unbounded `subprocess.run` and an unbounded `Popen` read loop
are both silent when the child never finishes, and the only symptom is the
endpoint security agent saturating the machine. Every spawn in this repo now goes
through one of the two primitives here so that failure mode cannot recur.

There are two primitives rather than one because the two consumption shapes need
genuinely different mechanisms, and forcing them together would mean
reimplementing `communicate()`:

  * `run_bounded()` -- the batch case. Runs to completion, one wall-clock bound,
    output collected at the end.

  * `stream_bounded()` -- the pipe case. A long-lived child whose stdout is read
    incrementally, where `timeout=` has nothing to attach to. Bounded by a
    *stall* timeout (no bytes for N seconds) and an *overall deadline*, because
    those catch different failures: the stall catches a wedged read from the CDN
    or the Passport, the deadline catches a child that makes slow progress
    forever, which is what the 5.5-hour encode was doing. Neither alone is
    enough.

What they share is the part that is easy to get wrong, `kill_tree()`:

  * Children are spawned with `start_new_session=True`, so the child leads its
    own process group and `os.killpg` reaches anything it spawned. `proc.kill()`
    alone signals the direct child only and leaves grandchildren running --
    exactly the orphan that burned 5.5 hours.
  * SIGTERM, a grace period, then SIGKILL, because ffmpeg flushes and closes its
    output on SIGTERM and a hard kill first leaves a half-written file behind.
  * The reap is confirmed rather than assumed, and `kill_tree()` reports whether
    it succeeded so callers can say so out loud.
  * `killpg` is refused when the child shares our own process group (i.e. when
    `start_new_session` did not take effect), because that would signal the
    pipeline itself.

Bounds are derived from expected work, never hardcoded to one constant: see
`bound_from_work`. A constant tight enough to catch a hang kills legitimate long
windows, and one loose enough to be safe does not catch a hang for hours.

Every bound that fires raises `ProcessTimeout`. Nothing here ever returns partial
output as if it were a result -- a truncated vote window is indistinguishable
downstream from "this window contained no vote", so a silent partial is a missing
council vote in published data rather than a slow run.
"""

from __future__ import annotations

import contextlib
import errno
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

# Seconds a child gets to exit on SIGTERM before SIGKILL. Long enough for ffmpeg
# to close its output, short enough that a wedged child does not stretch the
# bound it just blew.
KILL_GRACE = 5.0
# Seconds to confirm the reap after SIGKILL. An unreaped child after this is
# stuck in the kernel and is reported rather than waited on forever.
REAP_TIMEOUT = 10.0
# Seconds a child gets to exit by itself once we stop reading its stdout. ffmpeg
# gets EPIPE on its next write and exits promptly; anything slower is killed.
EXIT_GRACE = 15.0
# Bytes of stderr kept per child. Enough for ffmpeg's error tail, bounded so a
# child that logs per frame cannot grow the parent's heap.
STDERR_TAIL_BYTES = 64 * 1024


class BoundedProcessError(RuntimeError):
    """A subprocess this module supervised failed.

    A `RuntimeError` subclass on purpose: the pipeline's existing
    `except RuntimeError` handlers around ffmpeg already treat these as window
    failures, so bounding a call site does not change which errors are caught.
    """


class ProcessTimeout(BoundedProcessError):
    """A wall-clock bound fired. Never raised alongside usable partial output."""

    def __init__(
        self,
        message: str,
        *,
        label: str,
        kind: str,
        bound: float,
        elapsed: float,
        reaped: bool,
        stderr_tail: str = "",
    ) -> None:
        super().__init__(message)
        self.label = label
        # "timeout" | "stall" | "deadline" | "exit": which bound fired.
        self.kind = kind
        self.bound = bound
        self.elapsed = elapsed
        self.reaped = reaped
        self.stderr_tail = stderr_tail


# --- bounds derived from expected work --------------------------------------

def bound_from_work(
    work_seconds: float | None,
    *,
    multiplier: float,
    floor: float,
    ceiling: float | None = None,
) -> float:
    """Scale a bound off the work being asked for, with a floor.

    `work_seconds` is the size of the job in its own units -- seconds of video to
    decode, not seconds it should take -- and `multiplier` converts that into a
    wall-clock allowance. The floor covers the fixed costs that dominate a tiny
    job (process start, playlist parse, a cold Passport); the ceiling stops a
    pathologically long job from talking its way back into an unbounded run.

    `None` or a non-positive size means the caller could not measure the work, so
    the floor stands alone rather than the bound quietly disappearing.
    """
    if not work_seconds or work_seconds <= 0:
        return floor
    bound = work_seconds * multiplier
    if ceiling is not None:
        bound = min(bound, ceiling)
    return max(floor, bound)


def playlist_media_seconds(playlist: Path) -> float | None:
    """Seconds of video a local HLS playlist covers, summed from its EXTINF tags.

    This is the "work" every ffmpeg bound in the pipeline is scaled off. Read out
    of the file rather than probed, because `ffprobe` would be one more unbounded
    subprocess needing a bound of its own in order to work out how to bound this
    one. Returns None for anything that is not a playlist, so the caller falls
    back on work it can measure instead of inventing a duration.
    """
    if playlist.suffix.lower() not in {".m3u8", ".m3u"}:
        return None
    try:
        text = playlist.read_text()
    except OSError:
        return None
    total = 0.0
    for line in text.splitlines():
        if line.startswith("#EXTINF:"):
            try:
                total += float(line.split(":", 1)[1].rstrip(","))
            except ValueError:
                continue
    return total or None


def note_bound(label: str, detail: str) -> None:
    """Say out loud what bound is being applied, so a kill is explicable later."""
    print(f"  [{label}] bound: {detail}", file=sys.stderr)


# --- the kill path ----------------------------------------------------------

def _own_group(proc: subprocess.Popen) -> int | None:
    """The child's process group id, or None when it shares the pipeline's.

    Returning None is a refusal, not an error: signalling our own process group
    would kill the pipeline along with the child.
    """
    try:
        pgid = os.getpgid(proc.pid)
        if pgid == os.getpgrp():
            return None
    except OSError:
        return None
    return pgid


def _wait_briefly(proc: subprocess.Popen, seconds: float) -> bool:
    try:
        proc.wait(timeout=seconds)
        return True
    except subprocess.TimeoutExpired:
        return False


def kill_tree(
    proc: subprocess.Popen,
    *,
    label: str,
    grace: float = KILL_GRACE,
    reap_timeout: float = REAP_TIMEOUT,
    quiet: bool = False,
) -> bool:
    """SIGTERM then SIGKILL the child's whole process group; confirm the reap.

    Returns True when the child was reaped. False means something survived, and
    the caller must report it: an unreported survivor is the 5.5-hour failure.
    """
    if proc.poll() is not None:
        return True

    pgid = _own_group(proc)
    scope = f"process group {pgid}" if pgid is not None else f"pid {proc.pid} only"

    def send(sig: int) -> None:
        try:
            if pgid is not None:
                os.killpg(pgid, sig)
            else:
                proc.send_signal(sig)
        except (ProcessLookupError, PermissionError):
            pass
        except OSError as exc:  # ESRCH races with the child exiting on its own
            if exc.errno != errno.ESRCH:
                raise

    send(signal.SIGTERM)
    escalated = False
    if not _wait_briefly(proc, grace):
        escalated = True
        send(signal.SIGKILL)
        if not _wait_briefly(proc, reap_timeout):
            print(
                f"  [{label}] KILL FAILED: {scope} survived SIGTERM+SIGKILL after "
                f"{grace + reap_timeout:.0f}s; a process is still running",
                file=sys.stderr,
            )
            return False
    if pgid is not None:
        # The leader is reaped, but anything it spawned is still in the group and
        # is now the orphan that runs for hours. Sweep it. The pgid can only be
        # reused by a process that becomes a group leader under the pid just
        # reaped, which needs its own setsid within microseconds of the wait
        # returning; every group swept here is one this module created.
        send(signal.SIGKILL)
    if not quiet:
        print(
            f"  [{label}] killed {scope}"
            + (" (SIGTERM ignored, SIGKILL used)" if escalated else " on SIGTERM"),
            file=sys.stderr,
        )
    return True


def _as_text(blob) -> str:
    if blob is None:
        return ""
    if isinstance(blob, str):
        return blob
    return blob.decode("utf-8", "replace")


# --- primitive 1: the batch case -------------------------------------------

def run_bounded(
    cmd: list[str],
    *,
    timeout: float,
    label: str,
    text: bool = False,
    cwd: str | Path | None = None,
    env: dict | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """`subprocess.run` with a bound that survives a child that spawns children.

    Not a thin wrapper over `subprocess.run(timeout=)`. On a timeout `run()`
    calls `proc.kill()` -- the direct child only -- and then blocks in
    `communicate()` again waiting for the pipes to close. A grandchild that
    inherited stdout holds them open, so the "timeout" hangs for as long as the
    orphan lives. The wait, the kill and the drain are all bounded here instead.

    stdin is /dev/null so no child can block reading a terminal that is not
    there, which is a hang with no output at all to diagnose it by. ffmpeg polls
    stdin for interactive keys and is the reason this matters.

    Raises `ProcessTimeout` on the bound, and `BoundedProcessError` when `check`
    is set and the child exits non-zero. Never returns partial output as success.
    """
    empty = "" if text else b""
    started = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started
        reaped = kill_tree(proc, label=label)
        out, err = empty, empty
        if reaped:
            # Every holder of the pipes is dead, so this cannot block for long.
            # Still bounded, in case the kill left something behind.
            with contextlib.suppress(Exception):
                out, err = proc.communicate(timeout=REAP_TIMEOUT)
        tail = _as_text(err)[-STDERR_TAIL_BYTES:]
        raise ProcessTimeout(
            f"{label}: exceeded its {timeout:.0f}s bound after {elapsed:.0f}s "
            f"and was killed"
            + ("" if reaped else " -- BUT A PROCESS SURVIVED THE KILL")
            + (f"; stderr tail: {tail[-400:]}" if tail.strip() else ""),
            label=label,
            kind="timeout",
            bound=timeout,
            elapsed=elapsed,
            reaped=reaped,
            stderr_tail=tail,
        ) from None
    except BaseException:
        # KeyboardInterrupt included: leaving ffmpeg running past a Ctrl-C is how
        # the orphans outlived the run that started them.
        kill_tree(proc, label=label, quiet=True)
        raise

    if check and proc.returncode != 0:
        raise BoundedProcessError(
            f"{label}: exited {proc.returncode}; stderr tail: {_as_text(err)[-400:]}"
        )
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


# --- primitive 2: the streaming pipe case ----------------------------------

class BoundedStream:
    """A child whose stdout is read incrementally under two independent bounds.

    `timeout=` cannot apply here: the process is alive across many reads and the
    consumer does real work between them. So:

      * `stall_timeout` bounds how long one read may wait with no bytes arriving.
        It measures inactivity, not work, which is why it can be a constant: it
        is only ever charged for time this process spends blocked in `select`,
        never for the time the consumer spends gating frames it already has.
      * `deadline` bounds the child's whole lifetime, consumer time included,
        because a child that trickles one byte just inside every stall window
        never stalls and would otherwise run forever.

    Reads go through `os.read` on the raw descriptor rather than the buffered
    reader, so `select` sees the true readiness of the pipe. Nothing else may
    touch `proc.stdout`.
    """

    def __init__(
        self,
        cmd: list[str],
        *,
        label: str,
        stall_timeout: float,
        deadline: float,
        read_size: int = 1 << 20,
    ) -> None:
        self.cmd = cmd
        self.label = label
        self.stall_timeout = float(stall_timeout)
        self.deadline_seconds = float(deadline)
        self.read_size = read_size
        self.bytes_read = 0
        self.started = time.monotonic()
        self.killed = False
        self._deadline_at = self.started + self.deadline_seconds
        self._eof = False
        self._closed = False
        self._stderr = bytearray()

        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
        )
        self._fd = self.proc.stdout.fileno()
        self._selector = selectors.DefaultSelector()
        self._selector.register(self._fd, selectors.EVENT_READ)
        self._drain = threading.Thread(target=self._drain_stderr, daemon=True)
        self._drain.start()

    # -- stderr -------------------------------------------------------------

    def _drain_stderr(self) -> None:
        """Keep the stderr pipe empty so the child cannot block writing to it.

        Only the tail is retained: ffmpeg at `-loglevel error` says almost
        nothing, but a louder level emits a line per frame and that must not
        become the way a long clip exhausts memory.
        """
        stream = self.proc.stderr
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                self._stderr += chunk
                if len(self._stderr) > STDERR_TAIL_BYTES:
                    del self._stderr[: len(self._stderr) - STDERR_TAIL_BYTES]
        except (OSError, ValueError):
            pass

    def stderr_tail(self) -> str:
        return bytes(self._stderr).decode("utf-8", "replace")

    # -- reading ------------------------------------------------------------

    def read(self, size: int | None = None) -> bytes:
        """Next chunk from the child, or b"" at EOF.

        Raises `ProcessTimeout` on a stall or on the overall deadline, having
        killed the process group first. It never returns short-but-successful:
        the caller cannot tell a truncated window from an empty one, so a bound
        that fires has to be an exception.
        """
        if self._eof:
            return b""
        want = self.read_size if size is None else size
        while True:
            left_overall = self._deadline_at - time.monotonic()
            if left_overall <= 0:
                self._blew("deadline", self.deadline_seconds)
            wait = min(self.stall_timeout, left_overall)
            if not self._selector.select(timeout=wait):
                # Nothing readable for `wait` seconds. Which bound that is
                # depends on whether the stall window or what was left of the
                # deadline ran out first.
                if wait >= self.stall_timeout:
                    self._blew("stall", self.stall_timeout)
                self._blew("deadline", self.deadline_seconds)
            try:
                chunk = os.read(self._fd, want)
            except OSError as exc:
                if exc.errno == errno.EINTR:  # pragma: no cover - PEP 475 retries
                    continue
                if exc.errno != errno.EIO:
                    raise
                chunk = b""  # pty-style EOF
            if not chunk:
                self._eof = True
                return b""
            self.bytes_read += len(chunk)
            return chunk

    def _blew(self, kind: str, bound: float) -> None:
        elapsed = time.monotonic() - self.started
        self.killed = True
        reaped = kill_tree(self.proc, label=self.label)
        if kind == "stall":
            what = (
                f"produced no output for {bound:.0f}s "
                f"({self.bytes_read} bytes read in {elapsed:.0f}s so far)"
            )
        else:
            what = (
                f"exceeded its {bound:.0f}s overall deadline after {elapsed:.0f}s "
                f"({self.bytes_read} bytes read)"
            )
        raise ProcessTimeout(
            f"{self.label}: {what}; killed mid-stream, so this result is "
            f"incomplete and must not be recorded"
            + ("" if reaped else " -- AND A PROCESS SURVIVED THE KILL")
            + (f"; stderr tail: {self.stderr_tail()[-400:]}"
               if self.stderr_tail().strip() else ""),
            label=self.label,
            kind=kind,
            bound=bound,
            elapsed=elapsed,
            reaped=reaped,
            stderr_tail=self.stderr_tail(),
        )

    # -- teardown -----------------------------------------------------------

    def finish(self, *, exit_grace: float = EXIT_GRACE) -> None:
        """Confirm the child exited cleanly. Only valid after reading to EOF.

        This is what makes a complete run distinguishable from a truncated one,
        so it must be called on the success path and its exception must not be
        swallowed. `shutdown()` deliberately does not do this: it also runs when
        the consumer abandoned the stream, where a non-zero exit is just the
        EPIPE we caused.
        """
        if not self._eof:
            raise BoundedProcessError(
                f"{self.label}: finish() before end of stream after "
                f"{self.bytes_read} bytes; refusing to call this complete"
            )
        self.shutdown(exit_grace=exit_grace)
        if self.killed:
            raise ProcessTimeout(
                f"{self.label}: did not exit within {exit_grace:.0f}s of the end "
                f"of its output and was killed; result is incomplete",
                label=self.label,
                kind="exit",
                bound=exit_grace,
                elapsed=time.monotonic() - self.started,
                reaped=True,
                stderr_tail=self.stderr_tail(),
            )
        if self.proc.returncode != 0:
            raise BoundedProcessError(
                f"{self.label}: exited {self.proc.returncode} after "
                f"{self.bytes_read} bytes; stderr tail: {self.stderr_tail()[-400:]}"
            )

    def shutdown(self, *, exit_grace: float = EXIT_GRACE) -> None:
        """Guarantee the child is dead and reaped. Never raises.

        The old code did `proc.stdout.close(); proc.wait()` with no bound, which
        is its own silent hang: a child stuck on a network or disk read never
        notices the closed pipe and the unbounded `wait()` inherits its hang.
        """
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):
            self._selector.close()
        with contextlib.suppress(Exception):
            self.proc.stdout.close()
        if self.proc.poll() is None and not _wait_briefly(self.proc, exit_grace):
            self.killed = True
            kill_tree(self.proc, label=self.label)
        with contextlib.suppress(Exception):
            self._drain.join(timeout=REAP_TIMEOUT)
        with contextlib.suppress(Exception):
            self.proc.stderr.close()


@contextlib.contextmanager
def stream_bounded(
    cmd: list[str],
    *,
    label: str,
    stall_timeout: float,
    deadline: float,
    read_size: int = 1 << 20,
):
    """Run `cmd` with its stdout on a bounded pipe; always reaped on the way out.

    The `finally` is the point: a consumer that raises, returns early, or is a
    generator that gets closed all leave through it, and none of them may leave
    ffmpeg holding a pipe.
    """
    stream = BoundedStream(
        cmd,
        label=label,
        stall_timeout=stall_timeout,
        deadline=deadline,
        read_size=read_size,
    )
    try:
        yield stream
    finally:
        stream.shutdown()
