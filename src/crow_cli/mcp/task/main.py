"""The `task` tool — the MCP-side half of the task system.

Schema + sqlite coupling + dispatch. Durable state (tasks,
task_deliveries) lives in the shared sqlite; the ACP machinery is
delegated to crow_cli.client.subagent.SubagentDriver. The two halves
couple through the database, never in-process.

Phase 1 scope: bg-only subagents — launch, re-prompt, cancel. No fg,
no run_mode, no command tasks. Completions land in the owner's
task_deliveries mailbox THE MOMENT they arrive (finish_task is one
commit); the agent's react loop drains them (Phase 4).
"""

import asyncio
import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, Union

from fastmcp import Context
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

import crow_cli.memory as cm
from crow_cli.client.subagent import SubagentDriver
from crow_cli.mcp.memory import store
from crow_cli.mcp.server.app import mcp
from crow_cli.memory.reads import (
    count_tasks,
    get_session_mcp_servers,
    get_task,
    list_agents,
    load_agent_messages,
    task_by_sub_session,
)
from crow_cli.memory.writes import (
    cancel_task,
    finish_task,
    launch_task,
    reopen_task,
    set_task_sub_session,
)


class PromptItem(BaseModel):
    """Send a prompt to a session. session_id omitted/None launches a NEW
    subagent; with session_id it re-prompts an existing (ended/cancelled)
    session, re-attaching via session/load."""

    action: Literal["prompt"] = "prompt"
    prompt: str
    session_id: str | None = None
    priority: Literal["high", "low"] = "low"
    model: str | None = None


class CancelTurn(BaseModel):
    """session/cancel a running session mid-turn. Synchronous: when the
    tool call returns, the turn is dead and the task row is terminal.
    There is NO follow-up argument — to redirect, send a second prompt
    update with the same session_id."""

    action: Literal["cancel"] = "cancel"
    session_id: str


TaskUpdate = Annotated[Union[PromptItem, CancelTurn], Field(discriminator="action")]


@dataclass
class LiveTask:
    task_id: str
    driver: SubagentDriver
    # Set when the watcher has finalized state and released the session —
    # cancel awaits this so its ack means "terminal, re-promptable NOW".
    done: asyncio.Event = field(default_factory=asyncio.Event)


# Subagents THIS server process drives, keyed by the child's wire session
# id (cancel and re-prompt both address it). Process-local handle table —
# the durable truth is sqlite.
_LIVE: dict[str, LiveTask] = {}


def _engine():
    """WRITE engine on the shared db (the read-only facade is for query
    tools; the task tool registers state)."""
    return cm.get_engine(store.db_uri())


def _child_config() -> dict:
    """Config context for spawned subagents, forwarded from THIS process's
    env. Phase 5.1 injects these where the agent spawns per-session MCP
    servers, so the child resolves the SAME config (and db) the task tool
    writes state to."""
    kwargs: dict = {}
    if f := os.environ.get("CROW_CONFIG_FILE"):
        kwargs["config_file"] = Path(f)
    if d := os.environ.get("CROW_CONFIG_DIR"):
        kwargs["config_dir"] = Path(d)
    return kwargs


def _last_assistant_text(messages: list[dict]) -> str:
    """The subagent's final answer: last assistant message with content."""
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if any(t.strip() for t in texts):
                return " ".join(texts)
    return "(the subagent produced no final answer)"


def _child_answer(engine, sub_session: str) -> str:
    """The child's final answer, read from the shared sqlite — the same
    transcript `query_session` on its session id would see."""
    trunks = [
        a for a in list_agents(engine, session_id=sub_session) if a.fork_idx == 1
    ]
    if not trunks:
        return "(the subagent produced no transcript)"
    agent = max(trunks, key=lambda a: a.agent_idx)
    return _last_assistant_text(load_agent_messages(engine, agent))


async def _watch(task_id: str, sub: str, text: str, engine) -> None:
    """Drive the child's ONE turn to completion, then STATE FIRST: flip the
    task row (+ land the delivery for completed/failed) in one commit.

    Cancelled turns deliver NOTHING — the cancel was a synchronous tool
    call by the owner, who already knows. Releasing the session handle
    happens BEFORE the (slow) driver teardown so a cancel-then-re-prompt
    doesn't bounce off a stale "mid-turn" guard."""
    live = _LIVE[sub]
    driver = live.driver
    status, result = "completed", None
    try:
        resp = await driver.prompt(sub, text)
        if resp.stop_reason == "cancelled":
            status = "cancelled"
    except Exception as e:  # driver/transport failure
        status, result = "failed", str(e)

    try:
        if status == "completed":
            result = _child_answer(engine, sub)
            finish_task(
                engine,
                task_id,
                result=result,
                status=status,
                content=f"[{task_id}: subagent {sub} finished]\n{result}",
            )
        elif status == "failed":
            finish_task(
                engine,
                task_id,
                result=result,
                status=status,
                content=f"[{task_id}: subagent {sub} failed: {result}]",
            )
        else:  # cancelled — the caller knows; no delivery
            cancel_task(engine, task_id)
    finally:
        _LIVE.pop(sub, None)
        live.done.set()
        with contextlib.suppress(Exception):
            await driver.close()


