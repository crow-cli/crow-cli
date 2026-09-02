import asyncio

from contextlib import suppress
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, cast, NamedTuple
from copy import deepcopy
from math import floor
import rich.repr

from textual.content import Content
from textual.message import Message
from textual.message_pump import MessagePump


from crow_cli.tui import jsonrpc
import crow_cli.tui as tui
from crow_cli.tui.agent_schema import Agent as AgentData
from crow_cli.tui.agent import AgentBase, AgentReady, AgentFail
from crow_cli.tui.acp import protocol
from crow_cli.tui.acp import api
from crow_cli.tui.acp.api import API
from crow_cli.tui.acp import messages
from crow_cli.tui.messages import SessionUpdate
from crow_cli.tui.acp.prompt import build as build_prompt
from crow_cli.tui.db import DB
from crow_cli.tui import paths
from crow_cli.tui.mcp import load_mcp_servers
from crow_cli.tui import constants
from crow_cli.tui.answer import Answer

PROTOCOL_VERSION = 1

_LOG_FLUSH_INTERVAL = 0.2
"""Seconds between wire-log flushes."""
_LOG_BUFFER_LIMIT = 50_000
"""Queued log lines before the oldest are dropped."""
_LOG_WRITE_CHUNK = 5_000
"""Max lines written per flush."""

STREAM_FLUSH_INTERVAL = 0.03
"""Coalescing window for streamed text (seconds).

A fast endpoint emits hundreds of `session/update` chunks per second. Posting a
Textual message per chunk floods the message pump — to the point where keyboard
events stop being processed — so chunks are accumulated and flushed on roughly
a frame cadence instead.
"""
STREAM_FLUSH_MAX_CHARS = 16_384
"""Flush early once this much streamed text has accumulated."""


class Mode(NamedTuple):
    """An agent mode."""

    id: str
    name: str
    description: str | None


class ContextUsage(NamedTuple):
    """Context window usage."""

    used: int
    size: int
    cost: Cost | None = None

    @property
    def percentage_used(self) -> float:
        try:
            return (self.used / self.size) * 100.0
        except ZeroDivisionError:
            # Sanity check. If size is 0, then 100% is always used?
            return 100.0

    @property
    def percentage_display(self) -> str:
        return f"{floor(self.percentage_used * 10) / 10:.1f}%"


class Cost(NamedTuple):
    """A cost with associated currency."""

    amount: float
    currency: str

    def __str__(self) -> str:
        return f"{self:}"

    def __format__(self, _specifier: str) -> str:
        from format_currency import format_currency

        amount, currency = self
        currency_text = format_currency(amount, currency_code=currency).replace(" ", "")
        return currency_text


class TokenUsage(NamedTuple):
    """Tokens used for a single prompt (per-turn)."""

    total_tokens: int
    input_tokens: int
    output_tokens: int
    thought_tokens: int | None
    cached_read_tokens: int | None
    cached_write_tokens: int | None


def generate_datetime_filename(
    prefix: str, suffix: str, datetime_format: str | None = None
) -> str:
    """Generate a filename which includes the current date and time.

    Useful for ensuring a degree of uniqueness when saving files.

    Args:
        prefix: Prefix to attach to the start of the filename, before the timestamp string.
        suffix: Suffix to attach to the end of the filename, after the timestamp string.
            This should include the file extension.
        datetime_format: The format of the datetime to include in the filename.
            If None, the ISO format will be used.
    """
    if datetime_format is None:
        dt = datetime.now().isoformat()
    else:
        dt = datetime.now().strftime(datetime_format)

    file_name_stem = f"{prefix} {dt}"
    for reserved in ' <>:"/\\|?*.':
        file_name_stem = file_name_stem.replace(reserved, "_")
    return file_name_stem + suffix


