"""proc — run and launch processes from inside the kernel.

``subprocess`` is available in the kernel and is the right instrument for
``git --no-pager status``. It is the WRONG instrument for anything that outlives
the cell, and the failure is not an error: it is a cell that never returns.

    subprocess.run("python serve.py &", capture_output=True)      # hangs forever
    subprocess.run("nohup python serve.py &", capture_output=True) # hangs forever
    subprocess.run("setsid python serve.py", capture_output=True)  # hangs forever

All three hang for the same reason. ``capture_output=True`` gives the child a
pipe, and ``run`` waits for EOF on that pipe — which arrives only when EVERY
holder of the write end closes it. A backgrounded child inherits the write end,
so the pipe stays open and ``run`` waits for a process that is, by design, never
going to exit. ``nohup`` changes signal disposition, not file descriptors, so it
does not help; ``setsid`` changes the session, not the fds, so it does not help
either. The only fix is to point the child's stdout/stderr somewhere that is not
the pipe — a file, or DEVNULL — and that is what ``proc("start", ...)`` does.

So this module exists to make the two cases impossible to confuse:

* ``run``   — the cell waits for the command. Bounded by ``timeout``, and it
              waits on the PROCESS rather than on pipe EOF, so even a command
              that backgrounds something by accident returns with its partial
              output and a note instead of wedging the kernel.
* ``start`` — the cell does not wait at all. Own session, stdin from DEVNULL,
              stdout/stderr into a log file whose path is returned. The exit
              code is captured into a sibling file by a wrapper, so ``ps`` can
              report a real status for a process nobody is blocked on.

``ps`` / ``log`` / ``wait`` / ``kill`` are the lifecycle of what ``start``
launched. The registry is on disk under ``/tmp/crow-proc/<session>.jsonl``, so
it survives ``reload()`` and a kernel reset — a detached process is supposed to
outlive the kernel that started it, and so is the ability to find it.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import signal
import tempfile
import time
from pathlib import Path
from typing import Any

from .register import current_cell, subtool
from .results import ProcError, ProcResult

#: How long a ``run`` may take before its whole process group is SIGKILLed.
_DEFAULT_TIMEOUT = 60.0

#: Per-stream byte cap for ``run``. Output past the cap is drained and
#: discarded — kept flowing so the child never blocks on a full pipe, but not
#: stored, because a kernel is not a place to buffer gigabytes.
_MAX_BYTES = 400_000

#: How long to keep reading a pipe after the process has exited. EOF should be
#: immediate; if it is not, something backgrounded is holding the write end and
#: no amount of waiting will change that.
_GRACE = 2.0

#: How long to wait for a SIGKILLed group to actually disappear.
_KILL_GRACE = 3.0

_MODES = ("run", "start", "ps", "log", "wait", "kill")


def _root() -> Path:
    """Where the registry and the default logs live.

    Read per call rather than at import, so CROW_PROC_DIR can point it at a
    tmpdir for a test without the module having been imported first.
    """
    return Path(os.environ.get("CROW_PROC_DIR", "/tmp/crow-proc"))


# --------------------------------------------------------------------------
# the registry: one JSONL per session, merged by pid
# --------------------------------------------------------------------------


def _registry() -> Path:
    cell = current_cell()
    session = (cell.session_id if cell is not None else None) or "no-session"
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{session}.jsonl"


def _record(entry: dict[str, Any]) -> None:
    with _registry().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _records() -> list[dict[str, Any]]:
    """This session's launches, oldest first, later records merged onto earlier.

    A launch writes one record; a ``kill`` appends another carrying the signal,
    so the merged view knows a process that vanished was killed rather than
    having exited on its own.
    """
    path = _registry()
    if not path.exists():
        return []
    merged: dict[int, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        pid = rec.get("pid")
        if pid is None:
            continue
        merged.setdefault(int(pid), {}).update(rec)
    return list(merged.values())


def _find(pid: int) -> dict[str, Any]:
    for rec in _records():
        if rec["pid"] == pid:
            return rec
    raise ProcError(
        f"pid {pid} was not started by proc() in this session — refusing to "
        "touch a process this registry does not know (a pid is a handle, and "
        "pids get recycled)"
    )


def _same_process(rec: dict[str, Any], proc: Any) -> bool:
    """Guard against pid recycling: the start time has to match too."""
    try:
        return abs(proc.create_time() - float(rec["started"])) < 2.0
    except Exception:
        return False


def _proc(pid: int):
    import psutil

    try:
        return psutil.Process(pid)
    except Exception:
        return None


def _state(rec: dict[str, Any]) -> tuple[str, int | None]:
    """(state, exit code). state is alive | exited | killed | gone."""
    exit_file = Path(rec["exit"])
    code: int | None = None
    if exit_file.exists():
        try:
            code = int(exit_file.read_text().strip())
        except ValueError:
            code = None
    live = _proc(rec["pid"]) is not None
    if live:
        return ("alive", None)
    if code is not None:
        return ("exited", code)
    if rec.get("killed"):
        return ("killed", None)
    # No exit file and no signal from us: SIGKILLed by something else, or the
    # box went down. "gone" says we do not know, which is the truth.
    return ("gone", None)


def _kill_group(pid: int, sig: int) -> None:
    """Signal the whole group, not just the leader.

    ``start_new_session=True`` makes the child its own group leader, so its
    pgid is its pid — and a grandchild that inherited the pipe dies with it.
    Killing only the leader leaves that grandchild holding the write end, which
    is the same hang this module exists to prevent. (``fs_tool._kill_group`` is
    the same six lines for the same reason; both are kept local so neither
    module's reload can hand the other a stale function.)
    """
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass


# --------------------------------------------------------------------------
# run — the cell waits
# --------------------------------------------------------------------------


async def _drain(stream, buf: bytearray, limit: int, state: dict[str, bool]) -> None:
    """Read a stream into buf up to limit, then keep reading and discard.

    Discarding rather than stopping matters: a child that fills its pipe and
    gets no reader blocks on write forever, and the timeout then reports a hang
    that was really a full buffer.
    """
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            return
        room = limit - len(buf)
        if room > 0:
            buf.extend(chunk[:room])
        if len(chunk) > room:
            state["truncated"] = True


async def _run(
    cmd: str,
    cwd: str | None,
    env: dict[str, str] | None,
    timeout: float,
    limit: int,
) -> ProcResult:
    started = time.monotonic()
    # /bin/bash explicitly, not create_subprocess_shell's /bin/sh: the
    # docstring promises bash semantics (&&, [[ ]], process substitution) and
    # /bin/sh is dash on some boxes, where those are syntax errors.
    proc = await asyncio.create_subprocess_exec(
        "/bin/bash",
        "-c",
        cmd,
        cwd=cwd,
        env=_env(env),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    out, err = bytearray(), bytearray()
    state = {"truncated": False}
    readers = [
        asyncio.create_task(_drain(proc.stdout, out, limit, state)),
        asyncio.create_task(_drain(proc.stderr, err, limit, state)),
    ]

    timed_out = False
    try:
        async with asyncio.timeout(timeout):
            await proc.wait()
    except TimeoutError:
        timed_out = True
        _kill_group(proc.pid, signal.SIGKILL)
        try:
            async with asyncio.timeout(_KILL_GRACE):
                await proc.wait()
        except TimeoutError:
            pass

    note = ""
    try:
        async with asyncio.timeout(_GRACE):
            await asyncio.gather(*readers)
    except TimeoutError:
        for task in readers:
            task.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        note = (
            "the command exited but its output pipe stayed open — it left a "
            "background process holding the write end, which is what hangs "
            "subprocess.run(capture_output=True) forever. Returning what it had "
            "written. To launch a server or a daemon on purpose, use "
            "proc('start', ...)."
        )

    return ProcResult(
        mode="run",
        cmd=cmd,
        returncode=proc.returncode,
        stdout=bytes(out).decode("utf-8", "replace"),
        stderr=bytes(err).decode("utf-8", "replace"),
        pid=proc.pid,
        ms=int((time.monotonic() - started) * 1000),
        truncated=state["truncated"],
        timed_out=timed_out,
        note=note,
    )


def _env(extra: dict[str, str] | None) -> dict[str, str] | None:
    if not extra:
        return None
    return {**os.environ, **{str(k): str(v) for k, v in extra.items()}}


# --------------------------------------------------------------------------
# start — the cell does not wait
# --------------------------------------------------------------------------


async def _start(
    cmd: str, cwd: str | None, env: dict[str, str] | None, log: str | None
) -> ProcResult:
    if log:
        log_path = Path(log).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    else:
        (_root() / "logs").mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(suffix=".log", dir=str(_root() / "logs"))
        log_path = Path(name)
    exit_path = log_path.with_name(log_path.name + ".exit")

    # "$@" runs the command as its own argv, so cmd is never re-quoted; the
    # exit code lands in a file because nobody is blocked on this child and
    # ps would otherwise have nothing better than "not alive any more".
    wrapper = '"$@"; echo $? > ' + shlex.quote(str(exit_path))
    argv = ["/bin/bash", "-c", wrapper, "crow-proc", "/bin/bash", "-c", cmd]

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=_env(env),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=fd,
            stderr=fd,
            start_new_session=True,
        )
    finally:
        os.close(fd)  # the child has its own dup; ours would hold the file open

    _record(
        {
            "pid": proc.pid,
            "cmd": cmd,
            "cwd": cwd or os.getcwd(),
            "log": str(log_path),
            "exit": str(exit_path),
            "started": time.time(),
        }
    )
    return ProcResult(
        mode="start",
        cmd=cmd,
        pid=proc.pid,
        log=str(log_path),
        detached=True,
    )


# --------------------------------------------------------------------------
# ps / log / wait / kill
# --------------------------------------------------------------------------


def _ps() -> ProcResult:
    procs = []
    for rec in _records():
        state, code = _state(rec)
        procs.append(
            {
                "pid": rec["pid"],
                "cmd": rec["cmd"],
                "cwd": rec.get("cwd", ""),
                "log": rec.get("log"),
                "state": state,
                "returncode": code,
                "started": rec.get("started"),
            }
        )
    procs.sort(key=lambda p: p["started"] or 0)
    return ProcResult(mode="ps", procs=procs)


def _tail(path: Path, n: int) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        block = 65536
        data = b""
        while size > 0 and data.count(b"\n") <= n:
            step = min(block, size)
            size -= step
            fh.seek(size)
            data = fh.read(step) + data
    lines = data.decode("utf-8", "replace").splitlines()
    return "\n".join(lines[-n:])


async def _wait(rec: dict[str, Any], timeout: float) -> ProcResult:
    started = time.monotonic()
    deadline = started + timeout
    while True:
        state, code = _state(rec)
        if state != "alive":
            return ProcResult(
                mode="wait",
                cmd=rec["cmd"],
                pid=rec["pid"],
                log=rec.get("log"),
                returncode=code,
                detached=True,
                ms=int((time.monotonic() - started) * 1000),
                note="" if state == "exited" else f"process is {state}",
            )
        if time.monotonic() >= deadline:
            return ProcResult(
                mode="wait",
                cmd=rec["cmd"],
                pid=rec["pid"],
                log=rec.get("log"),
                returncode=None,
                detached=True,
                timed_out=True,
                ms=int((time.monotonic() - started) * 1000),
                note=(
                    "still running — wait gave up watching, it did NOT kill "
                    "anything. proc('kill', pid=…) stops it."
                ),
            )
        await asyncio.sleep(0.25)


async def _kill(rec: dict[str, Any], sig: str) -> ProcResult:
    signum = getattr(signal, f"SIG{sig.upper()}", None)
    if not isinstance(signum, signal.Signals):
        raise ProcError(f"unknown signal {sig!r} — try TERM, KILL, INT, HUP")
    pid = rec["pid"]
    live = _proc(pid)
    if live is not None and not _same_process(rec, live):
        raise ProcError(
            f"pid {pid} has been recycled — it is a different process now "
            f"(started {live.create_time():.0f}, this one started "
            f"{rec['started']:.0f}). Refusing to signal it."
        )
    _kill_group(pid, signum)
    if signum != signal.SIGKILL:
        await asyncio.sleep(0.4)
        if _proc(pid) is not None:
            _kill_group(pid, signal.SIGKILL)
    _record({"pid": pid, "killed": sig.upper()})
    state, code = _state({**rec, "killed": sig.upper()})
    return ProcResult(
        mode="kill", cmd=rec["cmd"], pid=pid, log=rec.get("log"), returncode=code,
        note=f"SIG{sig.upper()} sent to process group {pid}; now {state}",
    )


@subtool(tool="proc")
async def proc(
    mode: str,
    cmd: str | None = None,
    *,
    cwd: str | None = None,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
    log: str | None = None,
    pid: int | None = None,
    tail: int = 200,
    limit: int | None = None,
    sig: str = "TERM",
) -> ProcResult:
    """Run a command, or launch one that outlives the cell. Returns ProcResult.

    THE RULE — a server, a watcher, a build you will check on later, anything
    with ``&`` or ``nohup`` in it, goes through ``start`` and never through
    ``run`` or ``subprocess``:

        r = await proc("start", "python -m http.server 8000")   # returns NOW
        print(r.pid, r.log)

    ``nohup cmd &`` and ``setsid cmd`` do NOT detach from a captured pipe. The
    hang is not about signals or sessions, it is about file descriptors: the
    backgrounded child inherits the pipe's write end, EOF never arrives, and the
    caller waits forever. ``start`` is the only shape that works, because it
    points stdout/stderr at a file instead of a pipe. Verified live: a
    self-daemonizing script under ``subprocess.run(capture_output=True)`` wedged
    the kernel and needed a reset; the same script under ``proc("start", ...)``
    returned its pid in milliseconds.

    Args:
        mode: "run", "start", "ps", "log", "wait" or "kill".
        cmd: the shell command — required for run and start. Runs through
            ``/bin/bash -c``, so pipes, redirects and ``&&`` work as usual.
        cwd: working directory (default: the kernel's cwd). Absolute, or
            relative to it.
        timeout: run — seconds before the whole process group is SIGKILLed
                (default 60). wait — seconds to watch before giving up
                (default 60); giving up does NOT kill anything. Give the
                containing execute cell a larger timeout than this, or the
                cell returns "kernel busy" while proc is still waiting.
        env: extra environment variables, merged over os.environ.
        log: start — where stdout+stderr go (appended). Default is a fresh
            file under /tmp/crow-proc/logs/, and its path comes back as
            ``.log``. log — the file to tail, if you would rather name the
            path than the pid.
        pid: ps/log/wait/kill — which started process. Must be one THIS
            session started; an unregistered pid raises rather than signalling
            a stranger (pids get recycled, and the start time is checked).
        tail: log — how many trailing lines to return (default 200).
        limit: run — per-stream byte cap (default 400,000). Past the cap the
            output is drained and discarded, and ``.truncated`` is True.
        sig: kill — "TERM" (default), "KILL", "INT" or "HUP". TERM goes to the
            whole group first, and only becomes KILL if the leader survives it.

    Returns:
        ProcResult. ``.text`` is the bounded rendering — print(r) shows it.
        For code: ``.returncode`` — the exit status, negative for the signal
        that killed it (a timeout ends in ``-9``), and None only for a process
        that is still running,
        ``.stdout`` / ``.stderr`` (run), ``.pid`` / ``.log`` (start),
        ``.procs`` (ps: dicts of pid/cmd/cwd/log/state/returncode/started),
        ``.ms``, ``.truncated``, ``.timed_out``, ``.note``, and ``.ok`` —
        True for a run/wait that exited 0, and for the modes where returning
        at all is success.

    Raises:
        ProcError: unknown mode, missing cmd, a pid this session never
            started, a recycled pid, or an unreadable log.

    Note:
        ``run`` waits on the PROCESS, not on pipe EOF, then drains for up to
        two more seconds. So a command that accidentally backgrounds something
        returns with its partial output and a ``.note`` explaining what
        happened, instead of hanging the kernel — the trap is defused even when
        you fall into it. That is a safety net, not a licence: use ``start``.

        ``start`` returns when the child is SPAWNED, not when it is READY.
        Observed live: a static file server came back in 0 ms, and the next
        line — reading the portfile that server writes once its socket is
        bound — raised FileNotFoundError; the file appeared about a second
        later. Poll for the program's own readiness signal (a portfile, a line
        in ``proc("log", pid=…)``, an open port) instead of assuming the next
        statement can use it. proc deliberately does not guess one for you:
        only the program knows what ready means.

        A ``run`` that times out has already killed the process group; a
        ``wait`` that times out has not touched it. ``.timed_out`` is True for
        both, so read ``.note``.

        The registry is /tmp/crow-proc/<session>.jsonl and survives reload()
        and a kernel reset, which is the point: a detached process is supposed
        to outlive the kernel that started it, and so is the ability to find
        it. Set CROW_PROC_DIR to relocate it (tests do).

    Examples:
        Verified live::

            r = await proc("run", "git --no-pager status --short")
            print(r.returncode, r.stdout)

            r = await proc("run", "uv --project . run pytest -q", timeout=300)
            print(r.text)                      # exit 0 in 4213 ms + the tail

            r = await proc("start", "python -m http.server 0")
            print(r.pid, r.log)                # returned immediately
            while not (await proc("log", pid=r.pid)).stdout.strip():
                time.sleep(0.2)                # spawned is not ready: wait for the log line
            r = await proc("ps");      print(r.text)
            r = await proc("log", pid=r.pid);  print(r.stdout)
            r = await proc("wait", pid=..., timeout=120)
            r = await proc("kill", pid=...)
    """
    if mode not in _MODES:
        raise ProcError(f"unknown proc mode {mode!r} — expected one of {_MODES}")

    if mode in ("run", "start"):
        if not cmd:
            raise ProcError(f"mode={mode!r} requires cmd=")
        workdir = str(Path(cwd).expanduser().resolve()) if cwd else None
        if workdir and not Path(workdir).is_dir():
            raise ProcError(f"not a directory: {workdir}")
        if mode == "run":
            return await _run(
                cmd, workdir, env, float(timeout or _DEFAULT_TIMEOUT),
                int(limit or _MAX_BYTES),
            )
        return await _start(cmd, workdir, env, log)

    if mode == "ps":
        return _ps()

    if mode == "log":
        if pid is None and not log:
            raise ProcError("mode='log' requires pid= or log=")
        rec = _find(int(pid)) if pid is not None else None
        path = Path(log).expanduser() if log else Path(rec["log"])
        if not path.exists():
            raise ProcError(f"no such log file: {path}")
        return ProcResult(
            mode="log", cmd=rec["cmd"] if rec else "", pid=pid, log=str(path),
            stdout=_tail(path, int(tail)),
        )

    if pid is None:
        raise ProcError(f"mode={mode!r} requires pid=")
    rec = _find(int(pid))
    if mode == "wait":
        return await _wait(rec, float(timeout or _DEFAULT_TIMEOUT))
    return await _kill(rec, sig)
