#!/home/thomas/src/projects/mcp-testing/crow-acp/.venv/bin/python
"""
ACP-native Agent.

This is the single agent class that combines:
- ACP protocol implementation (from CrowACPAgent)
- Business logic (from old Agent)

No wrapper, no nested agents - just one clean Agent(acp.Agent) implementation.
"""

import asyncio
import json
import logging
from contextlib import AsyncExitStack
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
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
)
from fastmcp import Client as MCPClient
from json_schema_to_pydantic import create_model

from crow_acp.config import Config, get_default_config
from crow_acp.context import context_fetcher
from crow_acp.llm import configure_llm
from crow_acp.mcp_client import create_mcp_client_from_acp, get_tools
from crow_acp.session import Session, ensure_database

logger = logging.getLogger(__name__)


def maximal_deserialize(data):
    """
    Recursively drills into dictionaries and lists,
    deserializing any JSON strings it finds until
    no more strings can be converted to objects.
    """
    # 1. If it's a string, try to decode it
    if isinstance(data, str):
        try:
            # We strip it to avoid trying to load plain numbers/bools
            # as JSON if they are just "1" or "true"
            if data.startswith(("{", "[")):
                decoded = json.loads(data)
                # If it successfully decoded, recurse on the result
                # (to handle nested-serialized strings)
                return maximal_deserialize(decoded)
        except json.JSONDecodeError, TypeError, ValueError:
            # Not valid JSON, return the original string
            pass
        return data

    # 2. If it's a dictionary, recurse on its values
    elif isinstance(data, dict):
        return {k: maximal_deserialize(v) for k, v in data.items()}

    # 3. If it's a list, recurse on its elements
    elif isinstance(data, list):
        return [maximal_deserialize(item) for item in data]

    # 4. Return anything else as-is (int, float, bool, None)
    return data