@rich.repr.auto
class Agent(AgentBase):
    """An agent that speaks the APC (https://agentclientprotocol.com/overview/introduction) protocol."""

    def __init__(
        self,
        project_root: Path,
        agent: AgentData,
        session_id: str | None,
        session_pk: int | None = None,
    ) -> None:
        """

        Args:
            project_root: Project root path.
            command: Command to launch agent.
        """
        super().__init__(project_root)

        self._agent_data = agent
        self.session_id = session_id

        self.server = jsonrpc.Server()
        self.server.expose_instance(self)

        self._agent_task: asyncio.Task | None = None
        self._task: asyncio.Task | None = None
        self._process: asyncio.subprocess.Process | None = None
        self.done_event = asyncio.Event()

        self.agent_capabilities: protocol.AgentCapabilities = {
            "loadSession": False,
            "promptCapabilities": {
                "audio": False,
                "embeddedContent": False,
                "image": False,
            },
        }
        self.auth_methods: list[protocol.AuthMethod] = []
        self.session_pk: int | None = session_pk
        self.tool_calls: dict[str, protocol.ToolCall] = {}
        self._message_target: MessagePump | None = None

        self._terminal_count: int = 0

        log_filename: str = generate_datetime_filename(f"{agent['name']}", ".txt")
        if log_path := os.environ.get("CROW_LOG"):
            self._log_file_path = Path(log_path).resolve().absolute()
            with suppress(OSError):
                self._log_file_path.unlink(missing_ok=True)
        else:
            self._log_file_path = paths.get_log() / log_filename

        self._token_usage: TokenUsage | None = None
        self._context_usage: ContextUsage | None = None
        # Set the moment the user cancels; cleared when the session/prompt
        # response lands. While set, inbound session/update traffic is
        # dropped so the pipe drains at wire speed instead of render speed —
        # cancel is prioritized over rendering the dead turn's backlog.
        self._cancelling: bool = False
        # Streamed text awaiting a coalesced flush into the UI.
        self._pending_text: list[str] = []
        self._pending_thought: list[str] = []
        self._pending_chars = 0
        self._flush_handle: asyncio.TimerHandle | None = None
        self._log_buffer: list[str] = []

    @property
    def command(self) -> str | None:
        """The command used to launch the agent, or `None` if there isn't one."""
        acp_command = tui.get_os_matrix(self._agent_data["run_command"])
        return acp_command

    @property
    def supports_load_session(self) -> bool:
        """Does the agent support loading sessions?"""
        return self.agent_capabilities.get("loadSession", False)

    @property
    def supports_list_sessions(self) -> bool:
        """Does the agent support listing sessions (session/list)?"""
        session_capabilities = self.agent_capabilities.get("sessionCapabilities", {})
        return "list" in session_capabilities

    def __rich_repr__(self) -> rich.repr.Result:
        yield self.project_root_path
        yield self.command

    def log(self, line: str) -> None:
        """Queue a line for the agent log file.

        Deliberately cheap: this is called for every line of wire traffic, and
        under a fast stream it would otherwise dominate. A single background
        task drains the buffer to disk.
        """
        if self._message_target is None:
            return
        buffer = self._log_buffer
        if len(buffer) >= _LOG_BUFFER_LIMIT:
            # Losing log lines beats growing memory without bound.
            del buffer[: len(buffer) - _LOG_BUFFER_LIMIT + 1]
            buffer.append("[log buffer trimmed]")
        buffer.append(line)

    async def _flush_log(self) -> None:
        """Write queued log lines to disk in one append."""
        if not self._log_buffer:
            return
        lines, self._log_buffer = self._log_buffer[:_LOG_WRITE_CHUNK], self._log_buffer[_LOG_WRITE_CHUNK:]

        def write(log_file_path: Path, lines: list[str]) -> None:
            try:
                with log_file_path.open("at") as log_file:
                    log_file.writelines(f"{line.rstrip()}\n" for line in lines)
            except OSError:
                pass

        await asyncio.to_thread(write, self._log_file_path, lines)

    async def _log_writer(self) -> None:
        """Background task: periodically flush the wire log."""
        while True:
            await asyncio.sleep(_LOG_FLUSH_INTERVAL)
            with suppress(asyncio.CancelledError, Exception):
                await self._flush_log()

    def get_info(self) -> Content:
        agent_name = self._agent_data["name"]
        return Content(agent_name)

    async def start(self, message_target: MessagePump | None = None) -> None:
        """Start the agent."""
        self._message_target = message_target
        try:
            await asyncio.to_thread(
                self._log_file_path.parent.mkdir, parents=True, exist_ok=True
            )
        except OSError:
            pass
        self._agent_task = asyncio.create_task(self._run_agent())
        self._log_task = asyncio.create_task(self._log_writer())

    def _schedule_flush(self) -> None:
        """Queue a coalesced flush of streamed text into the UI."""
        if self._flush_handle is not None:
            return
        self._flush_handle = asyncio.get_running_loop().call_later(
            STREAM_FLUSH_INTERVAL, self._flush_stream
        )

    def _flush_stream(self) -> None:
        """Post accumulated streamed text as one message per kind.

        Called on the coalescing timer, and before any non-text update (tool
        calls, plans, mode changes) so transcript ordering is preserved.
        """
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None
        text, self._pending_text = "".join(self._pending_text), []
        thought, self._pending_thought = "".join(self._pending_thought), []
        self._pending_chars = 0
        if thought:
            self.post_message(messages.Thinking("text", thought))
        if text:
            self.post_message(messages.Update("text", text))

    def _queue_stream(self, buffer: list[str], text: str) -> None:
        """Accumulate one streamed chunk, flushing when it grows large."""
        buffer.append(text)
        self._pending_chars += len(text)
        if self._pending_chars >= STREAM_FLUSH_MAX_CHARS:
            self._flush_stream()
        else:
            self._schedule_flush()

    def send(self, request: jsonrpc.Request) -> None:
        """Send a request to the agent.

        This is called automatically, if you go through `self.request`.

        Args:
            request: JSONRPC request object.

        """
        if self._process is None:
            self.log("[error] Agent process isnt running")
            return

        self.log(f"[client] {request.body}")
        if (stdin := self._process.stdin) is not None:
            stdin.write(b"%s\n" % request.body_json)
            # Best-effort flush: under a congested loop (heavy streaming)
            # this pushes e.g. session/cancel bytes out immediately.
            asyncio.get_event_loop().create_task(stdin.drain())

    def request(self) -> jsonrpc.Request:
        """Create a request object."""
        return API.request(self.send)

    def post_message(self, message: Message) -> bool:
        """Post a message to the message target (the Conversation).

        Args:
            message: Message object.

        Returns:
            `True` if the message was posted successfully, or `False` if it wasn't.
        """
        if (message_target := self._message_target) is None:
            return False
        return message_target.post_message(message)

    @jsonrpc.expose("session/update")
    def rpc_session_update(
        self,
        sessionId: str,
        update: protocol.SessionUpdate,
        _meta: dict[str, Any] | None = None,
    ):
        """Agent requests an update.

        https://agentclientprotocol.com/protocol/schema
        """

        if self._cancelling:
            # The turn is dead; do not spend a render on its corpse. The
            # read loop drains these cheaply so the session/prompt response
            # (the real turn-over signal) reaches us ASAP.
            return

        # Streamed text is coalesced; everything else must appear after the
        # text that preceded it, so drain first.
        match update:
            case {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": type, "text": text},
            }:
                if text:
                    self._queue_stream(self._pending_text, text)
                return

            case {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": type, "text": text},
            }:
                if text:
                    self._queue_stream(self._pending_thought, text)
                return

        self._flush_stream()

        match update:
            case {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": type, "text": text},
            }:
                if text:
                    self.post_message(messages.UserMessage(type, text))

            case {
                "sessionUpdate": "tool_call",
                "toolCallId": tool_call_id,
            }:
                self.tool_calls[tool_call_id] = update
                self.post_message(messages.ToolCall(update))

            case {"sessionUpdate": "plan", "entries": entries}:
                self.post_message(messages.Plan(entries))

            case {
                "sessionUpdate": "tool_call_update",
                "toolCallId": tool_call_id,
            }:
                if tool_call_id in self.tool_calls:
                    current_tool_call = self.tool_calls[tool_call_id]
                    for key, value in update.items():
                        if value is not None:
                            current_tool_call[key] = value

                    self.post_message(
                        messages.ToolCallUpdate(deepcopy(current_tool_call), update)
                    )
                else:
                    # The agent can send a tool call update, without previously sending the tool call *rolls eyes*
                    current_tool_call: protocol.ToolCall = {
                        "sessionUpdate": "tool_call",
                        "toolCallId": tool_call_id,
                        "title": "Tool call",
                    }
                    for key, value in update.items():
                        if value is not None:
                            current_tool_call[key] = value

                    self.tool_calls[tool_call_id] = current_tool_call
                    self.post_message(messages.ToolCall(current_tool_call))

            case {
                "sessionUpdate": "available_commands_update",
                "availableCommands": available_commands,
            }:
                self.post_message(messages.AvailableCommandsUpdate(available_commands))

            case {"sessionUpdate": "current_mode_update", "currentModeId": mode_id}:
                self.post_message(messages.ModeUpdate(mode_id))

            case {"sessionUpdate": "usage_update", "used": used, "size": size}:
                match update.get("cost"):
                    case {"amount": amount, "currency": currency}:
                        self._context_usage = ContextUsage(
                            used, size, Cost(amount, currency)
                        )
                    case _:
                        self._context_usage = ContextUsage(used, size)
                self.update_status_line()

    def update_status_line(self) -> None:
        """Update the current status line."""

        if (usage := self._context_usage) is not None:
            status: list[Content] = []
            status.append(
                Content.assemble(
                    f"{usage.used / 1000:.1f}K",
                    " (",
                    (f"{usage.percentage_display}", "bold"),
                    ")",
                )
            )
            if (cost := usage.cost) is not None:
                status.append(Content.assemble((f"{cost}", "bold")))

            status_line = Content(" • ").join(status)
            self.post_message(messages.UpdateStatusLine(status_line))

    @jsonrpc.expose("session/request_permission")
    async def rpc_request_permission(
        self,
        sessionId: str,
        options: list[protocol.PermissionOption],
        toolCall: protocol.ToolCallUpdatePermissionRequest,
        _meta: dict | None = None,
    ) -> protocol.RequestPermissionResponse:
        """Agent requests permission to make a tool call.

        Args:
            sessionId: The session ID.
            options: A list of permission options (potential replies).
            toolCall: The tool or tools the agent is requesting permission to call.
            _meta: Optional meta information.

        Returns:
            The response to the permission request.
        """
        result_future: asyncio.Future[Answer] = asyncio.Future()
        tool_call_id = toolCall["toolCallId"]

        permission_tool_call = toolCall.copy()
        permission_tool_call.pop("sessionUpdate", None)
        tool_call = cast(protocol.ToolCall, permission_tool_call)
        if tool_call_id in self.tool_calls:
            self.tool_calls[tool_call_id] |= tool_call
        else:
            self.tool_calls[tool_call_id] = deepcopy(tool_call)

        tool_call = deepcopy(self.tool_calls[tool_call_id])

        message = messages.RequestPermission(options, tool_call, result_future)
        self.post_message(message)
        await result_future
        ask_result = result_future.result()

        request_permission_outcome: protocol.OutcomeSelected = {
            "optionId": ask_result.id,
            "outcome": "selected",
        }
        result: protocol.RequestPermissionResponse = {
            "outcome": request_permission_outcome
        }
        return result

    @jsonrpc.expose("fs/read_text_file")
    def rpc_read_text_file(
        self,
        sessionId: str,
        path: str,
        line: int | None = None,
        limit: int | None = None,
    ) -> dict[str, str]:
        """Read a file in the project."""
        # TODO: what if the read is outside of the project path?
        # https://agentclientprotocol.com/protocol/file-system#reading-files
        read_path = self.project_root_path / path
        try:
            text = read_path.read_text(encoding="utf-8", errors="ignore")
        except IOError:
            text = ""
        if line is not None:
            line = max(0, line - 1)
            if limit is None:
                text = "\n".join(text.splitlines()[line:])
            else:
                text = "\n".join(text.splitlines()[line : line + limit])
        return {"content": text}

    @jsonrpc.expose("fs/write_text_file")
    def rpc_write_text_file(self, sessionId: str, path: str, content: str) -> None:
        # TODO: What if the agent wants to write outside of the project path?
        # https://agentclientprotocol.com/protocol/file-system#writing-files

        write_path = self.project_root_path / path
        write_path.write_text(content, encoding="utf-8", errors="ignore")

    # https://agentclientprotocol.com/protocol/schema#createterminalrequest
    @jsonrpc.expose("terminal/create")
    async def rpc_terminal_create(
        self,
        command: str,
        _meta: dict | None = None,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[protocol.EnvVariable] | None = None,
        outputByteLimit: int | None = None,
        sessionId: str | None = None,
    ) -> protocol.CreateTerminalResponse:
        # Assign a terminal id
        self._terminal_count = self._terminal_count + 1
        terminal_id = f"terminal-{self._terminal_count}"

        terminal_env = (
            {variable["name"]: variable["value"] for variable in env} if env else {}
        )
        result_future: asyncio.Future[bool] = asyncio.Future()
        self.post_message(
            messages.CreateTerminal(
                terminal_id,
                command=command,
                args=args,
                cwd=cwd,
                env=terminal_env,
                output_byte_limit=outputByteLimit,
                result_future=result_future,
            )
        )
        await result_future
        if not result_future.result():
            raise jsonrpc.JSONRPCError("Failed to create a terminal.")
        return {"terminalId": terminal_id}

    # https://agentclientprotocol.com/protocol/schema#killterminalcommandrequest
    @jsonrpc.expose("terminal/kill")
    def rpc_terminal_kill(
        self, sessionID: str, terminalId: str, _meta: dict | None = None
    ) -> protocol.KillTerminalCommandResponse:
        self.post_message(messages.KillTerminal(terminalId))
        return {}

    # https://agentclientprotocol.com/protocol/schema#terminal%2Foutput
    @jsonrpc.expose("terminal/output")
    async def rpc_terminal_output(
        self, sessionId: str, terminalId: str, _meta: dict | None = None
    ) -> protocol.TerminalOutputResponse:
        from crow_cli.tui.widgets.terminal_tool import ToolState

        result_future: asyncio.Future[ToolState] = asyncio.Future()

        if not self.post_message(messages.GetTerminalState(terminalId, result_future)):
            raise RuntimeError("Unable to get terminal output")

        await result_future
        terminal_state = result_future.result()

        result: protocol.TerminalOutputResponse = {
            "output": terminal_state.output,
            "truncated": terminal_state.truncated,
        }
        if (return_code := terminal_state.return_code) is not None:
            result["exitStatus"] = {"exitCode": return_code}
        return result

    # https://agentclientprotocol.com/protocol/schema#terminal%2Frelease
    @jsonrpc.expose("terminal/release")
    def rpc_terminal_release(
        self, sessionId: str, terminalId: str, _meta: dict | None = None
    ) -> protocol.ReleaseTerminalResponse:
        self.post_message(messages.ReleaseTerminal(terminalId))
        return {}

    # https://agentclientprotocol.com/protocol/schema#terminal%2Fwait-for-exit
    @jsonrpc.expose("terminal/wait_for_exit")
    async def rpc_terminal_wait_for_exit(
        self, sessionId: str, terminalId: str, _meta: dict | None = None
    ) -> protocol.WaitForTerminalExitResponse:
        result_future: asyncio.Future[tuple[int, str | None]] = asyncio.Future()
        if not self.post_message(
            messages.WaitForTerminalExit(terminalId, result_future)
        ):
            raise RuntimeError("Unable to wait for terminal exit; no terminal found")

        await result_future
        return_code, signal = result_future.result()
        return {"exitCode": return_code, "signal": signal}

    async def _run_agent(self) -> None:
        """Task to communicate with the agent subprocess."""

        PIPE = asyncio.subprocess.PIPE
        env = os.environ.copy()
        env["CROW_CWD"] = str(Path("./").absolute())
        env.update(self._agent_data.get("env", {}))

        if (command := self.command) is None:
            self.post_message(
                AgentFail("Failed to start agent; no run command for this OS")
            )
            return
        try:
            process = self._process = await asyncio.create_subprocess_shell(
                command,
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE,
                env=env,
                cwd=str(self.project_root_path),
                limit=10 * 1024 * 1024,
            )
        except Exception as error:
            self.post_message(AgentFail("Failed to start agent", details=str(error)))
            return

        self._task = asyncio.create_task(self.run())

        assert process.stdout is not None
        assert process.stdin is not None

        tasks: set[asyncio.Task] = set()

        async def call_jsonrpc(request: jsonrpc.JSONObject | jsonrpc.JSONList) -> None:
            try:
                if (result := await self.server.call(request)) is not None:
                    result_json = json.dumps(result).encode("utf-8")
                    if process.stdin is not None:
                        process.stdin.write(b"%s\n" % result_json)
            finally:
                if (task := asyncio.current_task()) is not None:
                    tasks.discard(task)

        while line := await process.stdout.readline():
            # This line should contain JSON, which may be:
            #   A) a JSONRPC request
            #   B) a JSONRPC response to a previous request
            if not line.strip():
                continue

            try:
                line_str = line.decode("utf-8")
            except Exception as error:
                self.log(f"[error] Unable to decode utf-8 from agent: {error}")
                continue

            self.log(f"[agent] {line_str}")
            try:
                agent_data: jsonrpc.JSONType = json.loads(line_str)
            except Exception as error:
                self.log(f"[error] failed to decode JSON from agent: {error}")
                continue

            if isinstance(agent_data, dict):
                if "result" in agent_data or "error" in agent_data:
                    API.process_response(agent_data)
                    continue

            elif isinstance(agent_data, list):
                if not all(isinstance(datum, dict) for datum in agent_data):
                    self.log(f"[error] Agent sent invalid data: {agent_data!r}")
                    continue
                if all(
                    isinstance(datum, dict) and ("result" in datum or "error" in datum)
                    for datum in agent_data
                ):
                    API.process_response(agent_data)
                    continue

            if not isinstance(agent_data, dict):
                self.log("[error] Invalid JSON from agent {agent_data!r}")
                continue

            # By this point we know it is a JSON RPC call
            assert isinstance(agent_data, dict)
            tasks.add(asyncio.create_task(call_jsonrpc(agent_data)))
            await asyncio.sleep(0)

        # Cancel all remaining tasks and wait for them to finish
        for task in tasks:
            task.cancel()

        # Wait for all tasks to complete cancellation
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if process.returncode:
            assert process.stderr is not None
            fail_details = (await process.stderr.read()).decode("utf-8", "replace")
            self.post_message(
                AgentFail(
                    f"Agent returned a failure code: [b]{process.returncode}",
                    details=fail_details,
                )
            )

        self._process = None

    async def stop(self) -> None:
        """Gracefully stop the process."""
        if self.session_pk is not None:
            db = DB()
            await db.session_update_last_used(self.session_pk)

        if self._process is not None:
            try:
                self._process.terminate()
            except OSError:
                pass

    async def run(self) -> None:
        """The main logic of the Agent."""
        if constants.ACP_INITIALIZE:
            try:
                # Boilerplate to initialize comms
                await self.acp_initialize()

                if self.session_id is None:
                    # Create a new session
                    await self.acp_new_session()
                else:
                    # Load existing session
                    if not self.agent_capabilities.get("loadSession", False):
                        self.post_message(
                            AgentFail(
                                "Resume not supported",
                                f"{self._agent_data['name']} does not currently support resuming sessions.",
                                help="no_resume",
                            )
                        )
                        return
                    await self.acp_load_session()
                    if self.session_pk is not None:
                        db = DB()
                        await db.session_update_last_used(self.session_pk)
            except jsonrpc.APIError as error:
                if isinstance(error.data, dict):
                    reason = str(
                        error.data.get("reason") or "Failed to initialize agent"
                    )
                    details = str(
                        error.data.get("details") or error.data.get("error") or ""
                    )
                else:
                    reason = "Failed to initialize agent"
                    details = ""
                self.post_message(AgentFail(reason, details))

        self.post_message(AgentReady())

    async def send_prompt(self, prompt: str) -> str | None:
        """Send a prompt to the agent.

        !!! note
            This method blocks as it may defer to a thread to read resources.

        Args:
            prompt: Prompt text.
        """
        prompt_content_blocks = await asyncio.to_thread(
            build_prompt, self.project_root_path, prompt
        )
        return await self.acp_session_prompt(prompt_content_blocks)

    async def acp_initialize(self):
        """Initialize agent."""
        with self.request():
            initialize_response = api.initialize(
                PROTOCOL_VERSION,
                {
                    "fs": {
                        "readTextFile": True,
                        "writeTextFile": True,
                    },
                    "terminal": True,
                },
                {
                    "name": tui.NAME,
                    "title": tui.TITLE,
                    "version": tui.get_version(),
                },
            )

        response = await initialize_response.wait()
        assert response is not None

        # Store agents capabilities
        if agent_capabilities := response.get("agentCapabilities"):
            self.agent_capabilities = agent_capabilities
        if auth_methods := response.get("authMethods"):
            self.auth_methods = auth_methods

    async def acp_new_session(self) -> None:
        """Create a new session."""
        with self.request():
            session_new_response = api.session_new(
                str(self.project_root_path),
                load_mcp_servers(),
            )
        response = await session_new_response.wait()
        assert response is not None
        self.session_id = response["sessionId"]
        # Show the session id in the tab bar as soon as it exists.
        self.post_message(SessionUpdate(name=self.session_id))

        if self.supports_load_session:
            db = DB()
            session_name = "New Session"
            self.session_pk = await db.session_new(
                session_name,
                self._agent_data["name"],
                self._agent_data["identity"],
                self.session_id,
                protocol="acp",
                meta={
                    "cwd": str(self.project_root_path),
                    "agent_data": self._agent_data,
                },
            )

        if (modes := response.get("modes", None)) is not None:
            current_mode = modes["currentModeId"]
            available_modes = modes["availableModes"]
            modes_update = {
                mode["id"]: Mode(
                    mode["id"], mode["name"], mode.get("description", None)
                )
                for mode in available_modes
            }
            self.post_message(messages.SetModes(current_mode, modes_update))

    async def acp_load_session(self) -> None:
        assert self.session_id is not None, "Session id must be set"
        cwd = str(self.project_root_path)
        if self.session_pk is not None:
            db = DB()
            if (session := await db.session_get(self.session_pk)) is not None:
                if session["meta_json"]:
                    meta = json.loads(session["meta_json"])
                    if session_cwd := meta.get("cwd", None):
                        cwd = session_cwd
                    if agent_data := meta.get("agent_data"):
                        self._agent_data = agent_data

        with self.request():
            session_load_response = api.session_load(
                cwd, load_mcp_servers(), self.session_id
            )
        response = await session_load_response.wait()
        self.post_message(SessionUpdate(name=self.session_id))

        if (modes := response.get("modes", None)) is not None:
            current_mode = modes["currentModeId"]
            available_modes = modes["availableModes"]
            modes_update = {
                mode["id"]: Mode(
                    mode["id"], mode["name"], mode.get("description", None)
                )
                for mode in available_modes
            }
            self.post_message(messages.SetModes(current_mode, modes_update))

    async def acp_list_sessions(
        self, cwd: str | None = None, cursor: str | None = None
    ) -> protocol.ListSessionsResponse:
        """List sessions known to the agent.

        Args:
            cwd: Optional working directory to filter by (absolute path).
            cursor: Opaque pagination token from a previous response.

        Returns:
            The `session/list` response.
        """
        params: dict[str, Any] = {}
        if cwd is not None:
            params["cwd"] = cwd
        if cursor is not None:
            params["cursor"] = cursor
        with self.request():
            session_list_response = api.session_list(**params)
        response = await session_list_response.wait()
        assert response is not None
        return response

    async def acp_session_prompt(
        self, prompt: list[protocol.ContentBlock]
    ) -> str | None:
        """Send the prompt to the agent.

        Returns:
            The stop reason.

        """
        with self.request():
            session_prompt = api.session_prompt(prompt, self.session_id)
        try:
            result = await session_prompt.wait()
        except jsonrpc.APIError as error:
            details = ""
            match error.data:
                case {"details": details}:
                    pass

            self.post_message(
                AgentFail(
                    "Failed to send prompt" or error.message,
                    (
                        str(details)
                        if details
                        else f"{self._agent_data['name']} returned an error"
                    ),
                )
            )
            return None
        except jsonrpc.JSONRPCError as error:
            self.post_message(
                AgentFail(
                    "Failed to send prompt" or error.message,
                    (error.message or f"{self._agent_data['name']} returned an error"),
                )
            )
            return None
        finally:
            # Turn is over one way or another (end_turn, cancelled, error):
            # render traffic flows again. The agent serializes turns per
            # session, so everything before this response was the old turn.
            if self._cancelling:
                self._drop_pending_stream()
            else:
                self._flush_stream()
            self._cancelling = False

        assert result is not None
        # TODO: Where to display this?
        token_usage = result.get("usage")

        return result.get("stopReason")

    async def acp_session_set_mode(self, mode_id: str) -> str | None:
        """Update the current mode with the agent."""
        with self.request():
            response = api.session_set_mode(self.session_id, mode_id)
        try:
            await response.wait()
        except jsonrpc.APIError as error:
            match error.data:
                case {"details": details}:
                    return details if isinstance(details, str) else "Failed to set mode"
            return "Failed to set mode"
        else:
            return None

    async def set_mode(self, mode_id: str) -> str | None:
        return await self.acp_session_set_mode(mode_id)

    async def set_session_name(self, name: str) -> None:
        if self.session_pk is None:
            return
        db = DB()
        await db.session_update_title(self.session_pk, name)

    def _drop_pending_stream(self) -> None:
        """Discard streamed text that is no longer worth rendering."""
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None
        self._pending_text = []
        self._pending_thought = []
        self._pending_chars = 0

    def begin_cancel(self) -> bool:
        """Stop rendering the current turn and put `session/cancel` on the wire.

        Synchronous on purpose: cancelling must not wait on a worker, an RPC
        round-trip, or the message pump it is trying to escape. `session/cancel`
        is a notification, so there is nothing to await — the bytes are written
        to the agent's stdin before this returns.

        Returns:
            `True` if the notification was sent, `False` if no agent is running.
        """
        if self._process is None or self.session_id is None:
            return False
        # Raise the drop-flag first: nothing the agent emits from here on is
        # worth rendering, including text still buffered for the next flush.
        self._cancelling = True
        self._drop_pending_stream()
        with self.request():
            api.session_cancel(self.session_id, {})
        return True

    async def acp_session_cancel(self) -> bool:
        return self.begin_cancel()

    async def cancel(self) -> bool:
        return self.begin_cancel()
