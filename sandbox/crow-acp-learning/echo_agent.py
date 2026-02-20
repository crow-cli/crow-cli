import asyncio
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname
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

logging.basicConfig(
    filename="/home/thomas/src/projects/mcp-testing/sandbox//crow-acp-learning/echo-agent.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class EchoAgent(Agent):
    _conn: Client
    sessions: {}
    _cancel_events: dict[str, asyncio.Event] = {}  # session_id -> cancel_event

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:

        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        **kwargs: Any,
    ) -> NewSessionResponse:
        session_id = uuid4().hex
        # Create cancel event for this session
        self._cancel_events[session_id] = asyncio.Event()
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
        # Get the cancel event for this session
        cancel_event = self._cancel_events.get(session_id)

        # Wait 30 seconds before processing - useful for testing cancel functionality
        logging.info(f"Starting 30 second delay for session {session_id}")
        try:
            # Use wait_for to allow cancellation during the sleep
            await asyncio.wait_for(
                cancel_event.wait(),
                timeout=5.0
            )
            # If we get here, cancel_event was set (cancel requested)
            logging.info(f"Cancelled during delay for session {session_id}")
            return PromptResponse(stop_reason="cancelled")
        except asyncio.TimeoutError:
            # Normal timeout - continue processing
            logging.info(f"Delay complete, processing prompt for session {session_id}")

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
            logging.info(f"Text list: {text_list}")
            chunk = update_agent_message(text_block(" ".join(text_list)))
            chunk.field_meta = {"echo": True}
            chunk.content.field_meta = {"echo": True}

            await self._conn.session_update(
                session_id=session_id, update=chunk, source="echo_agent"
            )
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Handle cancellation request"""
        logging.info(f"Cancel request for session: {session_id}")
        cancel_event = self._cancel_events.get(session_id)
        if cancel_event is None:
            logging.warning(f"Session not found for cancel: {session_id}")
            return
        # Signal cancellation
        cancel_event.set()
        logging.info(f"Cancel event set for session: {session_id}")

def number_lines(content: str) -> list[str]:
    return [f"{k + 1}\t {v}" for k, v in enumerate(content.split("\n"))]


def context_fetcher(uri: str) -> str:
    res = find_line_numbers(uri)
    if res["status"] == "success":
        # pull out everything before the #L
        file_uri = uri.split("#L")[0]
        file_path = uri_to_path(file_uri)
        with open(file_path, "r") as f:
            content = f.read()
        split_content = number_lines(content)
        start = res["start"]
        end = res["end"]
        if start is not None and end is not None:
            content = split_content[start - 1 : end]
        elif start is not None:
            content = split_content[start - 1 :]
        elif end is not None:
            content = split_content[:end]
        else:
            content = split_content
    else:  # no line numbers, read whole file
        file_path = uri_to_path(uri)
        with open(file_path, "r") as f:
            content = f.read()
        content = number_lines(content)

    return "\n".join(content)


def uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    return url2pathname(parsed.path)


def find_line_numbers(uri: str) -> dict[str, Any]:
    pattern = r"#L(\d+)?(?::(\d+))?$"
    match = re.search(pattern, uri)
    response = {}
    if match:
        start, end = match.groups()
        response["status"] = "success"
        response["start"] = int(start) if start else None
        response["end"] = int(end) if end else None
    else:
        response["status"] = "failure"
        response["start"] = None
        response["end"] = None
    return response


async def main() -> None:
    await run_agent(EchoAgent())


if __name__ == "__main__":
    asyncio.run(main())
