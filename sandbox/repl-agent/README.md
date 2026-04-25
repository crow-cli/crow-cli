# repl-agent

I've been meaning to put together a more configurable crow-cli `AcpAgent` for a while and this sandbox project does this.

This requires that the [system prompt](./crow/prompts/system_prompt.jinja2) be located inside the `{config_dir}/prompts/system_prompts.jinja2` location.


## Define AcpAgent and new configuration values
First we bring in our agent and use the defaults we have in `~/.crow`, but redirect to [sandbox/repl-agent/.crow](./.crow) so we can make breaking changes to the database schema, whatever we want, and it won't mess up the global `crow-cli` config directory.

[main.py](./main.py)
```python
import asyncio
import sys
from pathlib import Path

from acp import run_agent
from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.main import AcpAgent


async def agent_run() -> None:
    config_dir = get_default_config_dir()
    config = Config.load(config_dir=config_dir)
    # Move the home directory
    config.config_dir = Path(
        "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow"
    )
    config.db_uri = (
        "sqlite:////home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/crow.db"
    )
    config.MAX_COMPACT_TOKENS = 990_000
    agent = AcpAgent(config)

    await run_agent(agent)


def main():
    asyncio.run(agent_run())


if __name__ == "__main__":
    main()

```

this of course spins up an crow-cli `AcpAgent` when you run with 

```bash
cd sandbox/repl-agent && uv --project . run main.py
```

## Client
What really lets us do interesting things with Python scripts with the above agent is the following client that we need to bring into the `crow-cli.client` package as it is **very** similar to the ACP Client we use to run `uvx crow-cli run "{prompt}"`. It's a bit of a mouthful but it's worth just having the code again here imo. Small repo, large `README.md`

[client.py](./client.py)
```python
"""
Generic ACP client for REPL / IPython testing.

Usage:
    client = ReplClient("uv", "--project", "...", "run", "...", cwd="/some/path")
    await client.send("list files")
    print(client.conversation[client.session_id])  # programmatic access
    await client.close()
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
from acp.stdio import spawn_agent_process
from rich.console import Console
from rich.panel import Panel
from rich.text import Text


class ReplClient(Client):
    """Generic ACP client where you specify the agent command."""

    _last_chunk: AgentMessageChunk | AgentThoughtChunk | None = None
    _console: Console
    _conn = None
    _process = None
    _session_id: str | None = None
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
    ):
        self.agent_command = agent_command
        self.agent_args = agent_args
        self.cwd = str(cwd) if cwd else None
        self.env = env
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
            except (EOFError, KeyboardInterrupt):
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

        session = await self._conn.new_session(mcp_servers=[], cwd=self.cwd or ".")
        self._session_id = session.session_id
        self.conversation[self._session_id] = []
        self._console.print(f"[green]Session: {self._session_id}[/green]")
        self._started = True
```

## Bringing it all together, programmatic ACP

Which brings us to the end result of doing customization of the [`AcpAgent`](../../crow-cli/src/crow_cli/agent/main.py) in [main.py](./main.py) and being able to invoke from a simple client in python is the following script which passes messages between different crow-cli `AcpAgent`s


```python
"""Smoke test: ReplClient -> repl-agent main.py, verify conversation state."""

import asyncio

from client import ReplClient

AGENT_CMD = "uv"
AGENT_ARGS = (
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent",
    "run",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/main.py",
)


async def test():
    c = ReplClient(AGENT_CMD, *AGENT_ARGS)
    d = ReplClient(AGENT_CMD, *AGENT_ARGS)

    await c.send("what is agent client protocol?")
    await c.send("do you think it's any good?")
    await c.send(
        "summarize the conversation and the steps you have taken, call no tools. this is an interagent summary/compaction event."
    )

    print("\n=== Conversation State ===")
    conversation = c.conversation.get(c._session_id, [])
    last_message = conversation[-1]["content"]
    print(last_message)
    await d.send(last_message)
    await c.close()
    await d.close()


asyncio.run(test())

```


I wanted to put together something like the above in a format that actually maps to the `agent-client-protocol` agent specs and I did in [agent_client.py](../agent-client/agent_client.py), but I haven't yet brought the same pattern to this simple client, YET...
