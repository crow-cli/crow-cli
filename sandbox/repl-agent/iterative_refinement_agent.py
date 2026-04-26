"""Iterative Refinement ACP Agent.

Spawns a worker agent and a critic agent, runs them in a feedback loop,
and presents as a single ACP agent to upstream clients (Zed, etc.).

Usage:
    uv --project . run iterative_refinement_agent.py
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from acp import (
    Agent,
    Client,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
    text_block,
)
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ClientCapabilities,
    CurrentModeUpdate,
    FileSystemCapabilities,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    PermissionOption,
    ResourceContentBlock,
    SseMcpServer,
    TextContentBlock,
    ToolCall,
    ToolCallProgress,
    ToolCallStart,
)
from acp.stdio import spawn_agent_process

logger = logging.getLogger("iterative-refinement-agent")


# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

AGENT_CMD = "uv"
AGENT_ARGS = (
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent",
    "run",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/scratch_db.py",
)

COMPACT_PROMPT = (
    "Summarize the conversation in RESTful markdown format and the "
    "steps you have taken. This is an interagent summary/compaction "
    "event. Respond directly. Call no tools."
)

CRITIC_RESPONSE_FORMAT = (
    "You MUST respond with XML in this exact format:\n"
    "<critique>\n"
    "  <score>0.0-1.0</score>\n"
    "  <task_complete>COMPLETE or INCOMPLETE</task_complete>\n"
    "  <summary>Brief summary of what was done well and what needs improvement</summary>\n"
    "</critique>\n"
    "Do NOT add any other text. Just the XML."
)


@dataclass
class CritiqueResult:
    score: float = 0.0
    task_complete: bool = False
    summary: str = ""
    raw: str = ""


def parse_critique(text: str) -> CritiqueResult:
    score_m = re.search(r"<score>([\d.]+)</score>", text)
    score = float(score_m.group(1)) if score_m else 0.0

    complete_m = re.search(r"<task_complete>([^<]+)</task_complete>", text)
    task_complete = False
    if complete_m:
        task_complete = complete_m.group(1).strip().upper() in ("COMPLETE", "TRUE")

    summary_m = re.search(r"<summary>(.*?)</summary>", text, re.DOTALL)
    summary = summary_m.group(1).strip() if summary_m else "(no summary)"

    return CritiqueResult(
        score=score, task_complete=task_complete, summary=summary, raw=text
    )


# ──────────────────────────────────────────────────────────────
# IterativeRefinementAgent
# ──────────────────────────────────────────────────────────────


@dataclass
class _ChildState:
    role: str  # "worker" | "critic"
    conn: Any
    spawn_cm: Any
    session_id: str | None = None
    conversation: list[dict[str, str]] = field(default_factory=list)
    _last_assistant: str = ""
    _thinking_buffer: str = ""


class IterativeRefinementAgent(Agent, Client):
    """Single ACP agent that runs worker + critic in a refinement loop.

    The loop:
        1. Worker attempts the task
        2. Critic evaluates against criteria, returns XML with score + task_complete
        3. If task_complete, stop. Otherwise feed critique back to worker.
        4. Repeat up to max_iterations.

    Subclass and override `configure()` to customize the agent commands,
    or override `run_refinement()` for custom loop logic.
    """

    # -- Subclass hooks --

    def configure(self) -> dict[str, Any]:
        """Return configuration dict.

        Keys:
            task: str — what the worker should do
            criteria: list[str] — what the critic evaluates against
            max_iterations: int (default 5)
            worker_command: list[str] (defaults to AGENT_CMD + AGENT_ARGS)
            critic_command: list[str] (defaults to AGENT_CMD + AGENT_ARGS)
            cwd: str (defaults to session cwd)
        """
        return {}

    async def run_refinement(
        self,
        worker: _ChildState,
        critic: _ChildState,
        task: str,
        criteria: list[str],
        cwd: str,
        max_iterations: int = 5,
    ) -> str:
        """Override to customize the refinement loop.

        Default: linear worker → compact → critic → XML → repeat loop.
        """
        criteria_block = "\n".join(f"- {c}" for c in criteria)

        # Announce chain start
        await self._upstream_update(
            worker,
            AgentMessageChunk(
                content=text_block(
                    f"▶ Refinement: {max_iterations} iterations max\n"
                    f"Criteria: {len(criteria)}\n\n"
                    f"Task: {task}"
                ),
                session_update="agent_message_chunk",
            ),
        )

        # Worker initial pass
        await self._send_to_child(worker, f"You must implement: {task}", cwd)
        await self._send_to_child(worker, COMPACT_PROMPT, cwd)
        worker_summary = worker._last_assistant

        iteration_summaries: list[dict] = []

        for iteration in range(1, max_iterations + 1):
            if self._cancel_event.is_set():
                await self._upstream_update(
                    critic,
                    AgentMessageChunk(
                        content=text_block("\n⚠️ Cancelled by user.\n"),
                        session_update="agent_message_chunk",
                    ),
                )
                break

            await self._upstream_update(
                critic,
                AgentMessageChunk(
                    content=text_block(
                        f"\n--- Iteration {iteration}/{max_iterations} ---\n"
                    ),
                    session_update="agent_message_chunk",
                ),
            )

            # Critic evaluates
            await self._send_to_child(
                critic,
                (
                    f"You must evaluate the agent's performance.\n\n"
                    f"Task: {task}\n"
                    f"Criteria to evaluate against:\n{criteria_block}\n"
                    f"Here is a summary of what it did:\n{worker_summary}\n\n"
                    f"{CRITIC_RESPONSE_FORMAT}"
                ),
                cwd,
            )
            critique_text = critic._last_assistant
            critique = parse_critique(critique_text)

            await self._upstream_update(
                critic,
                AgentMessageChunk(
                    content=text_block(
                        f"**Score:** {critique.score}\n"
                        f"**Status:** {'COMPLETE' if critique.task_complete else 'INCOMPLETE'}\n\n"
                        f"{critique.summary}"
                    ),
                    session_update="agent_message_chunk",
                ),
            )

            iteration_summaries.append(
                {
                    "iteration": iteration,
                    "worker_summary": worker_summary,
                    "critique": critique,
                }
            )

            if critique.task_complete:
                await self._upstream_update(
                    critic,
                    AgentMessageChunk(
                        content=text_block("\n✅ Task marked complete — stopping.\n"),
                        session_update="agent_message_chunk",
                    ),
                )
                break

            # Feed back to worker
            await self._send_to_child(
                worker,
                (
                    f"Here is feedback on your work:\n{critique.summary}\n"
                    f"Please improve your work based on the suggestions given."
                ),
                cwd,
            )
            await self._send_to_child(worker, COMPACT_PROMPT, cwd)
            worker_summary = worker._last_assistant

        return self._build_report(task, criteria, iteration_summaries)

    # -- Internal --

    def _build_report(self, task, criteria, summaries):
        lines = [
            f"# Iterative Refinement Report\n\n",
            f"**Task:** {task}\n\n",
            "**Criteria:**\n",
        ]
        for c in criteria:
            lines.append(f"- {c}\n")
        lines.append(f"\n**Iterations completed:** {len(summaries)}\n")

        if summaries:
            last = summaries[-1]["critique"]
            lines.extend(
                [
                    f"\n## Final Result\n\n",
                    f"- **Score:** {last.score}\n",
                    f"- **Status:** {'COMPLETE' if last.task_complete else 'INCOMPLETE'}\n",
                    f"- **Summary:** {last.summary}\n",
                ]
            )
            lines.append("\n## Iteration Details\n")
            for s in summaries:
                lines.append(f"\n### Iteration {s['iteration']}\n")
                lines.append(f"**Worker:** {s['worker_summary']}\n\n")
                lines.append(
                    f"**Critic (score={s['critique'].score}):** {s['critique'].summary}\n"
                )

        return "".join(lines)

    # -- ACP Agent Lifecycle --

    def __init__(self):
        self._upstream: Client | None = None
        self._upstream_capabilities: ClientCapabilities | None = None
        self._upstream_session_id: str | None = None
        self._worker: _ChildState | None = None
        self._critic: _ChildState | None = None
        self._started = False
        self._prompt_task: asyncio.Task | None = None
        self._cancel_event = asyncio.Event()

    def on_connect(self, conn: Client) -> None:
        self._upstream = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        self._upstream_capabilities = client_capabilities
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        self._upstream_session_id = str(uuid.uuid4())
        config = self.configure()
        agent_cwd = config.get("cwd") or cwd

        upstream_caps = self._upstream_capabilities
        downstream_caps = ClientCapabilities(
            terminal=bool(upstream_caps and getattr(upstream_caps, "terminal", False)),
            fs=FileSystemCapabilities(
                read_text_file=bool(
                    upstream_caps
                    and upstream_caps.fs
                    and getattr(upstream_caps.fs, "read_text_file", False)
                ),
                write_text_file=bool(
                    upstream_caps
                    and upstream_caps.fs
                    and getattr(upstream_caps.fs, "write_text_file", False)
                ),
            ),
        )

        worker_cmd = config.get("worker_command") or [AGENT_CMD] + list(AGENT_ARGS)
        critic_cmd = config.get("critic_command") or [AGENT_CMD] + list(AGENT_ARGS)

        for role, cmd in [("worker", worker_cmd), ("critic", critic_cmd)]:
            child_client = _ChildClient(self)
            spawn_cm = spawn_agent_process(
                child_client, *cmd, cwd=agent_cwd, env=config.get("env"),
            )
            conn, process = await spawn_cm.__aenter__()

            await conn.initialize(
                protocol_version=1,
                client_capabilities=downstream_caps,
                client_info=Implementation(
                    name="iterative-refinement-agent",
                    title="Iterative Refinement",
                    version="0.1.0",
                ),
            )

            session_resp = await conn.new_session(
                cwd=agent_cwd,
                mcp_servers=mcp_servers or [],
            )

            child = _ChildState(
                role=role,
                conn=conn,
                spawn_cm=spawn_cm,
                session_id=session_resp.session_id,
            )
            if role == "worker":
                self._worker = child
            else:
                self._critic = child

        self._started = True
        return NewSessionResponse(session_id=self._upstream_session_id)

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        self._cancel_event.clear()
        self._prompt_task = asyncio.current_task()
        try:
            return await self._run_prompt(prompt, session_id, **kwargs)
        except asyncio.CancelledError:
            return PromptResponse(stop_reason="cancelled")
        finally:
            # Signal end_turn so the client knows to pass control back
            if self._upstream and self._upstream_session_id:
                await self._upstream.session_update(
                    session_id=self._upstream_session_id,
                    update=CurrentModeUpdate(
                        session_update="current_mode_update",
                        current_mode_id="idle",
                    ),
                )
            self._prompt_task = None

    async def _run_prompt(
        self,
        prompt: list,
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        text = _extract_text(prompt)
        config = self.configure()

        task = config.get("task", text)
        criteria = config.get("criteria", ["Task completed satisfactorily"])
        max_iterations = config.get("max_iterations", 5)
        cwd = config.get("cwd") or "."

        if not self._worker or not self._critic:
            raise RuntimeError("Agents not spawned")

        final = await self.run_refinement(
            self._worker, self._critic, task, criteria, cwd, max_iterations
        )

        await self._upstream_update(
            self._critic,
            AgentMessageChunk(
                content=text_block(final),
                session_update="agent_message_chunk",
            ),
        )

        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        self._cancel_event.set()
        for child in [self._worker, self._critic]:
            if child:
                try:
                    await child.conn.cancel(session_id=child.session_id)
                except Exception:
                    pass
        if self._prompt_task and not self._prompt_task.done():
            self._prompt_task.cancel()

    async def close_session(self, session_id: str, **kwargs: Any) -> None:
        for child in [self._worker, self._critic]:
            if child:
                try:
                    await child.spawn_cm.__aexit__(None, None, None)
                except Exception:
                    pass
        self._worker = None
        self._critic = None
        self._started = False

    # -- Client interface (called by child agents) --

    async def session_update(
        self,
        session_id: str,
        update: AgentMessageChunk
        | AgentThoughtChunk
        | ToolCallStart
        | ToolCallProgress,
        **kwargs: Any,
    ) -> None:
        child = None
        for c in [self._worker, self._critic]:
            if c and c.session_id == session_id:
                child = c
                break
        agent_id = child.role if child else "unknown"

        if child:
            self._track_conversation(child, update)

        # Always use upstream session ID — the client only knows one session
        if self._upstream and self._upstream_session_id:
            # Attach agent identity for upstream routing
            if hasattr(update, "field_meta"):
                update.field_meta = {"agent_id": agent_id}
            # Send to upstream — never forward end_turn from children
            await self._upstream.session_update(
                session_id=self._upstream_session_id,
                update=update,
            )

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCall,
        **kwargs: Any,
    ) -> Any:
        if self._upstream:
            return await self._upstream.request_permission(
                options=options,
                session_id=self._upstream_session_id,
                tool_call=tool_call,
            )
        from acp.schema import RequestPermissionResponse

        return RequestPermissionResponse(option_id=options[0].id if options else "")

    async def read_text_file(self, path: str, session_id: str, **kwargs: Any):
        if self._upstream:
            return await self._upstream.read_text_file(
                path=path, session_id=self._upstream_session_id, **kwargs
            )
        raise RuntimeError("No upstream client")

    async def write_text_file(
        self, content: str, path: str, session_id: str, **kwargs: Any
    ):
        if self._upstream:
            return await self._upstream.write_text_file(
                content=content,
                path=path,
                session_id=self._upstream_session_id,
                **kwargs,
            )
        return None

    async def create_terminal(self, command: str, session_id: str, **kwargs: Any):
        if self._upstream:
            return await self._upstream.create_terminal(
                command=command, session_id=self._upstream_session_id, **kwargs
            )
        raise RuntimeError("No upstream client")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any):
        if self._upstream:
            return await self._upstream.terminal_output(
                session_id=self._upstream_session_id, terminal_id=terminal_id, **kwargs
            )
        raise RuntimeError("No upstream client")

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ):
        if self._upstream:
            return await self._upstream.wait_for_terminal_exit(
                session_id=self._upstream_session_id, terminal_id=terminal_id, **kwargs
            )
        raise RuntimeError("No upstream client")

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any):
        if self._upstream:
            return await self._upstream.release_terminal(
                session_id=self._upstream_session_id, terminal_id=terminal_id, **kwargs
            )
        return None

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any):
        if self._upstream:
            return await self._upstream.kill_terminal(
                session_id=self._upstream_session_id, terminal_id=terminal_id, **kwargs
            )
        return None

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "_iterative/status":
            return {
                "started": self._started,
                "worker_session": self._worker.session_id if self._worker else None,
                "critic_session": self._critic.session_id if self._critic else None,
                "worker_messages": len(self._worker.conversation)
                if self._worker
                else 0,
                "critic_messages": len(self._critic.conversation)
                if self._critic
                else 0,
            }
        if method == "_iterative/conversation":
            role = params.get("role")
            child = (
                self._worker
                if role == "worker"
                else self._critic
                if role == "critic"
                else None
            )
            if child:
                return {"role": role, "conversation": child.conversation}
            return {"error": "role must be 'worker' or 'critic'"}
        if self._upstream:
            return await self._upstream.ext_method(method, params)
        raise RuntimeError(f"Unknown extension method: {method}")

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        if self._upstream:
            await self._upstream.ext_notification(method, params)

    # -- Internal helpers --

    async def _upstream_update(self, child, update):
        if self._upstream and self._upstream_session_id:
            if hasattr(update, "field_meta"):
                update.field_meta = {"agent_id": child.role}
            await self._upstream.session_update(
                session_id=self._upstream_session_id,
                update=update,
            )

    async def _send_to_child(self, child: _ChildState, prompt: str, cwd: str) -> None:
        child._last_assistant = ""
        child._thinking_buffer = ""
        child.conversation.append({"role": "user", "content": prompt})

        resp = await child.conn.prompt(
            session_id=child.session_id,
            prompt=[text_block(prompt)],
        )

    def _track_conversation(self, child: _ChildState, update: Any) -> None:
        if isinstance(update, AgentMessageChunk):
            text = _extract_update_text(update.content)
            if child.conversation and child.conversation[-1].get("role") == "assistant":
                child.conversation[-1]["content"] += text
            else:
                child.conversation.append({"role": "assistant", "content": text})
            child._last_assistant = child.conversation[-1]["content"]

        elif isinstance(update, AgentThoughtChunk):
            child._thinking_buffer += _extract_update_text(update.content)
            if child.conversation and child.conversation[-1].get("role") == "assistant":
                child.conversation[-1]["reasoning_content"] = child._thinking_buffer

        elif isinstance(update, ToolCallStart):
            child.conversation.append(
                {
                    "role": "tool_call",
                    "tool_call_id": update.tool_call_id,
                    "title": update.title,
                }
            )

        elif isinstance(update, ToolCallProgress):
            for i, msg in enumerate(child.conversation):
                if msg.get("tool_call_id") == update.tool_call_id:
                    child.conversation[i]["status"] = update.status
                    break


def _extract_text(prompt: list):
    parts = []
    for block in prompt:
        if isinstance(block, TextContentBlock):
            parts.append(block.text)
        elif isinstance(block, ImageContentBlock):
            parts.append("[image]")
        elif isinstance(block, (ResourceContentBlock,)):
            parts.append(f"[resource: {getattr(block, 'uri', '')}]")
    return "\n".join(parts) or ""


def _extract_update_text(content: Any) -> str:
    if isinstance(content, TextContentBlock):
        return content.text
    elif hasattr(content, "text"):
        return content.text
    elif isinstance(content, dict):
        return content.get("text", "")
    return ""


class _ChildClient(Client):
    """Thin ACP Client that delegates all calls to the parent IterativeRefinementAgent.

    Each spawned child agent gets one of these. It forwards all
    client method calls and session updates to the parent,
    which then routes them to the upstream client.
    """

    def __init__(self, parent: "IterativeRefinementAgent"):
        self._parent = parent

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCall,
        **kwargs: Any,
    ) -> Any:
        return await self._parent.request_permission(
            options, session_id, tool_call, **kwargs
        )

    async def session_update(
        self,
        session_id: str,
        update: AgentMessageChunk
        | AgentThoughtChunk
        | ToolCallStart
        | ToolCallProgress,
        **kwargs: Any,
    ) -> None:
        await self._parent.session_update(session_id, update, **kwargs)

    async def write_text_file(
        self, content: str, path: str, session_id: str, **kwargs: Any
    ) -> Any:
        return await self._parent.write_text_file(content, path, session_id, **kwargs)

    async def read_text_file(
        self, path: str, session_id: str, **kwargs: Any
    ) -> Any:
        return await self._parent.read_text_file(path, session_id, **kwargs)

    async def create_terminal(
        self, command: str, session_id: str, **kwargs: Any
    ) -> Any:
        return await self._parent.create_terminal(command, session_id, **kwargs)

    async def terminal_output(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> Any:
        return await self._parent.terminal_output(session_id, terminal_id, **kwargs)

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> Any:
        return await self._parent.wait_for_terminal_exit(
            session_id, terminal_id, **kwargs
        )

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> Any:
        return await self._parent.release_terminal(session_id, terminal_id, **kwargs)

    async def kill_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> Any:
        return await self._parent.kill_terminal(session_id, terminal_id, **kwargs)

    async def ext_method(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._parent.ext_method(method, params)

    async def ext_notification(
        self, method: str, params: dict[str, Any]
    ) -> None:
        await self._parent.ext_notification(method, params)


async def main() -> None:
    agent = IterativeRefinementAgent()
    await run_agent(agent)


if __name__ == "__main__":
    asyncio.run(main())
