#!/home/thomas/src/projects/mcp-testing/crow-acp/.venv/bin/python
"""
ACP-native Agent.

This is the single agent class that combines:
- ACP protocol implementation (from CrowACPAgent)
- Business logic (from old Agent)

No wrapper, no nested agents - just one clean Agent(acp.Agent) implementation.
"""

import asyncio
import os
import uuid
from contextlib import AsyncExitStack, suppress
from datetime import datetime
from pathlib import Path
from threading import ExceptHookArgs
from typing import Any

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
from acp.helpers import (
    ToolCallContentVariant,
    start_edit_tool_call,
    start_read_tool_call,
    text_block,
    tool_content,
    tool_diff_content,
    update_tool_call,
)
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    AudioContentBlock,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    ResourceContentBlock,
    SseMcpServer,
    TerminalToolCallContent,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    SessionConfigOption,
    SetSessionConfigOptionResponse,
)
from fastmcp import Client as MCPClient
from json_schema_to_pydantic import create_model
from sqlalchemy.engine.cursor import ResultProxy

from crow_acp import mcp_client
from crow_acp.config import Config, get_default_config, settings
from crow_acp.context import context_fetcher, get_directory_tree, maximal_deserialize
from crow_acp.llm import configure_llm
from crow_acp.logger import logger
from crow_acp.mcp_client import create_mcp_client_from_acp, get_tools
from crow_acp.react import react_loop
from crow_acp.session import Session, lookup_or_create_prompt
from crow_acp.tools import (
    execute_acp_edit,
    execute_acp_read,
    execute_acp_terminal,
    execute_acp_tool,
    execute_acp_write,
)


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
        self._config = config or settings
        self._db_path = self._config.database_path
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
        self._config_values: dict[str, dict[str, str]] = {}  # session_id -> {config_id: value}

    def _get_config_options(self, session_id: str) -> list[SessionConfigOption]:
        """Generate the config options for a session based on current values."""
        options_list = []
        for model in self._config.llm.models:
            options_list.append(dict(
                value=f"{model.provider}:{model.model}",
                name=f"{model.provider}/{model.model}",
                description=f"Model {model.model} from {model.provider}"
            ))

        current_vals = self._config_values.get(session_id, {})
        default_model = f"{self._config.llm.models[0].provider}:{self._config.llm.models[0].model}" if self._config.llm.models else ""
        current_model = current_vals.get("model", default_model)

        return [
            SessionConfigOption(dict(
                id="model",
                name="Model",
                category="model",
                type="select",
                currentValue=current_model,
                options=options_list
            ))
        ]

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
        logger.info("Initializing Agent")
        logger.info(f"Client capabilities: {client_capabilities}")
        logger.info(f"Client info: {client_info}")

        self._client_capabilities = client_capabilities
        logger.info(f"Client capabilities: {client_capabilities}")
        # Check if client supports terminals
        if client_capabilities and getattr(client_capabilities, "terminal", False):
            logger.info("Client supports ACP terminals - will use client-side terminal")
        else:
            logger.info("Client does NOT support ACP terminals - will use MCP terminal")

        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(
                load_session=True,  # We support session loading
            ),
            agent_info=Implementation(
                name="crow",
                title="Crow Agent",
                version="0.1.0",
            ),
        )

    async def authenticate(
        self, method_id: str, **kwargs: Any
    ) -> AuthenticateResponse | None:
        """Handle authentication (no-op for now)"""
        logger.info("Authentication request: %s", method_id)
        return AuthenticateResponse()

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        **kwargs: Any,
    ) -> NewSessionResponse:
        """
        Create a new session with proper resource management.

        Uses AsyncExitStack to ensure MCP clients are cleaned up properly.
        Uses MCP servers from config, or builtin server as default.
        """
        logger.info("Creating new session in cwd: %s", cwd)

        # Use default MCP config if no servers provided
        fallback_config = self._config.get_builtin_mcp_config()

        # Create MCP client (builtin if no servers provided)
        mcp_client = await create_mcp_client_from_acp(
            mcp_servers,
            cwd,
            fallback_config=fallback_config,
        )

        # CRITICAL: Use AsyncExitStack for lifecycle management
        mcp_client = await self._exit_stack.enter_async_context(mcp_client)

        # Get tools from MCP server
        tools = await get_tools(mcp_client)

        # Load prompt template and get or create prompt_id

        template_path = Path(__file__).parent / "prompts" / "system_prompt.jinja2"
        template = template_path.read_text()
        prompt_id = lookup_or_create_prompt(
            template, name="crow-default", db_path=self._db_path
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
            model_identifier=self._config.llm.models[0].model,
            db_path=self._db_path,
            cwd=cwd,
        )

        # Store in-memory references
        self._sessions[session.session_id] = session
        self._session = session
        self._session_id = session.session_id
        self._mcp_clients[session.session_id] = mcp_client
        self._tools[session.session_id] = tools
        self._cancel_events[session.session_id] = asyncio.Event()

        # Set default values for new session config
        default_model = f"{self._config.llm.models[0].provider}:{self._config.llm.models[0].model}" if self._config.llm.models else ""
        self._config_values[session.session_id] = {"model": default_model}

        logger.info("Created session: %s with %d tools", session.session_id, len(tools))
        
        config_options = self._get_config_options(session.session_id)
        return NewSessionResponse(session_id=session.session_id, config_options=config_options)

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        **kwargs: Any,
    ) -> LoadSessionResponse | None:
        """Load an existing session with proper resource management."""
        logger.info("Loading session: %s", session_id)

        try:
            # Load session from database
            session = Session.load(session_id, db_path=self._db_path)

            # Setup MCP client (same as new_session)
            # Use default config if no servers provided
            fallback_config = self._config.get_builtin_mcp_config()
            if fallback_config:
                mcp_client = await create_mcp_client_from_acp(
                    mcp_servers,
                    cwd,
                    fallback_config=fallback_config,
                )
            else:
                mcp_client = await create_mcp_client_from_acp(mcp_servers, cwd)

            # CRITICAL: Use AsyncExitStack for lifecycle management
            mcp_client = await self._exit_stack.enter_async_context(mcp_client)

            # Get tools
            tools = await get_tools(mcp_client)

            # Store in-memory references
            self._sessions[session_id] = session
            self._session = session
            self._session_id = session.session_id
            self._mcp_clients[session_id] = mcp_client
            self._tools[session_id] = tools
            self._cancel_events[session_id] = asyncio.Event()

            # Initialize session config if not present
            if session_id not in self._config_values:
                default_model = f"{self._config.llm.models[0].provider}:{self._config.llm.models[0].model}" if self._config.llm.models else ""
                self._config_values[session_id] = {"model": session.model_identifier or default_model}

            # TODO: Replay conversation history to client

            config_options = self._get_config_options(session_id)
            return LoadSessionResponse(config_options=config_options)
        except Exception as e:
            logger.error("Failed to load session %s: %s", session_id, e)
            return None

    async def set_session_mode(
        self, mode_id: str, session_id: str, **kwargs: Any
    ) -> SetSessionModeResponse | None:
        """Handle session mode changes (not implemented yet)"""
        logger.info("Set session mode: %s -> %s", session_id, mode_id)
        return SetSessionModeResponse()

    async def set_config_option(
        self, config_id: str, session_id: str, value: str, **kwargs: Any
    ) -> SetSessionConfigOptionResponse | None:
        """Handle config option changes"""
        logger.info("Set session %s config option %s -> %s", session_id, config_id, value)
        
        # Initialize if not set
        if session_id not in self._config_values:
            self._config_values[session_id] = {}
            
        self._config_values[session_id][config_id] = value
        
        # Update session model if the config changed was the model
        if config_id == "model" and session_id in self._sessions:
            session = self._sessions[session_id]
            # Optionally split back from provider:model
            if ":" in value:
                provider, model = value.split(":", 1)
                # Keep provider info if needed, or just set model identifier
                # In Session we typically save model_identifier. If we want it to be provider:model then this is fine
                session.model_identifier = value
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
        logger.info("Prompt request for session: %s", session_id)

        async def _execute_turn() -> PromptResponse:
            # Generate turn ID for this prompt (used for ACP tool call IDs)
            turn_id = str(uuid.uuid4())

            # Get session
            session = self._sessions.get(session_id)
            if not session:
                logger.error("Session not found: %s", session_id)
                return PromptResponse(stop_reason="cancelled")

            # Extract text from prompt blocks
            text_list = []
            for block in prompt:
                _type = (
                    block.get("type", "")
                    if isinstance(block, dict)
                    else getattr(block, "type", "")
                )
                if _type == "text":
                    text = (
                        block.get("text", "")
                        if isinstance(block, dict)
                        else getattr(block, "text", "")
                    )
                    text_list.append(text)
                elif _type == "resource_link":
                    logger.info(f"block type: {type(block)}")
                    uri = (
                        block.get("uri", "")
                        if isinstance(block, dict)
                        else getattr(block, "uri", "")
                    )
                    text_list.append(context_fetcher(uri))

            # Add user message to session
            session.add_message("user", " ".join(text_list))

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
                default_model = f"{self._config.llm.models[0].provider}:{self._config.llm.models[0].model}" if self._config.llm.models else "glm-5"
                current_model_value = current_config.get("model", default_model)
                if ":" in current_model_value:
                    provider_name, model_name = current_model_value.split(":", 1)
                else:
                    provider_name = self._config.llm.models[0].provider if self._config.llm.models else ""
                    model_name = current_model_value

                provider = self._config.llm.providers.get(provider_name)
                # Fallback to the first provider if requested one is not found
                if not provider and self._config.llm.providers:
                    provider = next(iter(self._config.llm.providers.values()))
                
                llm = configure_llm(provider=provider, debug=False)

                async for chunk in react_loop(
                    conn=self._conn,
                    config=self._config,
                    client_capabilities=self._client_capabilities,
                    turn_id=turn_id,
                    mcp_clients=self._mcp_clients,
                    llm=llm,
                    model=model_name,
                    tools=tools,
                    sessions=self._sessions,
                    cancel_event=self._cancel_events[session_id],
                    session_id=session_id,
                    state_accumulators=self._state_accumulators,
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
                        logger.debug("Tool call: %s(%s", name, first_arg)

                    elif chunk_type == "tool_args":
                        logger.debug("Tool args: %s", chunk["token"])

                    elif chunk_type == "final_history":
                        break

                return PromptResponse(stop_reason="end_turn")

            except asyncio.CancelledError:
                logger.info("Prompt cancelled")
                # State is already persisted by react_loop's cancellation handler
                raise

        task = asyncio.create_task(_execute_turn())
        self._prompt_tasks[session_id] = task

        # 3. Await the task and handle the cancellation at the top level
        try:
            return await task
        except asyncio.CancelledError:
            logger.info("Prompt gracefully stopped due to client cancellation")
            return PromptResponse(stop_reason="cancelled")
        except Exception as e:
            logger.error("Error in prompt handling: %s", e, exc_info=True)
            return PromptResponse(stop_reason="end_turn")
        finally:
            # 4. Cleanup the task reference when done
            self._prompt_tasks.pop(session_id, None)

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Handle cancellation by immediately cancelling the underlying Task."""
        logger.info("Cancel request for session: %s", session_id)

        task = self._prompt_tasks.get(session_id)
        if task and not task.done():
            task.cancel()  # <--- This forcefully interrupts the LLM stream!

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle extension methods"""
        logger.info("Extension method: %s", method)
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle extension notifications"""
        logger.info("Extension notification: %s", method)

    async def cleanup(self) -> None:
        """
        Cleanup all resources managed by this agent.

        The AsyncExitStack ensures all resources are cleaned up in reverse order
        of their creation, even if exceptions occur during cleanup.
        """
        logger.info("Cleaning up Agent resources")
        await self._exit_stack.aclose()
        logger.info("Cleanup complete")


async def agent_run() -> None:
    await run_agent(AcpAgent())


def main():
    asyncio.run(agent_run())


if __name__ == "__main__":
    main()
