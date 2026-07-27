#! /home/thomas/src/nid/crow-acp/.venv/bin/python
"""
Crow ACP Client - A transparent, observable agent client.

This is our microscope. Our Frankenstein monitor. Full visibility into:
- AgentSession state (database)
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
import uuid
from datetime import datetime, timezone
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
    CreateTerminalResponse,
    EmbeddedResourceContentBlock,
    ImageContentBlock,
    Implementation,
    KillTerminalResponse,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    ResourceContentBlock,
    TerminalExitStatus,
    TerminalOutputResponse,
    TextContentBlock,
    ToolCall,
    ToolCallProgress,
    ToolCallStart,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)
from crow_cli.client.terminal import TerminalManager
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
    _task_list: list[dict] = []

    def __init__(self, console: Console):
        self._console = console
        self._task_list = []
        self._terminals = TerminalManager()

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
        if method == "task/read":
            return self._task_read()
        elif method == "task/write":
            return self._task_write(params)
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict) -> None:
        raise RequestError.method_not_found(method)

    # ─── Task management (client-side) ────────────────────────────────────

    def _task_read(self) -> dict:
        return {
            "tasks": self._task_list,
            "summary": self._format_task_summary(self._task_list),
        }

    def _task_write(self, params: dict) -> dict:
        todos = params.get("todos", [])
        now = datetime.now(timezone.utc).isoformat()
        tasks = []
        for i, todo in enumerate(todos):
            tasks.append({
                "id": str(uuid.uuid4()),
                "title": todo.get("content") or todo.get("title") or f"Task {i + 1}",
                "description": None,
                "status": todo.get("status", "pending"),
                "priority": todo.get("priority", "medium"),
                "assigned_to": todo.get("assignedTo"),
                "created_at": now,
                "updated_at": now,
            })
        self._task_list = tasks
        return {"tasks": tasks}

    # ─── Client-side terminal (ACP terminal/* methods) ────────────────────
    # The agent routes its `terminal` tool here once we advertise the
    # `terminal` capability (see connect_client). Commands run in a real PTY
    # so exit codes are correct and behavior roughly matches the IDE's
    # client-side terminals (lapce/zed).

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        env_dict = {e.name: e.value for e in (env or [])}
        terminal_id = self._terminals.create(
            command, cwd, env_dict, output_byte_limit
        )
        return CreateTerminalResponse(terminal_id=terminal_id)

    async def terminal_output(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> TerminalOutputResponse:
        term = self._terminals.get(terminal_id)
        if term is None:
            return TerminalOutputResponse(output="", truncated=False)
        output, truncated = term.output()
        exit_status = None
        if term.exited():
            exit_status = TerminalExitStatus(
                exit_code=term.exit_code, signal=term.signal_name
            )
        return TerminalOutputResponse(
            output=output, truncated=truncated, exit_status=exit_status
        )

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> WaitForTerminalExitResponse:
        term = self._terminals.get(terminal_id)
        if term is None:
            return WaitForTerminalExitResponse(exit_code=None, signal=None)
        exit_code, signal_name = await term.wait_exit()
        return WaitForTerminalExitResponse(exit_code=exit_code, signal=signal_name)

    async def kill_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> KillTerminalResponse:
        term = self._terminals.get(terminal_id)
        if term is not None:
            term.kill()
        return KillTerminalResponse()

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> ReleaseTerminalResponse:
        self._terminals.release(terminal_id)
        return ReleaseTerminalResponse()

    async def spawn_agent(self, cwd: str) -> asyncio.subprocess.Process:
        """Spawn the crow-acp agent subprocess."""
        # Check if running in PyInstaller frozen build
        is_frozen = getattr(sys, "frozen", False)

        if is_frozen:
            # For frozen builds, use the 'acp' subcommand
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "acp",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        else:
            # Development mode - use -m to run the module
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "crow_cli.agent.main",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
        """Send a single prompt and wait for completion, then nag on incomplete tasks."""
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

        self._console.print()

        # Nag loop: if the agent left incomplete tasks, keep prompting
        # until they're all done (or safety limit hit).
        for _ in range(50):
            incomplete = [
                t for t in self._task_list
                if t["status"] in ("pending", "in_progress")
            ]
            if not incomplete:
                break

            task_lines = "\n".join(
                f"- [{t['status']}] {t['title']}" for t in incomplete
            )
            nag = (
                f"You have {len(incomplete)} incomplete task(s):\n\n"
                f"{task_lines}\n\n"
                f'Call task_write with the full todos list, updating statuses '
                f'for completed tasks to "completed".'
            )

            self._console.print()
            self._console.rule("[dim yellow]Nag[/dim yellow]")
            self._console.print()

            await conn.prompt(
                session_id=session_id,
                prompt=[text_block(nag)],
            )

            self._console.print()

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
            # terminal=False: don't advertise the client-side PTY, so the agent's
            # `terminal` tool falls through to the crow-mcp MCP terminal tool
            # (agent-owned execution) instead of routing to create_terminal below.
            client_capabilities=ClientCapabilities(terminal=False),
            client_info=Implementation(
                name="crow-client",
                title="Crow Client",
                version="0.1.23",
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
