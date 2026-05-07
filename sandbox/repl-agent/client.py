"""
Generic ACP client for REPL / IPython testing.

Usage:
    client = ReplClient("uv", "--project", "...", "run", "...", cwd="/some/path")
    await client.send("list files")
    print(client.conversation[client.session_id])  # programmatic access
    await client.close()

With MCP servers:
    from acp.schema import McpServerStdio, EnvVariable
    client = ReplClient(
        "uv", "--project", "...", "run", "main.py",
        mcp_servers=[
            McpServerStdio(
                name="iterative-refinement",
                command="uv",
                args=["--project", "/path/to/repl-agent", "run", "iterative_refinement_mcp.py"],
            ),
        ],
    )
"""

import asyncio
from pathlib import Path
from typing import Any, Mapping

from acp import (
    Client,
    RequestError,
    text_block,
)
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AudioContentBlock,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    EnvVariable,
    HttpHeader,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    PermissionOption,
    ReadTextFileResponse,
    ResourceContentBlock,
    SseMcpServer,
    TextContentBlock,
    ToolCall,
    ToolCallProgress,
    ToolCallStart,
    WriteTextFileResponse,
)
from acp.stdio import spawn_agent_process
from rich.console import Console
from rich.panel import Panel
from rich.text import Text


def stdio_mcp(
    name: str,
    command: str,
    *args: str,
    env: dict[str, str] | None = None,
) -> McpServerStdio:
    """Create an MCP stdio server config.

    Args:
        name: Server identifier (e.g. "iterative-refinement").
        command: Binary to run (e.g. "uv").
        args: Command arguments (e.g. "--project", ".", "run", "mcp_server.py").
        env: Optional environment variables.

    Returns:
        An ``McpServerStdio`` instance ready for ``ReplClient(mcp_servers=[...])``.
    """
    env_list = [EnvVariable(name=k, value=v) for k, v in (env or {}).items()]
    return McpServerStdio(
        name=name,
        command=command,
        args=list(args),
        env=env_list,
    )


