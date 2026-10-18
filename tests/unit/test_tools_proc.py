"""proc — run/start/ps/log/wait/kill, over real processes.

No mocks, because the behaviour under test IS the OS-level part: process
groups, pipe lifetimes, and exit codes nobody is blocked on. Every test spawns
a real /bin/bash.

The headline test reproduces the hang this module exists to prevent — a command
that leaves a background child holding the stdout pipe, which wedges
``subprocess.run(capture_output=True)`` until that child exits and returns from
``proc("run")`` in about two seconds with a note saying what happened.
"""

import asyncio
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import psutil
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from crow_cli.memory.db import create_database
from crow_cli.memory.models import SubtoolCall
from crow_cli.tools import proc
from crow_cli.tools.register import begin_cell, clear, pending
from crow_cli.tools.results import ProcError, ProcResult

SESSION = "s-proc"


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    """A private registry per test, and a cell identity so it is keyed."""
    monkeypatch.setenv("CROW_PROC_DIR", str(tmp_path / "proc"))
    clear()
    begin_cell(session_id=SESSION, parent_tool_call_id="turn/call_p")
    yield
    # Nothing a test started may outlive it: a stray `sleep 30` in a suite is
    # a stray `sleep 30` on the machine.
    for rec in _registry_records():
        _sigkill(rec["pid"])
    clear()


def _registry_records() -> list[dict]:
    path = Path(os.environ["CROW_PROC_DIR"]) / f"{SESSION}.jsonl"
    if not path.exists():
        return []
    merged: dict[int, dict] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            merged.setdefault(json.loads(line)["pid"], {}).update(json.loads(line))
    return list(merged.values())


def _sigkill(pid: int) -> None:
    try:
        os.killpg(pid, 9)
    except (ProcessLookupError, PermissionError):
        pass


def _alive(pid: int) -> bool:
    return psutil.pid_exists(pid) and _same(pid)


def _same(pid: int) -> bool:
    """pid_exists is not enough — the pid may have been recycled by pytest's own
    churn. Compare against the start time the registry recorded."""
    for rec in _registry_records():
        if rec["pid"] == pid:
            try:
                return abs(psutil.Process(pid).create_time() - rec["started"]) < 2.0
            except psutil.Error:
                return False
    return psutil.pid_exists(pid)


def _sleeps_left() -> list[int]:
    """Our own leftover `sleep` processes, by group leader."""
    out = []
    for rec in _registry_records():
        try:
            p = psutil.Process(rec["pid"])
        except psutil.Error:
            continue
        if abs(p.create_time() - rec["started"]) < 2.0:
            out.append(rec["pid"])
    return out


# --- run -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_captures_stdout_stderr_and_code():
    r = await proc("run", "echo out; echo err >&2")

    assert isinstance(r, ProcResult) and r
    assert r.mode == "run"
    assert r.stdout == "out\n"
    assert r.stderr == "err\n"
    assert r.returncode == 0
    assert r.ok is True
    assert r.timed_out is False and r.truncated is False
    assert r.ms >= 0
    assert r.result_kind == "proc"
    assert r.acp_payload()["content"] == "text"


@pytest.mark.asyncio
async def test_run_nonzero_exit_is_a_result_not_an_error():
    r = await proc("run", "exit 3")
    assert r.returncode == 3
    assert r.ok is False
    assert "exit 3" in r.text


@pytest.mark.asyncio
async def test_run_honours_cwd_and_env(tmp_path):
    sub = tmp_path / "work"
    sub.mkdir()
    r = await proc("run", "pwd; echo $CROW_TEST_VAR", cwd=str(sub),
                   env={"CROW_TEST_VAR": "hello"})
    assert r.stdout.splitlines() == [str(sub.resolve()), "hello"]


@pytest.mark.asyncio
async def test_run_bad_cwd_raises(tmp_path):
    with pytest.raises(ProcError, match="not a directory"):
        await proc("run", "true", cwd=str(tmp_path / "nope"))


