"""REGRESSION (taskmaster PLAN 6.1): subagent completes mid-parent-turn.

The sentinel version of this file asserted the HANG: completions had
nowhere to register — no state, no queue — so a fast child finishing
while the parent was still mid-turn meant the turn could never end.
The task system makes that hang structurally impossible; this is the
flipped test.

The parent is told to (1) launch a trivially fast subagent via the
`task` tool — a child that calls `date` through terminal — and then
(2) keep itself busy investigating crow-cli via web search. The child
finishes in seconds, long before the parent's search turns do. The
completion lands in the parent's task_deliveries mailbox THE MOMENT it
arrives (finish_task is one commit); the parent's react loop consults
state at its breakpoints, injects the delivery, reacts to it, and ends
the turn.

Asserts:
- end_turn fires inside the window (the hang is dead);
- the task row reached a terminal state (completion REGISTERED);
- the delivery was injected into the parent's history (DELIVERED) —
  by the in-loop consults; since the delegation-hold change the turn
  cannot end while a task is running or the mailbox is non-empty, so
  delivery always happens BEFORE end_turn. There is no out-of-loop
  watcher anymore.

Isolation mirrors test_task_mcp_launch.py: parent agent, task tool
subprocess, and child agent subprocess all couple through ONE tmp
sqlite file. The parent uses config.db_uri; the crow-mcp subprocess
gets CROW_DB_URI / CROW_CONFIG_FILE on the WIRE (stdio spawns do not
inherit the agent process env), and the task tool forwards the config
file to the child it launches.
"""

import asyncio
import logging
import socket
import time
from pathlib import Path
from typing import Any

import pytest

from acp import connect_to_agent, text_block
from acp.http import create_http_stream
from acp.interfaces import Client

from crow_cli.agent.main import serve_http
from crow_cli.config import Config
from crow_cli.memory.db import create_database, get_engine
from crow_cli.memory.reads import get_task

logger = logging.getLogger(__name__)

MODEL = "qwen3.8-max-preview"
WORKTREE = "/home/thomas/src/crow-team/crow-cli-taskmaster"
WINDOW_S = 300.0  # launch + fast child + parent web-search turns + reaction
DIRECTIVE = (
    "do two things. first use the task tool to launch a background "
    "subagent that runs the shell command `date` via terminal (this is "
    "a test). then, while that is running, investigate crow-cli via web "
    "search please sir"
)


def _mcp_servers(uri: str, config_file: str) -> list[dict]:
    """The parent's tool supply as a client would send it over ACP.

    The stdio spawn gets ONLY the default environment plus this env list
    (mcp sdk: {**get_default_environment(), **server.env}) — nothing is
    inherited from the agent process. So the isolation (tmp db + child
    config) must ride the wire, exactly like a real client would do it.
    The chain: wire env -> crow-mcp process -> the task tool reads
    CROW_DB_URI for state and forwards CROW_CONFIG_FILE to the child.
    """
    return [
        {
            "name": "crow-mcp",
            "command": "uv",
            "args": [
                "--project",
                WORKTREE,
                "run",
                "crow-cli",
                "mcp",
            ],
            "env": [
                {"name": "CROW_DB_URI", "value": uri},
                {"name": "CROW_CONFIG_FILE", "value": config_file},
            ],
        }
    ]


