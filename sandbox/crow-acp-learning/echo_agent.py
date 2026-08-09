import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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
    AvailableCommand,
    AvailableCommandsUpdate,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    ResourceContentBlock,
    SessionConfigOption,
    SseMcpServer,
    TextContentBlock,
)

# Configure logging to file ONLY - no stderr output to avoid corrupting stdio protocol
log_file = Path("/home/thomas/src/projects/mcp-testing/sandbox/crow-acp-learning/echo-agent.log")
log_file.parent.mkdir(parents=True, exist_ok=True)

# Clear any existing handlers and configure file-only logging
logging.root.handlers = []
logging.basicConfig(
    filename=str(log_file),
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)
# Ensure no console output
logging.root.propagate = False


# Type for slash command functions
type EchoSlashCmdFunc = Callable[[str, str], None | Awaitable[None]]
"""A function that runs as an EchoAgent slash command."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SlashCommand[F: Callable[..., None | Awaitable[None]]]:
    name: str
    description: str
    func: F
    aliases: list[str]

    def slash_name(self):
        """/name (aliases)"""
        if self.aliases:
            return f"/{self.name} ({', '.join(self.aliases)})"
        return f"/{self.name}"


class SlashCommandRegistry[F: Callable[..., None | Awaitable[None]]]:
    """Registry for slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand[F]] = {}
        """Primary name -> SlashCommand"""
        self._command_aliases: dict[str, SlashCommand[F]] = {}
        """Primary name or alias -> SlashCommand"""

    def command(
        self,
        func: F | None = None,
        *,
        name: str | None = None,
        aliases: list[str] | None = None,
    ) -> F | Callable[[F], F]:
        """Decorator to register a slash command with optional custom name and aliases."""

        def _register(f: F) -> F:
            primary = name or f.__name__
            alias_list = list(aliases) if aliases else []

            cmd = SlashCommand[F](
                name=primary,
                description=(f.__doc__ or "").strip(),
                func=f,
                aliases=alias_list,
            )

            self._commands[primary] = cmd
            self._command_aliases[primary] = cmd

            for alias in alias_list:
                self._command_aliases[alias] = cmd

            return f

        if func is not None:
            return _register(func)
        return _register

    def find_command(self, name: str) -> SlashCommand[F] | None:
        return self._command_aliases.get(name)

    def list_commands(self) -> list[SlashCommand[F]]:
        """Get all unique primary slash commands."""
        return list(self._commands.values())


def parse_slash_command_call(user_input: str) -> tuple[str, str] | None:
    """
    Parse a slash command call from user input.

    Returns:
        Tuple of (command_name, args) if a slash command is found, else None.
    """
    user_input = user_input.strip()
    if not user_input or not user_input.startswith("/"):
        return None

    name_match = re.match(r"^\/([a-zA-Z0-9_-]+)", user_input)

    if not name_match:
        return None

    command_name = name_match.group(1)
    if (
        len(user_input) > name_match.end()
        and not user_input[name_match.end()].isspace()
    ):
        return None
    args = user_input[name_match.end() :].lstrip()
    return (command_name, args)


# Global slash command registry for EchoAgent
registry = SlashCommandRegistry[EchoSlashCmdFunc]()


@registry.command
async def help(args: str, session_id: str):
    """Show available slash commands"""
    commands = registry.list_commands()
    lines = ["Available slash commands:"]
    for cmd in commands:
        lines.append(f"  {cmd.slash_name()} - {cmd.description}")
    return "\n".join(lines)


@registry.command(aliases=["cls"])
async def clear(args: str, session_id: str):
    """Clear the session context"""
    logging.info(f"Clear command received for session {session_id}")
    return "Session context cleared."


@registry.command
async def stop(args: str, session_id: str):
    """Stop current operation"""
    logging.info(f"Stop command received for session {session_id}")
    return "Operation stopped."


@registry.command
async def info(args: str, session_id: str):
    """Show session information"""
    logging.info(f"Info command received for session {session_id}")
    return f"Session ID: {session_id}\nActive sessions: 1"


@registry.command
async def echo(args: str, session_id: str):
    """Echo back your message. Usage: /echo <message>"""
    return f"Echo: {args}" if args else "Echo: (no message)"


class EchoAgent(Agent):
    _conn: Client
    sessions: dict = {}
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
        session_config_options = SessionConfigOption(
            dict(
                id="model",
                name="Model",
                category="model",
                type="select",
                currentValue="google/gemini-3.1-pro-preview",
                options=[
                    dict(
                        value="google/gemini-3.1-pro-preview",
                        name="google/gemini-3.1-pro-preview",
                        description="good model",
                    )
                ],
            )
        )

        # Register available slash commands with the client
        available_commands = [
            AvailableCommand(name=cmd.name, description=cmd.description)
            for cmd in registry.list_commands()
        ]
        logging.info(f"Registered {len(available_commands)} commands for session {session_id}")

        # Send available commands update to client asynchronously after returning response
        # Using asyncio.create_task() ensures the response is returned immediately
        # and the notification is sent in the background
        if self._conn is not None:
            logging.info(f"Sending available commands update for session {session_id}")
            asyncio.create_task(
                self._conn.session_update(
                    session_id=session_id,
                    update=AvailableCommandsUpdate(
                        session_update="available_commands_update",
                        available_commands=available_commands,
                    ),
                )
            )
        else:
            logging.warning(f"Connection is None, cannot send available commands update for session {session_id}")

        return NewSessionResponse(
            session_id=session_id, config_options=[session_config_options]
        )

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
            await asyncio.wait_for(cancel_event.wait(), timeout=5.0)
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

                # Check for slash commands
                parsed = parse_slash_command_call(text)
                if parsed:
                    command_name, args = parsed
                    cmd = registry.find_command(command_name)
                    if cmd:
                        # Execute the command
                        result = await cmd.func(args, session_id)
                        chunk = update_agent_message(text_block(result))
                        chunk.field_meta = {"echo": True, "slash_command": True}
                        chunk.content.field_meta = {"echo": True, "slash_command": True}
                        await self._conn.session_update(
                            session_id=session_id, update=chunk, source="echo_agent"
                        )
                        return PromptResponse(stop_reason="end_turn")
                    else:
                        # Unknown command
                        response = f"Unknown command: /{command_name}. Type /help for available commands."
                        chunk = update_agent_message(text_block(response))
                        chunk.field_meta = {"echo": True}
                        chunk.content.field_meta = {"echo": True}
                        await self._conn.session_update(
                            session_id=session_id, update=chunk, source="echo_agent"
                        )
                        return PromptResponse(stop_reason="end_turn")

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
