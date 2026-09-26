"""Headless ACP v2 client that drives one subagent subprocess.

The client half of the task system: pure protocol orchestration — spawn a
child crow agent, handshake, ``session/new``, ``session/prompt``,
``session/cancel``, teardown. No sqlite and no tool knowledge. The ``task``
subtool owns state and lifecycle; this is the driver it uses, and the two
couple through the database, never in-process.

What v2 changed, and why this is not a mechanical port of
:mod:`crow_cli.client.subagent`:

**``prompt`` no longer returns the outcome.** v1's ``PromptResponse`` carried
``stop_reason``. v2's carries only ``field_meta``, and the outcome travels as a
``state_update`` notification — which is the whole point of the v2 lifecycle,
and the reason a wake can look exactly like a prompt. So somebody has to watch
the update stream for the idle. :class:`HeadlessClient` does, and
:meth:`SubagentDriver.prompt` still returns a stop reason, because "launch a
child and get its answer" is the contract the task system is written against
and nothing in v2 makes that contract wrong. The watch itself is
:meth:`SubagentDriver.wait` and ``prompt`` is that plus the send — a split
that lets a caller which ran out of patience hand the turn to a background
waiter instead of killing a child that was about to answer.

**There is no client-side terminal or fs capability to decline.** v1 sent
``ClientCapabilities(terminal=False)`` so the child's terminal tool would fall
through to its own MCP supply. v2's ``ClientCapabilities`` has ``auth``,
``elicitation``, ``nes`` and ``position_encodings`` and nothing else: the agent
owns execution, so the choice no longer exists.

**``session/load`` is ``session/resume``**, and it replays history only when
asked. A headless driver does not ask — the child's transcript is in the shared
sqlite, and replaying it into a queue nobody reads is pure cost.

**Absent handlers already answer ``method_not_found``.** v2's ``MethodRouter``
raises that for any request whose handler attribute is missing, so v1's
explicit ``raise RequestError.method_not_found(...)`` stubs are deleted rather
than ported. Omitting them produces the identical reply on the wire.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Optional

from acp.experimental import v2
from acp.stdio import spawn_stdio_transport

from crow_cli import __version__
from crow_cli.discover import Connection, adopt_v2

#: How much of a child's stderr to keep. The drain exists so the pipe cannot
#: fill and deadlock the child, not to archive its log, so it is bounded — and
#: the tail is exactly what an error message about a dead child needs.
STDERR_LINES = 200


class ChildExited(RuntimeError):
    """The child process ended before its turn did.

    Distinct from a transport error and from a timeout, because the caller's
    options differ: there is nothing to cancel, nothing to retry on the same
    session, and the stderr tail in the message is the only evidence that will
    ever exist. A task watcher turns this into a ``failed`` row.
    """


def child_config() -> dict[str, Path]:
    """Config context for a spawned child, forwarded from THIS process's env.

    The child loads its own config in its own process, so without these it
    resolves a different config dir — and therefore a different database —
    than the caller that is about to read the child's transcript out of.

    Duplicated from :mod:`crow_cli.client.subagent` rather than imported: that
    module speaks ACP v1 at import time and v1 is frozen, so importing one
    six-line function from it would drag the old protocol into every process
    that spawns a new one.
    """
    kwargs: dict[str, Path] = {}
    if f := os.environ.get("CROW_CONFIG_FILE"):
        kwargs["config_file"] = Path(f)
    if d := os.environ.get("CROW_CONFIG_DIR"):
        kwargs["config_dir"] = Path(d)
    return kwargs


def agent_argv(
    model: Optional[str] = None,
    config_dir: Optional[Path] = None,
    config_file: Optional[Path] = None,
) -> list[str]:
    """The argv that starts a v2 agent in this interpreter.

    Two shapes, mirroring v1's ``spawn_agent_process``. In a frozen build
    ``sys.executable`` IS the ``crow-cli`` binary, so the agent is a
    subcommand of it; in a source checkout it is a module, because there is no
    binary and ``-m`` is the only thing that resolves against the checkout
    under test.

    ``acp2`` and :func:`crow_cli.cli.main.run_agent2` are two halves of one
    contract. Spawning ``acp`` here instead would produce a child that
    answers a v2 handshake with a v1 one — which is why this refused to guess
    for as long as the subcommand did not exist.
    """
    args: list[str] = []
    if config_dir:
        args += ["--config-dir", str(config_dir)]
    if config_file:
        args += ["--config-file", str(config_file)]
    if model:
        args += ["--model", model]
    if getattr(sys, "frozen", False):
        return [sys.executable, "acp2", *args]
    return [sys.executable, "-m", "crow_cli.agent2.main", *args]


def client_info(name: str = "crow-task", title: str = "Crow Task") -> Any:
    """The Implementation a driver names itself with in the handshake.

    The agent logs it (``initialize: client <name> <version>``), so the task
    system and a human at a terminal stay distinguishable in the one place
    both are recorded.
    """
    return v2.schema.Implementation(name=name, title=title, version=__version__)


def mcp_servers_to_models(servers: Optional[list]) -> list[Any]:
    """Wire JSON dicts -> v2 MCP server models, before the request is built.

    The dicts come out of sqlite, where :func:`crow_cli.agent2.sessions.
    mcp_servers_to_wire` stored whatever a client originally sent. Building
    the models item by item is the lesson v1 learned the hard way: a list item
    that fails validation is dropped silently, and the child comes up toolless
    with no error anywhere. Here a bad shape raises at the caller.

    ``type`` is filled in rather than trusted, and ``sse`` is rewritten to
    ``http`` — v2 deleted ``SseMcpServer``, and an SSE endpoint is an HTTP
    endpoint, so rewriting it keeps an old stored server working where
    dropping it would not.
    """
    out: list[Any] = []
    for server in servers or ():
        if not isinstance(server, dict):
            out.append(server)  # already a model
            continue
        data = dict(server)
        kind = data.pop("type", None) or ("stdio" if data.get("command") else "http")
        if kind == "sse":
            kind = "http"
        if kind == "stdio":
            model = v2.schema.StdioMcpServer.model_validate(
                {"type": "stdio", "args": [], "env": [], **data}
            )
        elif kind == "http":
            model = v2.schema.HttpMcpServer.model_validate({"type": "http", **data})
        elif kind == "acp":
            model = v2.schema.AcpMcpServer.model_validate({"type": "acp", **data})
        else:
            model = v2.schema.OtherMcpServer.model_validate({"type": kind, **data})
        out.append(model)
    return out


def config_to_servers(mcp_servers: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """The config ``mcpServers`` MAP -> the wire LIST a v2 request carries.

    Config keys a server by name and spells its transport ``transport``; the
    wire puts the name inside the entry and spells it ``type``. This is the
    client half of that translation, and it belongs to the client because the
    client owns tool supply: the agent never reads ``mcpServers`` itself, so
    what a client sends here is exactly what the session gets.

    Duplicated from v1's ``agent.mcp_client.fastmcp_config_to_acp_servers``
    rather than imported, for the reason :func:`child_config` is duplicated:
    that module speaks ACP v1 at import time and v1 is frozen.

    ``sse`` is passed through as written and rewritten to ``http`` by
    :func:`mcp_servers_to_models`, which is where that rule already lives.
    """
    out: list[dict[str, Any]] = []
    for name, cfg in (mcp_servers or {}).items():
        if not isinstance(cfg, dict):
            raise ValueError(
                f"mcpServers.{name!r} must be a mapping, not {type(cfg).__name__}"
            )
        kind = cfg.get("transport") or cfg.get("type") or (
            "http" if cfg.get("url") else "stdio"
        )
        entry: dict[str, Any] = {"type": kind, "name": name}
        if kind == "stdio":
            if not cfg.get("command"):
                raise ValueError(f"mcpServers.{name!r}: a stdio server needs a command")
            entry["command"] = str(cfg["command"])
            entry["args"] = [str(a) for a in (cfg.get("args") or [])]
            entry["env"] = [
                {"name": str(k), "value": str(v)} for k, v in (cfg.get("env") or {}).items()
            ]
        else:
            if not cfg.get("url"):
                raise ValueError(f"mcpServers.{name!r}: a {kind} server needs a url")
            entry["url"] = str(cfg["url"])
            entry["headers"] = [
                {"name": str(k), "value": str(v)}
                for k, v in (cfg.get("headers") or {}).items()
            ]
        out.append(entry)
    return out


class HeadlessClient:
    """The client face shown to a subagent: record updates, answer nothing.

    Two jobs. ``updates`` is the record — the child's transcript is properly
    observable through the shared sqlite, so this is for debugging and for a
    caller that wants the wire rather than the database. ``stops`` is the part
    v2 makes necessary: one queue per session, fed by the idle
    ``state_update``, which is how a driver learns a turn ended now that the
    prompt response says nothing.
    """

    def __init__(self) -> None:
        self.updates: list[Any] = []
        self.stops: dict[str, asyncio.Queue] = {}
        self.running: set[str] = set()

    def watch(self, session_id: str) -> asyncio.Queue:
        """The queue this session's stop reasons land in.

        Called BEFORE the prompt is sent, not after: a turn that ends fast
        (a slash command, an empty prompt) can reach idle before ``prompt()``
        returns its empty response, and registering afterwards would wait
        forever for a notification that already arrived.
        """
        return self.stops.setdefault(session_id, asyncio.Queue())

    async def session_update(
        self, session_id: str, update: Any, **kwargs: Any
    ) -> None:
        """One ``session/update``. The router hands over the notification's
        fields as keywords, not the model — see :mod:`crow_cli.agent2.agent`'s
        docstring for the two consequences that follow from it."""
        self.updates.append(update)
        if getattr(update, "session_update", None) != "state_update":
            return
        state = getattr(update, "state", None)
        if state == "running" and session_id in self.stops:
            self.running.add(session_id)
        elif state == "idle" and session_id in self.running:
            self.running.remove(session_id)
            self.stops[session_id].put_nowait(getattr(update, "stop_reason", None))


class SubagentDriver:
    """Drives ONE v2 subagent: spawn -> handshake -> sessions -> turns."""

    def __init__(
        self,
        client: Optional[HeadlessClient] = None,
        info: Optional[Any] = None,
    ) -> None:
        """``client`` is the face shown to the child — a caller that renders the
        update stream passes its own :class:`HeadlessClient` subclass rather
        than inheriting the recording one. ``info`` is the Implementation the
        handshake names; the agent logs it, so a client that is not the task
        system says so."""
        self.client = client or HeadlessClient()
        self.info = info or client_info()
        self.conn: Optional[v2.ClientSideConnection] = None
        self.proc: Optional[Any] = None
        self.stderr: collections.deque = collections.deque(maxlen=STDERR_LINES)
        self._stack = AsyncExitStack()
        self._drainer: Optional[asyncio.Task] = None

    @property
    def stderr_tail(self) -> str:
        """What the child said last. Empty when it said nothing."""
        return "".join(self.stderr)

    async def start(
        self,
        cwd: str,
        model: Optional[str] = None,
        config_dir: Optional[Path] = None,
        config_file: Optional[Path] = None,
        argv: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        conn: Optional[Connection] = None,
    ) -> None:
        """Spawn the child, handshake, and be ready to open sessions.

        ``argv`` launches somebody else's agent: an ``agent_servers`` entry is
        a command the client honors exactly as written, so a driver that only
        ever spawned crow's own agent could not drive one. Omitted, it is
        :func:`agent_argv` — crow's v2 agent in this interpreter. ``env`` is
        merged OVER this process's environment, which is the entry's own extra
        variables; the base is inherited whole, for the reason spelled out
        below.

        ``conn`` is an already-spawned child somebody else asked: protocol
        discovery spawns once and hands the live streams to whichever stack
        the agent's answer selects, because a second spawn is a second cold
        start of the same process. Adopting one takes the stderr drain over
        by reference — two readers on one ``StreamReader`` would split the
        child's lines between them — and skips the handshake when the probe
        already did it. ``close()`` needs no matching change: the exit stack
        is empty for an adopted child, so the caller's context manager owns
        the shutdown.
        """
        if conn is not None:
            reader, writer = conn.reader, conn.writer
            self.proc = conn.proc
            self.stderr = conn.stderr
            self._drainer = conn.drainer
        else:
            reader, writer, self.proc = await self._stack.enter_async_context(
                spawn_stdio_transport(
                    *(
                        argv
                        or agent_argv(
                            model=model, config_dir=config_dir, config_file=config_file
                        )
                    ),
                    # spawn_stdio_transport's default environment is the
                    # MCP-best-practice trim — HOME, LOGNAME, PATH, SHELL, TERM,
                    # USER — because it exists to launch other people's servers.
                    # A crow child is not somebody else's server: v1 inherited the
                    # whole environment, and the trim silently loses shell-exported
                    # API keys, SEARXNG_URL, CROW_MEMORY_PORT and everything else
                    # this process was built out of. child_config() forwards the
                    # two config pointers as argv, which covers config resolution
                    # and nothing else.
                    env={**os.environ, **(env or {})},
                    cwd=cwd,
                )
            )
            self._drainer = asyncio.create_task(
                self._drain_stderr(), name="crow-subagent-stderr"
            )
        self.conn = v2.ClientSideConnection(self.client, writer, reader)
        if conn is not None and conn.initialized:
            # Already negotiated on the wire. v2's connection also gates every
            # method on a LOCAL initialization state that only its own
            # initialize() moves, and a second initialize is refused by the
            # agent, so the state is adopted rather than the request repeated.
            adopt_v2(self.conn, conn.response)
        else:
            await self.conn.initialize(
                protocol_version=v2.PROTOCOL_VERSION, info=self.info
            )

    async def _drain_stderr(self) -> None:
        """Keep the child's stderr pipe empty.

        Not optional and not cosmetic: ``spawn_stdio_transport`` gives the
        child a PIPE, and a child that logs more than the 64KB buffer holds
        blocks on the write and hangs with no error on either side. v1 had
        this bug — it opened the pipe and never read it.
        """
        stream = getattr(self.proc, "stderr", None)
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                return
            self.stderr.append(line.decode(errors="replace"))

    async def new_session(self, cwd: str, mcp_servers: Optional[list] = None) -> str:
        response = await self.conn.new_session(
            cwd=cwd, mcp_servers=mcp_servers_to_models(mcp_servers)
        )
        return response.session_id

    async def resume_session(
        self,
        session_id: str,
        cwd: str,
        mcp_servers: Optional[list] = None,
        replay: bool = False,
    ) -> None:
        """Re-attach to a session whose turn ended, so it can be prompted again.

        ``replay_from`` is left off BY DEFAULT. Omitting it means no history
        comes back over the wire, and the child's transcript is already in the
        shared sqlite where ``query_session`` can read it: asking for
        ``{"type": "start"}`` would stream the whole conversation into
        ``HeadlessClient.updates`` for nobody. A client with a human watching is
        that somebody — it renders the replayed transcript — so it passes
        ``replay=True`` and gets the conversation before the first prompt.
        """
        await self.conn.resume_session(
            session_id=session_id,
            cwd=cwd,
            mcp_servers=mcp_servers_to_models(mcp_servers),
            replay_from=(v2.schema.ReplayFromStartVariant() if replay else None),
        )

    async def fork_session(
        self,
        session_id: str,
        cwd: str,
        mcp_servers: Optional[list] = None,
        *,
        message_offset: Optional[int] = None,
        rlm_depth: Optional[int] = None,
    ) -> str:
        """``session_id``'s history under a NEW wire id, which is the fork's
        own agent id — so it is also the key the fork's transcript is stored
        under, and reading that transcript back needs no handshake.

        An empty ``mcp_servers`` means ZERO tools, which is what an
        interrogation fork wants and what a delegate that only has to answer a
        question does not need.

        ``message_offset`` and ``rlm_depth`` are not in the schema — v2's
        ``ForkSessionRequest`` carries the environment and nothing else — so
        they ride ``_meta``, which is what ``_meta`` is for and what v1 did with
        the same two. They are the delegation half of the fork contract: the
        offset steps the fork's history back over the call that made it, and the
        depth is persisted on the fork's agent row so the budget survives a
        resume in a different process. A delegate that forgets either is the
        infinity mirror.
        """
        meta: dict[str, Any] = {}
        if message_offset is not None:
            meta["messageOffset"] = message_offset
        if rlm_depth is not None:
            meta["rlmDepth"] = rlm_depth
        # ``**meta``, not ``field_meta=meta``: the connection's trailing
        # ``**kwargs`` IS the request's ``_meta``, which is what lets a caller
        # name a field the schema does not have without building the model.
        response = await self.conn.fork_session(
            session_id=session_id,
            cwd=cwd,
            mcp_servers=mcp_servers_to_models(mcp_servers),
            **meta,
        )
        return response.session_id

    async def set_config_option(
        self, session_id: str, config_id: str, value: str
    ) -> Any:
        """Set one of the session's config options; returns the whole array.

        A model choice rides this rather than the child's argv, because argv is
        crow's own agent's business while an ``agent_servers`` entry belongs to
        whoever wrote it. This is the one path that reaches every agent, which
        is why the client owns the choice.
        """
        return await self.conn.set_config_option(
            config_id=config_id, session_id=session_id, value=value, type="id"
        )

    async def prompt(
        self, session_id: str, text: str, *, timeout: Optional[float] = None
    ) -> Optional[str]:
        """Send one prompt and wait for the turn to end. Returns the stop reason.

        The wait is the v2 part: ``PromptResponse`` is empty, so returning from
        ``conn.prompt`` means "accepted", not "finished". ``None`` comes back
        when the agent reported an idle with no stop reason, which per the spec
        means it is not reporting one.

        ``timeout`` is for a turn that never ends — a model that will not stop
        calling tools, or an agent that does not report idle at all. crow's own
        always does, including while a delegated task runs in the background:
        in v2 that is exactly what ``idle`` means.
        """
        # Registered BEFORE the send, not after: a turn that ends fast (a slash
        # command, an empty prompt) can reach idle before ``conn.prompt``
        # returns its empty response, and watching afterwards would wait
        # forever for a notification that already arrived.
        self.client.watch(session_id)
        await self.conn.prompt(
            session_id=session_id,
            prompt=[v2.schema.TextContentBlock(text=text)],
        )
        return await self.wait(session_id, timeout=timeout)

    async def wait(
        self, session_id: str, *, timeout: Optional[float] = None
    ) -> Optional[str]:
        """Wait for a turn that is ALREADY in flight. Returns the stop reason.

        :meth:`prompt` is this plus the send, and the split is what lets a
        caller that ran out of patience hand the turn to a background task
        instead of killing it: the idle the first wait never saw is still
        coming, :meth:`HeadlessClient.watch` hands back the SAME queue, and a
        reason that landed in the gap is sitting on it — so a second wait
        finds it rather than waiting for a notification that already arrived.

        Three things can end the wait, and only one of them is the answer:

        * the idle ``state_update`` lands — the stop reason;
        * the child process ends — :class:`ChildExited`, because a dead child
          will never send another notification and the queue it would have sent
          it to is not going to fill. Waiting on it anyway is how a crashed
          subagent leaves its task row "running" forever, and its owner parked
          forever behind it;
        * ``timeout`` expires — :class:`TimeoutError`.
        """
        stops = self.client.watch(session_id)
        stop = asyncio.ensure_future(stops.get())
        died = asyncio.ensure_future(self._exited())
        done, _ = await asyncio.wait(
            {stop, died}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if stop in done:
            died.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await died
            return stop.result()
        # Cancelling the getter leaves a reason that arrived in the meantime on
        # the queue, so a caller that looks again finds it instead of waiting.
        stop.cancel()
        died.cancel()
        for pending in (stop, died):
            with contextlib.suppress(asyncio.CancelledError):
                await pending
        if died.done() and not died.cancelled():
            raise ChildExited(self._exit_note())
        raise TimeoutError(
            f"session {session_id} did not end its turn within {timeout}s"
        )

    async def _exited(self) -> None:
        """Return when the child process is gone (or immediately, if it never
        started — which is also "no notification will ever arrive")."""
        proc = self.proc
        if proc is None:
            return
        await proc.wait()

    def _exit_note(self) -> str:
        proc = self.proc
        code = getattr(proc, "returncode", None)
        tail = self.stderr_tail.strip().splitlines()[-3:]
        note = f"child process exited with code {code}"
        if tail:
            note += "; its last words were: " + " | ".join(
                line.strip() for line in tail
            )
        return note

    async def cancel(self, session_id: str) -> None:
        """Kill the child's in-flight turn. The session survives it.

        v2 cancellation is per-turn, so the child is still promptable
        afterwards — which is how a redirect works: cancel, then prompt again
        on the same session id.
        """
        await self.conn.cancel_session(session_id=session_id)

    async def close(self) -> None:
        """Tear down. Safe to call on a driver that never started."""
        with contextlib.suppress(Exception):
            if self.conn is not None:
                await self.conn.close()
        if self._drainer is not None:
            self._drainer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._drainer
            self._drainer = None
        # The stack owns spawn_stdio_transport's shutdown: stdin EOF, wait,
        # terminate, then kill. Hand-rolling that escalation is how v1 ended
        # up with a terminate/kill ladder of its own to keep in step.
        await self._stack.aclose()
        self.conn = None
        self.proc = None