def _register_task(engine, owner: str, item: PromptItem) -> str:
    """STATE FIRST: the running row exists before any ACP traffic, so a fast
    completion can never outrun the record.

    task-N numbering is GLOBAL — task_id is UNIQUE globally, so a per-owner
    counter collides the moment a second session launches its first task.
    The retry absorbs races (concurrent launches) and deleted-row gaps."""
    n = count_tasks(engine) + 1
    while True:
        task_id = f"task-{n}"
        try:
            launch_task(
                engine,
                task_id=task_id,
                owner_session=owner,
                prompt=item.prompt,
                model=item.model,
                priority=item.priority,
            )
            return task_id
        except IntegrityError:
            n += 1


async def _launch(engine, owner: str, item: PromptItem) -> str:
    cwd = os.getcwd()
    # Phase 0 round trip: the child inherits the owner's client-defined
    # mcpServers — the [] cascade regression stops here.
    servers = get_session_mcp_servers(engine, owner)
    task_id = _register_task(engine, owner, item)
    driver = SubagentDriver()
    try:
        await driver.start(cwd, model=item.model, **_child_config())
        sub = await driver.new_session(cwd, mcp_servers=servers)
    except Exception as e:
        finish_task(
            engine,
            task_id,
            result=str(e),
            status="failed",
            content=f"[{task_id}: launch failed: {e}]",
        )
        with contextlib.suppress(Exception):
            await driver.close()
        return f"{task_id}: launch failed: {e}"
    set_task_sub_session(engine, task_id, sub)
    _LIVE[sub] = LiveTask(task_id=task_id, driver=driver)
    asyncio.create_task(_watch(task_id, sub, item.prompt, engine))
    return f"launched {task_id}: subagent {sub} is working"


async def _reprompt(engine, owner: str, item: PromptItem) -> str:
    sid = item.session_id
    if sid in _LIVE:
        return f"error: session {sid} is mid-turn; cancel it first"
    row = task_by_sub_session(engine, sid)
    if row is None:
        return f"error: no task owns session {sid}"
    if row.status == "running":
        return f"error: task {row.task_id} is already running"
    reopen_task(engine, row.task_id)
    cwd = os.getcwd()
    servers = get_session_mcp_servers(engine, owner)
    driver = SubagentDriver()
    try:
        await driver.start(cwd, model=item.model or row.model, **_child_config())
        await driver.load_session(sid, cwd, mcp_servers=servers)
    except Exception as e:
        finish_task(
            engine,
            row.task_id,
            result=str(e),
            status="failed",
            content=f"[{row.task_id}: re-attach to {sid} failed: {e}]",
        )
        with contextlib.suppress(Exception):
            await driver.close()
        return f"error: re-attach to {sid} failed: {e}"
    _LIVE[sid] = LiveTask(task_id=row.task_id, driver=driver)
    asyncio.create_task(_watch(row.task_id, sid, item.prompt, engine))
    return f"re-prompted {row.task_id}: session {sid} is working again"


async def _cancel(engine, item: CancelTurn) -> str:
    """Cancel and WAIT for the watcher to finalize: when this returns, the
    task row is terminal and the session is re-promptable immediately. A
    cancel whose ack lied ("sent" but still mid-turn) is how the redirect
    workflow dies."""
    live = _LIVE.get(item.session_id)
    if live is None:
        return f"error: session {item.session_id} is not live in this process"
    # The turn can end naturally between the _LIVE lookup and this call —
    # a dead transport must not surface as a tool error; the final row
    # status below reports what actually happened.
    with contextlib.suppress(Exception):
        await live.driver.cancel(item.session_id)
    try:
        await asyncio.wait_for(live.done.wait(), timeout=15)
    except TimeoutError:
        return (
            f"cancel sent to {item.session_id} but teardown is still in "
            f"progress — retry the re-prompt in a few seconds"
        )
    row = get_task(engine, live.task_id)
    status = row.status if row is not None else "unknown"
    if status == "cancelled":
        return f"cancelled {item.session_id} (task {live.task_id})"
    return (
        f"cancel sent to {item.session_id}, but task {live.task_id} had "
        f"already finished: {status}"
    )


@mcp.tool
async def task(updates: list[TaskUpdate], ctx: Context) -> str:
    """Launch, re-prompt, or cancel background subagent sessions.

    updates is a list of items, each one of:
      - {"action": "prompt", "prompt": "..."}                     launch a NEW subagent
      - {"action": "prompt", "prompt": "...", "session_id": "s"}  re-prompt session s
        (same subagent, full history preserved — for ended OR cancelled sessions)
      - {"action": "cancel", "session_id": "s"}                   cancel s mid-turn

    Launches are NON-BLOCKING: each item returns an ack immediately, and
    the subagent's result arrives later as a message in this session.
    Cancel is BLOCKING: when it returns, the turn is dead. To redirect a
    running subagent, send TWO updates: cancel, then a prompt with the
    same session_id. Cancels produce NO completion message — you already
    know, you called cancel.
    """
    # Owner attribution rides the call's _meta, injected by the calling
    # agent (execute_acp_task) — the Context param is filtered out of the
    # LLM schema, so the model can neither see nor forge it.
    meta = ctx.request_context.meta if ctx.request_context else None
    owner = getattr(meta, "session_id", None) if meta else None
    if not owner:
        return "error: no session_id in call meta — cannot attribute tasks"
    engine = _engine()
    acks: list[str] = []
    for item in updates:
        if isinstance(item, CancelTurn):
            acks.append(await _cancel(engine, item))
        elif item.session_id is None:
            acks.append(await _launch(engine, owner, item))
        else:
            acks.append(await _reprompt(engine, owner, item))
    return "\n".join(acks)