class ReplClient(Client):
    """Generic ACP client where you specify the agent command."""

    _last_chunk: AgentMessageChunk | AgentThoughtChunk | None = None
    _console: Console
    _conn = None
    _process = None
    _session_id: str | None = None
    _spawn_cm = None
    _started = False

    # Conversation state: {session_id: [{"role": str, "content": str}]}
    conversation: dict[str, list[dict[str, str]]] = {}

    def __init__(
        self,
        agent_command: str,
        *agent_args: str,
        console: Console | None = None,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
    ):
        self.agent_command = agent_command
        self.agent_args = agent_args
        self.cwd = str(cwd) if cwd else None
        self.env = env
        self.mcp_servers = mcp_servers or []
        self._console = console or Console()
        self._response_buffer: str = ""
        self._thinking_buffer: str = ""

    # -- ACP Client interface stubs --

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
        if isinstance(update, AgentMessageChunk):
            if (
                self._last_chunk is None
                or isinstance(self._last_chunk, AgentThoughtChunk)
                or isinstance(self._last_chunk, (ToolCallStart, ToolCallProgress))
            ):
                self._console.print()
                self._console.rule("[bold purple]Assistant[/bold purple]")
                self._console.print()
            self._last_chunk = update
            text = self._extract_text(update.content)
            self._response_buffer += text
            self._console.print(text, end="", style="purple", highlight=False)

        elif isinstance(update, AgentThoughtChunk):
            if (
                self._last_chunk is None
                or isinstance(self._last_chunk, AgentMessageChunk)
                or isinstance(self._last_chunk, (ToolCallStart, ToolCallProgress))
            ):
                self._console.print()
                self._console.rule("[dim green]Thinking[/dim green]")
                self._console.print()
            self._last_chunk = update
            text = self._extract_text(update.content)
            self._thinking_buffer += text
            self._console.print(text, end="", style="dim green italic", highlight=False)

        elif isinstance(update, ToolCallStart):
            self._last_chunk = update
            self._console.print(f"\n⏳ {update.title}", style="cyan")

        elif isinstance(update, ToolCallProgress):
            self._last_chunk = update
            style = (
                "green"
                if update.status == "completed"
                else "red"
                if update.status == "failed"
                else "yellow"
            )
            self._console.print(f"{update.title or 'tool'}", style=style)

    def _extract_text(self, content: Any) -> str:
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
        return "<content>"

    async def ext_method(self, method: str, params: dict) -> dict:
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict) -> None:
        raise RequestError.method_not_found(method)

    # -- Lifecycle --

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def send(self, prompt_text: str) -> None:
        """Send a single prompt. Creates a new session on first use."""
        if not self._started:
            await self._start()

        self._console.print()
        self._console.print(
            Panel(
                f"[bold]{prompt_text}[/bold]",
                title="[cyan]You[/cyan]",
                border_style="cyan",
            )
        )
        self._console.print()

        # Clear response buffer before sending
        self._response_buffer = ""
        self._thinking_buffer = ""

        resp = await self._conn.prompt(
            session_id=self._session_id,
            prompt=[text_block(prompt_text)],
        )

        # Await remaining notification tasks that haven't finished yet.
        # These are the session_update handlers dispatched by the ACP connection.
        tasks = self._conn._conn._tasks._tasks
        pending_notifications = [
            t for t in tasks if t.get_name() == "acp.Dispatcher.notification"
        ]
        if pending_notifications:
            await asyncio.gather(*pending_notifications, return_exceptions=True)

        # Turn is complete — flush buffer into conversation state
        if self._session_id not in self.conversation:
            self.conversation[self._session_id] = []
        self.conversation[self._session_id].append(
            {
                "role": "user",
                "content": prompt_text,
            }
        )
        if self._response_buffer or self._thinking_buffer:
            self.conversation[self._session_id].append(
                {
                    "role": "assistant",
                    "content": self._response_buffer,
                    "reasoning_content": self._thinking_buffer,
                }
            )
        self._response_buffer = ""
        self._thinking_buffer = ""

        self._console.print()

    async def repl(self) -> None:
        """Run an interactive REPL loop."""
        self._console.print(
            Panel(
                "Type a message and press Enter. Ctrl+D/Ctrl+C to exit.",
                title="[magenta]Repl Client[/magenta]",
                border_style="magenta",
            )
        )
        while True:
            try:
                self._console.print()
                prompt_text = Text("repl> ", style="bold magenta")
                line = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: self._console.input(prompt_text)
                )
            except EOFError, KeyboardInterrupt:
                self._console.print("\n[yellow]Goodbye![/yellow]")
                break
            if not line.strip():
                continue
            await self.send(line)

    async def close(self) -> None:
        """Shutdown the agent subprocess and disconnect."""
        if self._spawn_cm is not None and self._conn is not None:
            await self._spawn_cm.__aexit__(None, None, None)
        self._started = False

    async def _start(self) -> None:
        """Spawn the agent, connect, and create a new session."""
        self._console.print(
            Panel(
                f"[bold]{self.agent_command}[/bold] {' '.join(self.agent_args)}",
                title="[yellow]Agent[/yellow]",
                border_style="yellow",
            )
        )
        spawn_cm = spawn_agent_process(
            self,
            self.agent_command,
            *self.agent_args,
            env=self.env,
            cwd=self.cwd,
        )
        self._spawn_cm = spawn_cm
        self._conn, self._process = await spawn_cm.__aenter__()

        await self._conn.initialize(
            protocol_version=1,
            client_capabilities=ClientCapabilities(),
            client_info=Implementation(
                name="repl-client",
                title="Repl Client",
                version="0.1.0",
            ),
        )
        print(self.mcp_servers)
        session = await self._conn.new_session(
            mcp_servers=self.mcp_servers, cwd=self.cwd or str(Path.cwd())
        )
        self._session_id = session.session_id
        self.conversation[self._session_id] = []
        self._console.print(f"[green]Session: {self._session_id}[/green]")
        self._started = True
