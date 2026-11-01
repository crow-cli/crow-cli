"""A dead MCP server: recognised, rebuilt, and the call retried once.

The failure this pins is the one that ended a session for good. crow-mcp2
aborted, the client's read stream hit EOF, its JSON-RPC dispatcher latched
``_closed`` — and every later call answered ``Connection closed`` forever,
``execute(reset=True)`` included, because the reset travels over the same dead
client. The model cannot fix that and had no way to learn it; it just kept
retrying. So the recovery is the agent's, not the model's: recognise the error
as infrastructure rather than as a tool result, rebuild the client, retry.

Real sqlite, real emitter, real v2 wire JSON, and the REAL installed mcp
exception — the code is the contract but its carrier moved between mcp 1.x
(``McpError.error.code``) and 2.x (``MCPError.code``), so a test that fakes the
shape proves nothing about the version actually installed. The only stand-ins
are the connection (records instead of sends) and the client (raises on cue).
"""

import json
import logging

import pytest
from acp.experimental.v2 import schema as vs
from mcp.types import CallToolResult, TextContent

from crow_cli.agent2.ctx import TurnCtx
from crow_cli.agent2.emitter import Emitter
from crow_cli.agent2.tools import (
    CONNECTION_CLOSED,
    KERNEL_LOST_NOTICE,
    _with_kernel_lost_notice,
    connection_gone,
    execute_tool_calls,
)
from crow_cli.config import Config
from crow_cli.memory.db import get_engine
from crow_cli.memory.models import Base

SESSION_ID = "recovery-session"
AGENT_ID = f"{SESSION_ID}-1-1"


# ---------------------------------------------------------------------------
# The real exception, whichever mcp is installed
# ---------------------------------------------------------------------------


def real_connection_closed() -> BaseException:
    """The installed mcp's own "the peer went away" exception.

    Built rather than imported by name: 1.x calls it ``McpError`` and takes an
    ``ErrorData``; 2.x calls it ``MCPError`` and takes ``(code, message)``.
    Both end up with the wire code reachable, which is all
    :func:`connection_gone` is allowed to rely on.
    """
    from mcp.shared import exceptions as exc
    from mcp.types import ErrorData

    cls = getattr(exc, "MCPError", None) or getattr(exc, "McpError", None)
    assert cls is not None, "no McpError/MCPError in the installed mcp"
    try:
        return cls(ErrorData(code=CONNECTION_CLOSED, message="Connection closed"))
    except TypeError:
        return cls(CONNECTION_CLOSED, "Connection closed")


class _Coded(Exception):
    """An exception carrying a JSON-RPC code the way 2.x does."""

    def __init__(self, code, message="boom"):
        super().__init__(message)
        self.code = code


class _Nested(Exception):
    """An exception carrying ``.error.code`` the way 1.x does."""

    def __init__(self, code, message="boom"):
        super().__init__(message)
        self.error = type("ErrorData", (), {"code": code})()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class RecordingConn:
    """Stands in for AgentSideConnection; keeps the wire JSON."""

    def __init__(self):
        self.wire: list[dict] = []

    async def session_update(self, session_id, update, **kwargs):
        self.wire.append(
            vs.UpdateSessionNotification(session_id=session_id, update=update)
            .model_dump(mode="json", by_alias=True, exclude_unset=True)
        )

    @property
    def updates(self) -> list[dict]:
        return [w["update"] for w in self.wire]


class _Session:
    def __init__(self, agent_id, cwd):
        self.agent_id = agent_id
        self.cwd = cwd
        self.rlm_depth = 0


def result(text: str) -> CallToolResult:
    """A successful execute/tool result carrying ``text``."""
    return CallToolResult(
        content=[TextContent(type="text", text=text)], isError=False
    )


def execute_result(output: str) -> CallToolResult:
    """What crow-mcp2's ``execute`` actually returns: JSON in a text block."""
    return result(json.dumps(
        {"exit_code": 0, "output": output, "timed_out": False, "raw_bytes_b64": ""}
    ))


