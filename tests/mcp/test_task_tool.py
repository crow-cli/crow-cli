"""The `task` MCP tool — dispatch guards, no subprocess.

Driven through a REAL in-process fastmcp Client (the shape the agent
uses — meta included); the live paths (launch/re-prompt/cancel driving
a real child agent) are e2e: tests/e2e/test_task_mcp_launch.py. Here
the tool talks to a REAL temp sqlite and exercises every branch that
must be correct BEFORE any ACP traffic: owner attribution, unknown
sessions, double-launch guards.
"""

import pytest
from fastmcp import Client

from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.writes import launch_task

pytestmark = pytest.mark.asyncio

OWNER = "owner-session"


@pytest.fixture
def task_env(tmp_path, monkeypatch):
    uri = f"sqlite:///{tmp_path / 'task-tool.db'}"
    create_database(uri)
    monkeypatch.setenv("CROW_DB_URI", uri)
    from crow_cli.mcp.server.app import mcp
    import crow_cli.mcp.task.main  # noqa: F401 — registers the tool

    return mcp, get_engine(uri)


async def _call(mcp, updates, owner=OWNER):
    async with Client(mcp) as client:
        kwargs = {"meta": {"session_id": owner}} if owner else {}
        result = await client.call_tool("task", {"updates": updates}, **kwargs)
    return result.data


async def test_schema_hides_attribution(task_env):
    """The LLM sees ONLY updates — session_id rides the call meta."""
    mcp, _ = task_env
    async with Client(mcp) as client:
        tools = await client.list_tools()
    [tool] = [t for t in tools if t.name == "task"]
    assert list(tool.inputSchema.get("properties", {}).keys()) == ["updates"]


async def test_missing_owner_is_refused(task_env):
    mcp, _ = task_env
    out = await _call(mcp, [{"action": "prompt", "prompt": "x"}], owner=None)
    assert "no session_id" in out


async def test_cancel_of_a_session_not_live_here(task_env):
    mcp, _ = task_env
    out = await _call(mcp, [{"action": "cancel", "session_id": "ghost-session"}])
    assert "not live" in out


async def test_reprompt_of_an_unknown_session(task_env):
    mcp, _ = task_env
    out = await _call(
        mcp,
        [{"action": "prompt", "prompt": "again", "session_id": "ghost-session"}],
    )
    assert "no task owns" in out


async def test_reprompt_refuses_a_running_task(task_env):
    """A task row still marked running (its watcher lives elsewhere or
    died uncleanly) must not be double-driven from this process."""
    mcp, engine = task_env
    launch_task(
        engine,
        task_id="task-1",
        owner_session=OWNER,
        sub_session="busy-session",
    )
    out = await _call(
        mcp,
        [{"action": "prompt", "prompt": "again", "session_id": "busy-session"}],
    )
    assert "already running" in out


async def test_task_ids_do_not_collide_across_owners(task_env):
    """Regression: task-N numbering is global because the UNIQUE constraint
    on task_id is. A per-owner counter made every session's FIRST task
    compute count(own)+1 == 1 and collide with the first-ever task-1."""
    from crow_cli.mcp.task.main import PromptItem, _register_task

    _, engine = task_env
    item = PromptItem(prompt="x")
    assert _register_task(engine, "session-a", item) == "task-1"
    assert _register_task(engine, "session-b", item) == "task-2"


async def test_register_task_absorbs_id_collisions(task_env):
    """count()+1 can still land on a taken id (deleted rows, concurrent
    launches); the IntegrityError retry moves on to the next free N."""
    from crow_cli.mcp.task.main import PromptItem, _register_task

    _, engine = task_env
    launch_task(engine, task_id="task-1", owner_session="session-a")
    launch_task(engine, task_id="task-3", owner_session="session-a")
    # count() == 2 -> first candidate task-3 collides -> retry lands task-4
    assert _register_task(engine, "session-b", PromptItem(prompt="x")) == "task-4"
