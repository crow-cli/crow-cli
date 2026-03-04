"""
ACP-native Agent.

This is the single agent class that combines:
- ACP protocol implementation (from CrowACPAgent)
- Business logic (from old Agent)

No wrapper, no nested agents - just one clean Agent(acp.Agent) implementation.
"""

import asyncio
import base64
import mimetypes
import os
import sys
import uuid
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from acp import (
    PROTOCOL_VERSION,
    Agent,
    AuthenticateResponse,
    InitializeResponse,
    LoadSessionResponse,
    NewSessionResponse,
    PromptResponse,
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
    AuthMethod,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    ListSessionsResponse,
    McpServerStdio,
    PromptCapabilities,
    ResourceContentBlock,
    SessionConfigOption,
    SessionInfo,
    SetSessionConfigOptionResponse,
    SseMcpServer,
    TextContentBlock,
)
from fastmcp import Client as MCPClient

from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.context import get_directory_tree
from crow_cli.agent.llm import configure_llm
from crow_cli.agent.logger import setup_logger
from crow_cli.agent.mcp_client import create_mcp_client_from_acp, get_tools
from crow_cli.agent.prompt import normalize_prompt
from crow_cli.agent.react import react_loop
from crow_cli.agent.session import Session, get_session_by_cwd, lookup_or_create_prompt


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

    def __init__(self, config: Config | None = None) -> None:
        """
        Initialize the merged agent.

        Args:
            config: Configuration object. If None, uses defaults from env vars

        Sets up:
        - AsyncExitStack for resource management
        - In-memory dictionaries for sessions and MCP clients
        - LLM client from configuration
        """
        if not config:
            config_dir: Path = get_default_config_dir()
            config: Config = Config.load(config_dir=config_dir)
        self._config = config
        self._logger = setup_logger(self._config.config_dir / "logs" / "crow-cli.log")
        self._db_uri = self._config.db_uri
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, Session] = {}
        self._session_id: str | None = None
        self._session: Session | None = None
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

    def _default_model_value(self) -> str:
        model = next(iter(self._config.llm.models.values()), None)
        if not model:
            return ""
        return f"{model.provider_name}:{model.model_id}"

    def _default_model_identifier(self) -> str:
        model = next(iter(self._config.llm.models.values()), None)
        return model.model_id if model else ""

    def _get_config_options(self, session_id: str) -> list[SessionConfigOption]:
        """Generate the config options for a session based on current values."""
        options_list: list[dict[str, str]] = []
        for model in self._config.llm.models.values():
            options_list.append(
                dict(
                    value=f"{model.provider_name}:{model.model_id}",
                    name=model.name,
                    description=model.model_id,
                )
            )

        current_vals = self._config_values.get(session_id, {})
        default_model = self._default_model_value()
        current_model = current_vals.get("model", default_model)

        return [
            SessionConfigOption(
                dict(
                    id="model",
                    name="Model",
                    category="model",
                    type="select",
                    currentValue=current_model,
                    options=options_list,
                )
            )
        ]

        # Ensure DB tables exist and crow-v1 prompt is seeded
        # ensure_database(self._db_uri)

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
        if command.endswith("crow-cli"):
            args = []
        else:
            # Find "crow-cli" in argv and get args before it
            try:
                idx = sys.argv.index("crow-cli")
                args = sys.argv[1 : idx + 1]
            except ValueError:
                # crow-cli not in argv, just use empty args
                args = []

        # Build terminal auth args
        terminal_args = args + ["auth"]

        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(
                load_session=True,  # We support session loading
                list_sessions=True,  # We support listing sessions
                prompt_capabilities=PromptCapabilities(
                    image=True,  # We support image content blocks for vision models
                    audio=False,  # Not yet implemented
                    embedded_context=True,  # We support embedded resources
                ),
            ),
            auth_methods=[
                AuthMethod(
                    id="none",
                    name="No Authentication Required",
                    description="This agent does not require authentication for FOSS deployments.",
                    field_meta={
                        "terminal-auth": {
                            "command": "uvx",
                            "args": ["crow-cli", "acp"],
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
                version="0.1.7",
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

        # Use default MCP config if no servers provided
        fallback_config = self._config.get_builtin_mcp_config()
        self._logger.info("fallback_config: %s", fallback_config)

        # Create MCP client (builtin if no servers provided)
        mcp_client = create_mcp_client_from_acp(
            mcp_servers=mcp_servers,
            cwd=cwd,
            fallback_config=fallback_config,
            logger=self._logger,
        )

        # CRITICAL: Use AsyncExitStack for lifecycle management
        mcp_client = await self._exit_stack.enter_async_context(mcp_client)

        # Get tools from MCP server
        tools = await get_tools(mcp_client)

        # Load prompt template and get or create prompt_id
        template_path = self._config.config_dir / "prompts" / "system_prompt.jinja2"
        template = template_path.read_text()
        prompt_id = lookup_or_create_prompt(
            template, name="crow-default", db_uri=self._db_uri
        )
        display_tree = get_directory_tree(cwd)
        agent_path = os.path.join(cwd, "AGENTS.md")
        if os.path.exists(agent_path):
            with open(agent_path, "r") as f:
                agents_content = f.read()
        else:
            agents_content = "No AGENTS.md found"

        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={
                "workspace": cwd,
                "display_tree": display_tree,
                "agents_content": agents_content,
            },
            tool_definitions=tools,
            request_params={"temperature": 0.2},
            model_identifier=self._default_model_identifier(),
            db_uri=self._db_uri,
            cwd=cwd,
        )

        # Store in-memory references
        self._sessions[session.session_id] = session
        self._session = session
        self._session_id = session.session_id
        self._mcp_clients[session.session_id] = mcp_client
        self._tools[session.session_id] = tools
        self._cancel_events[session.session_id] = asyncio.Event()
        self._session_logger = setup_logger(
            self._config.config_dir / "logs" / f"crow-cli-{self._session_id}.log",
            name=f"{self._session_id}-crow-logger",
        )
        # Set default values for new session config
        default_model = self._default_model_value()
        self._config_values[session.session_id] = {"model": default_model}

        self._logger.info(
            "Created session: %s with %d tools", session.session_id, len(tools)
        )
        self._session_logger.info(
            "Created session: %s with %d tools", session.session_id, len(tools)
        )

        config_options = self._get_config_options(session.session_id)

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
            # Load session from database
            self._logger.info("LOAD_SESSION: Step 1: Loading session from DB")
            session = Session.load(session_id, db_uri=self._db_uri)
            self._logger.info("LOAD_SESSION: Step 1 complete: Session loaded from DB")

            # Setup MCP client (same as new_session)
            # Use default config if no servers given
            self._logger.info("LOAD_SESSION: Step 2: Getting fallback config")
            fallback_config = self._config.get_builtin_mcp_config()
            self._logger.info(
                "LOAD_SESSION: Step 2 complete: fallback_config = %s", fallback_config
            )

            if fallback_config:
                self._logger.info(
                    "LOAD_SESSION: Step 3: Creating MCP client with fallback config"
                )
                mcp_client = create_mcp_client_from_acp(
                    mcp_servers=mcp_servers,
                    cwd=cwd,
                    fallback_config=fallback_config,
                    logger=self._logger,
                )
            else:
                mcp_client = create_mcp_client_from_acp(
                    mcp_servers=mcp_servers,
                    cwd=cwd,
                    fallback_config=[],
                    logger=self._logger,
                )
            self._logger.info("LOAD_SESSION: Step 3 complete: MCP client created")

            # CRITICAL: Use AsyncExitStack for lifecycle management
            self._logger.info("LOAD_SESSION: Step 4: Entering async context")
            mcp_client = await self._exit_stack.enter_async_context(mcp_client)
            self._logger.info(
                "LOAD_SESSION: Step 4 complete: MCP client context entered"
            )

            # Get tools
            tools = await get_tools(mcp_client)

            # Store in-memory references
            self._sessions[session_id] = session
            self._session = session
            self._session_id = session.session_id
            self._mcp_clients[session_id] = mcp_client
            self._tools[session_id] = tools
            self._cancel_events[session_id] = asyncio.Event()
            self._session_logger = setup_logger(
                self._config.config_dir / "logs" / f"crow-cli-{self._session_id}.log",
                name=f"{self._session_id}-crow-logger",
            )
            # Initialize session config if not present
            if session_id not in self._config_values:
                default_model = self._default_model_value()
                self._config_values[session_id] = {
                    "model": session.model_identifier or default_model
                }

            # TODO: Replay conversation history to client

            config_options = self._get_config_options(session_id)
            return LoadSessionResponse(config_options=config_options)
        except Exception as e:
            self._logger.error("Failed to load session %s: %s", session_id, e)
            return None

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

        # Initialize if not set
        if session_id not in self._config_values:
            self._config_values[session_id] = {}

        self._config_values[session_id][config_id] = value

        # Update session model if the config changed was the model
        if config_id == "model" and session_id in self._sessions:
            session = self._sessions[session_id]
            # Optionally split back from provider:model
            if ":" in value:
                _, model_name = value.split(":", 1)
                session.model_identifier = model_name
            else:
                session.model_identifier = value

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
        self._session_logger.info("Prompt request for session: %s", session_id)

        async def _execute_turn() -> PromptResponse:
            # Generate turn ID for this prompt (used for ACP tool call IDs)
            turn_id = str(uuid.uuid4())

            # Get session
            session = self._sessions.get(session_id)
            if not session:
                self._session_logger.error("Session not found: %s", session_id)
                return PromptResponse(stop_reason="cancelled")

            # Build user message content (supports text, images, and resource links)
            user_content = await normalize_prompt(prompt, self._session_logger)
            # Add user message to session with content array (supports multimodal)
            # Skip if no valid content blocks were collected
            if not user_content:
                self._session_logger.warning("Empty user content - skipping message")
                return PromptResponse(stop_reason="error")
            session.add_message({"role": "user", "content": user_content})

            # Clear cancel event for this new prompt
            cancel_event = self._cancel_events.get(session_id)
            if cancel_event:
                cancel_event.clear()

            # Initialize state accumulator for this prompt (for cancellation persistence)
            self._state_accumulators[session_id] = {
                "thinking": [],
                "content": [],
                "tool_call_inputs": [],
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
                if not provider:
                    raise RuntimeError(
                        "No LLM providers configured. Check ~/.crow/config.yaml."
                    )

                llm = configure_llm(provider=provider, debug=False)

                def on_compact(session_id: str, compacted_session: Session):
                    """Update sessions dict after compaction (needed for async task contexts)."""
                    self._sessions[session_id] = compacted_session

                async for chunk in react_loop(
                    conn=self._conn,
                    config=self._config,
                    client_capabilities=self._client_capabilities,
                    turn_id=turn_id,
                    mcp_clients=self._mcp_clients,
                    llm=llm,
                    tools=tools,
                    sessions=self._sessions,
                    session_id=session_id,
                    state_accumulators=self._state_accumulators,
                    on_compact=on_compact,
                    logger=self._session_logger,
                ):
                    chunk_type = chunk.get("type")

                    if chunk_type == "content":
                        await self._conn.session_update(
                            session_id,
                            update_agent_message(text_block(chunk["token"])),
                        )

                    elif chunk_type == "thinking":
                        await self._conn.session_update(
                            session_id,
                            update_agent_thought(text_block(chunk["token"])),
                        )

                    elif chunk_type == "tool_call":
                        name, first_arg = chunk["token"]
                        self._logger.debug("Tool call: %s(%s", name, first_arg)

                    elif chunk_type == "tool_args":
                        self._logger.debug("Tool args: %s", chunk["token"])

                    elif chunk_type == "final_history":
                        break

                return PromptResponse(stop_reason="end_turn")

            except asyncio.CancelledError:
                self._session_logger.info("Prompt cancelled")
                # State is already persisted by react_loop's cancellation handler
                raise

        task = asyncio.create_task(_execute_turn())
        self._prompt_tasks[session_id] = task

        # 3. Await the task and handle the cancellation at the top level
        try:
            return await task
        except asyncio.CancelledError:
            self._session_logger.info(
                "Prompt gracefully stopped due to client cancellation"
            )
            return PromptResponse(stop_reason="cancelled")
        except Exception as e:
            self._session_logger.error("Error in prompt handling: %s", e, exc_info=True)
            return PromptResponse(stop_reason="end_turn")
        finally:
            # 4. Cleanup the task reference when done
            self._prompt_tasks.pop(session_id, None)

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Handle cancellation by immediately cancelling the underlying Task."""
        self._session_logger.info("Cancel request for session: %s", session_id)

        task = self._prompt_tasks.get(session_id)
        if task and not task.done():
            task.cancel()  # <--- This forcefully interrupts the LLM stream!

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle extension methods"""
        self._logger.info("Extension method: %s", method)
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle extension notifications"""
        self._logger.info("Extension notification: %s", method)

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
        self._logger.info("Listing sessions for working directory: {cwd}", cwd=cwd)
        if cwd is None:
            return ListSessionsResponse(sessions=[], next_cursor=None)
        sessions_info = get_session_by_cwd(cwd, self._db_uri)
        sessions = [SessionInfo(**session) for session in sessions_info]
        return ListSessionsResponse(sessions=sessions, next_cursor=None)


async def agent_run() -> None:
    await run_agent(AcpAgent())


def main():
    asyncio.run(agent_run())


if __name__ == "__main__":
    main()