class FakeClient:
    """An MCPClient whose ``call_tool_mcp`` follows a script.

    Each entry is raised if it is an exception, returned otherwise. Once the
    script is exhausted the client is healthy again, so a test that expects a
    retry does not have to spell out the retry's answer twice.
    """

    def __init__(self, script=(), healthy="ok"):
        self.script = list(script)
        self.healthy = healthy
        self.calls: list[tuple] = []

    async def call_tool_mcp(self, name, args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        return result(self.healthy)


class RecordingReconnect:
    """A ``Reconnect`` that swaps the registry entry and keeps the args.

    Assigns into the SAME dict the dispatcher reads, because that is what
    :meth:`~crow_cli.agent2.sessions.SessionRegistry.reconnect_mcp` does and
    what makes the retry land on the new client: ``_dispatch`` resolves the
    client per attempt through ``_client_for``, so a reconnect that only
    RETURNS a client would leave the retry talking to the dead one.
    """

    def __init__(self, registry, clients):
        self.registry = registry
        self.clients = list(clients)
        self.calls: list[str] = []

    async def __call__(self, session_id):
        self.calls.append(session_id)
        client = self.clients.pop(0) if self.clients else None
        if client is not None:
            self.registry[session_id] = client
        return client


# ---------------------------------------------------------------------------
# The fixture: a real TurnCtx over a real db
# ---------------------------------------------------------------------------


@pytest.fixture
async def ctx_factory(tmp_path):
    config = Config(config_dir=tmp_path)
    config.db_uri = f"sqlite:///{tmp_path / 'crow.db'}"
    engine = get_engine(config.db_uri)
    Base.metadata.create_all(engine)
    engine.dispose()

    def build(client) -> tuple:
        conn = RecordingConn()
        ctx = TurnCtx(
            emitter=Emitter(conn, SESSION_ID),
            config=config,
            session=_Session(AGENT_ID, str(tmp_path)),
            turn_id="turn-0001",
            logger=logging.getLogger(__name__),
        )
        # The registry is keyed on the WIRE session id, which is what
        # _client_for looks up — the same derivation reconnect_mcp replaces.
        clients = {ctx.session_id: client}
        return ctx, conn, clients

    return build


def tool_call(name: str, args: dict, llm_id: str = "call_1") -> list[dict]:
    return [{
        "id": llm_id,
        "function": {"name": name, "arguments": json.dumps(args)},
    }]


# ---------------------------------------------------------------------------
# connection_gone
# ---------------------------------------------------------------------------


def test_the_installed_mcps_own_closed_error_is_recognised():
    """The version actually installed, not a hand-rolled lookalike."""
    exc = real_connection_closed()
    assert type(exc).__name__ in {"McpError", "MCPError"}
    assert connection_gone(exc)


def test_a_bare_wire_code_is_enough():
    assert connection_gone(_Coded(CONNECTION_CLOSED))


def test_a_nested_error_code_is_enough():
    assert connection_gone(_Nested(CONNECTION_CLOSED))


def test_the_message_is_the_fallback_for_a_rewrapping_transport():
    assert connection_gone(RuntimeError("Connection closed"))
    assert connection_gone(RuntimeError("...CONNECTION CLOSED by peer..."))


def test_a_tool_that_failed_is_not_a_dead_server():
    """The distinction the whole recovery rests on.

    A tool raising is the model's problem and its error text is the answer;
    treating it as infrastructure would rebuild a perfectly live client and
    hide the real message behind a retry.
    """
    assert not connection_gone(RuntimeError("permission denied"))
    assert not connection_gone(_Coded(-32603, "internal error"))
    assert not connection_gone(_Nested(-32601, "method not found"))
    assert not connection_gone(ValueError("no such mode"))


# ---------------------------------------------------------------------------
# _with_kernel_lost_notice
# ---------------------------------------------------------------------------


def test_the_notice_goes_in_front_of_plain_text():
    out = _with_kernel_lost_notice("42")
    assert out.startswith(KERNEL_LOST_NOTICE)
    assert out.endswith("42")


def test_the_notice_survives_a_block_list():
    """execute returns blocks when the cell produced images; the notice has
    to ride along rather than flatten them into a string."""
    blocks = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]
    out = _with_kernel_lost_notice(blocks)
    assert out[0] == {"type": "text", "text": KERNEL_LOST_NOTICE}
    assert out[1:] == blocks


# ---------------------------------------------------------------------------
# _dispatch: the recovery itself
# ---------------------------------------------------------------------------


async def test_a_dead_server_is_rebuilt_and_the_call_retried(ctx_factory):
    dead = FakeClient([real_connection_closed()])
    alive = FakeClient([result("retried")])
    ctx, _, clients = ctx_factory(dead)
    reconnect = RecordingReconnect(clients, [alive])

    results = await execute_tool_calls(
        ctx, clients, tool_call("fs", {"mode": "read", "path": "x.py"}),
        reconnect=reconnect,
    )

    assert results[0]["content"] == "retried"
    assert reconnect.calls == [SESSION_ID]
    # The retry ran on the NEW client and the dead one was not touched again:
    # _dispatch resolves the client per attempt, so the swap reconnect made in
    # the shared registry is what redirected it.
    assert [c[0] for c in alive.calls] == ["fs"]
    assert len(dead.calls) == 1


