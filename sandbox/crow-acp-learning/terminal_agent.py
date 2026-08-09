"""
Terminal Agent - Executes user commands via ACP client terminal.

This agent receives text from the user, treats it as a shell command,
and executes it using the ACP client's terminal capability.

The terminal output streams live in the client UI.
"""

import asyncio
import logging
from contextlib import suppress
from typing import Any
from uuid import uuid4

from acp import (
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
    text_block,
    update_agent_message,
)
from acp.interfaces import Client
from acp.schema import (
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
)

logging.basicConfig(
    filename="/home/thomas/src/projects/mcp-testing/sandbox/crow-acp-learning/terminal-agent.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class TerminalAgent(Agent):
    """
    Agent that executes shell commands via ACP client terminal.

    Flow:
    1. User sends command as text
    2. Agent creates terminal via ACP client
    3. Agent sends ToolCallProgress with TerminalToolCallContent
    4. Client displays live terminal output
    5. Agent waits for exit, gets output, releases terminal
    6. Agent returns result summary
    """

    _conn: Client
    _client_capabilities: ClientCapabilities | None = None
    _sessions: dict[str, dict] = {}  # session_id -> session state
    _cancel_events: dict[str, asyncio.Event] = {}

    # Turn tracking for unique tool call IDs
    _current_turn_id: str | None = None

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        logger.info(f"Initializing TerminalAgent")
        logger.info(f"Client capabilities: {client_capabilities}")
        logger.info(f"Client info: {client_info}")

        self._client_capabilities = client_capabilities

        # Check if client supports terminals
        if client_capabilities and getattr(client_capabilities, "terminal", False):
            logger.info("Client supports ACP terminals!")
        else:
            logger.warning("Client does NOT support ACP terminals")

        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        **kwargs: Any,
    ) -> NewSessionResponse:
        session_id = uuid4().hex
        self._cancel_events[session_id] = asyncio.Event()
        self._sessions[session_id] = {
            "cwd": cwd,
            "turn_id": None,
        }
        logger.info(f"Created session {session_id} with cwd={cwd}")
        return NewSessionResponse(session_id=session_id)

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
        cancel_event = self._cancel_events.get(session_id)
        session_state = self._sessions.get(session_id, {})

        # Generate turn ID for this prompt
        turn_id = uuid4().hex
        session_state["turn_id"] = turn_id
        self._sessions[session_id] = session_state

        # Extract text from prompt
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

        command = " ".join(text_list).strip()

        if not command:
            await self._conn.session_update(
                session_id=session_id,
                update=update_agent_message(text_block("Error: No command provided")),
            )
            return PromptResponse(stop_reason="end_turn")

        logger.info(f"Executing command: {command}")

        # Check if client supports terminals
        if not (
            self._client_capabilities
            and getattr(self._client_capabilities, "terminal", False)
        ):
            await self._conn.session_update(
                session_id=session_id,
                update=update_agent_message(
                    text_block("Error: Client does not support ACP terminals")
                ),
            )
            return PromptResponse(stop_reason="end_turn")

        # Generate tool call ID
        tool_call_id = f"{turn_id}/terminal"

        terminal_id: str | None = None
        exit_status = None
        timed_out = False
        timeout_seconds = 30.0

        try:
            # 1. Send tool call start
            await self._conn.session_update(
                session_id=session_id,
                update=ToolCallStart(
                    session_update="tool_call",
                    tool_call_id=tool_call_id,
                    title=f"terminal: {command[:50]}{'...' if len(command) > 50 else ''}",
                    kind="execute",
                    status="pending",
                ),
            )

            # Check for cancellation
            if cancel_event and cancel_event.is_set():
                return PromptResponse(stop_reason="cancelled")

            # 2. Create terminal via ACP client
            logger.info(f"Creating terminal for command: {command}")
            cwd = session_state.get("cwd", "/tmp")

            terminal_response = await self._conn.create_terminal(
                command=command,
                session_id=session_id,
                cwd=cwd,
                output_byte_limit=100000,  # 100KB limit
            )

            terminal_id = terminal_response.terminal_id
            logger.info(f"Terminal created: {terminal_id}")

            # 3. Send tool call update with terminal content
            # This makes the client display live terminal output
            await self._conn.session_update(
                session_id=session_id,
                update=ToolCallProgress(
                    session_update="tool_call_update",
                    tool_call_id=tool_call_id,
                    status="in_progress",
                    content=[
                        TerminalToolCallContent(
                            type="terminal",
                            terminalId=terminal_id,
                        )
                    ],
                ),
            )

            # Check for cancellation
            if cancel_event and cancel_event.is_set():
                logger.info("Cancelled after terminal creation")
                return PromptResponse(stop_reason="cancelled")

            # 4. Wait for terminal to exit
            try:
                async with asyncio.timeout(timeout_seconds):
                    exit_response = await self._conn.wait_for_terminal_exit(
                        session_id=session_id,
                        terminal_id=terminal_id,
                    )
                    logger.info(f"Exit response: {exit_response}")
                    exit_code = exit_response.exit_code
                    signal = exit_response.signal
                    logger.info(
                        f"Terminal exited with exit code: {exit_code}\nand signal: {signal}"
                    )
            except TimeoutError:
                logger.warning(f"Terminal timed out after {timeout_seconds}s")
                timed_out = True
                # Kill the terminal
                await self._conn.kill_terminal(
                    session_id=session_id, terminal_id=terminal_id
                )

            # 5. Get final output
            output_response = await self._conn.terminal_output(
                session_id=session_id, terminal_id=terminal_id
            )
            output = output_response.output

            exit_code = exit_status.exit_code if exit_status else None
            exit_signal = exit_status.signal if exit_status else None

            truncated_note = (
                " Output was truncated." if output_response.truncated else ""
            )

            # 6. Send final tool call update
            final_status = (
                "failed"
                if (exit_code and exit_code != 0) or exit_signal or timed_out
                else "completed"
            )

            await self._conn.session_update(
                session_id=session_id,
                update=ToolCallProgress(
                    session_update="tool_call_update",
                    tool_call_id=tool_call_id,
                    status=final_status,
                ),
            )

            # 7. Build result message
            if timed_out:
                result_msg = (
                    f"⏱️ Command killed by timeout ({timeout_seconds}s){truncated_note}"
                )
            elif exit_signal:
                result_msg = (
                    f"⚠️ Command terminated by signal: {exit_signal}{truncated_note}"
                )
            elif exit_code not in (None, 0):
                result_msg = (
                    f"❌ Command failed with exit code: {exit_code}{truncated_note}"
                )
            else:
                result_msg = f"✅ Command executed successfully{truncated_note}"

            # Send result to user
            await self._conn.session_update(
                session_id=session_id,
                update=update_agent_message(text_block(result_msg)),
            )

            return PromptResponse(stop_reason="end_turn")

        except asyncio.CancelledError:
            logger.info("Prompt cancelled")
            return PromptResponse(stop_reason="cancelled")

        except Exception as e:
            logger.error(f"Error executing command: {e}", exc_info=True)

            # Send error to user
            await self._conn.session_update(
                session_id=session_id,
                update=update_agent_message(text_block(f"Error: {str(e)}")),
            )

            return PromptResponse(stop_reason="end_turn")

        finally:
            # 8. Release terminal if created
            if terminal_id:
                with suppress(Exception):
                    await self._conn.release_terminal(terminal_id=terminal_id)
                    logger.info(f"Released terminal: {terminal_id}")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Handle cancellation request."""
        logger.info(f"Cancel request for session: {session_id}")
        cancel_event = self._cancel_events.get(session_id)
        if cancel_event:
            cancel_event.set()
            logger.info(f"Cancel event set for session: {session_id}")


async def main() -> None:
    logger.info("Starting TerminalAgent")
    await run_agent(TerminalAgent())


if __name__ == "__main__":
    asyncio.run(main())