class AcpAgent(Agent):
    """
    ACP-native agent - single agent class.

    This class:
    - Implements the ACP Agent protocol directly
    - Contains all business logic (react loop, tool execution)
    - Manages resources via AsyncExitStack
    - Stores minimal in-memory state (MCP clients, sessions)
    - Receives MCP servers from ACP client at runtime

    No wrapper, no nesting - just one clean implementation.
    """

    _conn: Client
    _cancel_events: dict[str, asyncio.Event] = {}  # session_id -> cancel_event

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
        self._config = config or get_default_config()
        self._db_path = self._config.database_path
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, Session] = {}
        self._session_id: str | None = None
        self._session: Session | None = None
        self._mcp_clients: dict[str, Any] = {}  # session_id -> mcp_client
        self._tools: dict[str, list[dict]] = {}  # session_id -> tools
        self._llm = configure_llm(debug=False)

        # Ensure DB tables exist and crow-v1 prompt is seeded
        ensure_database(self._db_path)

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

        session = Session.create(
            prompt_id="crow-v1",
            prompt_args={"workspace": cwd},
            tool_definitions=tools,
            request_params={"temperature": 0.2},
            model_identifier=self._config.llm.default_model,
            db_path=self._db_path,
        )

        # Store in-memory references
        self._sessions[session.session_id] = session
        self._session = session
        self._session_id = session.session_id
        self._mcp_clients[session.session_id] = mcp_client
        self._tools[session.session_id] = tools

        logger.info("Created session: %s with %d tools", session.session_id, len(tools))
        return NewSessionResponse(session_id=session.session_id, modes=None)

    async def load_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        session_id: str,
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

            # TODO: Replay conversation history to client

            return LoadSessionResponse()
        except Exception as e:
            logger.error("Failed to load session %s: %s", session_id, e)
            return None

    async def set_session_mode(
        self, mode_id: str, session_id: str, **kwargs: Any
    ) -> SetSessionModeResponse | None:
        """Handle session mode changes (not implemented yet)"""
        logger.info("Set session mode: %s -> %s", session_id, mode_id)
        return SetSessionModeResponse()

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

        This is where we run the react loop and stream updates back.
        """
        logger.info("Prompt request for session: %s", session_id)

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
                logging.info(f"block type: {type(block)}")
                uri = (
                    block.get("uri", "")
                    if isinstance(block, dict)
                    else getattr(block, "uri", "")
                )

                text_list.append(context_fetcher(uri))

        # Add user message to session
        session.add_message("user", " ".join(text_list))

        # Run agent loop and stream updates
        try:
            async for chunk in self._react_loop(session_id):
                chunk_type = chunk.get("type")

                if chunk_type == "content":
                    # Send agent message chunk
                    await self._conn.session_update(
                        session_id,
                        update_agent_message(text_block(chunk["token"])),
                    )

                elif chunk_type == "thinking":
                    # Send agent thought chunk (if client supports it)
                    await self._conn.session_update(
                        session_id,
                        update_agent_thought(text_block(chunk["token"])),
                    )

                elif chunk_type == "tool_call":
                    # Send tool call start
                    name, first_arg = chunk["token"]
                    # TODO: Send ToolCallStart notification
                    logger.debug("Tool call: %s(%s", name, first_arg)

                elif chunk_type == "tool_args":
                    # Send tool call progress
                    # TODO: Send ToolCallProgress notification
                    logger.debug("Tool args: %s", chunk["token"])

                elif chunk_type == "final_history":
                    # Done
                    break

            return PromptResponse(stop_reason="end_turn")

        except Exception as e:
            logger.error("Error in prompt handling: %s", e, exc_info=True)
            # Use 'end_turn' even on errors to satisfy ACP schema requirements
            return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Handle cancellation"""
        logger.info("Cancel request for session: %s", session_id)
        # TODO: Implement cancellation

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

    def _send_request(self, session_id: str):
        """
        Send request to LLM.

        Args:
            session_id: Session ID to get session data

        Returns:
            Streaming response from LLM
        """
        session = self._sessions[session_id]
        tools = self._tools[session_id]

        return self._llm.chat.completions.create(
            # model="glm-5",
            model="claude-opus-4-6",
            messages=session.messages,
            tools=tools,
            stream=True,
            parallel_tool_calls=True,
        )

    def _process_chunk(
        self,
        chunk,
        thinking: list[str],
        content: list[str],
        tool_calls: dict,
        tool_call_id: str | None,
    ) -> tuple[list[str], list[str], dict, str | None, tuple[str | None, Any]]:
        """
        Process a single streaming chunk.

        Args:
            chunk: Streaming chunk from LLM
            thinking: Accumulated thinking tokens
            content: Accumulated content tokens
            tool_calls: Accumulated tool calls
            tool_call_id: Current tool call ID

        Returns:
            Tuple of (thinking, content, tool_calls, tool_call_id, new_token)
        """
        delta = chunk.choices[0].delta
        new_token = (None, None)

        if not delta.tool_calls:
            if not hasattr(delta, "reasoning_content"):
                verbal_chunk = delta.content
                if verbal_chunk:
                    content.append(verbal_chunk)
                    new_token = ("content", verbal_chunk)
            else:
                reasoning_chunk = delta.reasoning_content
                if reasoning_chunk:
                    thinking.append(reasoning_chunk)
                    new_token = ("thinking", reasoning_chunk)
        else:
            for call in delta.tool_calls:
                if call.id is not None:
                    tool_call_id = call.id
                    if call.id not in tool_calls:
                        tool_calls[call.id] = {
                            "function_name": call.function.name,
                            "arguments": [call.function.arguments],
                        }
                        new_token = (
                            "tool_call",
                            (call.function.name, call.function.arguments),
                        )
                else:
                    arg_fragment = call.function.arguments
                    tool_calls[tool_call_id]["arguments"].append(arg_fragment)
                    new_token = ("tool_args", arg_fragment)

        return thinking, content, tool_calls, tool_call_id, new_token

    def _process_response(self, response):
        """
        Process streaming response from LLM.

        Args:
            response: Streaming response from LLM

        Yields:
            Tuple of (message_type, token) for each chunk

        Returns:
            Tuple of (thinking, content, tool_call_inputs, usage) when done
        """
        thinking, content, tool_calls, tool_call_id = [], [], {}, None
        final_usage = None

        for chunk in response:
            # Capture usage from the chunk (if present)
            if hasattr(chunk, "usage") and chunk.usage:
                final_usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }
            # Right here is where we aggregate for persistence and execution
            thinking, content, tool_calls, tool_call_id, new_token = (
                self._process_chunk(chunk, thinking, content, tool_calls, tool_call_id)
            )
            # And we yield so the streaming magic happens
            msg_type, token = new_token
            if msg_type:
                yield msg_type, token

        return (
            thinking,
            content,
            self._process_tool_call_inputs(tool_calls),
            final_usage,
        )

    def _process_tool_call_inputs(self, tool_calls: dict) -> list[dict]:
        """
        Process tool call inputs into OpenAI format.

        Args:
            tool_calls: Dictionary of tool calls

        Returns:
            List of tool call objects in OpenAI format
        """
        tool_call_inputs = []
        for tool_call_id, tool_call in tool_calls.items():
            tool_call_inputs.append(
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call["function_name"],
                        "arguments": "".join(tool_call["arguments"]),
                    },
                }
            )
        return tool_call_inputs

    async def _execute_tool_calls(
        self, session_id: str, tool_call_inputs: list[dict]
    ) -> list[dict]:
        """
        Execute tool calls via MCP.

        Args:
            session_id: Session ID to get MCP client
            tool_call_inputs: List of tool calls to execute

        Returns:
            List of tool results
        """

        mcp_client = self._mcp_clients[session_id]
        tool_results = []

        # tool_schema_map = {tool["name"]: tool for tool in tools}

        for tool_call in tool_call_inputs:
            tool_args = tool_call["function"]["arguments"]
            # logger.info(f"""TOOL-NAME: {tool_name}""")
            # logger.info(f"""TOOL-ARGS: {tool_args}""")
            try:
                arg_dict = maximal_deserialize(tool_args)

                result = await mcp_client.call_tool(
                    tool_call["function"]["name"],
                    arg_dict,
                )
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result.content[0].text,
                    }
                )
            except Exception as e:
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": f"Error: {str(e)}",
                    }
                )
        return tool_results

    async def _react_loop(self, session_id: str, max_turns: int = 50000):
        """
        Main ReAct loop.

        Args:
            session_id: Session ID to get session and tools
            max_turns: Maximum number of turns to execute

        Yields:
            Dictionary with 'type' and 'token' or 'messages' keys
        """
        session = self._sessions[session_id]

        for _ in range(max_turns):
            # Send request to LLM
            response = self._send_request(session_id)

            # Process streaming response
            gen = self._process_response(response)
            while True:
                try:
                    msg_type, token = next(gen)
                    yield {"type": msg_type, "token": token}
                except StopIteration as e:
                    thinking, content, tool_call_inputs, usage = e.value
                    break

            # If no tool calls, we're done
            if not tool_call_inputs:
                session.add_assistant_response(thinking, content, [], [])
                yield {"type": "final_history", "messages": session.messages}
                return

            # Execute tools
            tool_results = await self._execute_tool_calls(session_id, tool_call_inputs)

            # Add response to session
            session.add_assistant_response(
                thinking, content, tool_call_inputs, tool_results
            )


async def agent_run() -> None:
    logging.basicConfig(level=logging.INFO)
    await run_agent(AcpAgent())


def main():
    asyncio.run(agent_run())


if __name__ == "__main__":
    main()
