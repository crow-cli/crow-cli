"""
Minimal ACP test client that mimics crow-cli error handling.

Spawns agent as subprocess, captures stderr for error reporting,
and streams session updates back to user.
"""

import asyncio
import contextlib
import os
import sys
from pathlib import Path

from acp import PROTOCOL_VERSION, Client, connect_to_agent, text_block
from acp.core import ClientSideConnection
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ClientCapabilities,
    Implementation,
    ToolCallProgress,
    ToolCallStart,
)
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Tool icons
TOOL_ICONS = {
    "read": "📖",
    "edit": "✏️",
    "write": "📝",
    "delete": "🗑️",
    "move": "📦",
    "search": "🔍",
    "fetch": "🌐",
    "execute": "⚡",
    "other": "🔧",
}

STATUS_ICONS = {
    "pending": "⏳",
    "in_progress": "🔄",
    "completed": "✅",
    "failed": "❌",
}


class TestClient(Client):
    """Minimal ACP client for testing agent."""

    _last_chunk: (
        AgentMessageChunk | AgentThoughtChunk | ToolCallStart | ToolCallProgress | None
    ) = None
    _console: Console

    def __init__(self, console: Console):
        self._console = console

    async def session_update(
        self,
        session_id: str,
        update: AgentMessageChunk
        | AgentThoughtChunk
        | ToolCallStart
        | ToolCallProgress,
        **kwargs,
    ) -> None:
        """Stream agent output to console."""
        if isinstance(update, AgentMessageChunk):
            if self._last_chunk is None or isinstance(
                self._last_chunk, (AgentThoughtChunk, ToolCallStart, ToolCallProgress)
            ):
                self._console.print()
                self._console.rule("[bold purple]Assistant[/bold purple]")
                self._console.print()

            self._last_chunk = update
            text = (
                update.content.text
                if hasattr(update.content, "text")
                else str(update.content)
            )
            self._console.print(text, end="", style="purple", highlight=False)

        elif isinstance(update, AgentThoughtChunk):
            if self._last_chunk is None or isinstance(
                self._last_chunk, (AgentMessageChunk, ToolCallStart, ToolCallProgress)
            ):
                self._console.print()
                self._console.rule("[dim green]Thinking[/dim green]")
                self._console.print()

            self._last_chunk = update
            text = (
                update.content.text
                if hasattr(update.content, "text")
                else str(update.content)
            )
            self._console.print(text, end="", style="dim green italic", highlight=False)

        elif isinstance(update, ToolCallStart):
            self._last_chunk = update
            icon = TOOL_ICONS.get(update.kind, TOOL_ICONS["other"])
            status = STATUS_ICONS.get(update.status, "⏳")
            self._console.print(f"\n{status} {icon} {update.title}", style="cyan")

        elif isinstance(update, ToolCallProgress):
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

    async def ext_method(self, method: str, params: dict) -> dict:
        raise NotImplementedError

    async def ext_notification(self, method: str, params: dict) -> None:
        raise NotImplementedError


async def connect_client(proc, client):
    """Initialize ACP connection and handle errors."""
    try:
        conn = connect_to_agent(client, proc.stdin, proc.stdout)
        await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(),
            client_info=Implementation(
                name="test-client",
                title="Test Client",
                version="0.1.0",
            ),
        )
        return conn
    except Exception as e:
        # Try to read stderr to show agent error
        try:
            if hasattr(proc, "_stderr_reader") and not proc._stderr_reader.done():
                await asyncio.sleep(0.1)
                stderr_output = await proc._stderr_reader
                if stderr_output:
                    client._console.print()
                    client._console.print("[red]═══ Agent subprocess failed ═══[/red]")
                    client._console.print()
                    client._console.print(stderr_output.decode())
                    client._console.print()
                    client._console.print(
                        "[yellow]The agent subprocess exited with an error.[/yellow]"
                    )
        except Exception:
            pass
        raise


async def main():
    """Run test client."""
    console = Console()
    client = TestClient(console)

    # Get agent command and cwd
    agent_cmd = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "uv --project /home/thomas/src/nid/crow-cli run crow-cli"
    )
    cwd = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()

    # Parse command (handle spaces in agent command)
    import shlex

    agent_parts = shlex.split(agent_cmd)

    console.print(
        Panel(
            "[bold]Crow ACP Test Client[/bold]\n\n"
            f"Agent: [cyan]{agent_cmd}[/cyan]\n"
            f"Working directory: [cyan]{cwd}[/cyan]",
            title="[magenta]🪶 Crow Test Client[/magenta]",
            border_style="magenta",
        )
    )

    # Spawn agent subprocess
    proc = await asyncio.create_subprocess_exec(
        *agent_parts,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    if proc.stdin is None or proc.stdout is None:
        console.print("[red]Agent process does not expose stdio pipes[/red]")
        raise SystemExit(1)

    # Capture stderr for error reporting
    proc._stderr_reader = asyncio.create_task(proc.stderr.read())

    try:
        # Connect
        conn = await connect_client(proc, client)

        # Create session
        console.print("[cyan]Creating new session...[/cyan]")
        session = await conn.new_session(cwd=cwd, mcp_servers=[])
        console.print(f"[green]Session created: {session.session_id}[/green]")

        # Send prompt
        console.print()
        console.print(
            Panel(
                "[bold]say hello to a fellow agent. call the date command with terminal[/bold]",
                title="[cyan]You[/cyan]",
                border_style="cyan",
            )
        )

        await conn.prompt(
            session_id=session.session_id,
            prompt=[
                text_block(
                    "say hello to a fellow agent. call the date command with terminal"
                )
            ],
        )

        console.print()

    except Exception as e:
        # Try to get stderr before re-raising
        try:
            if hasattr(proc, "_stderr_reader") and not proc._stderr_reader.done():
                stderr_output = await proc._stderr_reader
                if stderr_output and stderr_output.strip():
                    console.print()
                    console.print("[red]═══ Agent subprocess failed ═══[/red]")
                    console.print()
                    console.print(stderr_output.decode())
        except Exception:
            pass
        raise

    finally:
        # Cleanup
        if proc.returncode is None:
            proc.terminate()
            with contextlib.suppress(ProcessLookupError):
                await proc.wait()


if __name__ == "__main__":
    asyncio.run(main())
