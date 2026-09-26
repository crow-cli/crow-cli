"""Session resolution, provisioning, and the per-session registries.

v1 kept nine dictionaries on ``AcpAgent`` — sessions, MCP clients, tools,
cancel events, state accumulators, tool-call ids, prompt tasks, config values,
loggers — and every handler reached into whichever ones it needed. Six of them
were keyed on a wire session id, two on an agent id, and keeping those straight
was the source of more than one bug. Here they are one object with one key
space and one owner.

What it does, and why each piece is not obvious:

**The DB is the authority on resolution.** Compaction forks ``agent_idx``
inside a stable wire session id, so ``self._sessions`` can only ever be a
cache: a bare session id resolves to the trunk HEAD (max agent_idx, fork 1)
and a three-part id names an exact fork. A miss hydrates from the DB, which is
what lets one agent process serve a session it never created — a restart, a
second client, a prompt with no ``session/new`` before it.

**Provisioning is separate from resolution** because a hydrated session arrives
bare: no MCP client, no tools, no logger. v1 had no builtin fallback and
neither does this — a session that no client handed ``mcpServers`` for runs
toolless until one does.

**The LLM is built per turn, not per session.** ``set_config_option`` can
change the model between turns and the provider follows the model, so the
driver is handed a factory rather than a client.

**Lifetime is per session, not per process.** ``session/close`` has to free ONE
session's resources while the others keep running, so each session's MCP client
is entered on a stack of its own rather than on one process-wide stack that can
only be closed wholesale. v1 had no ``session/close`` and never needed this;
its single ``AsyncExitStack`` is why an MCP client there lived exactly as long
as the agent process did.

"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from logging import Logger
from typing import Any, Optional

from acp.experimental.v2 import schema as v2
from fastmcp import Client as MCPClient
from fastmcp.client.transports import MCPConfigTransport

from crow_cli.agent.llm import configure_llm
from crow_cli.agent.logger import setup_logger
from crow_cli.agent.mcp_client import get_tools
from crow_cli.agent.prompt import SystemPromptFactory, default_system_prompt
from crow_cli.agent.session import AgentSession, get_coolname, make_agent_session
from crow_cli.config import Config
from crow_cli.memory import (
    build_agent_id,
    delegation_tool_call_ids,
    get_engine,
    list_session_infos,
    parse_agent_id,
    session_exists,
    set_agent_model,
    wire_session_id,
)

from .driver import DriverDeps, SessionDriver
from .emitter import Emitter
from .events import Inbox
from .llm import StreamState
from .watcher import WakeWatcher

logger = logging.getLogger(__name__)


def mcp_servers_to_wire(mcp_servers: Optional[list]) -> list[dict]:
    """Serialize wire MCP server objects to JSON dicts for sqlite.

    The stored dicts are exactly what a subagent's ``session/new`` receives:
    the task tool runs in a separate process, reads them from the agents
    table, and passes them through unchanged.
    """
    return [s.model_dump(mode="json", exclude_none=True) for s in (mcp_servers or [])]


def mcp_client_for(
    mcp_servers: Optional[list], cwd: str, log: Logger
) -> tuple[dict[str, Any], Optional[MCPClient]]:
    """Wire MCP server objects -> a FastMCP client, or None for zero servers.

    The client owns tool supply; there is no builtin fallback. An empty or
    missing list means the session runs with zero tools, which is a legitimate
    configuration and not an error worth raising over.

    Dispatched on the ``type`` discriminator rather than by isinstance: v2 has
    both ``StdioMcpServer`` (what a client sends) and ``McpServerStdio`` (what
    a config carries) for the same shape, and matching the discriminator means
    one branch covers both.
    """
    config: dict[str, Any] = {"mcpServers": {}}
    for server in mcp_servers or ():
        name = getattr(server, "name", None) or "mcp"
        kind = getattr(server, "type", None) or (
            "stdio" if getattr(server, "command", None) else "http"
        )
        if kind == "stdio":
            config["mcpServers"][name] = {
                "transport": "stdio",
                "command": server.command,
                "args": list(server.args or []),
                "env": {e.name: e.value for e in (server.env or ())},
            }
        elif kind in ("http", "sse"):
            config["mcpServers"][name] = {
                "transport": kind,
                "url": str(server.url),
                "headers": {h.name: h.value for h in (server.headers or ())},
            }
        elif kind == "acp":
            # An MCP server that is itself an ACP agent (proxy chains). Not
            # wired yet; skipping loudly beats advertising a tool that hangs.
            log.warning("MCP-over-ACP server %r is not supported yet — skipped", name)
        else:
            log.warning("unknown MCP server type %r for %r — skipped", kind, name)

    for server_config in config["mcpServers"].values():
        server_config["cwd"] = cwd

    if not config["mcpServers"]:
        log.info("no MCP servers -> zero tools")
        return config, None
    log.info("creating MCP client with %d server(s)", len(config["mcpServers"]))
    return config, MCPClient(MCPConfigTransport(config, name_as_prefix=False))


class SessionRegistry:
    """Every per-session object, in one place, under one key space.

    Keyed on the WIRE session id throughout — the trunk's bare id, a fork's
    agent id — because that is what the protocol speaks. The one exception is
    :attr:`sessions`, keyed on agent_id, since compaction mints a new agent
    row inside an unchanged wire id and both have to be reachable.
    """

    def __init__(
        self,
        config: Config,
        *,
        conn: Any = None,
        model_override: Any = None,
        hooks: tuple = (),
        system_prompt: Optional[SystemPromptFactory] = None,
        compactor: Any = None,
        compact_system_prompt: Any = None,
    ) -> None:
        self.config = config
        self.conn = conn
        self.model_override = model_override
        self.hooks = tuple(hooks)
        self.system_prompt = system_prompt or default_system_prompt
        self.compactor = compactor
        self.compact_system_prompt = compact_system_prompt
        #: One exit stack per wire session id, so ``close_session`` can release
        #: a single session's MCP client. A process-wide stack could only be
        #: closed wholesale, which is exactly what closing one session is not.
        self._stacks: dict[str, AsyncExitStack] = {}

        self.engine = get_engine(config.db_uri) if config.db_uri else None
        self.sessions: dict[str, AgentSession] = {}
        self.mcp_clients: dict[str, Optional[MCPClient]] = {}
        self.tools: dict[str, list[dict]] = {}
        self.emitters: dict[str, Emitter] = {}
        self.drivers: dict[str, SessionDriver] = {}
        self.loggers: dict[str, Logger] = {}
        self.config_values: dict[str, dict[str, str]] = {}
        self.stream_states: dict[str, StreamState] = {}
        # Built here, started later: the bus routes pokes into driver inboxes,
        # so all it needs from the registry is the driver table, but a process
        # with no drivers has nothing to route to and should not be holding a
        # subscription.
        self.watcher = WakeWatcher(config.redis_url, self._inbox_for)

    # -- connection --------------------------------------------------------

    def set_conn(self, conn: Any) -> None:
        """Point every live emitter at a new connection.

        A second client attaching, or a resume re-connecting, replaces the
        transport under a session that is still running. Nothing but the
        emitter holds the connection, so rebinding is the whole operation —
        the driver and the react loop keep going untouched.
        """
        self.conn = conn
        for emitter in self.emitters.values():
            emitter.rebind(conn)

    def _stack_for(self, session_id: str) -> AsyncExitStack:
        stack = self._stacks.get(session_id)
        if stack is None:
            stack = AsyncExitStack()
            self._stacks[session_id] = stack
        return stack

    # -- models ------------------------------------------------------------

    def default_model_value(self) -> str:
        model = self.model_override or next(iter(self.config.llm.models.values()), None)
        return f"{model.provider_name}:{model.model_id}" if model else ""

    def default_model_identifier(self) -> str:
        model = self.model_override or next(iter(self.config.llm.models.values()), None)
        return model.model_id if model else ""

    def apply_model_option(
        self, session_id: str, value: str, session: AgentSession, *, persist: bool = False
    ) -> None:
        """The ONE path for "this session now uses model X".

        Stores the ``provider:model`` value (provider routing plus the option's
        currentValue) AND points ``session.model_identifier`` at the model,
        because that is what the request actually sends. Doing only one of the
        two makes the option display a model the request does not use.

        ``persist`` also writes ``model_identifier`` back to the agent row, and
        only ``session/set_config_option`` asks for it. The row is the one thing
        a restart reads — ``AgentSession.load`` seeds the session from it — so
        the flag is the difference between a choice the client made about this
        session and a decision this process made for itself. Everything else
        that reaches here is the latter: :meth:`adopt_model_option` applies a
        ``-m`` override, which means "use THIS model for this run", and writing
        that down would pin the session to whatever someone typed on one
        command line for every process that came after.
        """
        self.config_values.setdefault(session_id, {})["model"] = value
        _, model_name = value.split(":", 1) if ":" in value else ("", value)
        session.model_identifier = model_name
        if persist and self.engine is not None:
            set_agent_model(self.engine, session.agent_id, model_name)

    def adopt_model_option(self, session: AgentSession, session_id: str) -> None:
        """Point a session's model option at the model IT was using.

        Seeding the process default is right for ``session/new`` and wrong for
        anything that arrives with a saved ``model_identifier`` — a resume, a
        fork, a prompt for a session this process never created. Without this a
        client that showed one model before a restart shows a different one
        after it, and the next request goes to the different one too.

        A ``-m`` override wins, as it did in v1: the flag is an explicit "use
        THIS model for this run", so it supersedes the saved value and — via
        :meth:`apply_model_option` — repoints the session at it, because the
        request sends ``model_identifier`` and not the option.
        """
        if self.config_values.get(session_id, {}).get("model"):
            # ``set_config_option`` got here first: a client changed the model
            # on a session this process had not provisioned yet, and the
            # ``prompt`` that follows provisions it. Its choice wins over both
            # the saved value and a ``-m`` override, which is what v1's
            # ``if session_id not in self._config_values`` guard amounted to.
            return
        saved = session.model_identifier
        if self.model_override is not None:
            if saved and saved != self.model_override.model_id:
                logger.info(
                    "-m override %r supersedes saved model %r for session %s",
                    self.model_override.name, saved, session_id,
                )
            self.apply_model_option(session_id, self.default_model_value(), session)
            return
        value = self.default_model_value()
        if saved:
            match = next(
                (m for m in self.config.llm.models.values() if m.model_id == saved),
                None,
            )
            if match is not None:
                value = f"{match.provider_name}:{match.model_id}"
            else:
                # Loud, not silent: the session's behaviour just changed and
                # the option would otherwise display a model the request does
                # not send.
                logger.warning(
                    "saved model %r for session %s is not in config.yaml;"
                    " falling back to %r", saved, session_id, value,
                )
        self.config_values.setdefault(session_id, {})["model"] = value

    def make_llm(self, session: AgentSession, log: Logger) -> Any:
        """Build the LLM client for one turn.

        The provider comes from the session's model option, falling back to
        the first configured provider with a warning: a stale option left over
        from a config edit should degrade to "works" rather than refuse to run.
        """
        # The WIRE id, not ``session.session_id``. Every writer of
        # ``config_values`` keys on ``wire_session_id(agent_id)``, and for a
        # fork (fork_idx > 1) that is the agent id, not the trunk's session id.
        # Reading the trunk's id here misses, and the ``or`` below turns the
        # miss into "the first model in config.yaml" — so every delegate
        # silently ran on whatever model was listed first instead of the one it
        # inherited, with no warning because the fallback is the quiet path.
        session_id = wire_session_id(session.agent_id)
        value = self.config_values.get(session_id, {}).get("model") or (
            self.default_model_value()
        )
        provider_name = value.split(":", 1)[0] if ":" in value else ""
        provider = self.config.llm.providers.get(provider_name)
        if not provider and self.config.llm.providers:
            provider = next(iter(self.config.llm.providers.values()))
            if provider_name:
                log.warning(
                    "provider %r from model selection %r not found in config.yaml;"
                    " falling back to %r",
                    provider_name, value, provider.name,
                )
        if not provider:
            raise RuntimeError(
                "No LLM providers configured. Check ~/.agents/crow/config.yaml."
            )
        # ``value`` routes the request; ``session.model_identifier`` is the model
        # named in its body (react.send_request sends that, not this).
        # apply_model_option is the one path that moves them together, so a split
        # means one was resolved behind the other's back. Say so with the URL:
        # the server at the other end answers to whatever IT has loaded and will
        # not complain about a model name it does not know.
        selected = value.split(":", 1)[1] if ":" in value else value
        if selected != session.model_identifier:
            log.warning(
                "model split for session %s: routing to %s at %s but the request "
                "will name %r",
                session_id, provider.name, provider.base_url, session.model_identifier,
            )
        else:
            log.info(
                "session %s -> %s:%s at %s",
                session_id, provider.name, selected, provider.base_url,
            )
        return configure_llm(
            provider=provider, debug=self.config.chunk_log, logger=log
        )

    def config_options(self, session_id: str) -> list:
        """The session's config options, with current values filled in.

        ``id`` became ``config_id`` in v2; ``category`` is a stable enum and
        ``"model"`` is what makes a client render this as a model picker
        rather than an anonymous dropdown.
        """
        current = self.config_values.get(session_id, {}).get(
            "model", self.default_model_value()
        )
        return [
            v2.SelectSessionConfigOption(
                config_id="model",
                name="Model",
                category="model",
                current_value=current,
                options=[
                    v2.SessionConfigSelectOption(
                        value=f"{m.provider_name}:{m.model_id}",
                        name=m.name,
                        description=m.model_id,
                    )
                    for m in self.config.llm.models.values()
                ],
            )
        ]

    # -- loggers -----------------------------------------------------------

    def logger_for(self, session_id: str) -> Logger:
        log = self.loggers.get(session_id)
        if log is None:
            log = setup_logger(
                self.config.config_dir / "logs" / f"crow-cli-{session_id}.log",
                name=f"{session_id}-crow-logger",
            )
            self.loggers[session_id] = log
        return log

    # -- resolution --------------------------------------------------------

    async def resolve(self, session_id: str) -> Optional[AgentSession]:
        """Wire session id -> the live AgentSession, hydrating on a miss."""
        try:
            parse_agent_id(session_id)
            agent_id = session_id
        except ValueError:
            max_idx = await AgentSession.get_max_agent_idx(
                session_id, memory_path=self.config.db_uri
            )
            if max_idx < 1:
                return None
            agent_id = build_agent_id(session_id, max_idx)
        session = self.sessions.get(agent_id)
        if session is None:
            try:
                session = await AgentSession.load(
                    agent_id, memory_path=self.config.db_uri
                )
            except ValueError:
                return None
            self.sessions[agent_id] = session
        return session

    def known(self, session_id: str) -> bool:
        """Whether this wire id names a session at all — live here, or in the store.

        Deliberately NOT :meth:`resolve`. ``session/close`` has to tell "nothing
        to free" from "no such session", and resolving hydrates every message of
        a session it is about to throw away — plus an ImageStore it will never
        read. This answers the same question with one indexed lookup.
        """
        if session_id in self.tools:
            return True
        if any(wire_session_id(a) == session_id for a in self.sessions):
            return True
        return self.engine is not None and session_exists(self.engine, session_id)

    def session_infos(
        self, cwd: Optional[str], limit: int, offset: int
    ) -> tuple[list[dict], Optional[int]]:
        """One page of ``session/list``, and the offset of the next.

        An agent with no database has no sessions to list and says so with an
        empty page rather than an error: everything else about it still works,
        and a client listing sessions against a stateless agent deserves an
        empty list, not a failure.
        """
        if self.engine is None:
            return [], None
        return list_session_infos(self.engine, cwd, limit, offset)

    # -- creation / provisioning -------------------------------------------

    async def create(
        self, cwd: str, mcp_servers: Optional[list] = None
    ) -> AgentSession:
        """A brand-new session: mint the id, build the prompt, make the row."""
        # The id is minted here rather than inside make_agent_session because
        # the system-prompt callable is handed it: crow's own template tells
        # the agent which session it is, so a project replacing the prompt has
        # to be able to say the same thing. Minted before the MCP client is
        # entered, too, because the client's lifetime is keyed on it — and a
        # failure between the two still leaves the stack in ``_stacks``, so
        # process teardown closes it rather than leaking the subprocess.
        session_id = get_coolname()
        _, mcp_client = mcp_client_for(mcp_servers, cwd, logger)
        if mcp_client is not None:
            mcp_client = await self._stack_for(session_id).enter_async_context(mcp_client)
        tools = await get_tools(mcp_client)

        system_prompt = self.system_prompt(self.config, cwd, session_id)
        session = await make_agent_session(
            self.config,
            tools,
            self.default_model_identifier(),
            cwd,
            session_id=session_id,
            template=system_prompt.template,
            template_args=system_prompt.template_args,
        )
        # Task system round trip: the separate-process task tool reads the
        # parent's client-defined mcpServers from sqlite to pass through to
        # the subagent's session/new.
        await session.client.set_agent_mcp_servers(
            session.agent_id, mcp_servers_to_wire(mcp_servers)
        )
        self._register(session, mcp_client, tools)
        logger.info(
            "created session %s (agent %s) with %d tools",
            session.session_id, session.agent_id, len(tools),
        )
        return session

    async def provision(
        self, session: AgentSession, mcp_servers: Optional[list] = None
    ) -> None:
        """Bring per-session infrastructure up. Idempotent.

        Resolution can return a session this process never created — a
        restart, a second client, a prompt with no ``session/new`` before it.
        The driver needs an MCP client, tools, a logger and a stream state;
        spin them up on first use.
        """
        session_id = wire_session_id(session.agent_id)
        if session_id in self.tools:
            return
        _, mcp_client = mcp_client_for(mcp_servers, session.cwd, logger)
        if mcp_client is not None:
            mcp_client = await self._stack_for(session_id).enter_async_context(mcp_client)
        tools = await get_tools(mcp_client)
        self._register(session, mcp_client, tools)
        logger.info(
            "provisioned hydrated session %s (agent %s) — %d tools",
            session_id, session.agent_id, len(tools),
        )

    async def fork(
        self,
        session_id: str,
        cwd: str,
        mcp_servers: Optional[list] = None,
        *,
        agent_idx: Optional[int] = None,
        turn_idx: Optional[int] = None,
        message_offset: Optional[int] = None,
        rlm_depth: Optional[int] = None,
    ) -> AgentSession:
        """A branch of ``session_id``'s history under its own wire id.

        The four anchors are not in the v2 schema — ``ForkSessionRequest``
        carries only the environment — so they ride ``_meta``, which is what
        ``_meta`` is for and what v1 did with the same four. Defaults fork at
        HEAD: newest trunk agent, all messages.

        ``delegation_ids`` comes from the subtool register and not from the
        caller, exactly as in v1: the model cannot be trusted to declare which
        of its own calls were delegations, and it does not have to, because the
        rail already recorded them. Read through the registry's own engine
        rather than a fresh one — v1 had no engine to hand and had to open and
        dispose a pool per fork.
        """
        delegation_ids = None
        if message_offset is not None and self.engine is not None:
            delegation_ids = delegation_tool_call_ids(self.engine, session_id)
        forked = await AgentSession.fork(
            session_id,
            memory_path=self.config.db_uri,
            cwd=cwd,
            agent_idx=agent_idx,
            turn_idx=turn_idx,
            message_offset=message_offset,
            delegation_ids=delegation_ids,
            rlm_depth=rlm_depth,
        )
        # Same round trip create() makes: a subagent launched from this fork
        # reads the fork's client-defined servers off its own agent row.
        await forked.client.set_agent_mcp_servers(
            forked.agent_id, mcp_servers_to_wire(mcp_servers)
        )
        await self.provision(forked, mcp_servers)
        logger.info(
            "forked %s from %s (forked_at=%s, %d messages in view)",
            forked.agent_id, session_id, forked.forked_at, len(forked.messages),
        )
        return forked

    def _register(
        self, session: AgentSession, mcp_client: Optional[MCPClient], tools: list[dict]
    ) -> None:
        session_id = wire_session_id(session.agent_id)
        self.sessions[session.agent_id] = session
        self.mcp_clients[session_id] = mcp_client
        self.tools[session_id] = tools
        self.stream_states.setdefault(session_id, StreamState())
        self.config_values.setdefault(session_id, {})
        self.adopt_model_option(session, session_id)
        self.logger_for(session_id)

    # -- drivers -----------------------------------------------------------

    def emitter_for(self, session_id: str) -> Emitter:
        emitter = self.emitters.get(session_id)
        if emitter is None:
            emitter = Emitter(self.conn, session_id)
            self.emitters[session_id] = emitter
        return emitter

    def _inbox_for(self, session_id: str) -> Optional[Inbox]:
        """Where a wake poke for this session should land, or None if not ours.

        The bus broadcasts to every process sharing the db, so "not ours" is
        the ordinary answer rather than a fault: some other client's agent
        holds the session and routes the same poke itself.
        """
        driver = self.drivers.get(session_id)
        return driver.inbox if driver is not None else None

    async def driver_for(
        self, session: AgentSession, slash: Any = None
    ) -> SessionDriver:
        """The session's driver, created and started on first ask."""
        session_id = wire_session_id(session.agent_id)
        driver = self.drivers.get(session_id)
        if driver is not None:
            driver.session = session  # compaction may have moved it
            return driver
        await self.provision(session)
        log = self.logger_for(session_id)
        chunk_log_dir = None
        if self.config.chunk_log:
            chunk_log_dir = self.config.config_dir / "logs" / session.session_id
            chunk_log_dir.mkdir(parents=True, exist_ok=True)
        driver = SessionDriver(
            session_id=session_id,
            session=session,
            emitter=self.emitter_for(session_id),
            logger=log,
            slash=slash,
            deps=DriverDeps(
                config=self.config,
                engine=self.engine,
                mcp_clients=self.mcp_clients,
                tools=self.tools[session_id],
                state=self.stream_states[session_id],
                make_llm=self.make_llm,
                hooks=self.hooks,
                compactor=self.compactor,
                compact_system_prompt=self.compact_system_prompt,
                chunk_log_dir=str(chunk_log_dir) if chunk_log_dir else None,
            ),
        )
        self.drivers[session_id] = driver
        # Before the driver parks, not after: the first thing a fresh driver
        # does with nothing to run is park, and a poke published in between
        # would land in an inbox nobody is subscribed to yet. Idempotent, so
        # every later session is a no-op.
        await self.watcher.start()
        await driver.start()
        return driver

    async def close_session(self, session_id: str) -> bool:
        """Free ONE session: its driver, its MCP client, every dict slot.

        Returns whether this process was holding anything. False is not an
        error and the caller does not turn it into one — the session may be
        live in another agent process sharing the store, or may simply have
        nothing to free because it was never prompted. Either way the resources
        the request asked about are gone, which is what ``session/close``
        means.

        The driver goes first and its stack second: the driver's turn may be
        mid-call through the MCP client, and closing the client under a live
        call turns a clean cancel into an exception in the react loop.
        ``driver.stop()`` awaits the run loop, so by the time it returns
        nothing is in flight.

        The wake bus is deliberately left running. It is one subscription per
        PROCESS, shared by every session, and other sessions still need it;
        ``_inbox_for`` already answers None for a session with no driver, so a
        poke for the closed one is dropped where it was always dropped.
        """
        driver = self.drivers.pop(session_id, None)
        if driver is not None:
            await driver.stop()
        stack = self._stacks.pop(session_id, None)
        if stack is not None:
            await stack.aclose()
        held = driver is not None or stack is not None
        for table in (
            self.mcp_clients, self.tools, self.emitters, self.loggers,
            self.config_values, self.stream_states,
        ):
            table.pop(session_id, None)
        for agent_id, session in list(self.sessions.items()):
            if wire_session_id(agent_id) == session_id:
                del self.sessions[agent_id]
                await session.close()
        logger.info(
            "closed session %s (%s)", session_id, "was live here" if held else "nothing held here"
        )
        return held

    async def close(self) -> None:
        """Stop the wake bus, then every driver, then release every MCP client.

        Bus first so a poke arriving mid-shutdown cannot be routed into an
        inbox whose driver is already gone.
        """
        await self.watcher.stop()
        for driver in list(self.drivers.values()):
            await driver.stop()
        self.drivers.clear()
        for stack in self._stacks.values():
            await stack.aclose()
        self._stacks.clear()
