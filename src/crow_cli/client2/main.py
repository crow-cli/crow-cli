"""The human-facing ACP v2 client: what ``crow-cli run`` drives a v2 agent with.

:mod:`crow_cli.client2.subagent` is a client too, and it is the right one for
the task system: it records the update stream, answers nothing, and hands back a
stop reason. At a terminal that is useless — the whole point of crow is that you
can watch it work — so this is the same protocol orchestration with a face on
it. The driver is reused, not reimplemented: :class:`TerminalClient` subclasses
:class:`~crow_cli.client2.subagent.HeadlessClient` so the record and the idle
queue stay in one place and only the rendering is new.

Three things a v2 client has to get right that v1 did not:

**The turn does not end when ``prompt`` returns.** ``PromptResponse`` is empty;
the outcome arrives later as an idle ``state_update``. The driver already waits
for it, so a prompt here blocks until the session says it is done. ``timeout``
is the escape hatch for a turn that does not end — a model that will not stop
calling tools, or an agent that never reports idle at all.

**Tool output has two audiences.** ``terminal_output_chunk`` and
``terminal_update.output`` are base64 PTY bytes for the human, ANSI intact, and
they go straight to ``sys.stdout.buffer``: rich would reinterpret the escapes it
is handed. The model's copy of the same bytes is the ANSI-stripped text in
``tool_call_update.raw_output``, and that is deliberately NOT rendered — showing
both is showing one thing twice.

**Nothing is silently dropped.** An update whose ``sessionUpdate`` this renderer
does not know prints its kind instead of vanishing. The protocol's union is
longer than any client's switch, and a new variant that renders as nothing is
indistinguishable from an agent that stopped talking.

What this is NOT: a permission surface (crow's agent never asks — it owns
execution), a NES client, or a TUI. There is no key handler, so a turn cannot be
cancelled from the REPL; Ctrl-C ends this process and the child dies with it.
Raw-mode input is ``tui2``'s job.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import sys
from typing import Any, Iterator, Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from acp.experimental import v2

from crow_cli.agents import AgentServer, tool_supply
from crow_cli.client2.subagent import (
    ChildExited,
    HeadlessClient,
    SubagentDriver,
    client_info,
    config_to_servers,
)
from crow_cli.config import Config
from crow_cli.discover import Connection

#: Tool kind -> icon, over v2's ToolKind vocabulary (``emitter.ToolKind``).
TOOL_ICONS = {
    "read": "📖",
    "edit": "✏️",
    "delete": "🗑️",
    "move": "📦",
    "search": "🔍",
    "fetch": "🌐",
    "execute": "⚡",
    "think": "🧠",
    "other": "🔧",
}

#: Tool-call status -> indicator.
STATUS_ICONS = {
    "pending": "⏳",
    "in_progress": "🔄",
    "completed": "✅",
    "failed": "❌",
    "cancelled": "🚫",
}


def dump_update(update: Any) -> dict:
    """The wire shape of an update — what ``-j`` emits, losslessly.

    The same flags the SDK serializes notifications with, so a JSONL line is
    the notification a client would have received rather than this renderer's
    opinion of it.
    """
    return update.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude_unset=True
    )


def diff_text(diff: Any) -> str:
    """A diff tool-call content as one ``operation path`` line per change.

    The patch itself is not printed: a unified diff dumped into a scrolling
    transcript buries the answer under it, and the bytes it describes already
    arrived over the terminal or as the edit's own content.
    """
    lines = []
    for change in getattr(diff, "changes", None) or ():
        operation = getattr(change, "operation", None) or type(change).__name__
        path = getattr(change, "path", None)
        old = getattr(change, "old_path", None)
        where = f"{old} -> {path}" if old and old != path else (path or "")
        lines.append(f"{operation} {where}".rstrip() + "\n")
    return "".join(lines)


def texts(content: Any) -> str:
    """The text of a content block, a list of them, or nothing.

    Chunks carry ONE block and whole-message updates carry a LIST, so both
    arrive here. Tool-call content arrives WRAPPED, and the wrapper is the
    thing a naive renderer prints: a ``content`` variant holds the block, a
    ``diff`` variant holds changes, a ``terminal`` variant is a reference to
    bytes that came over the terminal channel. Anything left renders as its
    type in angle brackets — an image is not text, and rendering it as nothing
    loses the fact that it was there.
    """
    if content is None:
        return ""
    if isinstance(content, (list, tuple)):
        return "".join(texts(item) for item in content)
    if isinstance(content, str):
        return content
    kind = getattr(content, "type", None)
    if kind == "text":
        return getattr(content, "text", "") or ""
    if kind == "content":
        return texts(getattr(content, "content", None))
    if kind == "diff":
        return diff_text(content)
    return f"<{kind or type(content).__name__}>"


class TerminalClient(HeadlessClient):
    """The client face a human sees: record everything, render most of it."""

    def __init__(self, console: Console, json_out: bool = False) -> None:
        super().__init__()
        self.console = console
        self.json_out = json_out
        #: What streamed last, so a transition between thinking and answering
        #: can draw a rule instead of running the two together.
        self._last: Optional[str] = None
        #: tool_call_id -> the fields a patch did not repeat. Updates are
        #: patches, so a title set on the first one is not on the last.
        self._tools: dict[str, dict] = {}
        #: Terminals this client already streamed bytes for. The snapshot in a
        #: ``terminal_update`` is for a client that was NOT watching; rendering
        #: it after the chunks is showing the same output twice.
        self._streamed: set[str] = set()
        #: True while a prompt THIS client sent is in flight. See ``own_echo``.
        self._our_prompt = False
        self.title: Optional[str] = None

    async def session_update(
        self, session_id: str, update: Any, **kwargs: Any
    ) -> None:
        # First: the record and the idle queue, which is what makes a prompt
        # return at all. Rendering is the second job and must not be able to
        # break it.
        await super().session_update(session_id, update, **kwargs)
        if self.json_out:
            self.emit(
                type="update", session_id=session_id, update=dump_update(update)
            )
            return
        self.render(update)

    # -- output ----------------------------------------------------------

    def emit(self, **event: Any) -> None:
        print(json.dumps(event, ensure_ascii=False), flush=True)

    def _raw(self, data: Optional[str]) -> None:
        """Base64 PTY bytes -> the terminal, ANSI intact.

        Not through rich: it parses markup and would eat the escapes, and the
        bytes are already formatted by whatever ran in the cell.
        """
        if not data:
            return
        sys.stdout.buffer.write(base64.b64decode(data))
        sys.stdout.buffer.flush()

    def _rule(self, label: str, style: str) -> None:
        if self._last == label:
            return
        self._last = label
        self.console.print()
        self.console.rule(f"[{style}]{label}[/{style}]")
        self.console.print()

    # -- rendering -------------------------------------------------------

    def render(self, update: Any) -> None:
        """One ``session/update``. Dispatched on the discriminator, not on
        isinstance: the union has 24 members and a variant this client has
        never seen should print its name, not fall through a type check into
        silence."""
        kind = getattr(update, "session_update", None) or ""
        handler = _RENDERS.get(kind)
        if handler is None:
            self.console.print(f"[dim]· {kind or type(update).__name__}[/dim]")
            return
        handler(self, update)

    def _message(self, update: Any, style: str, label: str) -> None:
        self._rule(label, style.split()[-1])
        text = texts(update.content)
        if text:
            self.console.print(text, end="", style=style, highlight=False, markup=False)

    def _agent_message(self, update: Any) -> None:
        self._message(update, "purple", "Assistant")

    def _thought(self, update: Any) -> None:
        self._message(update, "dim green italic", "Thinking")

    @contextlib.contextmanager
    def own_echo(self) -> Iterator[None]:
        """Suppress the agent's ``user_message`` echo for one prompt.

        v2 REQUIRES the agent to echo a prompt back as a ``user_message``
        carrying an agent-owned messageId — that is how a replay, a later
        correction, and a second client learn where the message landed in
        history. This client already printed what the human typed, so for the
        turn it sent, the echo is the same text a second time.

        Only ``user_message`` is suppressed, and only while the prompt is in
        flight. A replay emits it before anything is sent, so a resumed
        transcript still shows the human's side; a mailbox delivery is a
        ``user_message_chunk`` and stays rendered, because the model is about
        to answer something nobody typed here.
        """
        self._our_prompt = True
        try:
            yield
        finally:
            self._our_prompt = False

    def _user_message(self, update: Any) -> None:
        self._rule("You", "cyan")
        text = texts(update.content)
        if text:
            self.console.print(text, style="cyan", highlight=False, markup=False)

    def _user_echo(self, update: Any) -> None:
        if self._our_prompt:
            return
        self._user_message(update)

    def _tool_call(self, update: Any) -> None:
        known = self._tools.setdefault(update.tool_call_id, {})
        for field in ("name", "title", "kind", "status"):
            value = getattr(update, field, None)
            if value is not None:
                known[field] = value
        status = known.get("status", "pending")
        icon = TOOL_ICONS.get(known.get("kind", "other"), TOOL_ICONS["other"])
        title = known.get("title") or known.get("name") or update.tool_call_id
        style = {
            "completed": "green",
            "failed": "red",
            "cancelled": "yellow",
        }.get(status, "cyan")
        self._last = "tool"
        self.console.print(
            f"\n{STATUS_ICONS.get(status, '⏳')} {icon} {title}", style=style
        )
        if status == "failed":
            raw = getattr(update, "raw_output", None)
            detail = texts(raw) if raw is not None else ""
            if detail:
                self.console.print(detail[:2000], style="dim red", markup=False)

    def _tool_content(self, update: Any) -> None:
        text = texts(getattr(update, "content", None))
        if text:
            self.console.print(text, end="", style="dim", highlight=False, markup=False)

    def _terminal(self, update: Any) -> None:
        terminal_id = update.terminal_id
        if command := getattr(update, "command", None):
            self._last = "terminal"
            self.console.print(f"[dim]$ {command}[/dim]")
        output = getattr(update, "output", None)
        if output is not None and terminal_id not in self._streamed:
            self._raw(getattr(output, "data", None))
        exit_status = getattr(update, "exit_status", None)
        if exit_status is not None:
            code = getattr(exit_status, "exit_code", None)
            if code not in (None, 0):
                self.console.print(f"[dim red]exit {code}[/dim red]")

    def _terminal_chunk(self, update: Any) -> None:
        self._streamed.add(update.terminal_id)
        self._last = "terminal"
        self._raw(update.data)

    def _usage(self, update: Any) -> None:
        cost = getattr(update, "cost", None)
        extra = ""
        if cost is not None:
            extra = f" · {getattr(cost, 'amount', '?')} {getattr(cost, 'currency', '')}"
        self.console.print(
            f"\n[dim]context {update.used:,}/{update.size:,}{extra}[/dim]"
        )

    def _state(self, update: Any) -> None:
        state = getattr(update, "state", None)
        if state == "idle":
            reason = getattr(update, "stop_reason", None)
            self.console.print(f"\n[dim]idle{f' ({reason})' if reason else ''}[/dim]")
        elif state == "running":
            self._last = None
        else:
            # `requires_action`, and any state an agent invents: v2's state
            # enum is extensible, so the honest thing is to print what arrived
            # rather than fold it into idle or drop it.
            self.console.print(f"[dim yellow]state: {state}[/dim yellow]")

    def _session_info(self, update: Any) -> None:
        title = getattr(update, "title", None)
        if title:
            self.title = title
            self.console.print(f"[dim]session: {title}[/dim]")

    def _commands(self, update: Any) -> None:
        commands = getattr(update, "available_commands", None) or []
        names = ", ".join(getattr(c, "name", str(c)) for c in commands)
        self.console.print(f"[dim]commands: {names or 'none'}[/dim]")

    def _config_options(self, update: Any) -> None:
        # `id` became `config_id` in v2 — reading the v1 name here prints a
        # row of question marks and looks like an agent that published nothing.
        options = getattr(update, "config_options", None) or []
        current = ", ".join(
            f"{getattr(o, 'config_id', '?')}={getattr(o, 'current_value', None)}"
            for o in options
        )
        self.console.print(f"[dim]config: {current or 'none'}[/dim]")

    def _compaction(self, update: Any) -> None:
        status = getattr(update, "status", None)
        error = getattr(update, "error", None)
        self.console.print(
            f"[dim yellow]compaction {status}{f': {error}' if error else ''}[/dim yellow]"
        )

    def _compaction_chunk(self, update: Any) -> None:
        text = texts(getattr(update, "content", None))
        if text:
            self.console.print(text, end="", style="dim yellow", markup=False)

    def _notice(self, update: Any) -> None:
        """An agent-initiated banner: a severity, a title, optional detail.

        crow's agent emits none, so this is for an ``agent_servers`` entry
        that does. It is rendered rather than left to print its discriminator
        because a notice is not metadata about a turn — it is the only channel
        an agent has for something that happened outside one, and an ``error``
        severity reduced to ``· notice`` is a failure the human cannot act on.

        ``markup=False`` on both lines: the title and the description are the
        agent's text, and rich would eat anything in them that looks like a
        tag.
        """
        severity = getattr(update, "severity", "info")
        style = {"error": "red", "warning": "yellow"}.get(severity, "dim")
        self.console.print(
            f"{severity}: {getattr(update, 'title', '') or ''}",
            style=style, highlight=False, markup=False,
        )
        description = getattr(update, "description", None)
        if description:
            self.console.print(description, style=style, highlight=False, markup=False)


#: Discriminator -> renderer. A kind absent here prints its name (see
#: ``render``), so this table is what the client understands, not what the
#: protocol contains.
_RENDERS = {
    "agent_message_chunk": TerminalClient._agent_message,
    "agent_message": TerminalClient._agent_message,
    "agent_thought_chunk": TerminalClient._thought,
    "agent_thought": TerminalClient._thought,
    "user_message_chunk": TerminalClient._user_message,
    "user_message": TerminalClient._user_echo,
    "tool_call_update": TerminalClient._tool_call,
    "tool_call_content_chunk": TerminalClient._tool_content,
    "terminal_update": TerminalClient._terminal,
    "terminal_output_chunk": TerminalClient._terminal_chunk,
    "usage_update": TerminalClient._usage,
    "state_update": TerminalClient._state,
    "session_info_update": TerminalClient._session_info,
    "available_commands_update": TerminalClient._commands,
    "config_option_update": TerminalClient._config_options,
    "compaction_update": TerminalClient._compaction,
    "compaction_summary_chunk": TerminalClient._compaction_chunk,
    "notice": TerminalClient._notice,
}


class CrowClientV2:
    """One v2 agent, one session, driven for a human.

    The lifecycle ``crow-cli run`` needs: start whichever agent config named,
    open or re-attach a session, then send prompts until the human stops.

    Tool supply is handed to the agent at session creation because the CLIENT
    owns it: a v2 agent reads no config for tools, so whatever arrives here is
    exactly what the session gets, and an empty list is a session with no tools
    rather than an error.
    """

    def __init__(
        self,
        console: Console,
        json_out: bool = False,
        timeout: Optional[float] = None,
    ) -> None:
        self.console = console
        self.json_out = json_out
        #: A turn's ceiling. None waits forever, which is right for a human
        #: watching and wrong for a session parked on a long task.
        self.timeout = timeout
        self.client = TerminalClient(console, json_out)
        self.driver = SubagentDriver(
            client=self.client,
            info=client_info("crow-client", "Crow Client"),
        )
        self.session_id: Optional[str] = None

    def emit(self, **event: Any) -> None:
        """One JSONL event on the same channel the update stream uses.

        ``run_v2`` emits the lifecycle events (session, result) and the
        renderer emits the updates; both have to land on the one stdout a
        ``-j`` caller is parsing.
        """
        self.client.emit(**event)

    async def start(
        self,
        server: AgentServer,
        cwd: str,
        conn: Optional[Connection] = None,
    ) -> None:
        """Spawn the agent this server names and complete the handshake.

        ``conn`` is a child protocol discovery already spawned and asked; the
        driver adopts its streams instead of starting a second process.
        """
        await self.driver.start(cwd, argv=server.argv, env=server.env, conn=conn)

    async def open_session(
        self,
        cwd: str,
        mcp_servers: Optional[list] = None,
        session_id: Optional[str] = None,
        fork: bool = False,
        replay: bool = False,
    ) -> str:
        """Create, fork, or resume — and remember which session is current."""
        if fork:
            if not session_id:
                raise ValueError("--fork needs a session to fork")
            self.session_id = await self.driver.fork_session(
                session_id, cwd, mcp_servers=mcp_servers
            )
        elif session_id:
            await self.driver.resume_session(
                session_id, cwd, mcp_servers=mcp_servers, replay=replay
            )
            self.session_id = session_id
        else:
            self.session_id = await self.driver.new_session(
                cwd, mcp_servers=mcp_servers
            )
        return self.session_id

    async def set_model(self, model: str) -> None:
        """Choose the model over the wire, not in the agent's argv.

        The one path that reaches every agent: crow's own and an
        ``agent_servers`` entry written by somebody else alike.
        """
        if not self.session_id:
            raise ValueError("no session to configure")
        await self.driver.set_config_option(self.session_id, "model", model)

    async def send_prompt(self, text: str) -> Optional[str]:
        """One turn. Returns the stop reason the idle reported.

        The panel is this client's echo and the agent owes one too (see
        ``TerminalClient.own_echo``), so the agent's is held back for the
        length of the turn: one human, one message, one rendering of it.
        """
        if not self.json_out:
            self.console.print()
            self.console.print(
                Panel(
                    Text(text, style="bold"),
                    title="[cyan]You[/cyan]",
                    border_style="cyan",
                )
            )
            self.console.print()
        with self.client.own_echo():
            stop = await self.driver.prompt(
                self.session_id or "", text, timeout=self.timeout
            )
        if not self.json_out:
            self.console.print()
        return stop

    async def interactive_loop(self) -> None:
        """Read a line, run a turn, repeat. Ctrl-D or Ctrl-C leaves.

        Input runs in an executor so the event loop stays live while a human
        thinks — the update stream is being rendered the whole time, and a
        blocking ``input()`` would freeze it.
        """
        if not self.json_out:
            self.console.print(
                Panel(
                    "[bold]Crow Interactive Mode[/bold] · ACP v2\n\n"
                    "Type your message and press Enter to send.\n"
                    "Press Ctrl+D or Ctrl+C to exit.",
                    title="[magenta]🪶 Crow Client[/magenta]",
                    border_style="magenta",
                )
            )
        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await loop.run_in_executor(
                    None, lambda: self.console.input(Text("crow2> ", style="bold magenta"))
                )
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[yellow]Goodbye![/yellow]")
                return
            if not line.strip():
                continue
            try:
                await self.send_prompt(line)
            except TimeoutError as error:
                self.console.print(f"[yellow]{error}[/yellow]")
            except ChildExited as error:
                self.console.print(f"[red]{error}[/red]")
                return

    async def close(self) -> None:
        await self.driver.close()


async def run_v2(
    server: AgentServer,
    config: Config,
    *,
    console: Console,
    prompt: Optional[str] = None,
    interactive: bool = False,
    session_id: Optional[str] = None,
    fork: bool = False,
    cwd: Optional[str] = None,
    model: Optional[str] = None,
    json_out: bool = False,
    replay: bool = False,
    timeout: Optional[float] = None,
    conn: Optional[Connection] = None,
) -> None:
    """Drive one v2 agent for a human: spawn, open a session, run turns.

    ``server`` is the resolved ``agent_servers`` entry (or crow's own agent),
    and its argv is honored exactly as written — this function never adds flags
    to somebody else's command. Config pointers therefore ride crow's own argv
    only, baked in by :func:`crow_cli.agents.crow_agent_server`.

    The tool supply is the client's to give: the entry's own ``mcpServers`` if
    it declares one, else the global map. A v2 agent reads no config for tools,
    so this list is exactly what the session gets.

    ``conn`` is a child :mod:`crow_cli.discover` already spawned and asked.
    The protocol it reports — not the one the entry declared, which is why the
    entry does not have to declare one — is what the banner and the ``session``
    event name.

    Raises whatever the wire raised, after printing the child's stderr tail: a
    v2 agent that fails at startup says why on stderr and nowhere else, and
    without this the client reports a closed pipe instead of the reason.
    """
    workdir = cwd or os.getcwd()
    # What the agent said it speaks, which an undeclared entry leaves to the
    # probe rather than to a guess.
    protocol = conn.protocol if conn is not None else server.protocol
    client = CrowClientV2(console, json_out=json_out, timeout=timeout)
    supply = tool_supply(server, config.mcp_servers)
    servers = config_to_servers(supply)

    if not json_out:
        mode = "[green]Interactive[/green]" if interactive else "[yellow]Single-shot[/yellow]"
        tools = ", ".join(supply) or "[dim]none — zero tools[/dim]"
        console.print(
            Panel(
                f"[bold]Crow ACP v2 Client[/bold]\n\n"
                f"Agent: [cyan]{server.title}[/cyan] [dim]({protocol})[/dim]\n"
                f"Working directory: [cyan]{workdir}[/cyan]\n"
                f"Mode: {mode}\n"
                f"Session: {session_id or '[dim]New session[/dim]'}",
                title="[magenta]🪶 Crow[/magenta]",
                border_style="magenta",
            )
        )
        console.print(f"[cyan]MCP servers: {tools}[/cyan]")

    try:
        await client.start(server, workdir, conn=conn)
        sid = await client.open_session(
            workdir,
            mcp_servers=servers,
            session_id=session_id,
            fork=fork,
            replay=replay,
        )
        if model:
            await client.set_model(model)
        client.emit(
            type="session",
            session_id=sid,
            cwd=workdir,
            agent=server.name,
            protocol=protocol,
            mode="interactive" if interactive else "one_shot",
            model=model,
        )
        if not json_out:
            console.print(f"[green]Session created: {sid}[/green]")

        if interactive:
            await client.interactive_loop()
        else:
            stop = await client.send_prompt(prompt or "")
            client.emit(type="result", session_id=sid, stop_reason=stop)
            if not json_out:
                console.print(f"\n[dim]Session: {sid}[/dim]")
                console.print(
                    f"[dim]Continue with: crow-cli run -a {server.name} -s {sid} "
                    '"<your message>"[/dim]'
                )
    except Exception:
        tail = client.driver.stderr_tail.strip()
        if tail and not json_out:
            console.print()
            console.print("[red]═══ Agent subprocess failed ═══[/red]")
            console.print()
            console.print(tail)
            console.print(
                "[yellow]The agent subprocess exited with an error. "
                "The traceback above shows what went wrong.[/yellow]"
            )
        raise
    finally:
        await client.close()
