"""E2E: the `task` MCP tool drives REAL subagent subprocesses.

The full loop, no mocks: tool call -> STATE FIRST row -> SubagentDriver
spawns a child crow agent -> child runs a real model turn -> completion
lands in the owner's task_deliveries mailbox with the child's answer.

What this proves:
- launch: running row before ACP traffic, ack returns immediately,
  terminal state + delivery land when the child finishes.
- mcpServers passthrough: the child inherits the owner's client-defined
  servers (Phase 0 round trip) and actually USES them — the [] cascade
  regression stays dead.
- cancel: SYNCHRONOUS — the ack returns only after the task row is
  terminal, and NO delivery lands (the caller knows; it called cancel).
- cancel -> re-prompt: the redirect workflow as two tool updates —
  cancel, then a prompt with the same session_id. The SAME subagent
  answers with its history intact.

Isolation: the tool writes state to a tmp db (CROW_DB_URI); the child
gets a tmp config (CROW_CONFIG_FILE forwarded as --config-file) whose
memory_path points at the SAME tmp db — tool and child couple through
that file, exactly the production shape. Owner attribution rides the
call's _meta (injected by execute_acp_task in production; by this test
directly), never the environment.
"""

import asyncio
import os
import re
import signal
from pathlib import Path

import pytest
from fastmcp import Client

from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.reads import get_task, pending_deliveries
from crow_cli.memory.writes import create_agent, set_agent_mcp_servers

MODEL = "qwen3.8-max-preview"
WORKTREE = "/home/thomas/src/crow-team/crow-cli-taskmaster"
OWNER = "owner-e2e"

pytestmark = pytest.mark.asyncio


def _provider_available() -> bool:
    from crow_cli.config import Config

    try:
        config = Config.load()
        model = config.llm.models.get(MODEL)
        if model is None:
            return False
        return config.llm.providers.get(model.provider_name) is not None
    except Exception:
        return False


@pytest.fixture
async def task_e2e(tmp_path, monkeypatch):
    if not _provider_available():
        pytest.skip(f"{MODEL} / its provider is not configured")

    db = tmp_path / "task-e2e.db"
    uri = f"sqlite:///{db}"
    create_database(uri)

    # Child config = the real config with the db swapped for the tmp one,
    # so the child's transcript lands where the tool reads it.
    real = Path("~/.agents/crow/config.yaml").expanduser()
    lines = [
        f"memory_path: {db}"
        if line.startswith(("memory_path:", "db_uri:"))
        else line
        for line in real.read_text().splitlines()
    ]
    cfg = tmp_path / "child-config.yaml"
    cfg.write_text("\n".join(lines) + "\n")

    monkeypatch.setenv("CROW_DB_URI", uri)
    monkeypatch.setenv("CROW_CONFIG_FILE", str(cfg))

    from crow_cli.mcp.server.app import mcp

    import crow_cli.mcp.task.main as task_mod  # noqa: F401 — registers

    task_mod._LIVE.clear()
    yield mcp, get_engine(uri)
    # Teardown: never orphan a child, even when a test fails mid-flight.
    for live in list(task_mod._LIVE.values()):
        try:
            await live.driver.close()
        except Exception:
            pass
    task_mod._LIVE.clear()


async def _call(mcp, updates, owner=OWNER):
    async with Client(mcp) as client:
        kwargs = {"meta": {"session_id": owner}} if owner else {}
        r = await client.call_tool("task", {"updates": updates}, **kwargs)
    return r.data


