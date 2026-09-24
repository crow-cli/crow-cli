"""The phase-1 gate: CrowAgentV2 speaking real ACP v2 over a real transport.

Everything here is real — the agent, the JSON-RPC connection, the sqlite
session, the emitter, the react loop, the persistence, and (for the tool
round trip) a real FastMCP server spawned over stdio exactly the way a
client's ``mcpServers`` entry spawns one. There is one stand-in, at the one
boundary a gate cannot cross for free: the model. A gate that needs a
provider is not a gate; the live-model path lives in ``tests/e2e``.

Assertions are made on the wire tap — ``observers=[wire.append]`` gives the
JSON-RPC dicts that actually crossed the transport — not on Python objects
the agent happened to build. That is the whole point of gating here: v2's
schema silently coerces what it does not understand (an ``IdleStateUpdate``
carries a ``use_default_on_error`` validator over ``stop_reason`` and
``usage``, so a raw provider usage dict becomes ``None`` with no exception
and no log). "The object looked right" is not evidence. Only bytes are.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
import redis
import yaml

from acp._transport import memory_transport_pair
from acp.connection import StreamDirection
from acp.exceptions import RequestError
from acp.experimental import v2

from crow_cli.agent.compact import CompactResponse
from crow_cli.agent.session import AgentSession
from crow_cli.agent2.agent import CrowAgentV2
from crow_cli.agent2.driver import PARK_BACKSTOP_S
from crow_cli.config import Config
from crow_cli.memory import Agent, Session, running_tasks, wire_session_id
from crow_cli.memory.writes import finish_task, launch_task
from crow_cli.wake import Poke, publish_wake

#: Yielded by a script to mean "block here until cancelled".
HANG = object()

#: A real MCP server, spawned as a subprocess. Not an in-process fake: the
#: point is to exercise mcp_servers_to_wire -> mcp_client_for ->
#: MCPConfigTransport -> get_tools -> call_tool_mcp, which is the path a
#: client's mcpServers entry takes.
MCP_SERVER = '''from fastmcp import FastMCP

mcp = FastMCP("gate-tools")


@mcp.tool
def echo(text: str) -> str:
    """Echo text back, prefixed."""
    return f"echo: {text}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
'''

#: The same server on a real TCP port, because ``initialize`` advertises
#: ``session.mcp.http`` as well as ``stdio`` and an advertisement nobody acts
#: on is the shape of hole this file exists to close.
MCP_HTTP_SERVER = '''import sys

from fastmcp import FastMCP

mcp = FastMCP("gate-tools-http")


@mcp.tool
def echo(text: str) -> str:
    """Echo text back, prefixed."""
    return f"echo: {text}"


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=int(sys.argv[1]),
        show_banner=False,
    )
'''


# ---------------------------------------------------------------------------
# The scripted model
# ---------------------------------------------------------------------------


@dataclass
class Delta:
    reasoning_content: str | None = None
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class Choice:
    delta: Delta
    finish_reason: str | None = None


@dataclass
class Chunk:
    choices: list
    usage: object | None = None


def text(*pieces: str) -> list[Chunk]:
    return [Chunk(choices=[Choice(delta=Delta(content=p))]) for p in pieces]


def thought(*pieces: str) -> list[Chunk]:
    return [Chunk(choices=[Choice(delta=Delta(reasoning_content=p))]) for p in pieces]


def call(index: int, call_id: str, name: str, arguments: str) -> list[Chunk]:
    """One tool call, split the way providers split it.

    The head carries the id and the name, the tail the arguments — index-keyed
    accumulation is the only thing that ties them together, so a gate that
    sent them as one chunk would not be testing the accumulator.
    """
    head = SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=""),
    )
    tail = SimpleNamespace(
        index=index,
        id=None,
        function=SimpleNamespace(name=None, arguments=arguments),
    )
    return [
        Chunk(choices=[Choice(delta=Delta(tool_calls=[head]))]),
        Chunk(choices=[Choice(delta=Delta(tool_calls=[tail]))]),
    ]


def usage(total: int) -> Chunk:
    return Chunk(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=total // 2,
            completion_tokens=total - total // 2,
            total_tokens=total,
        ),
    )


class ScriptedLLM:
    """One scripted stream per call; an unscripted call fails loudly.

    Reproduces exactly what ``llm.stream`` asks of an ``AsyncOpenAI``:
    ``chat.completions.create(**kwargs)`` returning an async iterable of
    chunks with ``.choices[].delta`` and a final ``.usage``. Every call's
    kwargs are recorded, so a test can assert on what the model was sent and
    not only on what came back.
    """

    def __init__(self, scripts: list[list]) -> None:
        self.scripts = list(scripts)
        self.scripted = len(scripts)
        self.calls: list[dict] = []
        outer = self

        class Completions:
            async def create(self, **kwargs):
                outer.calls.append(kwargs)
                if not outer.scripts:
                    raise AssertionError(
                        f"model called {len(outer.calls)} time(s) but only "
                        f"{outer.scripted} were scripted"
                    )
                chunks = outer.scripts.pop(0)

                async def stream():
                    for chunk in chunks:
                        if chunk is HANG:
                            await asyncio.Event().wait()
                        yield chunk

                return stream()

        self.chat = SimpleNamespace(completions=Completions())


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------


class UpdateClient:
    """The client half. Updates are asserted from the wire tap, not here."""

    def __init__(self) -> None:
        self.updates: asyncio.Queue = asyncio.Queue()

    async def session_update(self, notification) -> None:
        await self.updates.put(notification)


def make_config(tmp_path: Path) -> Config:
    """A configured crow pointed at a throwaway sqlite.

    A provider and a model have to exist for ``config.is_configured`` — the
    agent answers a prompt with the setup message instead of running a turn
    when they do not. Neither is ever contacted: ``make_llm`` is replaced.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / ".env").write_text("API_KEY=gate-key\n")
    (config_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "gate-provider": {
                        "api_key": "${API_KEY}",
                        "base_url": "https://gate.invalid/v1",
                    }
                },
                "models": {
                    # First in the dict, so it is the default: both
                    # default_model_value and default_model_identifier take
                    # next(iter(models)) and a test that asserts on the model
                    # a fresh session sends depends on that order.
                    "gate-model": {
                        "provider": "gate-provider",
                        "model": "gate-model-id",
                    },
                    # A second one, so "the client changed the model" is
                    # observable in the next request. Same provider: the gate
                    # has one, and the routing is the thing under test.
                    "gate-model-2": {
                        "provider": "gate-provider",
                        "model": "gate-model-id-2",
                    },
                },
            }
        )
    )
    config = Config.load(config_dir)
    config.db_uri = f"sqlite:///{tmp_path / 'gate.db'}"
    return config


