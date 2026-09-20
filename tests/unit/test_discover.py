"""Protocol discovery: the agent is asked, the config is not trusted.

Every test here spawns a real child and speaks real newline-delimited
JSON-RPC over real pipes. The child is not a mock of the code under test —
the code under test is the client half of a handshake, and the child is the
other end of it. What only a subprocess can show: that the union request is
what actually arrives on the wire, that the answer selects the stack, and
that a child which dies produces an error carrying its own last words
instead of a hang with no error on either side.
"""

from __future__ import annotations

import asyncio
import collections
import json
import sys
from pathlib import Path

import pytest
from acp.exceptions import RequestError
from acp.experimental import v2

from crow_cli import __version__
from crow_cli.agents import V1, V2, AgentServer
from crow_cli.discover import (
    BY_VERSION,
    LATEST,
    ProtocolError,
    adopt_v2,
    agent_connection,
    handshake_params,
)

#: One child, every behaviour selected by its env: what to answer with, what
#: to say first, what to say on stderr, and whether to die instead.
FAKE_AGENT = r"""
import json
import os
import sys

reply = os.environ.get("FAKE_REPLY", "")
banner = os.environ.get("FAKE_BANNER", "")
noise = os.environ.get("FAKE_STDERR", "")
code = int(os.environ.get("FAKE_EXIT", "0"))
witness = os.environ.get("FAKE_WITNESS")

if noise:
    sys.stderr.write(noise)
    sys.stderr.flush()
if banner:
    sys.stdout.write(banner + "\n")
    sys.stdout.flush()

request = sys.stdin.readline()
# Only a real request is witnessed. At EOF readline returns "" — which is
# what a child sees when the client closes stdin without ever asking it
# anything, and the difference is the whole point of the declared-protocol
# tests.
if witness and request.strip():
    with open(witness, "w", encoding="utf-8") as handle:
        handle.write(request)

if reply:
    message = json.loads(reply)
    message["jsonrpc"] = "2.0"
    message["id"] = 0
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()

if code:
    raise SystemExit(code)

# Stay alive: a real agent does, and the client's teardown has to shut one
# down rather than race a child that already left.
sys.stdin.read()
"""


def result(version: int) -> str:
    """An ``initialize`` reply that selects ``version``.

    A v2 response is required to carry ``info``, so the v2-shaped answer does;
    a v1 one has no such field and a v1 client would ignore it anyway. Faking a
    response the schema forbids would make the adoption tests pass against an
    agent that cannot exist.
    """
    payload: dict = {"protocolVersion": version}
    if version >= LATEST:
        payload["info"] = {"name": "fake-agent", "version": "0.0.1"}
        payload["capabilities"] = {}
    return json.dumps({"result": payload})


@pytest.fixture
def fake(tmp_path: Path):
    """Builds an :class:`AgentServer` for the scripted child above."""
    script = tmp_path / "fake_agent.py"
    script.write_text(FAKE_AGENT)

    def build(protocol: str | None = None, **env) -> AgentServer:
        return AgentServer(
            name="fake",
            command=sys.executable,
            args=[str(script)],
            env={key: str(value) for key, value in env.items()},
            protocol=protocol,
        )

    return build


# -- the request -------------------------------------------------------------


def test_the_union_request_carries_both_halves():
    """One ``initialize`` serves both versions because each reads its own two
    fields and ignores the rest. Sending less than the union is what makes a
    v2 agent answer ``-32602 Field required: info``."""
    params = handshake_params()

    assert params["protocolVersion"] == LATEST == 2
    assert params["info"]["name"] == "crow-client"
    assert params["info"]["title"] == "Crow Client"
    assert params["info"]["version"] == __version__
    # v2's ClientCapabilities has no terminal and no fs to decline: the agent
    # owns execution, so the choice does not exist.
    assert params["capabilities"] == {}
    assert params["clientInfo"] == params["info"]
    # v1's terminal=False is load-bearing, not decoration: it is what makes
    # the agent's terminal tool fall through to its own MCP supply instead of
    # a client-side PTY.
    assert params["clientCapabilities"]["terminal"] is False


def test_the_version_table_is_exactly_what_this_client_speaks():
    assert BY_VERSION == {1: V1, 2: V2}


# -- the answer --------------------------------------------------------------


async def test_an_agent_that_answers_one_selects_the_v1_stack(fake, tmp_path):
    witness = tmp_path / "witness.json"
    server = fake(FAKE_REPLY=result(1), FAKE_WITNESS=witness)

    async with agent_connection(server, str(tmp_path)) as conn:
        assert conn.protocol == V1
        assert conn.initialized is True
        assert conn.response == {"protocolVersion": 1}

    asked = json.loads(witness.read_text())
    assert asked["method"] == "initialize"
    assert asked["id"] == 0
    # The union, on the wire, byte for byte — not a shape that merely parses.
    assert asked["params"] == handshake_params()


async def test_an_agent_that_answers_two_selects_the_v2_stack(fake, tmp_path):
    server = fake(FAKE_REPLY=result(2))

    async with agent_connection(server, str(tmp_path)) as conn:
        assert conn.protocol == V2
        assert conn.initialized is True


