"""
Test agent that demonstrates ACP terminal usage.

This agent:
1. Receives client capabilities (with terminal support)
2. Defines a terminal tool schema for the LLM
3. Actually executes commands via ACP terminal
4. Returns real output

No stubs - this really runs commands!
"""
import asyncio
import json
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
    tool_terminal_ref,
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
    TextContentBlock,
    ToolCallProgress,
    TerminalToolCallContent,
)


class TerminalTestAgent(Agent):
    _conn: Client
    _client_capabilities: ClientCapabilities | None = None
    _debug_file = None

    def on_connect(self, conn: Client) -> None:
        self._conn = conn
        self._debug_file = open("/tmp/terminal_test.log", "w")
        self._debug("TerminalTestAgent connected")

    def _debug(self, msg: str):
        if self._debug_file:
            self._debug_file.write(msg + "\n")
            self._debug_file.flush()

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        self._debug(f"initialize called")
        self._client_capabilities = client_capabilities
        
        if client_capabilities:
            self._debug(f"Client capabilities: {client_capabilities.model_dump()}")
            self._debug(f"Terminal support: {client_capabilities.terminal}")
        
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(
        self, cwd: str, mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio], **kwargs: Any
    ) -> NewSessionResponse:
        self._debug(f"new_session called with cwd={cwd}")
        return NewSessionResponse(session_id=uuid4().hex)

    def _get_terminal_tool_schema(self):
        """
        The JSON schema for the terminal tool.
        This is what we send to the LLM so it knows how to use the tool.
        """
        return {
            "type": "function",
            "function": {
                "name": "terminal",
                "description": "Execute a shell command in the workspace. Use this for running tests, installing packages, git operations, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute"
                        },
                        "cwd": {
                            "type": "string",
                            "description": "Working directory (optional, defaults to session cwd)"
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Timeout in seconds (optional, defaults to 30)",
                            "default": 30
                        }
                    },
                    "required": ["command"]
                }
            }
        }

    async def _execute_terminal_tool(self, command: str, cwd: str = None, timeout: float = 30.0):
        """
        Execute a terminal command via ACP.
        
        This is the real implementation - not a stub!
        """
        self._debug(f"Executing terminal command: {command}")
        
        if not self._client_capabilities or not self._client_capabilities.terminal:
            return {"error": "Client does not support terminals"}
        
        try:
            # Create terminal via ACP client
            self._debug(f"Calling create_terminal...")
            terminal = await self._conn.create_terminal(
                command=command,
                session_id=self._current_session_id,
                cwd=cwd,
                output_byte_limit=100000,  # 100KB limit
            )
            
            terminal_id = terminal.terminal_id
            self._debug(f"Terminal created: {terminal_id}")
            
            # Send progress update to client (shows terminal in UI)
            await self._conn.session_update(
                session_id=self._current_session_id,
                update=ToolCallProgress(
                    session_update="tool_call_update",
                    tool_call_id=self._current_tool_call_id,
                    status="in_progress",
                    content=[
                        TerminalToolCallContent(
                            type="terminal",
                            terminal_id=terminal_id,
                        )
                    ],
                ),
            )
            
            # Wait for command to complete with timeout
            try:
                async with asyncio.timeout(timeout):
                    exit_status = await self._conn.wait_for_terminal_exit(
                        terminal_id=terminal_id,
                        session_id=self._current_session_id,
                    )
                self._debug(f"Command completed with exit status: {exit_status}")
            except asyncio.TimeoutError:
                self._debug(f"Command timed out after {timeout}s")
                await self._conn.kill_terminal(
                    terminal_id=terminal_id,
                    session_id=self._current_session_id,
                )
                return {"error": f"Command timed out after {timeout}s"}
            
            # Get output
            output_response = await self._conn.terminal_output(
                terminal_id=terminal_id,
                session_id=self._current_session_id,
            )
            
            self._debug(f"Output: {output_response.output[:200]}...")
            
            # Return result
            result = {
                "output": output_response.output,
                "exit_code": exit_status.exit_code if exit_status else None,
                "signal": exit_status.signal if exit_status else None,
                "truncated": output_response.truncated,
                "terminal_id": terminal_id,
            }
            
            # Release terminal (cleanup!)
            await self._conn.release_terminal(
                terminal_id=terminal_id,
                session_id=self._current_session_id,
            )
            self._debug(f"Terminal released")
            
            return result
            
        except Exception as e:
            self._debug(f"Error executing terminal: {e}")
            import traceback
            traceback.print_exc(file=self._debug_file)
            return {"error": str(e)}

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
        self._current_session_id = session_id
        self._current_tool_call_id = f"tool_{uuid4().hex}"
        
        # Get user message
        user_text = ""
        for block in prompt:
            text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
            user_text += text
        
        self._debug(f"User said: {user_text}")
        
        # Build response
        response_parts = []
        
        # Show tool schema
        response_parts.append("## Terminal Tool Schema (sent to LLM)\n\n")
        response_parts.append("```json\n")
        response_parts.append(json.dumps(self._get_terminal_tool_schema(), indent=2))
        response_parts.append("\n```\n\n")
        
        # Execute a demo command
        if "test" in user_text.lower():
            # Run a test command
            response_parts.append("## Executing Test Command\n\n")
            response_parts.append("Running: `echo 'Hello from ACP terminal!' && pwd && ls -la | head -10`\n\n")
            
            result = await self._execute_terminal_tool(
                command="echo 'Hello from ACP terminal!' && pwd && ls -la | head -10",
                timeout=10.0
            )
        else:
            # Run a simple command
            response_parts.append("## Executing Demo Command\n\n")
            response_parts.append("Running: `echo 'Hello from ACP!' && date`\n\n")
            
            result = await self._execute_terminal_tool(
                command="echo 'Hello from ACP!' && date",
                timeout=5.0
            )
        
        # Show results
        if "error" in result:
            response_parts.append(f"**Error:** {result['error']}\n\n")
        else:
            response_parts.append("## Command Output\n\n")
            response_parts.append(f"**Exit Code:** `{result['exit_code']}`\n\n")
            response_parts.append(f"**Terminal ID:** `{result['terminal_id']}`\n\n")
            
            if result.get('truncated'):
                response_parts.append("⚠️ *Output was truncated*\n\n")
            
            response_parts.append("```\n")
            response_parts.append(result['output'])
            response_parts.append("\n```\n\n")
        
        # Send response
        full_response = "".join(response_parts)
        self._debug(f"Sending response: {full_response[:200]}...")
        
        chunk = update_agent_message(text_block(full_response))
        await self._conn.session_update(session_id=session_id, update=chunk, source="terminal_test")
        
        return PromptResponse(stop_reason="end_turn")


async def main() -> None:
    await run_agent(TerminalTestAgent())


if __name__ == "__main__":
    asyncio.run(main())