class Gate:
    """A :class:`CrowAgentV2` and a v2 client joined by an in-memory transport."""

    def __init__(self, tmp_path, config, agent, llm, conn, agent_conn, wire) -> None:
        self.tmp_path = tmp_path
        self.config = config
        self.agent = agent
        self.llm = llm
        self.conn = conn
        self.wire = wire
        self.session_id: str | None = None
        self._agent_conn = agent_conn

    @property
    def updates(self) -> list[dict]:
        """Every ``session/update`` that reached the client, in wire order."""
        return [
            event.message["params"]
            for event in self.wire
            if event.direction is StreamDirection.INCOMING
            and event.message.get("method") == "session/update"
        ]

    def kinds(self) -> list[str]:
        return [u["update"]["sessionUpdate"] for u in self.updates]

    def of_kind(self, kind: str) -> list[dict]:
        return [u["update"] for u in self.updates if u["update"]["sessionUpdate"] == kind]

    def updates_for(self, session_id: str) -> list[dict]:
        """Only the updates that named this session.

        Every ``session/update`` carries its ``sessionId`` in the params, so a
        test with two sessions open can ask what ONE of them saw — which is the
        only way to assert that closing or forking left the other alone.
        """
        return [u for u in self.updates if u.get("sessionId") == session_id]

    def kinds_for(self, session_id: str) -> list[str]:
        return [u["update"]["sessionUpdate"] for u in self.updates_for(session_id)]

    def last_result(self) -> dict:
        """The most recent INCOMING JSON-RPC ``result``, exactly as it arrived.

        The request methods below return validated models, which is convenient
        and also lossy: ``exclude_none`` decided which keys are absent, and
        "absent" is the whole content of a claim like ``SessionInfo.title``
        being optional. This reads the bytes instead.
        """
        for event in reversed(self.wire):
            if event.direction is StreamDirection.INCOMING and "result" in event.message:
                return event.message["result"]
        raise AssertionError("no JSON-RPC result crossed the wire")

    @property
    def init_capabilities(self) -> dict:
        """The ``initialize`` response's capabilities, read off the wire.

        Not off the object the handler built: what a client can act on is what
        crossed the transport, and ``exclude_none``/``exclude_unset`` decide
        which markers are actually there. An unclaimed capability is an absent
        key, and only the dump shows that.
        """
        for event in self.wire:
            if event.direction is not StreamDirection.INCOMING:
                continue
            result = event.message.get("result")
            if isinstance(result, dict) and "capabilities" in result:
                return result["capabilities"]
        raise AssertionError("no initialize response crossed the wire")

    def states(self) -> list[dict]:
        return self.of_kind("state_update")

    def idles(self) -> list[dict]:
        return [s for s in self.states() if s.get("state") == "idle"]

    @property
    def tools_used(self) -> int:
        """How many tool calls the last turn ran, read off the driver.

        The one fact in this file that has no wire representation, because no
        client asks for it. It is still a fact about the turn and not an
        implementation detail: the goal continuation decides whether to loop
        again on exactly this number, so a gate that cannot see it cannot test
        the guard that keeps a goal from burning tokens on a model talking to
        itself.
        """
        return self.agent.sessions.drivers[self.session_id]._last_tools_used

    @property
    def agent_id(self) -> str:
        """The one agent row this gate created."""
        ids = list(self.agent.sessions.sessions)
        assert len(ids) == 1, f"expected one agent row, got {ids}"
        return ids[0]

    def agent_id_of(self, session_id: str) -> str:
        """The agent row behind a WIRE id.

        ``agent_id`` asserts there is exactly one row in the registry, and a
        fork or a second session breaks that on purpose — a fork is a second
        row under a second wire id. This is the version that survives both.
        """
        rows = [
            a for a in self.agent.sessions.sessions if wire_session_id(a) == session_id
        ]
        assert len(rows) == 1, f"expected one agent row for {session_id}, got {rows}"
        return rows[0]

    async def history(self) -> list[dict]:
        """The session as the NEXT process would see it: reloaded from sqlite."""
        return await self.history_of(self.agent_id)

    async def history_of(self, agent_id: str) -> list[dict]:
        session = await AgentSession.load(agent_id, memory_path=self.config.db_uri)
        return session.messages

    # -- protocol ----------------------------------------------------------

    async def initialize(self):
        return await self.conn.initialize(
            v2.schema.InitializeRequest(
                protocol_version=v2.PROTOCOL_VERSION,
                info=v2.schema.Implementation(name="gate-client", version="2.0.0"),
            )
        )

    async def new_session(self, mcp_servers: list | None = None, cwd: str | None = None):
        response = await self.conn.new_session(
            v2.schema.NewSessionRequest(
                cwd=cwd or str(self.tmp_path), mcp_servers=mcp_servers or []
            )
        )
        self.session_id = response.session_id
        return response

    async def prompt(self, *blocks):
        return await self.conn.prompt(
            v2.schema.PromptRequest(session_id=self.session_id, prompt=list(blocks))
        )

    async def cancel(self) -> None:
        await self.conn.cancel_session(
            v2.schema.CancelSessionNotification(session_id=self.session_id)
        )

    async def list_sessions(self, cwd: str | None = None, cursor: str | None = None):
        return await self.conn.list_sessions(
            v2.schema.ListSessionsRequest(cwd=cwd, cursor=cursor)
        )

    async def resume_session(
        self,
        session_id: str | None = None,
        replay: bool = False,
        mcp_servers: list | None = None,
        cwd: str | None = None,
    ):
        """``replay=True`` sends ``replayFrom: {"type": "start"}`` — the only
        variant the schema has, and the one that asks for the transcript."""
        return await self.conn.resume_session(
            v2.schema.ResumeSessionRequest(
                session_id=session_id or self.session_id,
                cwd=cwd or str(self.tmp_path),
                mcp_servers=mcp_servers or [],
                replay_from=v2.schema.ReplayFromStartVariant() if replay else None,
            )
        )

    async def close_session(self, session_id: str | None = None):
        return await self.conn.close_session(
            v2.schema.CloseSessionRequest(session_id=session_id or self.session_id)
        )

    async def fork_session(self, session_id: str | None = None, **meta):
        """The anchors ride ``_meta``: v2's ForkSessionRequest carries the
        environment and nothing else, so there is nowhere else to put them."""
        return await self.conn.fork_session(
            v2.schema.ForkSessionRequest(
                session_id=session_id or self.session_id,
                cwd=str(self.tmp_path),
                mcp_servers=[],
                field_meta=meta or None,
            )
        )

    async def set_config_option(self, config_id: str, value: str, session_id: str | None = None):
        return await self.conn.set_config_option(
            v2.schema.SetSessionConfigOptionIdRequest(
                session_id=session_id or self.session_id,
                config_id=config_id,
                value=value,
                type="id",
            )
        )

    # -- waiting -----------------------------------------------------------

    async def wait_for(self, predicate, timeout: float = 20.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while not predicate():
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(
                    f"not satisfied within {timeout}s. Wire so far:\n"
                    + json.dumps([u["update"] for u in self.updates], indent=1, default=str)
                )
            await asyncio.sleep(0.01)

    async def wait_for_idle(self, count: int = 1, timeout: float = 20.0) -> None:
        """Block until the Nth idle, then let anything in flight land.

        The settle matters: several tests assert that nothing MORE arrived,
        and "nothing yet" is not the same as "nothing".
        """
        await self.wait_for(lambda: len(self.idles()) >= count, timeout)
        await asyncio.sleep(0.1)

    async def close(self) -> None:
        await self.conn.close()
        await self._agent_conn.close()
        await self.agent.cleanup()


@asynccontextmanager
async def gate(
    tmp_path: Path,
    scripts: list[list],
    config: Config | None = None,
    model: str | None = None,
    compactor=None,
):
    """One agent, one client, one transport.

    ``config`` is shared when a test needs TWO agents over the same store —
    which is what "the next process" means, and the only honest way to test a
    resume: a resume inside the agent that created the session finds it live
    and re-provisions nothing, so the hydrate-from-sqlite path never runs.

    ``model`` is the ``-m`` flag: an override every session in this agent is
    forced to, whatever the row says.

    ``compactor`` is the compaction strategy, and it is a constructor argument
    rather than something poked onto the agent afterwards because that is how
    a harness installs one: the registry binds it at ``driver_for`` time, so
    assigning it after a session exists would test nothing.
    """
    config = config or make_config(tmp_path)
    agent = CrowAgentV2(config, hooks=[], model=model, compactor=compactor)
    llm = ScriptedLLM(scripts)
    # The one stand-in. Swapped on the instance, so DriverDeps.make_llm —
    # bound at driver_for time — picks it up, and configure_llm (which would
    # build a real AsyncOpenAI against gate.invalid) is never reached.
    agent.sessions.make_llm = lambda session, log: llm

    client_transport, agent_transport = memory_transport_pair()
    # A real transport's send is not atomic — a stdio write can suspend — while
    # an in-memory queue.put never does. Yielding once per outgoing agent
    # message makes the pair behave like the real thing, so an ordering claim is
    # tested against interleaving rather than against an accident of speed: the
    # whole replay currently completes without one suspension, which would let a
    # driver started too early park "after" it and look correct.
    inner_send = agent_transport.send

    async def yielding_send(message):
        await asyncio.sleep(0)
        await inner_send(message)

    agent_transport.send = yielding_send
    wire: list = []
    agent_conn = v2.AgentSideConnection(agent, agent_transport)
    conn = v2.ClientSideConnection(
        UpdateClient(), client_transport, observers=[wire.append]
    )
    g = Gate(tmp_path, config, agent, llm, conn, agent_conn, wire)
    try:
        await g.initialize()
        yield g
    finally:
        await g.close()


def stdio_server(tmp_path: Path):
    script = tmp_path / "gate_mcp_server.py"
    script.write_text(MCP_SERVER)
    return v2.schema.StdioMcpServer(
        name="gate", command=sys.executable, args=[str(script)], env=[]
    )


def crow_mcp2_server():
    """The real crow-mcp2, on this interpreter.

    ``-m`` rather than the console script so the gate runs against THIS tree
    with no PATH lookup and no installed entry point. This is a real kernel
    subprocess, which makes the test that uses it the slowest in the file —
    and the only one that exercises the MCP progress relay against the server
    that actually sends progress notifications.
    """
    return v2.schema.StdioMcpServer(
        name="crow-mcp2",
        command=sys.executable,
        args=["-m", "crow_cli.mcp2.main"],
        env=[],
    )


async def wait_port(port: int, timeout: float = 30.0) -> None:
    """Block until something accepts a connection on ``port``.

    A twin of the one in ``test_mcp2_runner.py``. Neither file is the natural
    home for the other's helper, and a shared conftest entry for two callers
    would be harder to read than the duplication.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.1)
            continue
        writer.close()
        await writer.wait_closed()
        return
    raise TimeoutError(f"the gate's http MCP server never came up on :{port}")


@asynccontextmanager
async def http_server(tmp_path: Path, port: int):
    """A real MCP server on a real TCP port, handed back as an ``HttpMcpServer``.

    stderr goes to a file rather than a pipe: a server that dies before it
    binds leaves the test staring at a ``TimeoutError`` with no evidence, and a
    pipe nobody drains eventually fills and wedges the child instead.
    """
    script = tmp_path / "gate_mcp_http.py"
    script.write_text(MCP_HTTP_SERVER)
    errlog = tmp_path / "gate_mcp_http.stderr"
    with open(errlog, "wb") as errs:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(script), str(port),
            stdout=asyncio.subprocess.DEVNULL, stderr=errs,
        )
        try:
            await wait_port(port)
            yield v2.schema.HttpMcpServer(
                name="gate-http", url=f"http://127.0.0.1:{port}/mcp"
            )
        finally:
            proc.terminate()
            await proc.wait()
            errs.flush()
            noise = errlog.read_text(errors="replace")
            if "Traceback" in noise:
                print(noise)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


async def test_the_v2_prompt_lifecycle_lands_on_the_wire_in_order(tmp_path):
    """THE gate. One prompt, one turn, and every byte the client sees.

    v2 inverted the prompt: the response acknowledges and the turn's outcome
    travels as notifications. So the order below is not cosmetics, it is the
    contract a client is written against — ``{}`` first, then the user message
    the agent says it inserted, then running, then the reply, then idle
    carrying the stop reason v1 used to put in the response body.
    """
    async with gate(tmp_path, [text("Hello", ", world", "!") + [usage(42)]]) as g:
        await g.new_session()

        # A fresh session parks before any prompt. It reports idle — it is
        # ready — but with NO stop reason: the spec says an idle carries one
        # "when the transition ends foreground work", and no work ended.
        await g.wait_for_idle(1)
        assert g.kinds() == ["available_commands_update", "state_update"]
        assert g.idles()[0] == {"sessionUpdate": "state_update", "state": "idle"}

        prompt_response_index = len(g.wire)
        response = await g.prompt(v2.schema.TextContentBlock(text="say hi"))
        assert response.model_dump(mode="json", by_alias=True, exclude_none=True) == {}

        await g.wait_for_idle(2)

        assert g.kinds() == [
            "available_commands_update",
            "state_update",       # the fresh session's bare idle
            "user_message",       # where the prompt landed in history
            "state_update",       # running
            "session_info_update",  # the session just became nameable
            "agent_message_chunk",
            "agent_message_chunk",
            "agent_message_chunk",
            "usage_update",       # the context meter
            "state_update",       # idle, end_turn
        ]

        # The acknowledgement crossed the wire BEFORE any update about the
        # turn. This is the inversion; without it the client is still waiting
        # on the request while the agent streams.
        tail = g.wire[prompt_response_index:]
        result_at = next(
            i for i, e in enumerate(tail)
            if e.direction is StreamDirection.INCOMING and "result" in e.message
        )
        first_update_at = next(
            i for i, e in enumerate(tail) if e.message.get("method") == "session/update"
        )
        assert tail[result_at].message["result"] == {}
        assert result_at < first_update_at, (result_at, first_update_at)

        user = g.of_kind("user_message")[0]
        assert user["content"] == [{"text": "say hi", "type": "text"}]
        assert user["messageId"]

        chunks = g.of_kind("agent_message_chunk")
        assert [c["content"]["text"] for c in chunks] == ["Hello", ", world", "!"]
        # One reply, one messageId. A client keys its markdown document by it,
        # so three chunks with three ids render as three messages.
        assert len({c["messageId"] for c in chunks}) == 1
        # And it is not the user's id — that would overwrite the prompt.
        assert chunks[0]["messageId"] != user["messageId"]

        states = g.states()
        assert states[1] == {"sessionUpdate": "state_update", "state": "running"}
        assert states[2] == {
            "sessionUpdate": "state_update",
            "state": "idle",
            "stopReason": "end_turn",
            # The landmine: a raw provider dict validates to None here, with
            # no exception. prompt/completion must arrive as input/output.
            "usage": {"totalTokens": 42, "inputTokens": 21, "outputTokens": 21},
        }

        assert g.of_kind("usage_update")[0]["used"] == 42
        # A turn that only talked ran no tools. Half of the progress signal
        # the goal continuation reads; the other half is the tool round trip.
        assert g.tools_used == 0

        # One prompt, one model call.
        assert len(g.llm.calls) == 1
        sent = g.llm.calls[0]
        assert sent["model"] == "gate-model-id"
        assert sent["stream"] is True
        assert sent["messages"][-1] == {
            "role": "user",
            "content": [{"type": "text", "text": "say hi"}],
        }

        # And it persisted: the next process resolves this session and sees
        # the exchange, which is what makes a resume possible at all.
        history = await g.history()
        assert history[-2]["role"] == "user"
        assert history[-1]["role"] == "assistant"
        assert history[-1]["content"] == "Hello, world!"


async def test_reasoning_is_its_own_message(tmp_path):
    """Thoughts and the reply are two documents, so they are two messageIds.

    A client keys its markdown view by messageId. Sharing one between the
    reasoning pane and the answer would render "hmm. answer" as a single
    bubble; splitting them is what lets a client collapse the thinking. And a
    call with no reasoning mints no id at all — the loop is lazy about it.
    """
    script = thought("hmm", ". ") + text("answer") + [usage(7)]
    async with gate(tmp_path, [script]) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        await g.prompt(v2.schema.TextContentBlock(text="think, then answer"))
        await g.wait_for_idle(2)

        thoughts = g.of_kind("agent_thought_chunk")
        replies = g.of_kind("agent_message_chunk")
        assert "".join(t["content"]["text"] for t in thoughts) == "hmm. "
        assert "".join(c["content"]["text"] for c in replies) == "answer"
        assert len({t["messageId"] for t in thoughts}) == 1
        assert len({c["messageId"] for c in replies}) == 1
        assert thoughts[0]["messageId"] != replies[0]["messageId"]
        # Thinking first: it happened first.
        assert g.kinds().index("agent_thought_chunk") < g.kinds().index(
            "agent_message_chunk"
        )

        # Both persisted, on the one assistant row, in their own fields.
        last = (await g.history())[-1]
        assert last["content"] == "answer"
        assert last["reasoning_content"] == "hmm. "


async def test_an_attachment_reaches_the_model_and_the_transcript(tmp_path):
    """What a client attaches to a prompt, over the wire.

    A resource link is BASELINE — the spec requires every agent to accept text
    and resource links in a prompt, capability or no — and the image is what
    ``initialize`` advertised ``prompt.image`` for. Both are honoured by one
    pure function, which v2 silently broke by retyping every ``uri`` from
    ``str`` to ``AnyUrl``. The block was dropped behind an ``except`` that
    logged, the turn ran anyway, and the model answered as though nothing had
    been sent: from the client side, indistinguishable from a model that
    ignored the user.

    ``test_agent2_normalize_prompt.py`` pins the function. This pins the path
    into it, which is the half that decides whether the blocks arrive as
    protocol models or as aliased dicts — and the mime type assertion is what
    makes that distinction observable rather than assumed.
    """
    notes = tmp_path / "notes.md"
    notes.write_text("# the note\n")
    shot = base64.b64encode(b"\x89PNG-gate").decode()

    async with gate(tmp_path, [text("looked at it") + [usage(11)]]) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        await g.prompt(
            v2.schema.TextContentBlock(text="what does it say?"),
            v2.schema.ResourceContentBlock(name="notes", uri=notes.as_uri()),
            v2.schema.ImageContentBlock(data=shot, mime_type="image/jpeg"),
        )
        await g.wait_for_idle(2)

        # The echo goes back as it arrived — the agent reports where the
        # message landed in history, not what it made of it.
        user = g.of_kind("user_message")[0]
        assert [b["type"] for b in user["content"]] == ["text", "resource_link", "image"]
        assert user["content"][1]["uri"] == notes.as_uri()
        assert user["content"][2]["mimeType"] == "image/jpeg"

        # What the model was sent is the other half: the link resolved to the
        # file's numbered lines, the image to a data URL still carrying the
        # mime type it arrived with.
        sent = g.llm.calls[0]["messages"][-1]
        assert sent["role"] == "user"
        content = sent["content"]
        assert content[0] == {"type": "text", "text": "what does it say?"}
        assert content[1]["type"] == "text"
        assert content[1]["text"].startswith(str(notes))
        assert "0\t# the note" in content[1]["text"]
        assert content[2] == {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{shot}"},
        }


async def test_a_slash_command_is_a_turn_that_never_calls_the_model(tmp_path):
    """A command still owes the client a turn boundary.

    ``session/prompt`` answered ``{}``, so the only completion signal a client
    has is the idle ``state_update``. Answering from the command table and
    returning without one leaves a spinner running forever — and the driver's
    state dedupe hides it, because the session was already idle.
    """
    async with gate(tmp_path, []) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        await g.prompt(v2.schema.TextContentBlock(text="/help"))
        await g.wait_for_idle(2)

        assert g.kinds()[2:] == [
            "user_message",
            "state_update",     # running — a command is foreground work too
            "session_info_update",   # a command titles a session like any prompt
            "agent_message",
            "state_update",     # idle, end_turn
        ]
        body = g.of_kind("agent_message")[0]["content"][0]["text"]
        assert "Available slash commands" in body
        assert "/compact" in body
        # A command is a user message like any other, so it titles the session
        # — which is what session/list would report for it too. Consistent
        # rather than pretty: the two paths read the same store.
        assert g.of_kind("session_info_update") == [
            {"title": "/help", "sessionUpdate": "session_info_update"}
        ]

        assert g.idles()[1]["stopReason"] == "end_turn"
        assert g.llm.calls == []
        # The user's command is history; the reply is not (v1 never persisted
        # slash replies either).
        assert (await g.history())[-1]["role"] == "user"


async def test_a_tool_call_becomes_one_upsert_sequence_on_the_wire(tmp_path):
    """v2 has no ``tool_call``. One id, upserted pending -> in_progress -> done.

    Real MCP: the server is a subprocess spawned from the ``mcpServers`` the
    client sent, so this covers the wire conversion, the FastMCP client, the
    tool list handed to the model, and the result coming back — not just the
    emitter.
    """
    scripts = [
        call(0, "call_1", "echo", '{"text": "hi"}') + [usage(10)],
        text("done") + [usage(20)],
    ]
    async with gate(tmp_path, scripts) as g:
        await g.new_session(mcp_servers=[stdio_server(tmp_path)])
        await g.wait_for_idle(1)

        await g.prompt(v2.schema.TextContentBlock(text="echo hi"))
        await g.wait_for_idle(2)

        updates = g.of_kind("tool_call_update")
        assert [u["status"] for u in updates] == ["pending", "in_progress", "completed"]
        # One tool call, one id: these are patches, not three separate calls.
        assert len({u["toolCallId"] for u in updates}) == 1
        assert updates[0]["toolCallId"].endswith("/call_1")

        assert updates[0]["title"] == "echo"
        assert updates[0]["kind"] == "other"
        assert updates[0]["rawInput"] == {"text": "hi"}
        # Only the fields that changed ride along on a patch.
        assert "title" not in updates[1]
        assert "rawInput" not in updates[1]
        assert updates[2]["content"] == [
            {"content": {"text": "echo: hi", "type": "text"}, "type": "content"}
        ]

        # The loop went round: the second call saw the tool result.
        assert len(g.llm.calls) == 2
        second = g.llm.calls[1]["messages"]
        assert second[-2]["role"] == "assistant"
        assert second[-2]["tool_calls"][0]["function"] == {
            "name": "echo",
            "arguments": '{"text": "hi"}',
        }
        assert second[-1]["role"] == "tool"
        assert second[-1]["tool_call_id"] == "call_1"
        assert second[-1]["content"] == "echo: hi"

        assert g.of_kind("agent_message_chunk")[0]["content"]["text"] == "done"
        assert g.idles()[1]["stopReason"] == "end_turn"
        # One call in one batch, reported on the turn as a whole: the loop went
        # round twice but the second iteration only talked.
        assert g.tools_used == 1

        # History stays valid: every tool_call_id in an assistant message has
        # a matching tool response before anything else speaks.
        pending: list[str] = []
        for msg in await g.history():
            if msg["role"] == "assistant":
                assert not pending, f"unanswered tool calls: {pending}"
                pending = [tc["id"] for tc in msg.get("tool_calls") or []]
            elif msg["role"] == "tool":
                assert msg["tool_call_id"] in pending
                pending.remove(msg["tool_call_id"])
        assert not pending


async def test_an_http_mcp_server_supplies_the_tools_a_session_runs(
    tmp_path, free_tcp_port
):
    """The other half of the ``session.mcp`` claim: ``{"http": {}}``.

    ``initialize`` advertises both transports and
    ``test_initialize_claims_the_session_surface_it_actually_answers`` asserts
    the advertisement — but every other tool test in this file spawns a stdio
    server, so the http half was a capability crow claimed and nothing here
    ever acted on. Same echo tool, real TCP port: the agent has to translate an
    ``HttpMcpServer`` into a FastMCP config, connect, list the tools for the
    model, and call one.

    ``test_agent2_mcp_wiring.py`` pins the translation in isolation. This is
    the half that proves the config it produces actually connects.
    """
    scripts = [
        call(0, "call_http", "echo", '{"text": "over http"}') + [usage(10)],
        text("done") + [usage(20)],
    ]
    async with http_server(tmp_path, free_tcp_port) as server:
        async with gate(tmp_path, scripts) as g:
            await g.new_session(mcp_servers=[server])
            await g.wait_for_idle(1)

            await g.prompt(v2.schema.TextContentBlock(text="echo over http"))
            await g.wait_for_idle(2)

            # The model was offered exactly the tool the http server serves,
            # which is only true if a client connected and listed it.
            offered = g.llm.calls[0]["tools"]
            assert [t["function"]["name"] for t in offered] == ["echo"]

            updates = g.of_kind("tool_call_update")
            assert [u["status"] for u in updates] == [
                "pending", "in_progress", "completed"
            ]
            assert updates[0]["rawInput"] == {"text": "over http"}
            assert updates[-1]["content"] == [
                {"content": {"text": "echo: over http", "type": "text"}, "type": "content"}
            ]
            assert g.of_kind("agent_message_chunk")[0]["content"]["text"] == "done"


async def test_a_live_execute_call_is_a_terminal_and_not_a_tool_result(tmp_path):
    """``execute`` is not one tool call among others — it is a terminal.

    The generic path above puts the result text in the call's ``content``.
    ``execute`` puts the bytes somewhere a client can render them live and
    points the call at that instead, because one cell has two audiences: raw
    PTY bytes for the human, ANSI-stripped text for the model. So the shape
    differs in four ways a client has to be written against, and all four are
    asserted here: no ``pending`` (the call is created already running, since
    the terminal opening IS the progress), a ``terminal_update`` naming the
    command before any bytes, the bytes twice (live as chunks, then whole as a
    snapshot, because the server cannot know who was watching), and an exit
    status on the TERMINAL that is independent of the call's own status.

    Scripted model, real crow-mcp2, real kernel. ``tests/e2e`` proves a live
    provider drives the same path; only this pins the sequence deterministically.
    """
    cell = "print('CROW-GATE')"
    scripts = [
        call(0, "call_x", "execute", json.dumps({"code": cell})) + [usage(10)],
        text("ran it") + [usage(20)],
    ]
    async with gate(tmp_path, scripts) as g:
        await g.new_session(mcp_servers=[crow_mcp2_server()])
        await g.wait_for_idle(1)

        await g.prompt(v2.schema.TextContentBlock(text="run the cell"))
        # A real kernel start, not a scripted reply: the default 20s is for a
        # model, and this waits on ipykernel plus the subtool prelude.
        await g.wait_for_idle(2, timeout=120)

        calls = g.of_kind("tool_call_update")
        assert [c["status"] for c in calls] == ["in_progress", "completed"]
        acp_id = calls[0]["toolCallId"]
        assert acp_id.endswith("/call_x")
        assert calls[0]["title"] == "execute"
        assert calls[0]["kind"] == "execute"
        assert calls[0]["rawInput"] == {"code": cell}

        terms = g.of_kind("terminal_update")
        terminal_id = terms[0]["terminalId"]
        # The client correlates a call with its terminal by id, so the scheme
        # is part of the contract and not an implementation detail.
        assert terminal_id == f"term_{acp_id}"
        assert {t["terminalId"] for t in terms} == {terminal_id}

        # The whole sequence, projected. Exactly one tool call in this turn, so
        # nothing needs filtering out.
        projected = []
        for params in g.updates:
            u = params["update"]
            kind = u["sessionUpdate"]
            if kind == "tool_call_update":
                projected.append(f"call:{u['status']}")
            elif kind == "terminal_output_chunk":
                projected.append("chunk")
            elif kind == "terminal_update":
                # One field per update: the emitter passes the others as None
                # and the wire drops them, which is what makes these patches
                # rather than four full snapshots of the same terminal.
                fields = [f for f in ("command", "output", "exitStatus") if f in u]
                assert len(fields) == 1, u
                projected.append(f"terminal:{fields[0]}")
        assert projected[:2] == ["call:in_progress", "terminal:command"], projected
        assert projected[-3:] == [
            "terminal:output",
            "call:completed",
            "terminal:exitStatus",
        ], projected
        # Live bytes, between opening the terminal and snapshotting it. There
        # would be none if the agent had sent no progressToken.
        assert projected[2:-3] and set(projected[2:-3]) == {"chunk"}, projected

        opened, snapshot, closed = terms
        assert opened["command"] == cell
        assert opened["cwd"] == str(tmp_path)
        streamed = b"".join(
            base64.b64decode(c["data"])
            for c in g.of_kind("terminal_output_chunk")
        )
        assert streamed == b"CROW-GATE\n"
        # The snapshot is the same bytes sent whole, for a client that attached
        # late or is replaying — the server does not know who was watching.
        assert base64.b64decode(snapshot["output"]["data"]) == streamed
        assert closed["exitStatus"] == {"exitCode": 0}

        done = calls[1]
        # The call POINTS at the terminal instead of carrying the text.
        assert done["content"] == [{"terminalId": terminal_id, "type": "terminal"}]
        assert done["rawOutput"] == {"output": "CROW-GATE\n", "exit_code": 0}

        # The model's half of the split, and the reason the payload is JSON on
        # the MCP wire but plain text in the transcript: it reads the stripped
        # output, never the raw bytes and never the envelope around them.
        second = g.llm.calls[1]["messages"]
        assert second[-1]["role"] == "tool"
        assert second[-1]["tool_call_id"] == "call_x"
        assert second[-1]["content"] == "CROW-GATE\n"

        assert g.of_kind("agent_message_chunk")[0]["content"]["text"] == "ran it"
        assert g.idles()[1]["stopReason"] == "end_turn"


async def test_cancel_mid_stream_is_confirmed_by_an_idle(tmp_path):
    """``session/cancel`` ends the turn; the idle is the confirmation.

    v1 confirmed by returning ``stopReason: "cancelled"`` from the prompt
    response. That response is now ``{}`` and already sent, so the spec moves
    the confirmation to an idle ``state_update`` — and the half-finished
    completion still has to persist, or the next turn's history holds a
    message the API never saw.
    """
    async with gate(tmp_path, [text("partial ") + [HANG]]) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        await g.prompt(v2.schema.TextContentBlock(text="go on forever"))
        await g.wait_for(lambda: g.of_kind("agent_message_chunk"))

        await g.cancel()
        await g.wait_for_idle(2)

        assert g.idles()[1]["stopReason"] == "cancelled"
        assert g.of_kind("agent_message_chunk")[0]["content"]["text"] == "partial "

        # The driver survives its own turn: cancel is per-turn in v2, so the
        # session is still there and still promptable.
        assert g.agent.sessions.drivers[g.session_id].running is False

        history = await g.history()
        assert history[-1]["role"] == "assistant"
        assert history[-1]["content"] == "partial "


async def test_a_prompt_for_an_unknown_session_is_a_json_rpc_error(tmp_path):
    """v2's PromptResponse is empty, so an error is the only channel left.

    Acknowledging a prompt for a session that does not exist would leave the
    client waiting on an idle that can never come.
    """
    async with gate(tmp_path, []) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        g.session_id = "no-such-session"

        with pytest.raises(RequestError) as excinfo:
            await g.prompt(v2.schema.TextContentBlock(text="hello?"))
        assert excinfo.value.code == -32602
        assert excinfo.value.data == {
            "sessionId": "no-such-session",
            "details": "unknown session",
        }
        # Nothing was minted for the bogus id, and no turn ran. Resolving
        # first is what keeps a client from littering the log directory with
        # a file per guessed session id — logger_for opens one on sight.
        assert g.llm.calls == []
        assert g.kinds() == ["available_commands_update", "state_update"]
        assert not list((g.config.config_dir / "logs").glob("*no-such-session*"))
        assert "no-such-session" not in g.agent.sessions.emitters


def _bus_reachable(url: str) -> bool:
    try:
        client = redis.from_url(url, socket_connect_timeout=1.0, socket_timeout=1.0)
        client.ping()
        client.close()
        return True
    except Exception:
        return False


async def test_a_session_with_a_task_still_running_parks_idle(tmp_path):
    """A delegated task is BACKGROUND activity, and the spec is explicit about
    it: such activity may continue and emit updates while the agent reports
    ``idle``, those notifications do not change the state, and an agent ready
    for a new prompt MUST report ``idle``.

    crow used to park this session under a private ``_crow_blocked_on_task``.
    A strict v2 client reads a non-idle state as "input closed", so it greyed
    out a session that was in fact promptable; and ``client2.wait()`` returns
    on idle, so ``crow-cli run -a NAME`` could not be told the turn had ended
    and blocked for the whole delegated task. A running timer row did the same
    for the length of the timer.
    """
    async with gate(tmp_path, [text("launched it") + [usage(5)]]) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        engine = g.agent.sessions.engine
        launch_task(
            engine,
            task_id="t-still-running",
            owner_session=g.session_id,
            prompt="go",
        )
        # The row is what a wake reads. Asserting it is what keeps the test
        # honest: without this, a launch that silently wrote nothing would
        # park idle too and prove nothing.
        assert [t.task_id for t in running_tasks(engine, g.session_id)] == [
            "t-still-running"
        ]

        await g.prompt(v2.schema.TextContentBlock(text="kick something off"))
        await g.wait_for_idle(2)

        last = g.states()[-1]
        assert last["state"] == "idle"
        assert last["stopReason"] == "end_turn"
        # And nothing else was invented to say "busy but promptable". The
        # usage an idle carries is pinned elsewhere; the STATE is the claim.
        assert {s["state"] for s in g.states()} == {"idle", "running"}


async def test_a_finished_task_wakes_a_parked_session_before_the_backstop_poll(tmp_path):
    """The wake: a mailbox row plus a poke restarts a session that had stopped.

    This is the capability v1 did not have. There a returned react loop was a
    deaf loop, so a completion could only be picked up by blocking INSIDE the
    turn and polling every two seconds — the delegation hold, and with it the
    turn that could not be ended and the agent that could not be cancelled.
    Here the driver parks on its inbox and the bus gets it out again.

    The timing assertion is the test. Without it this passes on the driver's
    ``PARK_BACKSTOP_S`` poll alone, which is the fallback the poke exists to
    make unnecessary — a bus that never delivered anything would look exactly
    like a bus that works, thirty seconds slower.
    """
    async with gate(tmp_path, [text("awake") + [usage(3)]]) as g:
        if not _bus_reachable(g.config.redis_url):
            pytest.skip(f"no redis at {g.config.redis_url} (compose up -d redis)")
        await g.new_session()
        await g.wait_for_idle(1)

        # Parked, bare, and having run nothing.
        assert g.llm.calls == []
        assert g.states()[-1] == {"sessionUpdate": "state_update", "state": "idle"}

        engine = g.agent.sessions.engine
        launch_task(engine, task_id="task-wake", owner_session=g.session_id, prompt="go")
        # ROW FIRST, POKE SECOND — the order is the contract. A poke says "go
        # look", never "here is what you will find", so publishing before the
        # commit would let the driver consult an empty mailbox and park again.
        assert finish_task(
            engine,
            "task-wake",
            result="done",
            content="task-wake finished: the child said done",
        ) is True

        woken_at = time.monotonic()
        assert await publish_wake(
            g.config.redis_url, Poke(session_id=g.session_id, task_id="task-wake")
        ) is True
        await g.wait_for_idle(2, timeout=15.0)
        elapsed = time.monotonic() - woken_at

    assert elapsed < PARK_BACKSTOP_S, (
        f"the wake took {elapsed:.1f}s — that is the backstop poll, not the bus"
    )
    # The delivery reached the client as something the user can see...
    chunks = [c["content"]["text"] for c in g.of_kind("user_message_chunk")]
    assert any("task-wake finished" in c for c in chunks), chunks
    # ...and the model as something it actually read.
    assert len(g.llm.calls) == 1
    sent = g.llm.calls[0]["messages"]
    assert sent[-1]["role"] == "user"
    assert "task-wake finished" in sent[-1]["content"]
    assert g.idles()[1]["stopReason"] == "end_turn"

    # The wake is persisted like any other turn, so the NEXT process resumes
    # a session that knows what woke it and what it said about it.
    history = await g.history()
    assert [m["role"] for m in history[-2:]] == ["user", "assistant"]
    assert "task-wake finished" in history[-2]["content"]
    assert history[-1]["content"] == "awake"


# ---------------------------------------------------------------------------
# Phase 3: the session surface
# ---------------------------------------------------------------------------


async def test_initialize_claims_the_session_surface_it_actually_answers(tmp_path):
    """``capabilities.session`` is a promise, and v2 made most of it mandatory.

    The three per-method markers v1 had are gone: claiming sessions at all now
    means answering ``session/list``, ``session/resume`` and ``session/close``.
    Only ``fork`` and ``delete`` are still opt-in, so those two are the ones a
    client reads to decide what it may ask — and an agent that claims ``fork``
    without implementing it, or implements ``delete`` without claiming it, is
    lying in one direction or the other.

    ``mcp`` is claimed for the same reason ``fork`` is: it is true, and a client
    that reads it as absent sends no ``mcpServers`` — and the client owns crow's
    tool supply, so the session would come up with zero tools.
    """
    async with gate(tmp_path, []) as g:
        session = g.init_capabilities["session"]
        assert session["prompt"] == {"image": {}, "embeddedContext": {}}
        # stdio and http are what mcp_client_for builds. "acp" is skipped with
        # a warning, so claiming it would advertise a transport crow drops.
        assert session["mcp"] == {"stdio": {}, "http": {}}
        assert session["fork"] == {}
        # Not claimed, because not implemented: crow has no session deletion
        # and no additional-root model. Absent keys, not false ones.
        assert "delete" not in session
        assert "additionalDirectories" not in session


async def test_what_crow_does_not_claim_it_refuses_rather_than_answers(tmp_path, caplog):
    """The other half of the capability claim: an unimplemented method is -32601.

    ``initialize`` saying "no delete, no additionalDirectories" is only half a
    promise. The half a client actually depends on is what happens when it asks
    anyway — a third-party client, a newer one, or a bug. Every request crow has
    no handler for must come back ``Method not found`` naming the method, which
    is what v2's ``MethodRouter`` does for a missing handler attribute and why
    ``client2`` deleted v1's explicit stubs instead of porting them.

    The EXTENSION case is the one that was wrong. ``_``-prefixed methods route
    to ``handle_extension_request`` rather than to a named handler, so the
    router's absence check never ran — and the handler crow supplied answered
    every unknown extension with a success ``{}``. A client asking for
    ``_vendor/anything`` was told the agent had done it, and had no way to
    learn otherwise. An extension is a method; it gets a method's refusal.

    Notifications are the opposite, and stay silent: there is no reply to get
    wrong, and the router swallowing an unhandled one is the designed behaviour.
    """
    async with gate(tmp_path, [text("ok") + [usage(3)]]) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        with pytest.raises(RequestError) as ext:
            await g.conn.send_extension_request("_vendor/anything", {"x": 1})
        assert ext.value.code == -32601
        assert ext.value.data == {"method": "_vendor/anything"}

        # One per family crow has no handler for, rather than the whole
        # protocol. Raw ``send_request`` with None params, because the router
        # refuses BEFORE it validates: building five request models would test
        # the SDK's validators and prove nothing about crow's routing.
        for method in [
            "session/delete", "auth/login", "providers/list",
            "mcp/message", "nes/start",
        ]:
            with pytest.raises(RequestError) as excinfo:
                await g.conn._conn.send_request(method, None)
            assert excinfo.value.code == -32601, method
            assert excinfo.value.data == {"method": method}, method

        # No reply to be wrong, and no licence to disturb the session. The
        # notification hook is kept for its LOG, which is the only trace an
        # unexpected extension leaves — the router swallows an unhandled one
        # without a word. Pinned so the asymmetry with the deleted request
        # handler reads as the decision it is and not as an oversight.
        caplog.set_level(logging.INFO, logger="crow-agent2")
        await g.conn.send_extension_notification("_vendor/event", {"x": 1})
        await g.conn._conn.send_notification("document/didOpen", None)
        await g.wait_for(lambda: "_vendor/event" in caplog.text)

        await g.prompt(v2.schema.TextContentBlock(text="still here"))
        await g.wait_for_idle(2)
        assert [c["content"]["text"] for c in g.of_kind("agent_message_chunk")] == ["ok"]


async def test_session_list_carries_what_a_client_needs_to_render_history(tmp_path):
    """One page, newest first, with a title a history screen can show.

    ``cwd`` is a FILTER and it is optional, so leaving it out lists everything
    the store knows. v1 answered a missing cwd with an empty page, which made
    "what sessions do I have" unanswerable over the protocol — a client had to
    already know the directory it was asking about in order to ask.

    The title is the first user message, and a session that has not been spoken
    to has NO title rather than a placeholder: ``SessionInfo.title`` is optional
    and the client is the one that knows what an untitled session looks like.
    """
    other = tmp_path / "other"
    other.mkdir()
    async with gate(tmp_path, [text("ok") + [usage(3)]]) as g:
        await g.new_session()
        await g.new_session(cwd=str(other))
        spoken_to = g.session_id
        # Two drivers, two parks, two idles.
        await g.wait_for_idle(2)

        # Give the second one a title and make it unambiguously the newest.
        await g.prompt(v2.schema.TextContentBlock(text="say hi"))
        await g.wait_for_idle(3)
        titled, untitled = spoken_to, [
            sid for sid in g.agent.sessions.tools if sid != spoken_to
        ][0]

        await g.list_sessions()
        page = g.last_result()
        assert "nextCursor" not in page
        assert [i["sessionId"] for i in page["sessions"]] == [titled, untitled]

        first = page["sessions"][0]
        assert first["cwd"] == str(other)
        assert first["title"] == "say hi"
        # RFC 3339, and present: it is what a history screen sorts by.
        assert first["updatedAt"]
        assert "additionalDirectories" not in first

        second = page["sessions"][1]
        assert second["sessionId"] == untitled
        assert second["cwd"] == str(tmp_path)
        assert "title" not in second, second

        # The filter narrows rather than replacing the listing.
        await g.list_sessions(cwd=str(other))
        assert [i["sessionId"] for i in g.last_result()["sessions"]] == [titled]
        await g.list_sessions(cwd=str(tmp_path))
        assert [i["sessionId"] for i in g.last_result()["sessions"]] == [untitled]
        # A directory with nothing in it is an empty page, not an error and not
        # every session.
        await g.list_sessions(cwd=str(tmp_path / "nowhere"))
        assert g.last_result() == {"sessions": []}


async def test_session_list_paginates_with_the_cursor_it_issued(tmp_path, monkeypatch):
    """``nextCursor`` is opaque to the client and round-trips to the next page.

    One session per page so two sessions are two pages without building
    fifty-one of them. The interesting half is the refusal at the end: a cursor
    this agent did not issue is an error, not page zero. Restarting the listing
    would hand back sessions the client has already rendered, and duplicated
    history is the one thing a history screen cannot paper over.
    """
    monkeypatch.setattr("crow_cli.agent2.agent.PAGE_SIZE", 1)
    async with gate(tmp_path, []) as g:
        await g.new_session()
        older = g.session_id
        # Distinct created_at, so "newest first" is a fact and not a tie the
        # database happens to break the way this test wants.
        await asyncio.sleep(0.01)
        await g.new_session()
        newer = g.session_id
        await g.wait_for_idle(2)

        await g.list_sessions()
        page = g.last_result()
        assert [i["sessionId"] for i in page["sessions"]] == [newer]
        cursor = page["nextCursor"]
        assert cursor

        await g.list_sessions(cursor=cursor)
        page = g.last_result()
        assert [i["sessionId"] for i in page["sessions"]] == [older]
        # Absent, not null: "if absent, there are no more results."
        assert "nextCursor" not in page

        with pytest.raises(RequestError) as excinfo:
            await g.list_sessions(cursor="not-a-cursor")
        assert excinfo.value.code == -32602
        assert excinfo.value.data == {
            "cursor": "not-a-cursor",
            "details": "not a cursor this agent issued",
        }


async def test_a_session_is_named_on_the_wire_the_moment_it_can_be(tmp_path):
    """``session_info_update`` is the only channel a session's title has.

    No response in the protocol carries a ``SessionInfo`` — ``session/new``
    answers with a sessionId and config options — and the title is the first
    user message, which by definition does not exist yet when the session is
    created. A client holding a session list open therefore has no way to learn
    what the session it just made is called, short of re-listing. The spec put
    this notification there for exactly that: "This allows clients to display
    dynamic session names and track session state changes."

    The title is READ BACK out of the store rather than built from the prompt
    in hand, and the agreement asserted at the end is the reason: whatever
    ``session/list`` would say is what the client is told. Two derivations of
    one fact is how a list and a notification come to disagree about it.

    Once per session, and never for a fork — ``session/list`` excludes forks,
    so a branch has no entry to name.
    """
    async with gate(
        tmp_path,
        [
            text("ok") + [usage(3)],
            text("ok again") + [usage(4)],
            text("branched") + [usage(5)],
        ],
    ) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        sid = g.session_id
        # Nothing to name yet: no user message has landed, so there is no title.
        assert g.of_kind("session_info_update") == []

        await g.prompt(v2.schema.TextContentBlock(text="say hi"))
        await g.wait_for_idle(2)

        [announced] = g.of_kind("session_info_update")
        assert announced == {"title": "say hi", "sessionUpdate": "session_info_update"}
        # Patch semantics, and crow patches one field. An ``updatedAt`` here
        # would be a claim about a field the client is otherwise entitled to
        # keep — and ``session/list`` recomputes it from the store every page,
        # so a timestamp per message buys nothing and costs a firehose.
        assert "updatedAt" not in announced
        # After the turn's opening pair, not wedged inside it: the spec names
        # user_message then running, and this is about the session, not the turn.
        kinds = g.kinds_for(sid)
        at = kinds.index("session_info_update")
        assert kinds[at - 2:at] == ["user_message", "state_update"]

        await g.prompt(v2.schema.TextContentBlock(text="say hi again"))
        await g.wait_for_idle(3)
        # Still one. The title is the FIRST user message; announcing on every
        # prompt would rename the session behind the client's back.
        assert g.of_kind("session_info_update") == [announced]

        await g.list_sessions()
        [listed] = [i for i in g.last_result()["sessions"] if i["sessionId"] == sid]
        assert listed["title"] == announced["title"]

        # A fork is a session a client can drive, and driving it names nothing.
        await g.fork_session(sid)
        fork_id = g.last_result()["sessionId"]
        await g.wait_for_idle(4)
        g.session_id = fork_id
        await g.prompt(v2.schema.TextContentBlock(text="on the branch"))
        await g.wait_for_idle(5)
        assert g.of_kind("session_info_update") == [announced]
        assert "session_info_update" not in g.kinds_for(fork_id)


async def test_a_session_with_nothing_to_say_gets_no_name(tmp_path):
    """An image-only first message has no text in it, so there is no title.

    ``SessionInfo.title`` is optional and crow leaves it absent rather than
    inventing a placeholder — the client is the one that knows what an untitled
    session looks like. The announcement has to agree, and "agree" means
    staying silent: an empty ``session_info_update`` is a patch of nothing at
    all, which reads to a client as an update and then updates nothing.
    """
    shot = base64.b64encode(b"not a png; nothing on this path decodes it").decode()
    async with gate(tmp_path, [text("sure") + [usage(3)]]) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        sid = g.session_id
        await g.prompt(v2.schema.ImageContentBlock(data=shot, mime_type="image/png"))
        await g.wait_for_idle(2)

        assert g.of_kind("session_info_update") == []
        await g.list_sessions()
        [listed] = [i for i in g.last_result()["sessions"] if i["sessionId"] == sid]
        assert "title" not in listed, listed


async def test_a_resume_without_a_replay_cursor_reattaches_silently(tmp_path):
    """``replayFrom`` omitted means "resume", not "resume and re-tell me".

    The spec is explicit that omitted and ``null`` both mean resume without
    replaying, and that only ``{"type": "start"}`` asks for the conversation.
    A client that already has the transcript on screen — a reconnect, a second
    window — must not be handed a second copy of it.

    Tested across TWO agents over one store, because that is what a resume is:
    inside the agent that created the session, ``resolve`` finds it live and
    the hydrate-from-sqlite path never runs.
    """
    config = make_config(tmp_path)
    script = thought("hmm. ") + text("answer") + [usage(9)]
    async with gate(tmp_path, [script], config) as g1:
        await g1.new_session()
        await g1.wait_for_idle(1)
        sid = g1.session_id
        await g1.prompt(v2.schema.TextContentBlock(text="think then answer"))
        await g1.wait_for_idle(2)

    async with gate(tmp_path, [], config) as g2:
        await g2.resume_session(sid)
        await g2.wait_for_idle(1)

        # Commands, then the driver's park. Nothing about the past.
        assert g2.kinds() == ["available_commands_update", "state_update"]
        # And the park is bare: no turn ended in THIS process, so there is no
        # stop reason to report and inventing one would be a lie.
        assert g2.idles()[0] == {"sessionUpdate": "state_update", "state": "idle"}

        # The response carries the session's own model, not the process
        # default: a client that showed one model before a restart shows the
        # same one after it.
        options = g2.last_result()["configOptions"]
        assert [o["configId"] for o in options] == ["model"]
        assert options[0]["currentValue"] == "gate-provider:gate-model-id"

        # An id that exists nowhere is refused the same way prompt refuses it.
        # Attaching to nothing and answering cleanly would leave the client
        # waiting on an idle that can never come.
        with pytest.raises(RequestError) as excinfo:
            await g2.resume_session("no-such-session")
        assert excinfo.value.code == -32602
        assert excinfo.value.data == {
            "sessionId": "no-such-session",
            "details": "unknown session",
        }


async def test_replay_from_start_rebuilds_the_transcript_before_the_idle(tmp_path):
    """``session/load`` is gone; this is what replaced it.

    Two claims, and the second is the one that is easy to get wrong:

    * **whole messages, not chunks.** v2's updates are upserts — a
      whole-message update replaces content, a chunk appends — so the assembled
      strings history holds map onto the replace form directly. Re-splitting
      them into chunks would be theatre no client can see, at N notifications
      instead of one.
    * **the idle comes LAST.** The driver's first act with nothing to do is
      park, and parking emits an idle, so starting the driver before the replay
      would put "ready for a new prompt" on the wire ahead of the transcript it
      refers to. A client drives its input box from that idle.
    """
    config = make_config(tmp_path)
    script = thought("hmm. ") + text("answer") + [usage(9)]
    async with gate(tmp_path, [script], config) as g1:
        await g1.new_session()
        await g1.wait_for_idle(1)
        sid = g1.session_id
        await g1.prompt(v2.schema.TextContentBlock(text="think then answer"))
        await g1.wait_for_idle(2)

    async with gate(tmp_path, [text("again") + [usage(2)]], config) as g2:
        await g2.resume_session(sid, replay=True)
        await g2.wait_for_idle(1)

        assert g2.kinds() == [
            "available_commands_update",
            "user_message",
            "agent_thought",
            "agent_message",
            "state_update",          # idle — after the transcript, not before
        ]
        assert g2.of_kind("user_message")[0]["content"] == [
            {"text": "think then answer", "type": "text"}
        ]
        # Stripped: the persisted reasoning ends in a space and a replay is a
        # document, not a stream.
        assert g2.of_kind("agent_thought")[0]["content"] == [{"text": "hmm.", "type": "text"}]
        assert g2.of_kind("agent_message")[0]["content"] == [{"text": "answer", "type": "text"}]

        # Three documents, three ids: a client keys its markdown view by
        # messageId, so sharing one would render "hmm. answer" as one bubble
        # and overwrite the prompt with the reply.
        replayed = (
            g2.of_kind("user_message")
            + g2.of_kind("agent_thought")
            + g2.of_kind("agent_message")
        )
        assert len({u["messageId"] for u in replayed}) == 3

        # The transcript the client just saw is the one the model reads — same
        # list object, so the two cannot disagree about what happened.
        g2.session_id = sid
        await g2.prompt(v2.schema.TextContentBlock(text="and again?"))
        await g2.wait_for_idle(2)
        sent = g2.llm.calls[0]["messages"]
        assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
        assert sent[1]["content"] == [{"type": "text", "text": "think then answer"}]
        assert sent[2]["content"] == "answer"
        assert sent[2]["reasoning_content"] == "hmm. "


async def test_a_replayed_tool_call_is_one_upsert_not_the_three_nobody_watched(
    tmp_path,
):
    """Live traffic walks a call through pending -> in_progress -> completed.

    A replay has no sequence to walk: v2 has no create/patch split to replay
    into, and re-staging a finished call through two states it was never
    observed in would be a lie about a history the client did not watch. One
    ``tool_call_update``, terminal status, done.

    The ids are minted, not recovered — the live id was ``<turn_id>/<llm id>``
    and the turn id was never persisted. ``replay/<seq>/<llm id>`` is unique
    within a replay, stable across two replays of the same history so a client
    can dedupe, and can never collide with a live one.

    No ``mcpServers`` on the resume: a replay reads persisted history and runs
    nothing, so it needs no tool supply.
    """
    config = make_config(tmp_path)
    scripts = [
        call(0, "call_1", "echo", '{"text": "hi"}') + [usage(10)],
        text("done") + [usage(20)],
    ]
    async with gate(tmp_path, scripts, config) as g1:
        await g1.new_session(mcp_servers=[stdio_server(tmp_path)])
        await g1.wait_for_idle(1)
        sid = g1.session_id
        await g1.prompt(v2.schema.TextContentBlock(text="echo hi"))
        await g1.wait_for_idle(2)
        # Live: three patches on one id.
        assert [u["status"] for u in g1.of_kind("tool_call_update")] == [
            "pending", "in_progress", "completed",
        ]

    async with gate(tmp_path, [], config) as g2:
        await g2.resume_session(sid, replay=True)
        await g2.wait_for_idle(1)

        assert g2.kinds() == [
            "available_commands_update",
            "user_message",
            "tool_call_update",      # the call, once
            "agent_message",         # "done"
            "state_update",
        ]
        [update] = g2.of_kind("tool_call_update")
        assert update["toolCallId"] == "replay/1/call_1"
        assert update["status"] == "completed"
        assert update["title"] == "echo"
        assert update["kind"] == "other"
        assert update["rawInput"] == {"text": "hi"}
        assert update["content"] == [
            {"content": {"text": "echo: hi", "type": "text"}, "type": "content"}
        ]
        # The assistant row that carried the call had no text of its own, so it
        # produces no empty message.
        assert [u["content"][0]["text"] for u in g2.of_kind("agent_message")] == ["done"]


async def test_a_replayed_execute_call_snapshots_its_terminal_first(tmp_path):
    """Execute replays as a terminal snapshot the call then REFERENCES.

    Order is the contract: the call's content is a ``TerminalToolCallContent``
    pointing at a terminal id, and a client that renders the reference before
    it has the terminal has nothing to render. Live traffic has the same
    constraint and satisfies it the same way.

    The snapshot carries the ANSI-STRIPPED text, because that is what survived.
    The raw PTY bytes went to the client live and nowhere else, and the exit
    code went with them — inventing ANSI for a snapshot would be worse than
    admitting the loss.

    Also here: a call with NO answer replays ``cancelled``. That is derivable
    from history and nearly always true — the turn was cancelled or the process
    died — where ``failed`` is not derivable at all, because ``result.isError``
    decided it live and only text survived. So every answered call replays
    ``completed`` and this one does not.
    """
    config = make_config(tmp_path)
    async with gate(tmp_path, [], config) as g1:
        await g1.new_session()
        await g1.wait_for_idle(1)
        sid = g1.session_id
        # A history no live turn produced: an execute call that finished, and
        # one that never got an answer. Written straight to the store, which is
        # where a replay reads from.
        session = g1.agent.sessions.sessions[g1.agent_id]
        await session.add_message(
            {"role": "user", "content": [{"type": "text", "text": "run it"}]}
        )
        await session.add_message({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_x",
                "type": "function",
                "function": {"name": "execute", "arguments": '{"code": "print(1)"}'},
            }],
        })
        await session.add_message(
            {"role": "tool", "tool_call_id": "call_x", "content": "1"}
        )
        await session.add_message({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_y",
                "type": "function",
                "function": {"name": "echo", "arguments": '{"text": "never"}'},
            }],
        })

    async with gate(tmp_path, [], config) as g2:
        await g2.resume_session(sid, replay=True)
        await g2.wait_for_idle(1)

        kinds = g2.kinds()
        assert kinds == [
            "available_commands_update",
            "user_message",
            "terminal_update",      # the snapshot...
            "tool_call_update",     # ...then the call that references it
            "tool_call_update",     # the unanswered one
            "state_update",
        ]
        assert kinds.index("terminal_update") < kinds.index("tool_call_update")

        terminal = g2.of_kind("terminal_update")[0]
        assert terminal["terminalId"] == "term_replay/1/call_x"
        assert terminal["command"] == "print(1)"
        assert terminal["cwd"] == str(tmp_path)
        assert base64.b64decode(terminal["output"]["data"]).decode() == "1"
        # The exit code did not survive, and is not invented.
        assert "exitStatus" not in terminal

        done, cancelled = g2.of_kind("tool_call_update")
        assert done["toolCallId"] == "replay/1/call_x"
        assert done["status"] == "completed"
        assert done["kind"] == "execute"
        assert done["rawInput"] == {"code": "print(1)"}
        assert done["content"] == [
            {"terminalId": terminal["terminalId"], "type": "terminal"}
        ]

        assert cancelled["toolCallId"] == "replay/2/call_y"
        assert cancelled["status"] == "cancelled"
        assert "content" not in cancelled, cancelled


def _server_procs(tmp_path: Path) -> int:
    """How many gate MCP subprocesses are alive right now.

    ``session/close`` has to free the session's resources, and the resource an
    MCP client holds is a subprocess. Whether the registry dropped a dict entry
    is bookkeeping; whether the process is gone is the thing actually released,
    and a leaked one per closed session is a machine that runs out of file
    descriptors by lunchtime.
    """
    marker = str(tmp_path / "gate_mcp_server.py")
    alive = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().decode(errors="replace")
        except OSError:
            continue
        alive += marker in cmdline
    return alive


async def test_close_frees_one_session_and_leaves_the_other_running(tmp_path):
    """Per-session lifetime, which is the thing v1 could not do.

    v1 had no ``session/close`` and one process-wide ``AsyncExitStack``, so an
    MCP client lived exactly as long as the agent process. Closing ONE session
    while another keeps running needs a stack per session, and needs the driver
    stopped before that stack is closed — the driver's turn may be mid-call
    through the client, and closing the client under a live call turns a clean
    cancel into an exception in the react loop.

    What does NOT follow is the idle a real ``session/cancel`` is answered with.
    Cancel is a notification, so that idle is its only confirmation channel;
    close is a request, and its response is the confirmation. A cancelled idle
    afterwards would be a state change on a session that no longer exists.
    """
    async with gate(tmp_path, [text("still here") + [usage(4)]]) as g:
        server = stdio_server(tmp_path)
        await g.new_session(mcp_servers=[server])
        doomed = g.session_id
        await g.new_session(mcp_servers=[server])
        keeper = g.session_id
        await g.wait_for_idle(2)
        assert _server_procs(tmp_path) == 2

        await g.close_session(doomed)
        assert g.last_result() == {}
        await g.wait_for(lambda: _server_procs(tmp_path) == 1, timeout=15)

        registry = g.agent.sessions
        for table in (registry.tools, registry.drivers, registry.mcp_clients,
                      registry.emitters, registry.loggers, registry.config_values,
                      registry.stream_states, registry._stacks):
            assert doomed not in table
        assert not [a for a in registry.sessions if wire_session_id(a) == doomed]
        # The other session's stack is its own, and is still open.
        assert keeper in registry._stacks and keeper in registry.tools

        # No idle for the closed session — only the park it was born with.
        assert g.kinds_for(doomed) == ["available_commands_update", "state_update"]

        # And the survivor still runs a turn.
        g.session_id = keeper
        await g.prompt(v2.schema.TextContentBlock(text="you there?"))
        await g.wait_for_idle(3)
        assert [c["content"]["text"] for c in g.of_kind("agent_message_chunk")] == [
            "still here"
        ]
        assert g.idles()[-1]["stopReason"] == "end_turn"
        # The wake bus is per PROCESS, not per session, so closing one leaves it
        # subscribed for the others — and _inbox_for already answers None for a
        # session with no driver, so a poke for the closed one is dropped where
        # it was always dropped.
        assert registry.watcher.running is True


async def test_close_tells_nothing_to_free_apart_from_no_such_session(tmp_path):
    """Two different "no", and only one of them is an error.

    A session this process never held may be live in another agent over the
    same store, or may simply never have been prompted. Either way the
    resources the request asked about are gone, which is what ``session/close``
    means. A session that does not exist ANYWHERE is a client bug, and answering
    it cleanly would leave that client believing it closed something.

    The existence check is one indexed lookup and not a ``resolve``: resolving
    hydrates every message of a session about to be thrown away, plus an
    ImageStore nobody will read, to answer a yes/no question.
    """
    config = make_config(tmp_path)
    async with gate(tmp_path, [], config) as g1:
        await g1.new_session()
        await g1.wait_for_idle(1)
        sid = g1.session_id

    async with gate(tmp_path, [], config) as g2:
        registry = g2.agent.sessions
        assert registry.known(sid) is True
        # Answered without hydrating anything — that is the whole reason
        # session_exists exists instead of resolve.
        assert registry.sessions == {}
        assert registry.known("no-such-session") is False

        await g2.close_session(sid)
        assert g2.last_result() == {}
        assert registry.sessions == {}

        with pytest.raises(RequestError) as excinfo:
            await g2.close_session("no-such-session")
        assert excinfo.value.code == -32602
        assert excinfo.value.data == {
            "sessionId": "no-such-session",
            "details": "unknown session",
        }


async def test_fork_gives_a_branch_its_own_addressable_wire_id(tmp_path):
    """A fork is a session, and its wire id is its agent id.

    That equality is what makes a fork addressable: a delegate's transcript can
    be read back with no handshake and no side channel, because the id the
    client was handed IS the row. It is also why ``session/list`` excludes forks
    — a fork is a branch of a listed session, not a session of its own.

    The rows are SHARED, not copied: the fork's context is the trunk's prefix up
    to an anchor message id, so a fork of a long session costs one agent row.
    """
    async with gate(tmp_path, [text("one") + [usage(2)]]) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        source = g.session_id
        await g.prompt(v2.schema.TextContentBlock(text="first"))
        await g.wait_for_idle(2)

        source_before = g.kinds_for(source)

        await g.fork_session(source)
        raw = g.last_result()
        fork_id = raw["sessionId"]
        assert fork_id != source
        assert fork_id == f"{source}-1-2"
        assert fork_id == g.agent_id_of(fork_id)
        # A fork is a session a client can drive, so it gets the options too.
        assert [o["configId"] for o in raw["configOptions"]] == ["model"]

        await g.wait_for_idle(3)
        roles = ["system", "user", "assistant"]
        assert [m["role"] for m in await g.history_of(fork_id)] == roles
        assert [m["role"] for m in await g.history_of(g.agent_id_of(source))] == roles

        # Live: it advertised its commands and parked, exactly like a new one.
        assert g.kinds_for(fork_id) == ["available_commands_update", "state_update"]
        # And the source is untouched: still provisioned, and not one byte more
        # on its own wire than it had before the fork.
        assert source in g.agent.sessions.tools
        assert g.kinds_for(source) == source_before


async def test_fork_anchors_ride_meta_and_a_bad_one_is_refused(tmp_path):
    """``_meta`` is the only channel the four anchors have.

    v2's ``ForkSessionRequest`` carries the environment and nothing else, so
    ``agentIdx``/``turnIdx``/``messageOffset``/``rlmDepth`` ride ``_meta``
    exactly as they rode v1's.

    A present-but-unparsable anchor is REFUSED rather than dropped. Silently
    forking at HEAD when the caller asked for three messages back produces a
    delegate that can see its own delegation — the infinity mirror the offset
    exists to prevent. Stepping back past everything is refused for the same
    reason: ``cut == 0`` used to fall through to ``records[-1]``, i.e. "keep
    nothing" quietly became "fork at HEAD".
    """
    scripts = [text("one") + [usage(2)], text("two") + [usage(2)]]
    async with gate(tmp_path, scripts) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        source = g.session_id
        await g.prompt(v2.schema.TextContentBlock(text="first"))
        await g.wait_for_idle(2)
        await g.prompt(v2.schema.TextContentBlock(text="second"))
        await g.wait_for_idle(3)
        assert [m["role"] for m in await g.history()] == [
            "system", "user", "assistant", "user", "assistant",
        ]

        await g.fork_session(source, messageOffset=2)
        back = g.last_result()["sessionId"]
        history = await g.history_of(back)
        assert [m["role"] for m in history] == ["system", "user", "assistant"]
        assert history[1]["content"] == [{"type": "text", "text": "first"}]
        assert (await g.history_of(g.agent_id_of(source)))[3]["content"] == [
            {"type": "text", "text": "second"}
        ]

        with pytest.raises(RequestError) as excinfo:
            await g.fork_session(source, messageOffset="three")
        assert excinfo.value.code == -32602
        assert excinfo.value.data == {
            "_meta": {"messageOffset": "three"},
            "details": "_meta.messageOffset must be an integer",
        }

        with pytest.raises(RequestError) as excinfo:
            await g.fork_session(source, messageOffset=99)
        assert excinfo.value.code == -32602
        assert "cannot fork" in excinfo.value.data["details"]
        assert "no history to fork" in excinfo.value.data["details"]


async def test_set_config_option_returns_the_whole_array_and_reaches_the_request(
    tmp_path,
):
    """One option changed; the FULL set comes back; the request changes too.

    The full array is the spec's wording — one change can affect other options —
    and the third clause is the one that makes it more than display: the option
    repoints ``session.model_identifier``, which is what the request actually
    sends. Doing only one of the two makes the picker show a model the request
    does not use.

    An unknown ``configId`` is refused rather than stored. The array this agent
    sent is the only place a client can have learned an id from, so one that is
    not in it is a bug worth naming; v1 stored it quietly and the client was
    left showing an option that had no effect on anything.
    """
    async with gate(tmp_path, [text("hi") + [usage(2)]]) as g:
        await g.new_session()
        await g.wait_for_idle(1)

        await g.set_config_option("model", "gate-provider:gate-model-id-2")
        options = g.last_result()["configOptions"]
        assert [o["configId"] for o in options] == ["model"]
        assert options[0]["currentValue"] == "gate-provider:gate-model-id-2"
        assert options[0]["category"] == "model"
        assert [o["value"] for o in options[0]["options"]] == [
            "gate-provider:gate-model-id",
            "gate-provider:gate-model-id-2",
        ]
        # No config_option_update: that notification is for changes the AGENT
        # makes on its own initiative, and this one was requested.
        assert "config_option_update" not in g.kinds()

        await g.prompt(v2.schema.TextContentBlock(text="hi"))
        await g.wait_for_idle(2)
        assert g.llm.calls[0]["model"] == "gate-model-id-2"

        with pytest.raises(RequestError) as excinfo:
            await g.set_config_option("temperature", "0.5")
        assert excinfo.value.code == -32602
        assert excinfo.value.data == {
            "sessionId": g.session_id,
            "configId": "temperature",
            "known": ["model"],
            "details": "unknown config option",
        }
        assert "temperature" not in g.agent.sessions.config_values[g.session_id]


async def test_a_model_chosen_before_the_session_is_provisioned_wins(tmp_path):
    """``set_config_option`` then ``prompt``, with no ``session/new`` between.

    v2 does not require a ``session/new`` in the same process before a prompt —
    the session being in the store is enough. So this sequence is reachable, and
    the second step provisions: ``prompt`` -> ``driver_for`` -> ``provision`` ->
    ``_register`` -> ``adopt_model_option``, which reads the saved model off the
    row. Unguarded, that adopt overwrites the choice the client just made, and
    the request goes to the wrong model with the picker still showing the right
    one.

    The second agent runs with ``-m gate-model``, which is what makes the guard
    load-bearing rather than merely tidy. Without an override the adopt resolves
    ``session.model_identifier`` — which ``apply_model_option`` already repointed
    — back to the same value and writes it again, so the clobber is invisible.
    A ``-m`` override does not consult the session at all: it applies itself.
    """
    config = make_config(tmp_path)
    async with gate(tmp_path, [text("first") + [usage(2)]], config) as g1:
        await g1.new_session()
        await g1.wait_for_idle(1)
        sid = g1.session_id
        await g1.prompt(v2.schema.TextContentBlock(text="go"))
        await g1.wait_for_idle(2)
        assert g1.llm.calls[0]["model"] == "gate-model-id"

    async with gate(tmp_path, [text("second") + [usage(2)]], config, model="gate-model") as g2:
        await g2.set_config_option(
            "model", "gate-provider:gate-model-id-2", session_id=sid
        )
        # Resolved by the handler, but NOT provisioned — that is the window the
        # guard has to cover.
        assert sid not in g2.agent.sessions.tools

        g2.session_id = sid
        await g2.prompt(v2.schema.TextContentBlock(text="go on"))
        await g2.wait_for_idle(1)
        assert g2.llm.calls[0]["model"] == "gate-model-id-2"
        assert g2.agent.sessions.config_values[sid]["model"] == (
            "gate-provider:gate-model-id-2"
        )


def model_in_the_store(g: Gate, agent_id: str) -> str:
    """The ``model_identifier`` the store holds for one generation.

    Read off the row and not off the session object, because the row is the
    only thing a restart reads: ``AgentSession.load`` seeds the session from
    it and nothing else survives a process.
    """
    with Session(g.agent.sessions.engine) as db:
        return db.query(Agent).filter_by(agent_id=agent_id).first().model_identifier


async def test_a_model_chosen_over_the_wire_survives_a_restart(tmp_path):
    """``set_config_option`` writes the row, so the next process reads it back.

    ``model_identifier`` used to be written once, at ``create_agent``, and
    nothing ever updated it — ``apply_model_option`` repointed the in-memory
    session and stopped there. So a model a client picked lived exactly as
    long as the process it was picked in, and a restart resumed the session on
    the model it was BORN with. That is the failure ``adopt_model_option``'s
    own docstring argues against ("a client that showed one model before a
    restart shows a different one after it"), from the other end: the adopt
    reads the row faithfully, and the row was never told.

    The second gate IS the restart — same config, same database, no ``-m``. It
    resolves the session, which loads the row, and the request must go to the
    model the first process was told to use. The first gate scripts NO model
    call, so a turn that ran by accident would fail rather than pass quietly.
    """
    config = make_config(tmp_path)
    async with gate(tmp_path, [], config) as g1:
        await g1.new_session()
        await g1.wait_for_idle(1)
        sid = g1.session_id
        assert model_in_the_store(g1, f"{sid}-1-1") == "gate-model-id"

        await g1.set_config_option("model", "gate-provider:gate-model-id-2")
        assert model_in_the_store(g1, f"{sid}-1-1") == "gate-model-id-2"

    async with gate(tmp_path, [text("second") + [usage(2)]], config) as g2:
        g2.session_id = sid
        await g2.prompt(v2.schema.TextContentBlock(text="go on"))
        await g2.wait_for_idle(1)
        assert g2.llm.calls[0]["model"] == "gate-model-id-2"
        # The picker agrees with the request, which is the other half of what
        # adopt_model_option is for.
        assert g2.agent.sessions.config_values[sid]["model"] == (
            "gate-provider:gate-model-id-2"
        )


async def test_a_model_imposed_by_the_command_line_is_not_written_to_the_row(
    tmp_path,
):
    """``-m`` means "use THIS model for this run", not "this session is that".

    ``adopt_model_option`` applies an override through the same
    ``apply_model_option`` the wire handler uses, so ``persist`` is the only
    thing standing between a launch flag and a permanent change to the
    session. Without it, running the agent once with ``-m`` would pin the
    session to that model for every process that came after — including the
    third gate below, which is started without the flag and is the one a user
    would notice.
    """
    config = make_config(tmp_path)
    async with gate(tmp_path, [text("first") + [usage(2)]], config) as g1:
        await g1.new_session()
        await g1.wait_for_idle(1)
        sid = g1.session_id
        await g1.prompt(v2.schema.TextContentBlock(text="go"))
        await g1.wait_for_idle(2)
        assert g1.llm.calls[0]["model"] == "gate-model-id"

    async with gate(
        tmp_path, [text("second") + [usage(2)]], config, model="gate-model-2"
    ) as g2:
        g2.session_id = sid
        await g2.prompt(v2.schema.TextContentBlock(text="go on"))
        await g2.wait_for_idle(1)
        # The override reached the request...
        assert g2.llm.calls[0]["model"] == "gate-model-id-2"
        # ...and stopped there.
        assert model_in_the_store(g2, f"{sid}-1-1") == "gate-model-id"

    async with gate(tmp_path, [text("third") + [usage(2)]], config) as g3:
        g3.session_id = sid
        await g3.prompt(v2.schema.TextContentBlock(text="and again"))
        await g3.wait_for_idle(1)
        assert g3.llm.calls[0]["model"] == "gate-model-id"


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------

#: Small enough that one scripted usage chunk crosses it.
CEILING = 100


async def test_a_compaction_narrates_itself_in_the_order_the_spec_requires(tmp_path):
    """in_progress -> chunks -> completed, one id, and NO summary at the end.

    The order is not cosmetic. The spec says an agent sends summary chunks
    "only after an ``in_progress`` update and before the terminal update for
    the same ID", so a client is entitled to drop a chunk that arrives outside
    that window — a compaction that emitted ``completed`` first would look
    like a pass that produced nothing.

    The absent ``summary`` is the other half of the contract. ``summary`` is a
    complete REPLACEMENT of what the chunks accumulated, and crow's handoff is
    the model's prose plus a flattened dump of the last twenty messages.
    Sending it would trade the readable summary the client just watched arrive
    for a transcript. Absent, not empty: ``summary: []`` CLEARS.
    """
    config = make_config(tmp_path)
    config.MAX_COMPACT_TOKENS = CEILING
    async with gate(
        tmp_path,
        [
            text("answer") + [usage(5000)],      # the turn that crosses
            text("SUMMARY ", "of the big job"),  # compact()'s summary pass
            text("done"),                        # the restarted turn
        ],
        config,
    ) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        sid = g.session_id
        await g.prompt(v2.schema.TextContentBlock(text="do the big job"))
        await g.wait_for_idle(2)

        assert [k for k in g.kinds() if k.startswith("compaction")] == [
            "compaction_update",
            "compaction_summary_chunk",
            "compaction_summary_chunk",
            "compaction_update",
        ]

        updates = g.of_kind("compaction_update")
        assert [u["status"] for u in updates] == ["in_progress", "completed"]
        chunks = g.of_kind("compaction_summary_chunk")
        assert [c["content"]["text"] for c in chunks] == ["SUMMARY ", "of the big job"]
        ids = {u["compactionId"] for u in updates} | {c["compactionId"] for c in chunks}
        assert len(ids) == 1, ids
        assert "summary" not in updates[-1]
        assert "error" not in updates[-1]

        # The successor is a real row and the driver is holding it, so the
        # NEXT prompt resolves to generation 2 rather than re-summarizing 1.
        assert g.agent.sessions.drivers[sid].session.agent_id == f"{sid}-2-1"

        # The restarted turn ran on the successor and nothing else: born
        # [system, handoff]. The old tail rode along as flattened text inside
        # the handoff, not as twenty real messages.
        third = g.llm.calls[2]["messages"]
        assert [m["role"] for m in third] == ["system", "user"]
        assert "SUMMARY of the big job" in third[1]["content"]
        assert "Last messages:" in third[1]["content"]

        successor = await g.history_of(f"{sid}-2-1")
        assert successor[0]["role"] == "system"
        assert "SUMMARY of the big job" in successor[1]["content"]


async def test_a_compactor_that_never_streams_gets_its_summary_in_the_terminal_update(
    tmp_path,
):
    """The other branch: no chunks, so ``completed`` carries the replacement.

    A custom strategy is under no obligation to ask the model anything — the
    interesting ones read files, or compute the handoff from the transcript
    directly. Such a pass streams nothing, and a terminal update with no
    summary would leave the client retaining NOTHING for a compaction it was
    told completed. So the handoff goes in whole.

    Also the proof that ``on_summary_chunk`` reaches the strategy at all: the
    ctx a compactor is handed carries the callback whether or not it is used.
    """
    config = make_config(tmp_path)
    config.MAX_COMPACT_TOKENS = CEILING
    seen = {}

    async def quiet_compactor(ctx):
        seen["ctx"] = ctx
        prompt = ctx.system_prompt(ctx)
        return CompactResponse(
            system_template=prompt.template,
            system_args=prompt.template_args,
            prompt="PROJECT HANDOFF, no model asked",
        )

    async with gate(
        tmp_path,
        [text("answer") + [usage(5000)], text("done")],
        config,
        compactor=quiet_compactor,
    ) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        await g.prompt(v2.schema.TextContentBlock(text="do the big job"))
        await g.wait_for_idle(2)

        # Two turn calls, ZERO summary calls: the strategy replaced the pass.
        assert len(g.llm.calls) == 2
        assert callable(seen["ctx"].on_summary_chunk)

        assert "compaction_summary_chunk" not in g.kinds()
        updates = g.of_kind("compaction_update")
        assert [u["status"] for u in updates] == ["in_progress", "completed"]
        assert updates[-1]["summary"] == [
            {"text": "PROJECT HANDOFF, no model asked", "type": "text"}
        ]


async def test_a_compaction_that_raises_reports_failed_and_not_completed(tmp_path):
    """``failed`` carries the error, and the turn ends rather than spinning.

    ``error`` is only valid with ``failed`` — so is the absence of a summary.
    The re-raise matters as much as the update: swallowing it would leave the
    react loop holding the generation it just failed to replace, over the
    ceiling, compacting again on the next turn forever.
    """
    config = make_config(tmp_path)
    config.MAX_COMPACT_TOKENS = CEILING

    async def broken_compactor(ctx):
        raise RuntimeError("no summary for you")

    async with gate(
        tmp_path, [text("answer") + [usage(5000)]], config, compactor=broken_compactor
    ) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        sid = g.session_id
        await g.prompt(v2.schema.TextContentBlock(text="do the big job"))
        await g.wait_for_idle(2)

        updates = g.of_kind("compaction_update")
        assert [u["status"] for u in updates] == ["in_progress", "failed"]
        assert updates[-1]["error"] == "no summary for you"
        assert "summary" not in updates[-1]
        assert "compaction_summary_chunk" not in g.kinds()

        # One model call only: the turn died instead of restarting.
        assert len(g.llm.calls) == 1
        assert g.idles()[1]["stopReason"] == "error"
        # The driver reports a dead turn as a whole agent_message, not a
        # chunk: there is nothing to stream, and the text is its own.
        assert [m["content"][0]["text"] for m in g.of_kind("agent_message")] == [
            "agent error: no summary for you"
        ]
        # Nothing was minted, so the session is still generation 1.
        assert g.agent.sessions.drivers[sid].session.agent_id == f"{sid}-1-1"


async def test_a_cancel_mid_compaction_reports_cancelled(tmp_path):
    """A summary pass is the slowest thing crow does; the user can stop it.

    ``cancelled`` needs its own branch because :class:`asyncio.CancelledError`
    is a :class:`BaseException` — ``except Exception`` sails straight past it,
    and the client's compaction entity would sit ``in_progress`` forever with
    no terminal update coming. The session survives: cancel is per-turn in v2,
    and a compaction that never minted a row left nothing to roll back.
    """
    config = make_config(tmp_path)
    config.MAX_COMPACT_TOKENS = CEILING
    async with gate(
        tmp_path, [text("answer") + [usage(5000)], [HANG]], config
    ) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        sid = g.session_id
        await g.prompt(v2.schema.TextContentBlock(text="do the big job"))
        await g.wait_for(lambda: g.of_kind("compaction_update"))

        await g.cancel()
        await g.wait_for_idle(2)

        updates = g.of_kind("compaction_update")
        assert [u["status"] for u in updates] == ["in_progress", "cancelled"]
        assert "summary" not in updates[-1]
        assert "error" not in updates[-1]
        assert "compaction_summary_chunk" not in g.kinds()
        assert g.idles()[1]["stopReason"] == "cancelled"
        assert g.agent.sessions.drivers[sid].session.agent_id == f"{sid}-1-1"
        assert g.agent.sessions.drivers[sid].running is False


async def test_a_successor_born_over_the_ceiling_is_not_recompacted(tmp_path):
    """The guard, on the wire: one compaction, not a generational loop.

    The restarted turn is scripted to come back over the ceiling too. It must
    NOT compact again — a successor is born ``[system, handoff]`` and nothing
    has been added since, so re-summarizing the summary cannot help and models
    reliably write a bigger one. Measured live in v1: 11.9k -> 12.8k -> 19.5k
    -> 26.1k prompt tokens, one ~2-minute call per generation, forever.
    """
    config = make_config(tmp_path)
    config.MAX_COMPACT_TOKENS = CEILING
    async with gate(
        tmp_path,
        [
            text("answer") + [usage(5000)],
            text("SUMMARY"),
            text("done") + [usage(9999)],  # the successor is over too
        ],
        config,
    ) as g:
        await g.new_session()
        await g.wait_for_idle(1)
        await g.prompt(v2.schema.TextContentBlock(text="do the big job"))
        await g.wait_for_idle(2)

        assert len(g.llm.calls) == 3
        assert [u["status"] for u in g.of_kind("compaction_update")] == [
            "in_progress",
            "completed",
        ]
        assert g.idles()[1]["stopReason"] == "end_turn"
        assert g.of_kind("agent_message_chunk")[-1]["content"]["text"] == "done"


async def test_a_compacted_session_keeps_the_name_its_first_message_gave_it(tmp_path):
    """Compaction does not rename a session: the title is the ROOT's first message.

    A successor is born ``[system, handoff]``, so a driver that titled from the
    agent it happens to be holding would rename the session to the first fifty
    characters of a summary — and rename it again at every generation, which is
    the failure ``_session_title`` reads the root to avoid. The announcement
    therefore DERIVES the root's id rather than taking ``session.agent_id``.

    Across two processes because that is the only way a driver STARTS on a
    successor: inside the process that compacted, the title was announced on
    the first prompt, long before the summary existed.
    """
    config = make_config(tmp_path)
    config.MAX_COMPACT_TOKENS = CEILING
    scripts = [
        text("answer") + [usage(5000)],      # the turn that crosses
        text("SUMMARY ", "of the big job"),  # compact()'s summary pass
        text("done"),                        # the restarted turn
    ]
    async with gate(tmp_path, scripts, config) as g1:
        await g1.new_session()
        await g1.wait_for_idle(1)
        sid = g1.session_id
        await g1.prompt(v2.schema.TextContentBlock(text="do the big job"))
        await g1.wait_for_idle(2)
        assert g1.of_kind("session_info_update") == [
            {"title": "do the big job", "sessionUpdate": "session_info_update"}
        ]
        assert g1.agent.sessions.drivers[sid].session.agent_id == f"{sid}-2-1"

    async with gate(tmp_path, [text("carried on") + [usage(2)]], config) as g2:
        await g2.resume_session(sid)
        await g2.wait_for_idle(1)
        # The resumed driver holds the successor, whose first message is the
        # handoff — and the name it announces is still the original.
        assert g2.agent.sessions.drivers[sid].session.agent_id == f"{sid}-2-1"
        g2.session_id = sid
        await g2.prompt(v2.schema.TextContentBlock(text="carry on"))
        await g2.wait_for_idle(2)
        assert g2.of_kind("session_info_update") == [
            {"title": "do the big job", "sessionUpdate": "session_info_update"}
        ]

        await g2.list_sessions()
        [listed] = [i for i in g2.last_result()["sessions"] if i["sessionId"] == sid]
        assert listed["title"] == "do the big job"

