"""
Minimal ACP agent to test client capabilities.

This agent simply echoes back what capabilities the client reports,
particularly whether the client supports terminals.
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
)


class CapabilityProbingAgent(Agent):
    _conn: Client
    _client_capabilities: ClientCapabilities | None = None
    _debug_file = None

    def on_connect(self, conn: Client) -> None:
        self._conn = conn
        # Open debug file for logging
        self._debug_file = open("/tmp/agent_debug.log", "w")
        self._debug(f"on_connect called, conn has methods: {[m for m in dir(conn) if not m.startswith('_')]}")

    def _debug(self, msg: str):
        """Write debug output to file, not stdout (which would pollute JSON-RPC)"""
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
        self._debug(f"client_capabilities type: {type(client_capabilities)}")
        self._debug(f"client_capabilities: {client_capabilities}")
        
        # Store for later inspection
        self._client_capabilities = client_capabilities
        
        # Print what we got
        if client_capabilities:
            self._debug(f"client_capabilities fields: {client_capabilities.model_dump()}")
        
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(
        self, cwd: str, mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio], **kwargs: Any
    ) -> NewSessionResponse:
        self._debug(f"new_session called with cwd={cwd}")
        self._debug(f"mcp_servers: {mcp_servers}")
        return NewSessionResponse(session_id=uuid4().hex)

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
        self._debug(f"prompt called with session_id={session_id}")
        
        # Build response showing what we discovered
        response_parts = []
        
        # Echo the user's message
        user_text = ""
        for block in prompt:
            text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
            user_text += text
        
        response_parts.append(f"You said: {user_text}\n\n")
        
        # Report client capabilities
        if self._client_capabilities:
            caps_dict = self._client_capabilities.model_dump()
            response_parts.append("## Client Capabilities\n\n")
            response_parts.append(f"```json\n{json.dumps(caps_dict, indent=2)}\n```\n\n")
            
            # Specifically check for terminal support
            has_terminal = getattr(self._client_capabilities, 'terminal', None)
            response_parts.append(f"**Terminal Support:** `{has_terminal}`\n\n")
            
            if has_terminal:
                response_parts.append("✅ Client supports ACP terminals!\n\n")
                response_parts.append("I can use `create_terminal()` to run shell commands.\n")
            else:
                response_parts.append("❌ Client does NOT support terminals.\n\n")
                response_parts.append("I would need a fallback shell tool.\n")
        else:
            response_parts.append("❌ No client capabilities received!\n\n")
        
        # Report client connection methods
        response_parts.append("## Client Connection Methods\n\n")
        client_methods = [m for m in dir(self._conn) if not m.startswith('_')]
        terminal_methods = [m for m in client_methods if 'terminal' in m.lower()]
        
        response_parts.append(f"All methods: `{client_methods}`\n\n")
        response_parts.append(f"Terminal methods: `{terminal_methods}`\n\n")
        
        # Send the response
        full_response = "".join(response_parts)
        self._debug(f"Sending response:\n{full_response}")
        
        chunk = update_agent_message(text_block(full_response))
        await self._conn.session_update(session_id=session_id, update=chunk, source="capability_prober")
        
        return PromptResponse(stop_reason="end_turn")


async def main() -> None:
    # No print statements - they pollute JSON-RPC stream
    await run_agent(CapabilityProbingAgent())


if __name__ == "__main__":
    asyncio.run(main())