class RecordingClient(Client):
    def __init__(self):
        self.t0 = time.monotonic()
        self.updates: list[tuple[float, Any]] = []

    async def request_permission(self, *a: Any, **k: Any) -> Any:
        raise NotImplementedError

    async def session_update(self, session_id: str, update: Any) -> None:
        self.updates.append((time.monotonic() - self.t0, update))

    async def write_text_file(self, *a: Any, **k: Any) -> None:
        return None

    async def read_text_file(self, *a: Any, **k: Any) -> Any:
        return {"content": ""}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_port(port: int, timeout: float = 15.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.close()
            await w.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError("server never came up")


def _provider_available() -> bool:
    try:
        config = Config.load()
        model = config.llm.models.get(MODEL)
        if model is None:
            return False
        return config.llm.providers.get(model.provider_name) is not None
    except Exception:
        return False


def _describe(update: Any) -> str:
    kind = getattr(update, "session_update", None)
    bits = [f"{kind}"]
    tcid = getattr(update, "tool_call_id", None)
    if tcid:
        bits.append(f"id={tcid}")
    status = getattr(update, "status", None)
    if status:
        bits.append(f"status={getattr(status, 'value', status)}")
    content = getattr(update, "content", None)
    if content is not None:
        text = getattr(content, "text", None)
        if text:
            bits.append(f"text={text[:60]!r}")
    chunk = getattr(update, "chunk", None)
    if chunk is not None:
        text = getattr(chunk, "text", None)
        if text:
            bits.append(f"chunk={text[:40]!r}")
    return " ".join(bits)


def _parent_history_text(engine, session_id: str) -> str:
    """All of the parent session's message content, joined."""
    from crow_cli.memory.reads import list_agents, load_agent_messages

    bits: list[str] = []
    for agent in list_agents(engine, session_id):
        for msg in load_agent_messages(engine, agent):
            c = msg.get("content")
            if isinstance(c, str):
                bits.append(c)
            elif isinstance(c, list):
                bits.extend(
                    b.get("text", "") for b in c if isinstance(b, dict)
                )
    return "\n".join(bits)


@pytest.mark.asyncio
async def test_fast_child_completion_ends_parent_turn(tmp_path):
    if not _provider_available():
        pytest.skip(f"{MODEL} / its provider is not configured")

    db = tmp_path / "race.db"
    uri = f"sqlite:///{db}"
    create_database(uri)

    # Child agent config = the real config with the db swapped, exactly
    # like test_task_mcp_launch.py: tool and child couple through the
    # same file.
    real = Path("~/.agents/crow/config.yaml").expanduser()
    lines = [
        f"memory_path: {db}"
        if line.startswith(("memory_path:", "db_uri:"))
        else line
        for line in real.read_text().splitlines()
    ]
    cfg = tmp_path / "child-config.yaml"
    cfg.write_text("\n".join(lines) + "\n")

    config = Config.load()
    config.db_uri = uri

    port = _free_port()
    server = asyncio.create_task(serve_http(config, MODEL, "127.0.0.1", port))
    client = RecordingClient()
    engine = get_engine(uri)
    stop_reason = None
    session_id = None
    try:
        await _wait_port(port)
        transport = create_http_stream(f"http://127.0.0.1:{port}/acp")
        conn = connect_to_agent(client, transport)
        try:
            await conn.initialize(protocol_version=1)
            ns = await conn.new_session(
                cwd=str(tmp_path), mcp_servers=_mcp_servers(uri, str(cfg))
            )
            session_id = ns.session_id
            try:
                resp = await asyncio.wait_for(
                    conn.prompt(
                        session_id=session_id,
                        prompt=[text_block(DIRECTIVE)],
                    ),
                    timeout=WINDOW_S,
                )
                stop_reason = resp.stop_reason
            except asyncio.TimeoutError:
                stop_reason = None  # the hang — must never happen again

            # ------------------------------------------------------- dump
            print(f"\n=== TIMELINE ({len(client.updates)} wire events) ===")
            for t, u in client.updates:
                print(f"[{t:7.2f}s] {_describe(u)}")
            print(f"=== stop_reason: {stop_reason} ===")

            # 1. The hang is dead: the turn ENDS inside the window.
            assert stop_reason == "end_turn", (
                f"stop_reason={stop_reason!r} — the parent turn did not "
                "end cleanly; the race regression is back."
            )

            # 2. The completion REGISTERED: task-1 is terminal in state.
            task = None
            for _ in range(60):
                task = get_task(engine, "task-1")
                if task is not None and task.status != "running":
                    break
                await asyncio.sleep(2)
            assert task is not None, "task-1 never registered in state"
            assert task.status == "completed", task.status

            # 3. The delivery was DELIVERED into the parent's history —
            # in-loop consults only (no watcher anymore); poll briefly as
            # a safety net against slow persistence.
            for _ in range(30):
                if "task-1" in _parent_history_text(engine, session_id):
                    break
                await asyncio.sleep(2)
            history = _parent_history_text(engine, session_id)
            assert "task-1" in history, (
                "the completion landed in state but was never injected "
                "into the parent session"
            )
        finally:
            await conn.close()
            await transport.close()
    finally:
        server.cancel()

    # The history assertion above is the delivery proof; this just reports
    # how many times the delivery surfaced on the wire (must be exactly
    # once — the atomic claim).
    injected = [
        u
        for _, u in client.updates
        if getattr(u, "session_update", None) == "user_message_chunk"
        and "task-1" in (getattr(getattr(u, "content", None), "text", "") or "")
    ]
    print(f"=== delivery injections seen on the wire: {len(injected)} ===")
