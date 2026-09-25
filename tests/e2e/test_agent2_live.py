"""E2E: CrowAgentV2 as a real subprocess, a real provider, a real wire.

The gate (``tests/integration/test_agent2_gate.py``) proves the v2 wire
contract with a scripted model over an in-memory transport. This proves the
same contract survives the three things a gate cannot stand in for:

* a real stdio subprocess — ``python -m crow_cli.agent2.main`` under
  ``run_agent``, with the JSON-RPC framing, the 50MB buffer limit and the
  graceful-shutdown dance that goes with it;
* a real provider stream — reasoning deltas, split tool-call arguments and a
  usage chunk that arrives where the provider puts it, not where a script does;
* the real config — providers, keys and model routing resolved from
  ``~/.agents/crow/config.yaml``, with only ``db_uri`` pointed at a throwaway.

The first two tests send no MCP servers, so those sessions run toolless — the
point there is the lifecycle. The third hands the session a real crow-mcp2
(``python -m crow_cli.mcp2.main``: this tree, this interpreter) and asks a live
model to run a cell, which is the only place the execute-as-terminal contract
meets a real kernel, a real provider's tool-call arguments and a real MCP
progress stream all at once.

Nondeterministic by nature, so the assertions are about SHAPE — order, ids,
stop reasons — not about what the model said.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import yaml

from acp.connection import StreamDirection
from acp.experimental import v2
from acp.stdio import spawn_stdio_transport

from crow_cli.config import Config

#: The always-on cloud model. The e2e tier is mandatory, so it must not depend
#: on whichever model the local config happens to list first (often a llamacpp
#: box that is down). Skip rather than fall back: a live test against the wrong
#: model is a live test that tells you nothing.
PREFERRED_MODEL = "qwen3.8-max"

#: A live turn's budget. Generous, because a cold provider is slow and a
#: timeout here reads as a protocol failure rather than what it is.
LIVE_TIMEOUT = 180.0


def live_model_or_skip() -> str:
    config = Config.load()
    if not config.is_configured:
        pytest.skip("No LLM provider configured")
    if PREFERRED_MODEL not in config.llm.models:
        pytest.skip(f"{PREFERRED_MODEL} not in config.yaml models")
    return PREFERRED_MODEL


class UpdateClient:
    """The client half. Assertions read the wire tap, not this queue."""

    def __init__(self) -> None:
        self.updates: asyncio.Queue = asyncio.Queue()

    async def session_update(self, session_id, update, **kwargs) -> None:
        await self.updates.put((session_id, update))


@asynccontextmanager
async def live_agent(tmp_path: Path, model: str):
    """Spawn agent2 as a subprocess and yield ``(conn, wire, stderr)``.

    ``wire`` is the observer tap: the JSON-RPC dicts that actually crossed the
    pipe, in order, both directions. ``stderr`` is drained into a list rather
    than left on the pipe — an undrained 64KB buffer deadlocks the child, and
    when a live test fails the child's traceback is the only evidence there is.
    """
    override = tmp_path / "override.yaml"
    override.write_text(yaml.safe_dump({"db_uri": f"sqlite:///{tmp_path / 'live.db'}"}))

    stderr: list[str] = []
    wire: list = []
    async with spawn_stdio_transport(
        sys.executable,
        "-m",
        "crow_cli.agent2.main",
        "--model",
        model,
        "--config-file",
        str(override),
        cwd=str(tmp_path),
    ) as (reader, writer, process):

        async def drain() -> None:
            assert process.stderr is not None
            while True:
                line = await process.stderr.readline()
                if not line:
                    return
                stderr.append(line.decode(errors="replace"))

        drainer = asyncio.create_task(drain())
        conn = v2.ClientSideConnection(
            UpdateClient(), writer, reader, observers=[wire.append]
        )
        try:
            yield conn, wire, stderr
        finally:
            await conn.close()
            drainer.cancel()
            if process.returncode is None:
                process.kill()


def updates(wire: list) -> list[dict]:
    """Every session/update the client received, in wire order."""
    return [
        event.message["params"]
        for event in wire
        if event.direction is StreamDirection.INCOMING
        and event.message.get("method") == "session/update"
    ]


def kinds(wire: list) -> list[str]:
    return [u["update"]["sessionUpdate"] for u in updates(wire)]


def of_kind(wire: list, kind: str) -> list[dict]:
    return [u["update"] for u in updates(wire) if u["update"]["sessionUpdate"] == kind]


def idles(wire: list) -> list[dict]:
    return [
        u for u in of_kind(wire, "state_update") if u.get("state") == "idle"
    ]


def crow_mcp2() -> v2.schema.StdioMcpServer:
    """This tree's crow-mcp2, on this interpreter.

    ``-m`` rather than the console script: ``sys.executable`` here is the
    project venv's python, so the server is THIS tree's code with no PATH
    lookup and no dependence on an installed entry point.
    """
    return v2.schema.StdioMcpServer(
        name="crow-mcp2",
        command=sys.executable,
        args=["-m", "crow_cli.mcp2.main"],
        env=[],
    )


def terminal_timeline(wire: list, acp_id: str, terminal_id: str) -> list[str]:
    """One execute call's sequence, projected to labels in wire order.

    Only the events belonging to THIS call and THIS terminal: the model streams
    text around them, and a second call would have its own terminal. Each
    ``terminal_update`` carries exactly one of command / output / exitStatus —
    the emitter passes the rest as None and the wire drops them — so the label
    says which of the three it was.
    """
    timeline: list[str] = []
    for update in updates(wire):
        d = update["update"]
        kind = d["sessionUpdate"]
        if kind == "tool_call_update" and d.get("toolCallId") == acp_id:
            timeline.append(f"call:{d.get('status')}")
        elif kind == "terminal_output_chunk" and d.get("terminalId") == terminal_id:
            timeline.append("chunk")
        elif kind == "terminal_update" and d.get("terminalId") == terminal_id:
            for field, label in (
                ("command", "command"),
                ("output", "output"),
                ("exitStatus", "exit"),
            ):
                if field in d:
                    timeline.append(f"terminal:{label}")
                    break
    return timeline


async def wait_for(predicate, wire: list, stderr: list, timeout: float = LIVE_TIMEOUT):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(
                f"not satisfied within {timeout}s.\n"
                f"wire: {json.dumps([u['update'] for u in updates(wire)], indent=1, default=str)}\n"
                f"agent stderr:\n{''.join(stderr)}"
            )
        await asyncio.sleep(0.05)


async def wait_for_idle(wire, stderr, count: int = 1, timeout: float = LIVE_TIMEOUT):
    await wait_for(lambda: len(idles(wire)) >= count, wire, stderr, timeout)
    await asyncio.sleep(0.2)


async def test_a_live_turn_over_real_stdio(tmp_path):
    """initialize -> new -> prompt -> ack -> user_message -> running -> idle.

    The whole v2 inversion, against a provider that has never seen our script.
    The acknowledgement is not empty: it carries the ``messageId`` the prompt
    landed under, and the ``user_message`` that follows carries the same one.
    """
    model = live_model_or_skip()
    async with live_agent(tmp_path, model) as (conn, wire, stderr):
        init = await conn.initialize(
            protocol_version=v2.PROTOCOL_VERSION,
            info=v2.schema.Implementation(name="live-e2e", version="2.0.0"),
        )
        assert init.protocol_version == v2.PROTOCOL_VERSION
        assert init.info.name == "crow-cli"
        # auth_methods omitted on purpose: advertising any commits us to
        # auth/login AND auth/logout, and crow configures providers in yaml.
        assert not init.auth_methods

        new = await conn.new_session(
            cwd=str(tmp_path), mcp_servers=[]
        )
        assert new.session_id
        # The model picker, offering every configured model with the agent's
        # -m choice already current.
        options = {o.config_id: o for o in (new.config_options or [])}
        assert "model" in options
        picker = options["model"]
        assert picker.current_value in {o.value for o in picker.options}
        assert model in {o.name for o in picker.options}

        await wait_for_idle(wire, stderr, 1)

        marked = len(wire)
        response = await conn.prompt(
            session_id=new.session_id,
            prompt=[
                v2.schema.TextContentBlock(
                    text="Reply with exactly one short sentence. Do not use tools."
                )
            ],
        )
        await wait_for_idle(wire, stderr, 2)

        # The acknowledgement went out before any update about the turn.
        tail = wire[marked:]
        result_at = next(
            i
            for i, e in enumerate(tail)
            if e.direction is StreamDirection.INCOMING and "result" in e.message
        )
        update_at = next(
            i for i, e in enumerate(tail) if e.message.get("method") == "session/update"
        )
        assert tail[result_at].message["result"] == {"messageId": response.message_id}
        assert result_at < update_at, (result_at, update_at)

        sequence = kinds(wire)
        # available_commands, the fresh session's bare idle, then the turn.
        assert sequence[0] == "available_commands_update"
        assert sequence[1] == "state_update"
        assert sequence[2] == "user_message"
        assert sequence[3] == "state_update"
        assert of_kind(wire, "state_update")[1]["state"] == "running"
        assert "agent_message_chunk" in sequence
        assert sequence[-1] == "state_update"

        # A fresh session's idle reports readiness, not a stop reason.
        assert "stopReason" not in idles(wire)[0]

        chunks = of_kind(wire, "agent_message_chunk")
        reply = "".join(c["content"]["text"] for c in chunks)
        assert reply.strip(), f"model streamed no text; stderr:\n{''.join(stderr)}"
        # One reply, one messageId — a client keys its document by it.
        assert len({c["messageId"] for c in chunks}) == 1
        echoed = of_kind(wire, "user_message")[0]["messageId"]
        assert chunks[0]["messageId"] != echoed
        # The acknowledgement named the message the agent then echoed. Two
        # mints would each be unique and neither would be findable.
        assert echoed == response.message_id

        final = idles(wire)[1]
        assert final["stopReason"] == "end_turn"
        # Real providers report usage; if this one did, it must arrive
        # converted. A raw prompt/completion dict validates to None silently.
        if "usage" in final:
            assert set(final["usage"]) <= {
                "totalTokens",
                "inputTokens",
                "outputTokens",
                "thoughtTokens",
                "cachedReadTokens",
                "cachedWriteTokens",
            }
            assert final["usage"]["totalTokens"] > 0

        # The user's echo went back exactly as it arrived.
        assert of_kind(wire, "user_message")[0]["content"] == [
            {
                "text": "Reply with exactly one short sentence. Do not use tools.",
                "type": "text",
            }
        ]


async def test_a_live_cancel_is_confirmed_by_an_idle(tmp_path):
    """Cancel a real stream mid-flight; the idle is the only confirmation.

    v1 answered ``session/prompt`` with ``stopReason: "cancelled"``. That
    response is now a ``messageId`` and long gone, so a client that does not
    get an idle has no way to know the cancel landed — and a provider stream is where
    that is most likely to go wrong, because the socket is doing something at
    the moment the task dies.
    """
    model = live_model_or_skip()
    async with live_agent(tmp_path, model) as (conn, wire, stderr):
        await conn.initialize(
            protocol_version=v2.PROTOCOL_VERSION,
            info=v2.schema.Implementation(name="live-e2e", version="2.0.0"),
        )
        new = await conn.new_session(
            cwd=str(tmp_path), mcp_servers=[]
        )
        await wait_for_idle(wire, stderr, 1)

        await conn.prompt(
            session_id=new.session_id,
            prompt=[
                v2.schema.TextContentBlock(
                    text="Count from 1 to 500, one number per line. No tools."
                )
            ],
        )
        await wait_for(lambda: len(of_kind(wire, "agent_message_chunk")) >= 2, wire, stderr)

        await conn.cancel_session(
            session_id=new.session_id
        )
        await wait_for_idle(wire, stderr, 2)

        assert idles(wire)[1]["stopReason"] == "cancelled"
        # Whatever arrived before the cancel is still on the wire — the spec
        # says finish sending pending updates, then report idle.
        assert of_kind(wire, "agent_message_chunk")

        # And the session is still alive: cancel is per-turn in v2, so a
        # second prompt on the same session must still work.
        await conn.prompt(
            session_id=new.session_id,
            prompt=[v2.schema.TextContentBlock(text="Reply with exactly: PONG")],
        )
        await wait_for_idle(wire, stderr, 3)
        assert idles(wire)[2]["stopReason"] == "end_turn"
        after = "".join(
            c["content"]["text"] for c in of_kind(wire, "agent_message_chunk")
        )
        assert "PONG" in after.upper(), f"no reply after cancel; stderr:\n{''.join(stderr)}"


async def test_a_live_execute_call_becomes_a_terminal_on_the_wire(tmp_path):
    """``execute`` as an ACP v2 terminal, with a real kernel and a real model.

    The gate proves this sequence against a scripted model. What only a live
    run can prove is the other end of it: that a provider's tool-call
    arguments — JSON written by someone else, split across stream deltas —
    arrive as a cell the kernel accepts, and that the bytes come back through
    MCP progress notifications while the cell is still running rather than
    only in the snapshot at the end.

    The sequence under test is the one ``agent2/tools.py::_run_execute``
    documents: create the call, open the terminal, stream the bytes, snapshot
    them, complete the call pointing AT the terminal, then close the terminal
    with an exit status independent of the call's own status.
    """
    model = live_model_or_skip()
    async with live_agent(tmp_path, model) as (conn, wire, stderr):
        await conn.initialize(
            protocol_version=v2.PROTOCOL_VERSION,
            info=v2.schema.Implementation(name="live-e2e", version="2.0.0"),
        )
        new = await conn.new_session(
            cwd=str(tmp_path), mcp_servers=[crow_mcp2()]
        )
        await wait_for_idle(wire, stderr, 1)

        await conn.prompt(
            session_id=new.session_id,
            prompt=[
                v2.schema.TextContentBlock(
                    text=(
                        "Use the execute tool to run exactly this Python "
                        "cell, unchanged:\n"
                        "    print('CROW-E2E-MARKER')\n"
                        "Then reply with the exact text it printed and "
                        "nothing else."
                    )
                )
            ],
        )
        await wait_for_idle(wire, stderr, 2)
        assert idles(wire)[1]["stopReason"] == "end_turn"

        created = [
            c for c in of_kind(wire, "tool_call_update") if c.get("kind") == "execute"
        ]
        assert created, (
            f"the model never called execute.\nkinds: {kinds(wire)}\n"
            f"stderr:\n{''.join(stderr)}"
        )
        acp_id = created[0]["toolCallId"]
        calls = [
            c for c in of_kind(wire, "tool_call_update") if c["toolCallId"] == acp_id
        ]
        # The cell the provider assembled out of stream deltas, intact.
        assert "CROW-E2E-MARKER" in created[0]["rawInput"]["code"]

        all_terminals = of_kind(wire, "terminal_update")
        assert all_terminals, f"no terminal on the wire: {kinds(wire)}"
        terminal_id = all_terminals[0]["terminalId"]
        terms = [t for t in all_terminals if t["terminalId"] == terminal_id]

        timeline = terminal_timeline(wire, acp_id, terminal_id)
        assert timeline[:2] == ["call:in_progress", "terminal:command"], timeline
        assert timeline[-3:] == [
            "terminal:output",
            "call:completed",
            "terminal:exit",
        ], timeline
        # The live bytes, between opening the terminal and snapshotting it.
        # There would be none if the client had sent no progressToken, and
        # _run_execute always sends a progress_handler.
        middle = timeline[2:-3]
        assert middle and set(middle) == {"chunk"}, timeline

        opened = next(t for t in terms if "command" in t)
        assert opened["cwd"] == str(tmp_path)
        assert opened["command"] == created[0]["rawInput"]["code"]

        streamed = b"".join(
            base64.b64decode(c["data"])
            for c in of_kind(wire, "terminal_output_chunk")
            if c["terminalId"] == terminal_id
        )
        assert b"CROW-E2E-MARKER" in streamed

        # The snapshot is the same bytes, sent whole, for a client that was
        # not watching them arrive.
        snapshot = next(t for t in terms if "output" in t)
        assert base64.b64decode(snapshot["output"]["data"]) == streamed

        done = next(c for c in calls if c.get("status") == "completed")
        # The completed call POINTS at the terminal instead of carrying text:
        # the bytes already live there, and a client renders one or the other.
        assert done["content"] == [{"terminalId": terminal_id, "type": "terminal"}]
        assert done["rawOutput"]["exit_code"] == 0
        assert "CROW-E2E-MARKER" in done["rawOutput"]["output"]
        # ANSI-stripped text is the model's half of the split.
        assert "\x1b" not in done["rawOutput"]["output"]

        closed = next(t for t in terms if "exitStatus" in t)
        assert closed["exitStatus"] == {"exitCode": 0}

        # And the stripped text is what the model actually read: it answers
        # with the cell's output, which it can only have got from rawOutput.
        reply = "".join(
            c["content"]["text"] for c in of_kind(wire, "agent_message_chunk")
        )
        assert "CROW-E2E-MARKER" in reply, (
            f"the model did not report the cell's output.\n"
            f"reply: {reply!r}\nstderr:\n{''.join(stderr)}"
        )
