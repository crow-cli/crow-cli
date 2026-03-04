#! /home/thomas/src/nid/crow-acp/.venv/bin/python
"""
Crow ACP Client - A transparent, observable agent client.

This is our microscope. Our Frankenstein monitor. Full visibility into:
- Session state (database)
- Message flow (what we send/receive)
- Agent behavior (logs, tool calls)

Usage:
    # Single-shot mode (default) - send prompt, get response, exit
    crow-client "list the files in this directory"

    # Interactive mode - REPL loop
    crow-client -i

    # Load existing session
    crow-client -s lumpy-energetic-hyrax-of-opportunity-77bcbd

    # Combine flags
    crow-client -i -s exuberant-grinning-nautilus-of-sunshine-9d3d35

    # Inspect database
    crow-client inspect
    crow-client inspect --session lumpy-energetic-hyrax-of-opportunity-77bcbd
"""

import asyncio
import sys
from typing import Any

from acp import (
    PROTOCOL_VERSION,
    Client,
    RequestError,
    connect_to_agent,
    text_block,
)
from acp.core import ClientSideConnection
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AudioContentBlock,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    ImageContentBlock,
    Implementation,
    PermissionOption,
    ReadTextFileResponse,
    ResourceContentBlock,
    TextContentBlock,
    ToolCall,
    ToolCallProgress,
    ToolCallStart,
    WriteTextFileResponse,
)
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class CrowClient(Client):
    """
    Minimal ACP client that streams agent output beautifully.
    """

    _last_chunk: AgentMessageChunk | AgentThoughtChunk | None = None
    _console: Console
    _tool_calls: dict[str, dict] = {}  # Track tool call metadata by ID

    def __init__(self, console: Console):
        self._console = console

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCall,
        **kwargs: Any,
    ) -> Any:
        raise RequestError.method_not_found("session/request_permission")

    async def write_text_file(
        self, content: str, path: str, session_id: str, **kwargs: Any
    ) -> WriteTextFileResponse | None:
        raise RequestError.method_not_found("fs/write_text_file")

    async def read_text_file(
        self, path: str, session_id: str, **kwargs: Any
    ) -> ReadTextFileResponse:
        raise RequestError.method_not_found("fs/read_text_file")

    async def session_update(
        self,
        session_id: str,
        update: AgentMessageChunk
        | AgentThoughtChunk
        | ToolCallStart
        | ToolCallProgress,
        **kwargs: Any,
    ) -> None:
        """Handle streaming updates from the agent."""
        if isinstance(update, AgentMessageChunk):
            if (
                self._last_chunk is None
                or isinstance(self._last_chunk, AgentThoughtChunk)
                or isinstance(self._last_chunk, (ToolCallStart, ToolCallProgress))
            ):
                # Transition to message output
                self._console.print()
                self._console.rule("[bold purple]Assistant[/bold purple]")
                self._console.print()

            self._last_chunk = update
            content = update.content
            text = self._extract_text(content)
            self._console.print(text, end="", style="purple", highlight=False)

        elif isinstance(update, AgentThoughtChunk):
            if (
                self._last_chunk is None
                or isinstance(self._last_chunk, AgentMessageChunk)
                or isinstance(self._last_chunk, (ToolCallStart, ToolCallProgress))
            ):
                # Transition to thinking output
                self._console.print()
                self._console.rule("[dim green]Thinking[/dim green]")
                self._console.print()

            self._last_chunk = update
            content = update.content
            text = self._extract_text(content)
            self._console.print(text, end="", style="dim green italic", highlight=False)

        elif isinstance(update, ToolCallStart):
            # Tool call started
            self._last_chunk = update
            icon = TOOL_ICONS.get(update.kind, TOOL_ICONS["other"])
            status = STATUS_ICONS.get(update.status, "⏳")
            self._console.print(f"\n{status} {icon} {update.title}", style="cyan")

        elif isinstance(update, ToolCallProgress):
            # Tool call progress/completion
            self._last_chunk = update
            icon = TOOL_ICONS.get(update.kind, TOOL_ICONS["other"])
            status = STATUS_ICONS.get(update.status, "⏳")
            style = (
                "green"
                if update.status == "completed"
                else "red"
                if update.status == "failed"
                else "yellow"
            )
            self._console.print(
                f"{status} {icon} {update.title or 'tool'}", style=style
            )

    def _extract_text(self, content: Any) -> str:
        """Extract text from various content block types."""
        if isinstance(content, TextContentBlock):
            return content.text
        elif isinstance(content, ImageContentBlock):
            return "<image>"
        elif isinstance(content, AudioContentBlock):
            return "<audio>"
        elif isinstance(content, ResourceContentBlock):
            return content.uri or "<resource>"
        elif isinstance(content, EmbeddedResourceContentBlock):
            return "<resource>"
        elif isinstance(content, dict):
            return content.get("text", "<content>")
        else:
            return "<content>"

    async def ext_method(self, method: str, params: dict) -> dict:
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict) -> None:
        raise RequestError.method_not_found(method)

    async def spawn_agent(self, cwd: str) -> asyncio.subprocess.Process:
        """Spawn the crow-acp agent subprocess."""
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "crow_cli.agent.main",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,  # Capture stderr for error reporting
            cwd=cwd,
        )
        if proc.stdin is None or proc.stdout is None:
            self._console.print("[red]Agent process does not expose stdio pipes[/red]")
            raise SystemExit(1)
        # Store stderr reader for later error reporting
        proc._stderr_reader = asyncio.create_task(proc.stderr.read())
        return proc

    async def send_prompt(
        self,
        conn: ClientSideConnection,
        session_id: str,
        prompt: str,
    ) -> None:
        """Send a single prompt and wait for completion."""
        self._console.print()
        self._console.print(
            Panel(
                f"[bold]{prompt}[/bold]", title="[cyan]You[/cyan]", border_style="cyan"
            )
        )
        self._console.print()

        await conn.prompt(
            session_id=session_id,
            prompt=[text_block(prompt)],
        )

        self._console.print()  # Final newline after agent response

    async def interactive_loop(
        self, conn: ClientSideConnection, session_id: str
    ) -> None:
        """Interactive REPL loop."""
        self._console.print(
            Panel(
                "[bold]Crow Interactive Mode[/bold]\n\n"
                "Type your message and press Enter to send.\n"
                "Press Ctrl+D or Ctrl+C to exit.",
                title="[magenta]🪶 Crow Client[/magenta]",
                border_style="magenta",
            )
        )

        while True:
            try:
                # Use rich prompt
                self._console.print()
                prompt_text = Text("crow> ", style="bold magenta")
                line = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: self._console.input(prompt_text)
                )
            except EOFError:
                self._console.print("\n[yellow]Goodbye![/yellow]")
                break
            except KeyboardInterrupt:
                self._console.print("\n[yellow]Goodbye![/yellow]")
                break

            if not line.strip():
                continue

            await self.send_prompt(conn, session_id, line)


async def connect_client(
    proc: asyncio.subprocess.Process, client: CrowClient
) -> ClientSideConnection:
    """Initialize ACP connection to agent."""
    try:
        conn = connect_to_agent(client, proc.stdin, proc.stdout)

        await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(),
            client_info=Implementation(
                name="crow-client",
                title="Crow Client",
                version="0.1.7",
            ),
        )
        return conn
    except Exception as e:
        # If connection fails, try to read stderr to show the actual error
        try:
            if hasattr(proc, "_stderr_reader") and not proc._stderr_reader.done():
                # Wait a moment for stderr to be available
                await asyncio.sleep(0.1)
                stderr_output = await proc._stderr_reader
                if stderr_output:
                    client._console.print()
                    client._console.print("[red]═══ Agent subprocess failed ═══[/red]")
                    client._console.print()
                    client._console.print(stderr_output.decode())
                    client._console.print()
                    client._console.print(
                        "[yellow]The agent subprocess exited with an error. "
                        "The traceback above shows what went wrong.[/yellow]"
                    )
        except Exception:
            # If we can't read stderr, just continue with the original error
            pass
        raise e
