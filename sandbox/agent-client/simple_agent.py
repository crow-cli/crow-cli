"""
Simple test agent - no WebSocket, just echo.
"""

import asyncio
import logging
from pathlib import Path
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

# Log to file, NOT stdio
log_file = Path(__file__).parent / "simple_agent.log"
logging.basicConfig(
    filename=str(log_file),
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class SimpleAgent(Agent):
    """Simple agent that just logs and echoes."""

    def __init__(self):
        logger.info("SimpleAgent.__init__()")
        self._conn: Client | None = None

    def on_connect(self, conn: Client) -> None:
        logger.info("SimpleAgent.on_connect()")
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        logger.info(f"SimpleAgent.initialize(protocol_version={protocol_version})")
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        **kwargs: Any,
    ) -> NewSessionResponse:
        logger.info(f"SimpleAgent.new_session(cwd={cwd})")
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
        logger.info(f"SimpleAgent.prompt(session_id={session_id})")

        for block in prompt:
            text = (
                block.get("text", "")
                if isinstance(block, dict)
                else getattr(block, "text", "")
            )
            logger.info(f"  Echoing: {text}")

            chunk = update_agent_message(text_block(f"Echo: {text}"))
            await self._conn.session_update(
                session_id=session_id, update=chunk, source="simple_agent"
            )

        logger.info("  Prompt complete")
        return PromptResponse(stop_reason="end_turn")


async def main() -> None:
    logger.info("Starting SimpleAgent")
    await run_agent(SimpleAgent())


if __name__ == "__main__":
    asyncio.run(main())