async def test_execute_is_told_its_kernel_went_with_the_server(ctx_factory):
    """The retry ran in a fresh interpreter; the model has to know its setup
    is gone, or it reads the NameError as a bug in its own code."""
    dead = FakeClient([real_connection_closed()])
    alive = FakeClient([execute_result("hi from the new kernel")])
    ctx, _, clients = ctx_factory(dead)

    results = await execute_tool_calls(
        ctx, clients, tool_call("execute", {"code": "print('hi')"}),
        reconnect=RecordingReconnect(clients, [alive]),
    )

    content = results[0]["content"]
    assert content.startswith(KERNEL_LOST_NOTICE)
    assert "hi from the new kernel" in content


async def test_another_tool_is_not_told_about_a_kernel_it_does_not_have(ctx_factory):
    """A non-execute server may be a different process that never died;
    warning about lost REPL state would send the model re-running setup for
    nothing."""
    dead = FakeClient([real_connection_closed()])
    alive = FakeClient([result("plain")])
    ctx, _, clients = ctx_factory(dead)

    results = await execute_tool_calls(
        ctx, clients, tool_call("web", {"mode": "fetch", "url": "https://x"}),
        reconnect=RecordingReconnect(clients, [alive]),
    )

    assert results[0]["content"] == "plain"
    assert KERNEL_LOST_NOTICE not in str(results[0]["content"])


async def test_without_a_reconnect_the_error_is_still_the_answer(ctx_factory):
    """Optional by design: a caller with no registry behind it gets the old
    behaviour rather than a crash in the recovery path."""
    dead = FakeClient([real_connection_closed()])
    ctx, conn, clients = ctx_factory(dead)

    results = await execute_tool_calls(
        ctx, clients, tool_call("fs", {"mode": "read", "path": "x.py"})
    )

    assert results[0]["content"].startswith("Error:")
    assert "Connection closed" in results[0]["content"]
    assert [u["status"] for u in conn.updates][-1] == "failed"


async def test_a_reconnect_that_fails_says_so_rather_than_looping(ctx_factory):
    """The honest answer. ``Connection closed`` on repeat is what made the
    model retry forever; naming the real state — including that its own
    reset=True lever cannot help — is what makes it stop and report."""
    dead = FakeClient([real_connection_closed()])
    ctx, _, clients = ctx_factory(dead)

    results = await execute_tool_calls(
        ctx, clients, tool_call("execute", {"code": "1"}),
        reconnect=RecordingReconnect(clients, [None]),
    )

    content = results[0]["content"]
    assert content.startswith("Error:")
    assert "could not be restarted" in content
    assert "execute(reset=True)" in content


async def test_a_tool_error_is_not_treated_as_a_dead_server(ctx_factory):
    client = FakeClient([RuntimeError("permission denied")])
    ctx, _, clients = ctx_factory(client)
    reconnect = RecordingReconnect(clients, [FakeClient()])

    results = await execute_tool_calls(
        ctx, clients, tool_call("fs", {"mode": "read", "path": "/root"}),
        reconnect=reconnect,
    )

    assert results[0]["content"] == "Error: permission denied"
    assert reconnect.calls == []          # never rebuilt
    assert len(client.calls) == 1         # never retried


async def test_the_retry_happens_once_not_until_the_turn_is_gone(ctx_factory):
    """A server that dies twice in a row is not having a bad moment."""
    dead = FakeClient([real_connection_closed()])
    also_dead = FakeClient([real_connection_closed()])
    ctx, _, clients = ctx_factory(dead)
    reconnect = RecordingReconnect(clients, [also_dead, FakeClient()])

    results = await execute_tool_calls(
        ctx, clients, tool_call("fs", {"mode": "read", "path": "x.py"}),
        reconnect=reconnect,
    )

    assert results[0]["content"].startswith("Error:")
    assert reconnect.calls == [SESSION_ID]
    assert len(also_dead.calls) == 1


async def test_the_retry_reuses_the_same_tool_call_id(ctx_factory):
    """``tool_call_update`` is an upsert keyed on toolCallId, so a client that
    watched the first attempt fail sees the SAME call progress — not a
    duplicate, and not an orphan left stuck in ``in_progress``."""
    dead = FakeClient([real_connection_closed()])
    alive = FakeClient([result("retried")])
    ctx, conn, clients = ctx_factory(dead)

    await execute_tool_calls(
        ctx, clients, tool_call("fs", {"mode": "read", "path": "x.py"}),
        reconnect=RecordingReconnect(clients, [alive]),
    )

    ids = {u["toolCallId"] for u in conn.updates}
    assert ids == {"turn-0001/call_1"}
    assert [u["status"] for u in conn.updates][-1] == "completed"