@pytest.mark.asyncio
async def test_run_truncates_at_the_byte_cap():
    r = await proc("run", "yes AAAAAAAAAA | head -n 100000", limit=500)
    assert r.truncated is True
    assert len(r.stdout) <= 500
    assert "TRUNCATED" in r.text


@pytest.mark.asyncio
async def test_run_timeout_kills_the_whole_group(tmp_path):
    """The backgrounded subshell is in the child's group, so it dies too.

    Killing only the leader would leave it running, and it would write its
    marker file two seconds after the "kill" — the exact grandchild-survives
    failure fs_tool._kill_group documents.
    """
    marker = tmp_path / "survived"
    cmd = f"(sleep 1.5; echo x > {marker}) & sleep 30"
    started = time.monotonic()
    r = await proc("run", cmd, timeout=1.0)
    assert r.timed_out is True
    assert r.returncode == -9, "a timeout ends in SIGKILL, and -9 says so"
    assert r.ok is False
    assert time.monotonic() - started < 6
    assert not _sleeps_left(), "the group leader survived its own timeout"

    await asyncio.sleep(2.0)
    assert not marker.exists(), "a grandchild outlived the group kill"


@pytest.mark.asyncio
async def test_run_returns_when_a_background_child_holds_the_pipe():
    """THE trap. bash exits; the backgrounded sleep keeps the stdout pipe's
    write end open, so EOF never arrives. proc waits on the PROCESS, then
    bounds the drain, so this returns in ~2s instead of ~8s."""
    started = time.monotonic()
    r = await proc("run", "echo out; sleep 8 &", timeout=30)
    elapsed = time.monotonic() - started

    assert r.stdout == "out\n"
    assert r.returncode == 0
    assert elapsed < 6, f"waited {elapsed:.1f}s — that is pipe EOF, not the process"
    assert "background process holding the write end" in r.note
    assert "proc('start'" in r.note


@pytest.mark.asyncio
async def test_subprocess_run_hangs_on_the_same_command():
    """The other half of the claim: the stdlib shape really does block.

    Same command, same machine, in a thread so the suite survives it. If this
    ever stops hanging, the trap has changed shape and the docstring above is
    lying — which is worth knowing.
    """
    box: dict = {}

    def go():
        box["r"] = subprocess.run(
            ["/bin/bash", "-c", "echo out; sleep 6 &"],
            capture_output=True, text=True,
        )

    t = threading.Thread(target=go, daemon=True)
    t.start()
    t0 = time.monotonic()
    r = await proc("run", "echo out; sleep 6 &", timeout=30)
    assert r.stdout == "out\n"
    assert time.monotonic() - t0 < 5

    t.join(timeout=1.0)
    assert t.is_alive(), "subprocess.run returned — the pipe closed on its own"
    assert "r" not in box


# --- start / ps / log / wait / kill ---------------------------------------


@pytest.mark.asyncio
async def test_start_returns_immediately_with_pid_and_log(tmp_path):
    started = time.monotonic()
    r = await proc("start", "echo served; sleep 30")
    assert time.monotonic() - started < 2.0

    assert r.mode == "start" and r.detached is True
    assert r.returncode is None and r.alive is True
    assert r.pid and psutil.pid_exists(r.pid)
    assert r.log and Path(r.log).parent.exists()
    assert "detached, logging to" in r.text


@pytest.mark.asyncio
async def test_start_log_path_is_honoured_and_appended(tmp_path):
    log = tmp_path / "srv.log"
    await proc("start", "echo one", log=str(log))
    r = await proc("start", "echo two", log=str(log))
    await proc("wait", pid=r.pid, timeout=10)
    assert Path(r.log).read_text().split() == ["one", "two"]