async def test_a_version_nobody_speaks_is_refused_by_name(fake, tmp_path):
    """The spec leaves this to the client: it SHOULD close the connection and
    inform the user. Silently driving a version we cannot parse is how a hang
    becomes a mystery."""
    server = fake(FAKE_REPLY=result(99))

    with pytest.raises(ProtocolError) as exc:
        async with agent_connection(server, str(tmp_path)):
            pass

    assert "99" in str(exc.value)
    assert "1, 2" in str(exc.value)


async def test_an_error_reply_is_reported_with_its_code(fake, tmp_path):
    server = fake(
        FAKE_REPLY=json.dumps({"error": {"code": -32602, "message": "Invalid params"}})
    )

    with pytest.raises(ProtocolError) as exc:
        async with agent_connection(server, str(tmp_path)):
            pass

    assert "Invalid params" in str(exc.value)
    assert "-32602" in str(exc.value)


async def test_a_banner_on_stdout_does_not_defeat_the_probe(fake, tmp_path):
    """An agent that logs to stdout is rude but survivable. Refusing to look
    past a non-JSON line turns a cosmetic habit into a hang."""
    server = fake(FAKE_BANNER="fake-agent 1.0 starting", FAKE_REPLY=result(2))

    async with agent_connection(server, str(tmp_path)) as conn:
        assert conn.protocol == V2


# -- the failures that used to be hangs --------------------------------------


async def test_a_child_that_dies_reports_its_own_last_words(fake, tmp_path):
    """The stderr tail is the only evidence that will ever exist: an agent
    that fails at startup says why there and nowhere the client can see."""
    server = fake(FAKE_STDERR="boom: no LLM provider configured\n", FAKE_EXIT=3)

    with pytest.raises(ProtocolError) as exc:
        async with agent_connection(server, str(tmp_path)):
            pass

    message = str(exc.value)
    assert "boom: no LLM provider configured" in message
    assert "child exited 3" in message


async def test_a_child_that_never_answers_times_out(fake, tmp_path):
    server = fake()

    with pytest.raises(ProtocolError) as exc:
        async with agent_connection(server, str(tmp_path), timeout=1.0):
            pass

    assert "no answer within 1s" in str(exc.value)


async def test_the_stderr_drain_is_one_and_belongs_to_the_probe(fake, tmp_path):
    """Two drainers on one ``StreamReader`` would split the child's lines
    between them, so the probe owns exactly one and hands it over by
    reference for the adopting stack to keep filling."""
    server = fake(FAKE_STDERR="line one\nline two\n", FAKE_REPLY=result(2))

    async with agent_connection(server, str(tmp_path)) as conn:
        assert isinstance(conn.stderr, collections.deque)
        assert conn.drainer is not None and not conn.drainer.done()
        for _ in range(100):
            if len(conn.stderr) >= 2:
                break
            await asyncio.sleep(0.05)
        assert conn.stderr_tail() == "line one\nline two"


# -- handing the negotiated child to the v2 stack -----------------------------


async def test_adopting_a_v2_connection_opens_its_local_gate(fake, tmp_path):
    """v2's ``ClientSideConnection`` gates every method on a LOCAL
    ``InitializationState`` that only its own ``initialize()`` moves, and a
    second ``initialize`` on the wire is refused by the agent. So a correctly
    negotiated child still answers its first ``session/new`` with "connection
    must be initialized" unless adoption opens that gate too.

    This is also the pin on the private attribute: an SDK that renames
    ``_state`` fails here instead of failing somebody's session.
    """
    server = fake(FAKE_REPLY=result(2))

    async with agent_connection(server, str(tmp_path)) as conn:
        assert conn.protocol == V2 and conn.initialized is True
        wire = v2.ClientSideConnection(object(), conn.writer, conn.reader)

        assert wire._state.phase == "uninitialized"
        with pytest.raises(RequestError):
            await wire._state.require("session/new")

        adopt_v2(wire, conn.response)

        assert wire._state.phase == "initialized"
        await wire._state.require("session/new")
        await wire.close()


# -- an entry that already knows ---------------------------------------------


async def test_a_declared_protocol_is_honored_without_asking(fake, tmp_path):
    """The override exists to skip the round trip, so the child must see
    nothing: the stack it is handed to does its own handshake, and a second
    ``initialize`` on one connection is one v2 explicitly refuses."""
    witness = tmp_path / "witness.json"
    server = fake(V1, FAKE_WITNESS=witness)

    async with agent_connection(server, str(tmp_path)) as conn:
        assert conn.protocol == V1
        assert conn.initialized is False
        assert conn.response is None

    assert not witness.exists(), "a declared entry must not be probed"


async def test_a_declared_v2_entry_is_not_probed_either(fake, tmp_path):
    witness = tmp_path / "witness.json"
    server = fake(V2, FAKE_WITNESS=witness)

    async with agent_connection(server, str(tmp_path)) as conn:
        assert conn.protocol == V2
        assert conn.initialized is False

    assert not witness.exists()
