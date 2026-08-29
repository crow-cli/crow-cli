"""
ACP-native Agent.

This is the single agent class that combines:
- ACP protocol implementation ( from CrowACPAgent)
- Business logic (from old Agent)

No wrapper, no nested agents - just one clean Agent(acp.Agent) implementation.
"""

SETUP_MESSAGE = """# Welcome!
👋 Hi there! Thanks for trying out `crow-cli`!

Unfortunately I _don't_ have access to an LLM provider yet, so let's walk you through the steps to get one configured.

# Install Dependencies
To install `uv` run the following in a terminal:
```bash
# On macOS and Linux.
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Local models
To get started you can download [`ollama`](ollama.com/download) or any of the plethora of local model provider programs. I highly recommend building [llama.cpp from source.](https://gist.github.com/odellus/b9a22e06493a83171435a17602934be9)
```bash
# Install ollama to get started
curl -fsSL https://ollama.com/install.sh | sh
# Size up your model from this to fit your hardware capabilities
ollama pull qwen3.5:0.8b
```
By default ollama's `API_KEY` is `empty` and the base url is [http://localhost:11434/v1](http://localhost:11434/v1)

# Configure `crow-cli`
Now you're guaranteed to have an API key and a base url to access an LLM, run the following and throw your url and keys in there.
```bash
crow-cli init
```

Then restart your agent.
"""

import argparse
import asyncio
import base64
import json
import mimetypes
import os
import platform
import sys
import uuid
from contextlib import AsyncExitStack
from logging import Logger
from pathlib import Path
from typing import Any
from importlib.metadata import version

import httpx
from acp import (
    PROTOCOL_VERSION,
    Agent,
    AuthenticateResponse,
    InitializeResponse,
    LoadSessionResponse,
    NewSessionResponse,
    PromptResponse,
    RequestError,
    SetSessionModeResponse,
    run_agent,
    text_block,
    update_agent_message,
    update_agent_thought,
)
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    AudioContentBlock,
    AuthMethodAgent,
    AvailableCommand,
    AvailableCommandsUpdate,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    ForkSessionResponse,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    ListSessionsResponse,
    McpServerStdio,
    PromptCapabilities,
    ResourceContentBlock,
    SessionCapabilities,
    SessionConfigOptionSelect,
    SessionConfigSelectOption,
    SessionForkCapabilities,
    SessionInfo,
    SessionListCapabilities,
    SetSessionConfigOptionResponse,
    SetSessionModeResponse,
    SseMcpServer,
    TextContentBlock,
)
from fastmcp import Client as MCPClient

from crow_cli.agent.compact import compact
from crow_cli.config import Config, apply_config_overrides, get_default_config_dir
from crow_cli.agent.hooks import (
    CommandHook,
    uv_project_hook,
)
from crow_cli.agent.llm import configure_llm
from crow_cli.agent.logger import setup_logger
from crow_cli.agent.mcp_client import create_mcp_client_from_acp, get_tools
from crow_cli.agent.prompt import normalize_prompt, get_directory_tree
from crow_cli.memory import (
    build_agent_id,
    get_engine,
    parse_agent_id,
    wire_session_id,
)
from crow_cli.agent.react import react_loop
from crow_cli.agent.session import (
    AgentSession,
    get_session_by_cwd,
    lookup_or_create_prompt,
    get_coolname,
    make_agent_session,
)
from crow_cli.agent.slash import (
    _SLASH_COMMANDS,
    parse_slash_command,
    register_slash_command,
)


def _mcp_servers_to_wire(mcp_servers: list | None) -> list[dict]:
    """Serialize ACP mcp server objects to wire JSON dicts for sqlite.

    The stored dicts are exactly what a subagent's session/new
    receives: the task tool (a separate MCP server process) reads them from
    the agents table and passes them through unchanged.
    """
    return [s.model_dump(mode="json", exclude_none=True) for s in (mcp_servers or [])]