@pytest.mark.asyncio
async def test_start_records_the_exit_code_nobody_waited_for():
    r = await proc("start", "echo hi; exit 3")
    w = await proc("wait", pid=r.pid, timeout=15)
    assert w.returncode == 3
    assert w.ok is False
    assert w.mode == "wait"

    log = await proc("log", pid=r.pid)
    assert log.stdout.strip() == "hi"


@pytest.mark.asyncio
async def test_ps_shows_alive_then_exited():
    live = await proc("start", "sleep 30")
    dead = await proc("start", "true")
    await proc("wait", pid=dead.pid, timeout=15)

    r = await proc("ps")
    assert r.mode == "ps"
    by_pid = {p["pid"]: p for p in r.procs}
    assert by_pid[live.pid]["state"] == "alive"
    assert by_pid[live.pid]["returncode"] is None
    assert by_pid[dead.pid]["state"] == "exited"
    assert by_pid[dead.pid]["returncode"] == 0
    assert "PID" in r.text and str(dead.pid) in r.text


@pytest.mark.asyncio
async def test_ps_with_nothing_started_says_so():
    r = await proc("ps")
    assert r.procs == []
    assert r.text == "no processes started by proc()"


@pytest.mark.asyncio
async def test_log_tails_only_the_last_n_lines(tmp_path):
    log = tmp_path / "many.log"
    r = await proc("start", "seq 1 500", log=str(log))
    await proc("wait", pid=r.pid, timeout=15)
    out = await proc("log", pid=r.pid, tail=5)
    assert out.stdout.splitlines() == ["496", "497", "498", "499", "500"]


@pytest.mark.asyncio
async def test_log_by_path_needs_no_registry(tmp_path):
    log = tmp_path / "plain.log"
    log.write_text("hello\n")
    r = await proc("log", log=str(log))
    assert r.stdout == "hello"
    assert r.pid is None


@pytest.mark.asyncio
async def test_kill_stops_the_group_and_ps_says_killed():
    r = await proc("start", "sleep 30 & sleep 30")
    pid = r.pid
    assert _alive(pid)

    k = await proc("kill", pid=pid)
    assert k.mode == "kill" and "SIGTERM" in k.note

    await asyncio.sleep(0.3)
    assert not _alive(pid)
    states = {p["pid"]: p["state"] for p in (await proc("ps")).procs}
    assert states[pid] == "killed"


@pytest.mark.asyncio
async def test_wait_times_out_without_killing_anything():
    r = await proc("start", "sleep 30")
    w = await proc("wait", pid=r.pid, timeout=1)
    assert w.timed_out is True and w.returncode is None
    assert "did NOT kill" in w.note
    assert _alive(r.pid), "wait is not kill"


@pytest.mark.asyncio
async def test_wait_returns_at_once_for_an_already_finished_process():
    r = await proc("start", "true")
    await asyncio.sleep(0.6)
    started = time.monotonic()
    w = await proc("wait", pid=r.pid, timeout=30)
    assert w.returncode == 0
    assert time.monotonic() - started < 1.0


# --- the registry is a handle, not a pid ----------------------------------


@pytest.mark.asyncio
async def test_an_unregistered_pid_is_refused():
    for mode in ("kill", "log", "wait"):
        with pytest.raises(ProcError, match="not started by proc"):
            await proc(mode, pid=999999)


@pytest.mark.asyncio
async def test_a_recycled_pid_is_refused():
    """The registry knows when the process it started was born. A pid that now
    belongs to somebody else must not be signalled just because the number
    matches."""
    r = await proc("start", "sleep 30")
    reg = Path(os.environ["CROW_PROC_DIR"]) / f"{SESSION}.jsonl"
    forged = {**[x for x in _registry_records() if x["pid"] == r.pid][0],
              "started": 1_000_000_000.0}   # 2001: not this process
    reg.write_text(reg.read_text() + json.dumps(forged) + "\n")

    with pytest.raises(ProcError, match="recycled"):
        await proc("kill", pid=r.pid)
    # Not _alive(): that helper reads the registry, which this test just
    # forged. Ask the kernel directly whether the process is still there.
    live = psutil.Process(r.pid)
    assert live.status != psutil.STATUS_ZOMBIE, "it signalled the stranger anyway"


