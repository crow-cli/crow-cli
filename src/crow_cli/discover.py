"""Which protocol does this agent speak? Ask it.

``initialize`` is the negotiation: the client sends the latest version it
supports and the agent replies with the version it chose — the same one if it
can speak it, otherwise the latest it does. That answer decides which client
stack drives the connection, so an ``agent_servers`` entry never has to declare
a protocol. An entry is a command, and the command says what it speaks the
first time you talk to it. A config field asserting the same thing is a second
source of truth whose only talent is disagreeing with the first: it is how an
agent that works gets launched by a client speaking the other version, which
hangs with no error on either side.

The probe IS the connection, not a prelude to one. It spawns the child once and
hands the live, already-handshaked streams to whichever stack the version
selects, so discovery costs one round trip rather than a second process.

One request serves both versions because ``initialize`` is the one method whose
params they still share a shape for: v1 reads ``clientInfo`` and
``clientCapabilities`` and ignores the rest, v2 requires ``info`` and ignores
the rest. Sending the union means each agent sees exactly the fields its own
client would have sent — v1's ``terminal: false`` included, which is what makes
the agent's terminal tool fall through to its own MCP supply rather than a
client-side PTY — and only ``protocolVersion`` has to be read back.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from acp import PROTOCOL_VERSION as V1_VERSION
from acp.experimental import v2
from acp.schema import ClientCapabilities, Implementation
from acp.stdio import spawn_stdio_transport

from crow_cli import __version__
from crow_cli.agents import V1, V2, AgentServer

logger = logging.getLogger("crow-discover")

#: How long the handshake gets. This is a spawn budget, not a network one:
#: ``uv run`` cold-starts an interpreter and imports crow before the agent can
#: answer, and a cold cache makes that slow rather than broken.
PROBE_TIMEOUT = 120.0

#: How much of the child's stderr to keep. The drain exists so the pipe cannot
#: fill and deadlock the child; the tail is what an error about a dead child
#: needs, and it is the only evidence that will ever exist.
STDERR_LINES = 200

#: The latest version this client speaks, which the spec says the request MUST
#: carry. An agent that speaks it answers with it; one that does not answers
#: with the latest it does.
LATEST = v2.PROTOCOL_VERSION

#: An answered version, and the client stack it selects.
BY_VERSION = {V1_VERSION: V1, LATEST: V2}

CLIENT_NAME = "crow-client"
CLIENT_TITLE = "Crow Client"

#: The handshake's JSON-RPC id. Nothing else is in flight when it is sent, so
#: it is the only reply that can arrive. Reusing 0 is safe even though the
#: SDK's own connection also starts counting at 0: JSON-RPC ids only have to
#: distinguish requests that are outstanding together, and this one is
#: answered before the stack sends anything.
_REQUEST_ID = 0


class ProtocolError(Exception):
    """The agent never answered the handshake, or answered one we cannot speak.

    The message carries the child's stderr tail: an agent that fails at startup
    says why there and nowhere else.
    """


def handshake_params() -> dict[str, Any]:
    """One ``initialize`` params object that both protocol versions accept.

    Each half is what that version's own client sends, so neither agent sees a
    capability it would not have been offered anyway.
    """
    info = Implementation(
        name=CLIENT_NAME, title=CLIENT_TITLE, version=__version__
    ).model_dump(mode="json", by_alias=True, exclude_none=True)
    return {
        "protocolVersion": LATEST,
        # v2 reads these two and ignores the rest.
        "info": info,
        "capabilities": {},
        # v1 reads these two and ignores the rest. terminal=False is what
        # connect_client sends and is load-bearing, not decoration.
        "clientInfo": info,
        "clientCapabilities": ClientCapabilities(terminal=False).model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
    }


@dataclass(frozen=True)
class Connection:
    """A spawned agent, the protocol it speaks, and whether it handshook.

    ``initialized`` is False when the entry declared its protocol and the stack
    must do its own handshake exactly as it always has; True when this module
    already did it and the stack would be doing it twice.
    """

    protocol: str
    reader: Any
    writer: Any
    proc: Any
    initialized: bool
    response: Optional[dict[str, Any]] = None
    stderr: collections.deque = field(
        default_factory=lambda: collections.deque(maxlen=STDERR_LINES)
    )
    drainer: Optional[asyncio.Task] = None

    def stderr_tail(self) -> str:
        """What the child said on stderr, for the error that reports it died."""
        return "".join(self.stderr).strip()


def adopt_v2(conn: Any, response: dict[str, Any]) -> None:
    """Tell a v2 client connection that the handshake already happened.

    ``ClientSideConnection.initialize`` does two things at once: it moves the
    connection's local ``InitializationState`` to ``initialized``, and it sends
    the request. Every later method calls ``state.require(method)`` first, so a
    connection this module already negotiated is refused *locally* — and
    sending ``initialize`` again is refused by the agent, which allows exactly
    one per connection. The SDK exposes no way to adopt a negotiated
    connection, so this drives the same two state transitions ``initialize``
    does, minus the wire. ``tests/unit/test_discover.py`` pins it, so an SDK
    that renames the private state fails a test instead of failing a session.
    """
    parsed = v2.schema.InitializeResponse.model_validate(response)
    request = v2.schema.InitializeRequest(
        protocol_version=v2.PROTOCOL_VERSION, info=parsed.info
    )
    conn._state.begin(request)
    conn._state.complete(parsed)


@asynccontextmanager
async def agent_connection(
    server: AgentServer,
    cwd: str,
    *,
    timeout: float = PROBE_TIMEOUT,
) -> AsyncIterator[Connection]:
    """Spawn ``server`` once and yield it, handshaked if we had to ask.

    A declared protocol is honored without asking — crow's own entries know
    what they are — and the child is yielded un-initialized so the chosen stack
    handshakes itself. An undeclared one is asked, and the child is yielded
    already handshaked.

    ``env`` is an overlay on this process's environment, never a substitution:
    an entry's env is its extra variables, and dropping PATH or HOME would
    break the child's own subprocesses.

    Raises:
        ProtocolError: the child died, stayed silent, or speaks a version this
            client does not.
    """
    async with spawn_stdio_transport(
        *server.argv,
        env={**os.environ, **server.env},
        cwd=cwd,
    ) as (reader, writer, proc):
        stderr: collections.deque = collections.deque(maxlen=STDERR_LINES)
        drainer = asyncio.create_task(
            _drain_stderr(proc, stderr), name="crow-discover-stderr"
        )
        try:
            if server.protocol is None:
                response = await _handshake(
                    writer, reader, proc, drainer, stderr, timeout
                )
                version = response.get("protocolVersion")
                protocol = BY_VERSION.get(version)
                if protocol is None:
                    raise ProtocolError(
                        f"{server.title} answered initialize with protocol "
                        f"version {version!r}; this client speaks "
                        f"{', '.join(str(v) for v in sorted(BY_VERSION))}."
                    )
                logger.info("initialize: %s speaks protocol %s", server.title, version)
                yield Connection(
                    protocol, reader, writer, proc, True, response, stderr, drainer
                )
            else:
                yield Connection(
                    server.protocol, reader, writer, proc, False, None, stderr, drainer
                )
        finally:
            drainer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await drainer


async def _drain_stderr(proc: Any, sink: collections.deque) -> None:
    """Keep the child's stderr pipe empty.

    ``spawn_stdio_transport`` gives the child a PIPE, and a child that logs
    more than the buffer holds blocks on the write and hangs with no error on
    either side.
    """
    stream = getattr(proc, "stderr", None)
    if stream is None:
        return
    while True:
        line = await stream.readline()
        if not line:
            return
        sink.append(line.decode(errors="replace"))


async def _handshake(
    writer: Any,
    reader: Any,
    proc: Any,
    drainer: asyncio.Task,
    stderr: collections.deque,
    timeout: float,
) -> dict[str, Any]:
    """Send the union initialize and return the agent's result object."""
    request = {
        "jsonrpc": "2.0",
        "id": _REQUEST_ID,
        "method": "initialize",
        "params": handshake_params(),
    }
    try:
        payload = json.dumps(request, separators=(",", ":")) + "\n"
        writer.write(payload.encode())
        await writer.drain()
    except OSError:
        # The child was already gone — a bad config or a missing module kills
        # an agent before it reads anything, and that is the commonest failure
        # there is. It gets the same error as one that dies after reading,
        # with its stderr on it, not a BrokenPipeError nobody can act on.
        raise ProtocolError(
            await _silent(proc, drainer, stderr, "died before it could be asked")
        ) from None

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        left = deadline - loop.time()
        if left <= 0:
            raise ProtocolError(
                await _silent(proc, drainer, stderr, f"no answer within {timeout:g}s")
            )
        try:
            line = await asyncio.wait_for(reader.readline(), left)
        except asyncio.TimeoutError:
            raise ProtocolError(
                await _silent(proc, drainer, stderr, f"no answer within {timeout:g}s")
            ) from None
        if not line:
            raise ProtocolError(
                await _silent(proc, drainer, stderr, "closed stdout without answering")
            )
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            # Not ours. An agent that banners on stdout is rude but survivable,
            # and refusing to look past it turns a cosmetic habit into a hang.
            continue
        if not isinstance(message, dict) or message.get("id") != _REQUEST_ID:
            continue
        if message.get("error") is not None:
            err = message["error"] or {}
            raise ProtocolError(
                f"initialize failed: {err.get('message')} "
                f"(code {err.get('code')})"
            )
        result = message.get("result")
        if not isinstance(result, dict):
            raise ProtocolError(f"initialize returned {result!r}, not an object")
        return result


async def _silent(
    proc: Any, drainer: asyncio.Task, stderr: collections.deque, what: str
) -> str:
    """The error for a child that did not answer, with its last words on it."""
    if not drainer.done():
        # The child is gone or silent; let the drain reach EOF so the tail is
        # whole rather than cut mid-line.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(drainer), 2.0)
    if getattr(proc, "returncode", None) is None:
        # Nobody has reaped the child, and "it died" without the code it died
        # with is half an answer. One that closed both pipes is already gone
        # so this returns at once; a live but silent one costs the bound,
        # which is nothing next to the wait that got us here.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), 2.0)
    tail = "".join(stderr).strip()
    code = getattr(proc, "returncode", None)
    exit_note = "" if code is None else f"; child exited {code}"
    return f"agent {what}{exit_note}" + (f":\n{tail[-2000:]}" if tail else "")