class AcpAgent(Agent):
    """
    ACP-native agent - single agent class.

    This class:
    - Implements the ACP Agent protocol directly
    - Contains all business logic (react loop, tool execution)
    - Manages resources via AsyncExitStack
    - Stores minimal in-memory state (MCP clients, sessions)
    - Receives MCP servers from ACP client at runtime
    - Replaces terminal tool with ACP client terminal when supported

    No wrapper, no nesting - just one clean implementation.
    """

    _conn: Client
    _client_capabilities: ClientCapabilities | None = None
    _logger: Logger

    def __init__(
        self,
        config: Config | None = None,
        hooks: list[CommandHook] | None = None,
        model: str | None = None,
    ) -> None:
        """
        Initialize the merged agent.

        Args:
            config: Configuration object. If None, uses defaults from env vars
            hooks: Command hooks to run before terminal execution.
                   If None, defaults to [uv_project_hook].
                   Pass [] to disable all hooks.
            model: Model NAME from config.yaml's models: section to force for
                   all sessions (the `-m` flag). Overrides the first-in-config
                   default and any session's saved model.

        Sets up:
        - AsyncExitStack for resource management
        - In-memory dictionaries for sessions and MCP clients
        - LLM client from configuration
        """
        if not config:
            config_dir: Path = get_default_config_dir()
            config: Config = Config.load(config_dir=config_dir)
        self._config = config
        self._hooks: list[CommandHook] = (
            hooks if hooks is not None else [uv_project_hook]
        )
        self._logger = setup_logger(self._config.config_dir / "logs" / "crow-cli.log")
        self._model_override = None
        if model is not None:
            self._model_override = config.llm.models.get(model)
            if self._model_override is None:
                valid = sorted(config.llm.models)
                self._logger.error(
                    "-m model %r not found in config.yaml models: %s", model, valid
                )
                raise ValueError(
                    f"model {model!r} not found in config.yaml models: {valid}"
                )
        self._memory_db_uri = self._config.db_uri
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, AgentSession] = {}
        self._mcp_clients: dict[str, MCPClient] = {}  # session_id -> mcp_client
        self._tools: dict[str, list[dict]] = {}  # session_id -> tools
        self._cancel_events: dict[str, asyncio.Event] = {}  # session_id -> cancel_event
        self._state_accumulators: dict[
            str, dict
        ] = {}  # session_id -> partial state for cancellation
        self._tool_call_ids: dict[
            str, str
        ] = {}  # session_id -> persistent terminal_id for stateful terminals
        self._prompt_tasks: dict[str, asyncio.Task] = {}
        self._config_values: dict[
            str, dict[str, str]
        ] = {}  # session_id -> {config_id: value}
        self._session_locks: dict[str, asyncio.Lock] = {}  # session_id -> prompt serialization
        self._session_loggers: dict[str, Logger] = {}  # session_id -> per-session logger
        self._notification_queue: list[dict] = []  # queued extension notifications

    def _default_model_value(self) -> str:
        model = self._model_override or next(iter(self._config.llm.models.values()), None)
        if not model:
            return ""
        return f"{model.provider_name}:{model.model_id}"

    def _default_model_identifier(self) -> str:
        model = self._model_override or next(iter(self._config.llm.models.values()), None)
        return model.model_id if model else ""

    def _logger_for(self, session_id: str) -> Logger:
        """Per-session logger, falling back to the agent-level logger."""
        return self._session_loggers.get(session_id, self._logger)

    async def _resolve_session(self, session_id: str) -> AgentSession | None:
        """Resolve session_id to the live AgentSession.

        The DB is the authority: compaction forks agent_idx inside a stable
        session_id, and get_max_agent_idx always reflects the newest fork.
        self._sessions is a cache of live objects; hydrate from the DB on a
        miss (process restart, prompt without new/load_session, or a second
        connection attaching to a session it did not create).

        A bare session_id resolves to the trunk HEAD (max agent_idx, fork 1);
        a three-part wire id names an exact agent (a fork).
        """
        try:
            parse_agent_id(session_id)
            agent_id = session_id
        except ValueError:
            max_idx = await AgentSession.get_max_agent_idx(
                session_id, memory_path=self._memory_db_uri
            )
            if max_idx < 1:
                return None
            agent_id = build_agent_id(session_id, max_idx)
        session = self._sessions.get(agent_id)
        if session is None:
            try:
                session = await AgentSession.load(
                    agent_id, memory_path=self._memory_db_uri
                )
            except ValueError:
                return None
            self._sessions[agent_id] = session
        return session

    async def _provision_session(self, session: AgentSession) -> None:
        """Bring per-session infrastructure up for a hydrated session.

        Resolution can return a session this agent instance never created
        (process restart, second connection, prompt without new/load). The
        react loop needs an MCP client, tools, cancel event, logger, and
        config values per session_id — spin them up on first use. Idempotent.
        Keyed by WIRE id: the trunk's bare session_id, a fork's agent_id.
        """
        session_id = wire_session_id(session.agent_id)
        if session_id in self._tools:
            return
        # No builtin MCP fallback: a hydrated session that no client handed
        # mcp_servers for runs toolless until a load/new_session provides them.
        config, mcp_client = create_mcp_client_from_acp(
            mcp_servers=None,
            cwd=session.cwd,
            logger=self._logger,
        )
        if mcp_client is not None:
            mcp_client = await self._exit_stack.enter_async_context(mcp_client)
        tools = await get_tools(mcp_client)
        self._logger.info(
            "Provisioning hydrated session %s (agent %s) — no client mcp_servers, %d tools",
            session_id,
            session.agent_id,
            len(tools),
        )
        self._mcp_clients[session_id] = mcp_client
        self._tools[session_id] = tools
        self._cancel_events[session_id] = asyncio.Event()
        self._session_loggers[session_id] = setup_logger(
            self._config.config_dir / "logs" / f"crow-cli-{session_id}.log",
            name=f"{session_id}-crow-logger",
        )
        self._config_values.setdefault(
            session_id, {"model": self._default_model_value()}
        )

    def _get_config_options(self, session_id: str) -> list[SessionConfigOptionSelect]:
        """Generate the config options for a session based on current values."""
        options_list: list[SessionConfigSelectOption] = []
        for model in self._config.llm.models.values():
            options_list.append(
                SessionConfigSelectOption(
                    value=f"{model.provider_name}:{model.model_id}",
                    name=model.name,
                    description=model.model_id,
                )
            )

        current_vals = self._config_values.get(session_id, {})
        default_model = self._default_model_value()
        current_model = current_vals.get("model", default_model)

        return [
            SessionConfigOptionSelect(
                type="select",
                id="model",
                name="Model",
                category="model",
                current_value=current_model,
                options=options_list,
            )
        ]

    def _apply_model_option(self, session_id: str, value: str, session) -> None:
        """Apply the session's model config option (ACP session config options).

        The ONE code path for "this session now uses model X" — shared by
        session/set_config_option and the -m override at load/fork time.
        Stores the provider:model value (provider routing + the option's
        currentValue) AND points session.model_identifier at the model,
        because that is what react.py sends to the API. Doing only one of
        the two makes the option display a model the request doesn't use.
        """
        self._config_values.setdefault(session_id, {})["model"] = value
        _, model_name = value.split(":", 1) if ":" in value else ("", value)
        session.model_identifier = model_name

    def on_connect(self, conn: Client) -> None:
        """Store connection for sending updates"""
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        """Handle ACP initialization"""
        self._logger.info("Initializing Agent")
        self._logger.info(f"Client capabilities: {client_capabilities}")
        self._logger.info(f"Client info: {client_info}")

        self._client_capabilities = client_capabilities
        self._logger.info(f"Client capabilities: {client_capabilities}")
        # Check if client supports terminals
        if client_capabilities and getattr(client_capabilities, "terminal", False):
            self._logger.info(
                "Client supports ACP terminals - will use client-side terminal"
            )
        else:
            self._logger.info(
                "Client does NOT support ACP terminals - will use MCP terminal"
            )

        # Get command and args of current process for terminal-auth
        command = sys.argv[0]
        if os.path.basename(command).startswith("crow-cli"):
            args = []
        else:
            # Find the crow-cli executable in argv and get args before it
            idx = next(
                (
                    i
                    for i, a in enumerate(sys.argv)
                    if os.path.basename(a).startswith("crow-cli")
                ),
                None,
            )
            args = sys.argv[1 : idx + 1] if idx is not None else []

        # Build terminal auth args
        terminal_args = args + ["auth"]

        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(
                load_session=True,  # We support session loading
                session_capabilities=SessionCapabilities(
                    list=SessionListCapabilities(),  # We support session/list
                    fork=SessionForkCapabilities(),  # We support session/fork (unstable)
                ),
                prompt_capabilities=PromptCapabilities(
                    image=True,  # We support image content blocks for vision models
                    audio=False,  # Not yet implemented
                    embedded_context=True,  # We support embedded resources
                ),
            ),
            auth_methods=[
                AuthMethodAgent(
                    id="none",
                    name="No Authentication Required",
                    description="This agent does not require authentication for FOSS deployments.",
                    field_meta={
                        "terminal-auth": {
                            "command": "uvx",
                            "args": ["--from", "crow-cli", "crow-cli", "acp"],
                            "label": "Crow Auth",
                            "env": {},
                            "type": "terminal",
                        }
                    },
                ),
            ],
            agent_info=Implementation(
                name="crow-cli",
                title="crow-cli",
                version=version("crow-cli"),
            ),
        )

    async def authenticate(
        self, method_id: str, **kwargs: Any
    ) -> AuthenticateResponse | None:
        """Handle authentication (no-op for now)"""
        self._logger.info("Authentication request: %s", method_id)
        return AuthenticateResponse()

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        """
        Create a new session with proper resource management.

        Uses AsyncExitStack to ensure MCP clients are cleaned up properly.
        Uses MCP servers from config, or builtin server as default.
        """
        self._logger.info("Creating new session in cwd: %s", cwd)

        ########################################
        #  system prompt initialization
        #  mcp servers == tools == system prompt
        # ######################################

        self._logger.info("new_session mcp_servers from ACP: %s", mcp_servers)

        # Client owns tool supply: use exactly what it passed (empty = zero tools)
        config, mcp_client = create_mcp_client_from_acp(
            mcp_servers=mcp_servers,
            cwd=cwd,
            logger=self._logger,
        )
        self._logger.info("new_session merged config from create_mcp_client_from_acp: %s", config)
        # CRITICAL: Use AsyncExitStack for lifecycle management
        if mcp_client is not None:
            mcp_client = await self._exit_stack.enter_async_context(mcp_client)

        # Get tools from MCP server ([] when the client passed none). The
        # task tool lives in the separate crow-mcp process, not here.
        tools = await get_tools(mcp_client)
        session = await make_agent_session(
            self._config,
            tools,
            self._default_model_identifier(),
            cwd,
        )

        # Store in-memory references keyed on agent_id / session_id
        self._sessions[session.agent_id] = session
        self._mcp_clients[session.session_id] = mcp_client
        self._tools[session.session_id] = tools
        # Task system round trip: the separate-process task tool reads the
        # parent's client-defined mcpServers from sqlite to pass them
        # through to the subagent's session/new.
        await session.client.set_agent_mcp_servers(
            session.agent_id, _mcp_servers_to_wire(mcp_servers)
        )
        self._cancel_events[session.session_id] = asyncio.Event()
        self._session_loggers[session.session_id] = setup_logger(
            self._config.config_dir / "logs" / f"crow-cli-{session.session_id}.log",
            name=f"{session.session_id}-crow-logger",
        )
        # Set default values for new session config
        default_model = self._default_model_value()
        self._config_values[session.session_id] = {"model": default_model}

        self._logger.info(
            "Created session: %s (session_id: %s) with %d tools",
            session.session_id,
            session.agent_id,
            len(tools),
        )
        self._logger_for(session.session_id).info(
            "Created session: %s (agent_id: %s) with %d tools",
            session.session_id,
            session.agent_id,
            len(tools),
        )

        config_options = self._get_config_options(session.session_id)

        # Send available commands update asynchronously
        if self._conn is not None:
            available_commands = [
                AvailableCommand(name=cmd["name"], description=cmd["description"])
                for cmd in _SLASH_COMMANDS
            ]
            asyncio.create_task(
                self._conn.session_update(
                    session_id=session.session_id,
                    update=AvailableCommandsUpdate(
                        session_update="available_commands_update",
                        available_commands=available_commands,
                    ),
                )
            )

        return NewSessionResponse(
            session_id=session.session_id, config_options=config_options
        )

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        **kwargs: Any,
    ) -> LoadSessionResponse | None:
        """Load an existing session with proper resource management."""
        self._logger.info("LOAD_SESSION: Loading session: %s", session_id)

        try:
            # A three-part wire id names an exact agent (a fork); a bare
            # session_id resolves to the trunk HEAD (max agent_idx, fork 1).
            try:
                parse_agent_id(session_id)
                agent_id = session_id
            except ValueError:
                max_idx = await AgentSession.get_max_agent_idx(session_id, memory_path=self._memory_db_uri)
                agent_id = build_agent_id(session_id, max_idx)
            self._logger.info(
                "LOAD_SESSION: Step 1: Loading agent %s from DB", agent_id
            )
            session = await AgentSession.load(
                agent_id,
                memory_path=self._memory_db_uri,
            )
            self._logger.info("LOAD_SESSION: Step 1 complete: Agent loaded from DB")

            # Setup MCP client (same as new_session): client owns tool supply
            self._logger.info("LOAD_SESSION: mcp_servers from ACP: %s", mcp_servers)
            config, mcp_client = create_mcp_client_from_acp(
                mcp_servers=mcp_servers,
                cwd=cwd,
                logger=self._logger,
            )
            self._logger.info("LOAD_SESSION merged config: %s", config)

            # CRITICAL: Use AsyncExitStack for lifecycle management
            if mcp_client is not None:
                mcp_client = await self._exit_stack.enter_async_context(mcp_client)

            # Get tools ([] when the client passed none). The task tool
            # lives in the separate crow-mcp process, not here.
            tools = await get_tools(mcp_client)

            # Store in-memory references keyed on agent_id / WIRE session id
            # (bare session for the trunk, agent_id for a fork).
            self._sessions[session.agent_id] = session
            self._mcp_clients[session_id] = mcp_client
            self._tools[session_id] = tools
            await session.client.set_agent_mcp_servers(
                session.agent_id, _mcp_servers_to_wire(mcp_servers)
            )
            self._cancel_events[session_id] = asyncio.Event()
            self._session_loggers[session_id] = setup_logger(
                self._config.config_dir / "logs" / f"crow-cli-{session.session_id}.log",
                name=f"{session.session_id}-crow-logger",
            )
            # Initialize session config if not present
            if session_id not in self._config_values:
                # Resolve model_identifier to "provider_name:model_id" format.
                # A -m override wins over the session's saved model: the CLI
                # flag is an explicit "use THIS model for this run".
                resolved = self._default_model_value()
                if self._model_override is not None:
                    if session.model_identifier != self._model_override.model_id:
                        self._logger.info(
                            "load_session: -m override %r supersedes saved model %r",
                            self._model_override.name,
                            session.model_identifier,
                        )
                    # The override IS this session's model config option:
                    # apply it exactly like session/set_config_option so the
                    # API request (react.py sends session.model_identifier)
                    # is routed at the override, not at the saved model.
                    self._apply_model_option(session_id, resolved, session)
                else:
                    if session.model_identifier:
                        match = next(
                            (
                                m
                                for m in self._config.llm.models.values()
                                if m.model_id == session.model_identifier
                            ),
                            None,
                        )
                        if match is not None:
                            resolved = f"{match.provider_name}:{match.model_id}"
                        else:
                            # Don't fall back silently: the session's behavior
                            # would change with no notice (critique item).
                            self._logger.warning(
                                "load_session: saved model %r is not in config.yaml; "
                                "falling back to default %r",
                                session.model_identifier,
                                resolved,
                            )
                    self._config_values[session_id] = {"model": resolved}

            # TODO: Replay conversation history to client

            config_options = self._get_config_options(session_id)
            return LoadSessionResponse(config_options=config_options)
        except Exception as e:
            self._logger.error("Failed to load session %s: %s", session_id, e)
            return None

    async def fork_session(
        self,
        session_id: str,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        additional_directories: list[str] | None = None,
        agentIdx: int | None = None,
        turnIdx: int | None = None,
        **kwargs: Any,
    ) -> ForkSessionResponse:
        """Fork an existing session (UNSTABLE session/fork).

        ``agentIdx``/``turnIdx`` ride the request ``_meta`` and arrive
        flattened into kwargs by the SDK router. Defaults fork at HEAD: the
        newest trunk agent, all messages. turnIdx snaps to turn boundaries —
        an assistant tool_calls group is never split from its tool results.
        The fork's wire sessionId is its own agent_id; the client owns tool
        supply exactly like new/load_session (empty mcpServers = zero tools,
        which is what an interrogation fork wants).
        """
        self._logger.info(
            "FORK_SESSION: %s agentIdx=%s turnIdx=%s cwd=%s mcp_servers=%s",
            session_id,
            agentIdx,
            turnIdx,
            cwd,
            mcp_servers,
        )
        try:
            session = await AgentSession.fork(
                session_id,
                memory_path=self._memory_db_uri,
                cwd=cwd,
                agent_idx=agentIdx,
                turn_idx=turnIdx,
            )
        except Exception as e:
            self._logger.error("Failed to fork session %s: %s", session_id, e)
            raise RequestError.invalid_params(
                f"cannot fork session '{session_id}': {e}"
            )

        wire_id = session.agent_id  # forks are addressed by their agent_id

        # Provision exactly like load_session: client owns tool supply.
        config, mcp_client = create_mcp_client_from_acp(
            mcp_servers=mcp_servers,
            cwd=cwd,
            logger=self._logger,
        )
        if mcp_client is not None:
            mcp_client = await self._exit_stack.enter_async_context(mcp_client)
        tools = await get_tools(mcp_client)

        self._sessions[session.agent_id] = session
        self._mcp_clients[wire_id] = mcp_client
        self._tools[wire_id] = tools
        await session.client.set_agent_mcp_servers(
            session.agent_id, _mcp_servers_to_wire(mcp_servers)
        )
        self._cancel_events[wire_id] = asyncio.Event()
        self._session_loggers[wire_id] = setup_logger(
            self._config.config_dir / "logs" / f"crow-cli-{session.session_id}.log",
            name=f"{session.session_id}-crow-logger",
        )
        # Model resolution: the fork inherits the source's model unless -m
        # overrides it; resolve to provider:model like load_session does.
        resolved = self._default_model_value()
        if self._model_override is not None:
            if session.model_identifier != self._model_override.model_id:
                self._logger.info(
                    "fork_session: -m override %r supersedes inherited model %r",
                    self._model_override.name,
                    session.model_identifier,
                )
            self._apply_model_option(wire_id, resolved, session)
        else:
            if session.model_identifier:
                match = next(
                    (
                        m
                        for m in self._config.llm.models.values()
                        if m.model_id == session.model_identifier
                    ),
                    None,
                )
                if match is not None:
                    resolved = f"{match.provider_name}:{match.model_id}"
            self._config_values[wire_id] = {"model": resolved}

        self._logger.info(
            "FORK_SESSION: created %s (forked_at=%s, %d messages in view, %d tools)",
            wire_id,
            session.forked_at,
            len(session.messages),
            len(tools),
        )
        return ForkSessionResponse(
            session_id=wire_id,
            config_options=self._get_config_options(wire_id),
        )

    async def set_session_mode(
        self, mode_id: str, session_id: str, **kwargs: Any
    ) -> SetSessionModeResponse | None:
        """Handle session mode changes (not implemented yet)"""
        self._logger.info("Set session mode: %s -> %s", session_id, mode_id)
        return SetSessionModeResponse()

    async def set_config_option(
        self, config_id: str, session_id: str, value: str, **kwargs: Any
    ) -> SetSessionConfigOptionResponse | None:
        """Handle config option changes"""
        self._logger.info(
            "Set session %s config option %s -> %s", session_id, config_id, value
        )

        session = await self._resolve_session(session_id)
        if session is None:
            self._logger.warning("set_config_option: unknown session %s", session_id)
            return None

        if config_id == "model":
            self._apply_model_option(session_id, value, session)
        else:
            self._config_values.setdefault(session_id, {})[config_id] = value

        config_options = self._get_config_options(session_id)
        return SetSessionConfigOptionResponse(config_options=config_options)

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        """
        Handle prompt request - main entry point for user messages.

        Directly iterates over react_loop without intermediate buffering.
        Cancellation is handled via try/except - state is persisted by react_loop.
        """
        session_logger = self._logger_for(session_id)
        session_logger.info("Prompt request for session: %s", session_id)
        if not self._config.is_configured:
            await self._conn.session_update(
                session_id=session_id,
                update=update_agent_message(text_block(SETUP_MESSAGE)),
            )
            return PromptResponse(stop_reason="end_turn")

        async def _execute_turn() -> PromptResponse:
            # Generate turn ID for this prompt (used for ACP tool call IDs)
            turn_id = str(uuid.uuid4())

            # Resolve session_id -> live AgentSession. The DB is the authority
            # (compaction forks agent_idx inside a stable session_id); the dict
            # is a cache, hydrated on miss. This is what lets one agent serve
            # many sessions — including ones it never created this process.
            session = await self._resolve_session(session_id)
            if session is None:
                session_logger.error("No session found for session_id=%s", session_id)
                return PromptResponse(stop_reason="error")

            # Hydrated sessions arrive bare — spin up their MCP client/tools.
            await self._provision_session(session)

            agent_id = session.agent_id

            # Build user message content (supports text, images, and resource links)
            user_content = await normalize_prompt(prompt, session_logger)
            # Skip if no valid content blocks were collected
            if not user_content:
                session_logger.warning("Empty user content - skipping message")
                return PromptResponse(stop_reason="error")

            # Check for slash commands (only for text-only messages)
            if len(user_content) == 1 and user_content[0].get("type") == "text":
                text = user_content[0].get("text", "")
                parsed = parse_slash_command(text)
                if parsed:
                    cmd_name, cmd_args = parsed
                    # Find and execute the command
                    for cmd in _SLASH_COMMANDS:
                        if cmd["name"] == cmd_name:
                            # Add user message to session
                            await session.add_message(
                                {"role": "user", "content": user_content}
                            )
                            result = await cmd["func"](session, cmd_args, self)
                            # Send response
                            await self._conn.session_update(
                                session_id=session.session_id,
                                update=update_agent_message(text_block(result)),
                            )
                            return PromptResponse(stop_reason="end_turn")
                    # Unknown command
                    await self._conn.session_update(
                        session_id=session.session_id,
                        update=update_agent_message(
                            text_block(
                                f"Unknown command: /{cmd_name}. Type /help for available commands."
                            )
                        ),
                    )
                    return PromptResponse(stop_reason="end_turn")

            # Add user message to session with content array (supports multimodal)
            await session.add_message({"role": "user", "content": user_content})

            # Clear cancel event for this new prompt
            cancel_event = self._cancel_events.get(session_id)
            if cancel_event:
                cancel_event.clear()

            # Initialize state accumulator for this prompt (for cancellation persistence)
            self._state_accumulators[session_id] = {
                "thinking": [],
                "content": [],
                "tool_calls": {},
            }

            tools = self._tools[session_id]

            # Stream chunks directly from react_loop - no queue, no latency
            try:
                current_config = self._config_values.get(session_id, {})
                current_model_value = (
                    current_config.get("model") or self._default_model_value()
                )
                provider_name = (
                    current_model_value.split(":", 1)[0]
                    if ":" in current_model_value
                    else ""
                )

                provider = self._config.llm.providers.get(provider_name)
                if not provider and self._config.llm.providers:
                    provider = next(iter(self._config.llm.providers.values()))
                    if provider_name:
                        self._logger.warning(
                            "provider %r from model selection %r not found in "
                            "config.yaml; falling back to %r",
                            provider_name,
                            current_model_value,
                            provider.name,
                        )
                if not provider:
                    raise RuntimeError(
                        "No LLM providers configured. Check ~/.agents/crow/config.yaml."
                    )

                llm = configure_llm(provider=provider, debug=self._config.chunk_log, logger=session_logger)

                def on_compact(old_agent_id: str, compacted_session: AgentSession):
                    """Register the forked agent so future prompts resolve to it.

                    No scalar bookkeeping: the next prompt re-resolves
                    session_id -> agent_id from the DB, which compaction
                    already updated before this callback fired.
                    """
                    self._sessions[compacted_session.agent_id] = compacted_session

                # Setup chunk log directory if chunk_log enabled
                chunk_log_dir = None
                if self._config.chunk_log:
                    chunk_log_dir = self._config.config_dir / "logs" / session.session_id
                    chunk_log_dir.mkdir(parents=True, exist_ok=True)

                async for chunk in react_loop(
                    conn=self._conn,
                    config=self._config,
                    client_capabilities=self._client_capabilities,
                    turn_id=turn_id,
                    mcp_clients=self._mcp_clients,
                    llm=llm,
                    tools=tools,
                    sessions=self._sessions,
                    agent_id=agent_id,
                    state_accumulators=self._state_accumulators,
                    on_compact=on_compact,
                    logger=session_logger,
                    hooks=self._hooks,
                    chunk_log_dir=chunk_log_dir,
                ):
                    chunk_type = chunk.get("type")

                    if chunk_type == "content":
                        await self._conn.session_update(
                            session_id=session.session_id,
                            update=update_agent_message(text_block(chunk["token"])),
                        )

                    elif chunk_type == "thinking":
                        await self._conn.session_update(
                            session_id=session.session_id,
                            update=update_agent_thought(text_block(chunk["token"])),
                        )

                    elif chunk_type == "tool_call":
                        name, first_arg = chunk["token"]
                        self._logger.debug("Tool call: %s(%s", name, first_arg)

                    elif chunk_type == "tool_args":
                        self._logger.debug("Tool args: %s", chunk["token"])

                    elif chunk_type == "compaction":
                        await self._conn.session_update(
                            session_id=session.session_id,
                            update=update_agent_message(text_block(chunk["token"])),
                        )

                    elif chunk_type == "final_history":
                        break

                return PromptResponse(stop_reason="end_turn")

            except asyncio.CancelledError:
                session_logger.info("Prompt cancelled")
                # State is already persisted by react_loop's cancellation handler
                raise

        # One turn at a time per session; distinct sessions run in parallel.
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())

        async def _locked_turn() -> PromptResponse:
            async with lock:
                return await _execute_turn()

        task = asyncio.create_task(_locked_turn())
        self._prompt_tasks[session_id] = task

        # 3. Await the task and handle the cancellation at the top level
        try:
            return await task
        except asyncio.CancelledError:
            session_logger.info(
                "Prompt gracefully stopped due to client cancellation"
            )
            return PromptResponse(stop_reason="cancelled")
        except Exception as e:
            session_logger.error("Error in prompt handling: %s", e, exc_info=True)
            # Surface the failure as an ACP JSON-RPC error (code -32603) instead
            # of a clean end_turn. A clean end_turn made the client think the
            # turn finished normally and re-fire the task/nag loop — so a
            # failing agent (e.g. LLM context overflow) got nagged thousands
            # of times. The acp SDK serializes a raised RequestError into an
            # error response; the client gates its task loop on that Err and
            # broadcasts the message to the user.
            raise RequestError.internal_error({"error": str(e)})
        finally:
            # 4. Cleanup the task reference when done
            self._prompt_tasks.pop(session_id, None)

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Handle cancellation by immediately cancelling the underlying Task."""
        self._logger_for(session_id).info("Cancel request for session: %s", session_id)

        task = self._prompt_tasks.get(session_id)
        if task and not task.done():
            task.cancel()

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle extension methods"""
        self._logger.info("Extension method: %s", method)
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle extension notifications"""
        self._logger.info("Extension notification: %s with params: %s", method, params)

        # Queue _send notifications for processing
        if method == "_send":
            if not hasattr(self, '_notification_queue'):
                self._notification_queue = []
            self._notification_queue.append(params)
            self._logger.info("Queued _send notification, queue size: %d", len(self._notification_queue))

    async def cleanup(self) -> None:
        """
        Cleanup all resources managed by this agent.

        The AsyncExitStack ensures all resources are cleaned up in reverse order
        of their creation, even if exceptions occur during cleanup.
        """
        self._logger.info("Cleaning up Agent resources")
        await self._exit_stack.aclose()
        self._logger.info("Cleanup complete")

    async def list_sessions(
        self, cursor: str | None = None, cwd: str | None = None, **kwargs: Any
    ) -> ListSessionsResponse:
        self._logger.info("Listing sessions for working directory: %s", cwd)
        if cwd is None:
            return ListSessionsResponse(sessions=[], next_cursor=None)

        page_size = 50
        offset = 0
        if cursor is not None:
            try:
                offset = int(json.loads(base64.b64decode(cursor)).get("offset", 0))
            except Exception:
                raise ValueError(f"Invalid session/list cursor: {cursor!r}")

        page, next_offset = await get_session_by_cwd(
            cwd, self._memory_db_uri, limit=page_size, offset=offset
        )
        sessions = [SessionInfo(**session) for session in page]
        next_cursor = (
            base64.b64encode(json.dumps({"offset": next_offset}).encode()).decode()
            if next_offset is not None
            else None
        )
        return ListSessionsResponse(sessions=sessions, next_cursor=next_cursor)


async def serve_http(
    config: Config, model: str | None, host: str, port: int
) -> None:
    """Serve the agent over Streamable HTTP + WebSocket (experimental, same
    JSON-RPC lifecycle as stdio). One AcpAgent instance per connection; all
    instances share the sqlite session store, so any client can address the
    same sessions."""
    import hypercorn.asyncio
    from acp.http.asgi import create_asgi_app
    from hypercorn.config import Config as HypercornConfig

    app = create_asgi_app(lambda conn: AcpAgent(config=config, model=model))
    hcfg = HypercornConfig()
    hcfg.bind = [f"{host}:{port}"]
    # Streamable HTTP requires HTTP/2; hypercorn negotiates h2c/h2.
    hcfg.alpn_protocols = ["h2", "http/1.1"]
    await hypercorn.asyncio.serve(app, hcfg)


async def agent_run(
    config_dir: Path | None = None,
    config: Config | None = None,
    config_file: Path | None = None,
    debug: bool = False,
    model: str | None = None,
    http: bool = False,
    host: str = "127.0.0.1",
    port: int = 2769,
) -> None:
    if config is None:
        config = Config.load(config_dir=config_dir)
        config = apply_config_overrides(config, config_file)
    if debug:
        config.chunk_log = True
    if http:
        await serve_http(config, model, host, port)
    else:
        # use_unstable_protocol: session/fork (and resume/close) are UNSTABLE
        # ACP methods — without the flag the router answers method_not_found.
        await run_agent(AcpAgent(config=config, model=model), use_unstable_protocol=True)


def main(
    config_dir: Path | None = None,
    config: Config | None = None,
    config_file: Path | None = None,
    debug: bool = False,
    model: str | None = None,
    http: bool = False,
    host: str = "127.0.0.1",
    port: int = 2769,
):
    asyncio.run(
        agent_run(
            config_dir=config_dir,
            config=config,
            config_file=config_file,
            debug=debug,
            model=model,
            http=http,
            host=host,
            port=port,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", type=Path, default=None)
    parser.add_argument("--config-file", type=Path, default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args()
    main(
        config_dir=args.config_dir,
        config_file=args.config_file,
        debug=args.debug,
        model=args.model,
    )