@pytest.mark.asyncio
async def test_the_registry_is_on_disk_and_survives_a_reset():
    """A detached process outlives the kernel that started it, so the ability
    to find it has to outlive the kernel too: identity is dropped and re-set,
    which is what a reset does to module state, and ps still sees the launch."""
    r = await proc("start", "sleep 30")
    reg = Path(os.environ["CROW_PROC_DIR"]) / f"{SESSION}.jsonl"
    assert reg.exists() and str(r.pid) in reg.read_text()

    clear()
    begin_cell(session_id=SESSION, parent_tool_call_id="turn2/call_q")
    listed = {p["pid"] for p in (await proc("ps")).procs}
    assert r.pid in listed

    await proc("kill", pid=r.pid)


@pytest.mark.asyncio
async def test_a_different_session_sees_a_different_registry():
    r = await proc("start", "sleep 30")
    clear()
    begin_cell(session_id="s-other", parent_tool_call_id="t/c")
    assert (await proc("ps")).procs == []
    with pytest.raises(ProcError):
        await proc("kill", pid=r.pid)

    clear()
    begin_cell(session_id=SESSION, parent_tool_call_id="t/c")
    await proc("kill", pid=r.pid)


# --- argument handling ----------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_mode_raises():
    with pytest.raises(ProcError, match="unknown proc mode"):
        await proc("launch", "true")


@pytest.mark.asyncio
async def test_run_and_start_need_a_cmd():
    for mode in ("run", "start"):
        with pytest.raises(ProcError, match="requires cmd"):
            await proc(mode)


@pytest.mark.asyncio
async def test_log_needs_a_pid_or_a_path():
    with pytest.raises(ProcError, match="requires pid= or log="):
        await proc("log")


@pytest.mark.asyncio
async def test_kill_and_wait_need_a_pid():
    for mode in ("kill", "wait"):
        with pytest.raises(ProcError, match="requires pid"):
            await proc(mode)


@pytest.mark.asyncio
async def test_an_unknown_signal_raises():
    r = await proc("start", "sleep 30")
    with pytest.raises(ProcError, match="unknown signal"):
        await proc("kill", pid=r.pid, sig="NUKE")


# --- the other two channels ----------------------------------------------


@pytest.mark.asyncio
async def test_the_call_is_recorded_with_its_mode(tmp_path):
    uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(uri)
    clear()
    begin_cell(session_id=SESSION, parent_tool_call_id="turn/call_r", db_uri=uri)

    await proc("run", "echo hi")

    engine = create_engine(uri)
    with sessionmaker(engine)() as s:
        rows = s.execute(select(SubtoolCall)).scalars().all()
    engine.dispose()
    assert len(rows) == 1
    assert rows[0].tool == "proc"
    assert rows[0].mode == "run"
    assert rows[0].status == "completed"
    assert rows[0].args["cmd"] == "echo hi"
    assert rows[0].acp_payload["content"] == "text"
    assert [e.status for e in pending()] == ["completed"]


@pytest.mark.asyncio
async def test_a_failure_is_recorded_as_failed(tmp_path):
    uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(uri)
    clear()
    begin_cell(session_id=SESSION, parent_tool_call_id="turn/call_f", db_uri=uri)

    with pytest.raises(ProcError):
        await proc("nope")

    engine = create_engine(uri)
    with sessionmaker(engine)() as s:
        rows = s.execute(select(SubtoolCall)).scalars().all()
    engine.dispose()
    assert rows[0].status == "failed"
    assert "unknown proc mode" in rows[0].error
    assert rows[0].acp_payload is None
