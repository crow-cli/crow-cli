"""E2E (diagnostic): a HIGH-priority completion must PREEMPT the active turn.

Preemption contract under test: when a HIGH-priority delivery lands while the
parent is still mid-turn (batch after batch of tool calls), the react loop's
between-batch consult (``consult_deliveries(high_only=True)``) claims it and
injects it at the NEXT batch boundary — i.e. the delivery's
``user_message_chunk`` reaches the client BEFORE ``conn.prompt()`` returns.

Since the delegation-hold change there is no out-of-loop watcher at all: a
turn cannot end while a task is running or the mailbox is non-empty, so a
delivery arriving AFTER prompt() returns is structurally impossible (absent a
cancel). This test therefore asserts the delivery lands DURING the active
turn; if it doesn't, the in-loop consult chain is broken.

Observable (RecordingClient timestamps every wire event):
  n_at_turn_end = len(client.updates) captured the instant prompt() returns.
  - delivery user_message_chunk in updates[:n_at_turn_end]  -> PREEMPTED
  - only appears after                                      -> IMPOSSIBLE, fail

Same isolation as test_task_race_regression.py: parent agent, crow-mcp
subprocess and child agent subprocess all couple through ONE tmp sqlite file;
the db uri + child config ride the WIRE env (stdio spawns inherit nothing).
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
WINDOW_S = 300.0
# Priority is forced HIGH and the parent is told to stay busy with several
# slow tool batches, so the fast child finishes MID-TURN — that is the only
# window in which preemption can happen.
DIRECTIVE = (
    "do two things. first use the task tool to launch ONE background "
    "subagent with priority set to \"high\" that runs the shell command "
    "`date` via terminal (this is a test). then, while that is running, "
    "keep yourself busy: do at least three separate web searches about "
    "crow-cli, one at a time, fetching a page between searches. do not "
    "finish until you have done several of them."
)


def _mcp_servers(uri: str, config_file: str) -> list[dict]:
    return [
        {
            "name": "crow-mcp",
            "command": "uv",
            "args": ["--project", WORKTREE, "run", "crow-cli", "mcp"],
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


def _is_delivery_chunk(u: Any) -> bool:
    """The injected delivery surfaces as a user_message_chunk naming the task."""
    if getattr(u, "session_update", None) != "user_message_chunk":
        return False
    text = getattr(getattr(u, "content", None), "text", "") or ""
    return "task-1" in text


def _describe(update: Any) -> str:
    kind = getattr(update, "session_update", None)
    bits = [f"{kind}"]
    status = getattr(update, "status", None)
    if status:
        bits.append(f"status={getattr(status, 'value', status)}")
    content = getattr(update, "content", None)
    if content is not None:
        text = getattr(content, "text", None)
        if text:
            bits.append(f"text={text[:50]!r}")
    chunk = getattr(update, "chunk", None)
    if chunk is not None:
        text = getattr(chunk, "text", None)
        if text:
            bits.append(f"chunk={text[:40]!r}")
    return " ".join(bits)


@pytest.mark.asyncio
async def test_high_priority_delivery_preempts_active_turn(tmp_path):
    if not _provider_available():
        pytest.skip(f"{MODEL} / its provider is not configured")

    db = tmp_path / "preempt.db"
    uri = f"sqlite:///{db}"
    create_database(uri)

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
    # --debug equivalent: dump the EXACT request payload + raw response
    # chunks for every turn into config_dir/logs/<session_id>/ so we can
    # verify whether the injected delivery message is actually sent to the
    # LLM, and where it sits in the payload.
    config.chunk_log = True

    port = _free_port()
    server = asyncio.create_task(serve_http(config, MODEL, "127.0.0.1", port))
    client = RecordingClient()
    engine = get_engine(uri)
    stop_reason = None
    session_id = None
    n_at_turn_end = -1
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
                stop_reason = None
            # Capture the wire-event count the INSTANT the turn returns —
            # everything before this index arrived DURING the active turn.
            n_at_turn_end = len(client.updates)

            print(f"\n=== TIMELINE ({len(client.updates)} wire events) ===")
            for i, (t, u) in enumerate(client.updates):
                mark = " <== TURN ENDED" if i == n_at_turn_end else ""
                print(f"[{t:7.2f}s] #{i:3d} {_describe(u)}{mark}")
            print(f"=== stop_reason: {stop_reason} ===")
            print(f"=== events during turn: {n_at_turn_end} ===")
            chunk_dir = config.config_dir / "logs" / session_id
            print(f"=== chunk logs: {chunk_dir} ===")

            assert stop_reason == "end_turn", (
                f"stop_reason={stop_reason!r} — parent turn did not end cleanly"
            )

            # The task actually ran and was launched HIGH.
            task = None
            for _ in range(60):
                task = get_task(engine, "task-1")
                if task is not None and task.status != "running":
                    break
                await asyncio.sleep(2)
            assert task is not None, "task-1 never registered in state"
            assert task.priority == "high", (
                f"task-1 priority={task.priority!r} — the directive did not "
                "produce a HIGH-priority launch; cannot test preemption"
            )

            # THE preemption assertion: the delivery's user_message_chunk must
            # be among the events that arrived BEFORE prompt() returned —
            # injected at a batch boundary mid-turn. Post-turn delivery is
            # structurally impossible now (no watcher; the turn holds open
            # while a task runs), so anything after this is a hard failure.
            in_turn = [_is_delivery_chunk(u) for _, u in client.updates[:n_at_turn_end]]
            delivery_during_turn = any(in_turn)

            # Give any straggler wire events a moment, then report where the
            # delivery landed.
            await asyncio.sleep(4)
            delivery_anywhere = any(_is_delivery_chunk(u) for _, u in client.updates)

            print(
                f"=== delivery during active turn: {delivery_during_turn} | "
                f"delivered at all: {delivery_anywhere} ==="
            )

            assert delivery_during_turn, (
                "the HIGH-priority delivery was NOT injected during the active "
                f"turn (events[:{n_at_turn_end}] carry no task-1 "
                f"user_message_chunk; delivered_at_all={delivery_anywhere}). "
                "The in-loop consult chain (between-batch / end-of-turn) is "
                "not preempting."
            )
        finally:
            await conn.close()
            await transport.close()
    finally:
        server.cancel()