async def _wait_terminal(engine, task_id, timeout=240):
    for _ in range(timeout // 2):
        t = get_task(engine, task_id)
        if t is not None and t.status != "running":
            return t
        await asyncio.sleep(2)
    pytest.fail(f"{task_id} still running after {timeout}s")


async def _wait_sub_session(engine, task_id, timeout=60):
    for _ in range(timeout // 2):
        t = get_task(engine, task_id)
        if t is not None and t.sub_session:
            return t.sub_session
        await asyncio.sleep(2)
    pytest.fail(f"{task_id} never got a sub session")


async def test_launch_runs_to_completion(task_e2e):
    mcp, engine = task_e2e
    ack = await _call(
        mcp,
        [
            {
                "action": "prompt",
                "prompt": "What is 27 * 43? Reply with ONLY the number.",
                "model": MODEL,
            }
        ],
    )
    assert ack.startswith("launched task-1")

    task = await _wait_terminal(engine, "task-1")
    assert task.status == "completed"
    assert "1161" in task.result

    deliveries = pending_deliveries(engine, OWNER)
    assert len(deliveries) == 1
    assert deliveries[0].task_id == "task-1"
    assert "finished" in deliveries[0].content
    assert "1161" in deliveries[0].content


async def test_two_subagents_high_and_low_both_deliver(task_e2e):
    """PLAN 6.2: one `task` call launches TWO subagents, one high one low
    priority. Both run to completion and BOTH deliveries land in the
    owner's mailbox, each carrying its own priority — the mailbox is the
    durable proof; the loop's priority routing is covered by the
    integration/consult tests."""
    mcp, engine = task_e2e
    ack = await _call(
        mcp,
        [
            {
                "action": "prompt",
                "prompt": "What is 2 + 2? Reply with ONLY the number.",
                "priority": "high",
                "model": MODEL,
            },
            {
                "action": "prompt",
                "prompt": "What is 3 + 3? Reply with ONLY the number.",
                "priority": "low",
                "model": MODEL,
            },
        ],
    )
    assert "launched task-1" in ack
    assert "launched task-2" in ack

    t1 = await _wait_terminal(engine, "task-1")
    t2 = await _wait_terminal(engine, "task-2")
    assert t1.status == "completed" and "4" in t1.result
    assert t2.status == "completed" and "6" in t2.result

    deliveries = pending_deliveries(engine, OWNER)
    assert len(deliveries) == 2
    by_task = {d.task_id: d for d in deliveries}
    assert by_task["task-1"].priority == "high"
    assert by_task["task-2"].priority == "low"
    assert "4" in by_task["task-1"].content
    assert "6" in by_task["task-2"].content


async def test_owner_mcp_servers_pass_through(task_e2e):
    """The child inherits the owner's mcpServers and USES them: the
    directive needs the terminal tool, which only exists if the crow-mcp
    round trip survived launch."""
    mcp, engine = task_e2e
    # mcpServers ride the agents table: provision the owner's trunk row, then
    # store the client's list on it (exactly what session/new does).
    owner_agent = f"{OWNER}-1-1"
    create_agent(engine, agent_id=owner_agent, session_id=OWNER, agent_idx=1, fork_idx=1)
    set_agent_mcp_servers(
        engine,
        owner_agent,
        [
            {
                "name": "crow-mcp",
                "command": "uv",
                "args": ["--project", WORKTREE, "run", "crow-cli", "mcp"],
                "env": [],
            }
        ],
    )
    ack = await _call(
        mcp,
        [
            {
                "action": "prompt",
                "prompt": (
                    "Do NOT delegate this to a subagent and do not use the "
                    "task tool. Use the terminal tool you have been given "
                    "to run this exact command: date. Then reply with ONLY the "
                    "raw output, nothing else."
                ),
                "model": MODEL,
            }
        ],
    )
    assert ack.startswith("launched task-1")

    task = await _wait_terminal(engine, "task-1", timeout=300)
    assert task.status == "completed"
    # date(1) output: HH:MM:SS — only reachable through the passed-through
    # terminal tool.
    assert re.search(r"\d{2}:\d{2}:\d{2}", task.result), task.result


async def test_cancel_mid_turn(task_e2e):
    """Cancel is SYNCHRONOUS: when the ack returns, the task row is
    already terminal — and no delivery lands, because the caller is the
    one who cancelled."""
    mcp, engine = task_e2e
    ack = await _call(
        mcp,
        [
            {
                "action": "prompt",
                "prompt": (
                    "Write a 3000-word essay about the history of lighthouses. "
                    "Take your time and be thorough."
                ),
                "model": MODEL,
            }
        ],
    )
    assert ack.startswith("launched task-1")
    sub = await _wait_sub_session(engine, "task-1")
    await asyncio.sleep(10)  # let the child get mid-turn

    ack = await _call(mcp, [{"action": "cancel", "session_id": sub}])
    assert ack.startswith("cancelled ")

    # No wait: the ack is the guarantee.
    task = get_task(engine, "task-1")
    assert task.status == "cancelled"
    assert pending_deliveries(engine, OWNER) == []


async def test_cancel_then_reprompt_same_session(task_e2e):
    """The redirect workflow, end to end: launch a long task, cancel it
    mid-turn, then re-prompt the SAME session_id. The same subagent
    answers — with the history of the cancelled turn intact — and the
    completion delivers exactly once."""
    mcp, engine = task_e2e
    ack = await _call(
        mcp,
        [
            {
                "action": "prompt",
                "prompt": (
                    "First tell me what 12 * 12 is (just the number), then "
                    "write a 3000-word essay about the history of lighthouses. "
                    "Take your time and be thorough."
                ),
                "model": MODEL,
            }
        ],
    )
    assert ack.startswith("launched task-1")
    sub = await _wait_sub_session(engine, "task-1")
    await asyncio.sleep(10)

    ack = await _call(mcp, [{"action": "cancel", "session_id": sub}])
    assert ack.startswith("cancelled ")
    assert get_task(engine, "task-1").status == "cancelled"

    # Redirect: a prompt with the same session_id re-attaches and reopens.
    ack = await _call(
        mcp,
        [
            {
                "action": "prompt",
                "prompt": (
                    "Stop the essay, it was just a test. Reply with exactly: "
                    "REDIRECTED"
                ),
                "session_id": sub,
            }
        ],
    )
    assert "re-prompted task-1" in ack

    task = await _wait_terminal(engine, "task-1", timeout=120)
    assert task.status == "completed"
    assert "REDIRECTED" in task.result
    deliveries = pending_deliveries(engine, OWNER)
    assert len(deliveries) == 1
    assert "REDIRECTED" in deliveries[0].content
    assert "was cancelled" not in deliveries[0].content


async def test_child_crash_registers_failed(task_e2e):
    """A child that dies mid-turn must register failed + deliver — never
    hang. Kill -9 the subprocess; the watcher's prompt future breaks on
    the dead transport and finish_task lands the failure."""
    mcp, engine = task_e2e

    import crow_cli.mcp.task.main as task_mod

    ack = await _call(
        mcp,
        [
            {
                "action": "prompt",
                "prompt": (
                    "Write a 3000-word essay about the history of lighthouses. "
                    "Take your time and be thorough."
                ),
                "model": MODEL,
            }
        ],
    )
    assert ack.startswith("launched task-1")
    sub = await _wait_sub_session(engine, "task-1")
    await asyncio.sleep(8)  # let the child get mid-turn

    live = task_mod._LIVE[sub]
    os.kill(live.driver.proc.pid, signal.SIGKILL)

    task = await _wait_terminal(engine, "task-1", timeout=60)
    assert task.status == "failed"
    deliveries = pending_deliveries(engine, OWNER)
    assert len(deliveries) == 1
    assert "failed" in deliveries[0].content
