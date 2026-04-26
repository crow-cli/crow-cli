"""Refinement Orchestrator: ACP agent that natively handles the iterative_refine tool.

When the LLM decides to call iterative_refine, we intercept the tool call,
spawn worker + critic agents, run the refinement loop, stream updates to
the upstream client using a unified session ID, and return the result.

Usage:
    uv --project . run orchestrator.py
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
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
from openai import AsyncOpenAI

logger = logging.getLogger("orchestrator")

# ──────────────────────────────────────────────────────────────
# Child Agent Commands
# ──────────────────────────────────────────────────────────────
AGENT_CMD = ["uv", "--project", "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent", "run", "scratch_db.py"]
COMPACT_PROMPT = "Summarize this conversation concisely. No tools."
CRITIC_XML = (
    "<critique>\n"
    "  <score>0.0-1.0</score>\n"
    "  <task_complete>COMPLETE or INCOMPLETE</task_complete>\n"
    "  <summary>Brief summary</summary>\n"
    "</critique>\n"
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "iterative_refine",
            "description": "Run a worker-critic refinement loop for complex tasks",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "What to implement"},
                    "criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Evaluation criteria",
                    },
                    "max_iterations": {
                        "type": "integer",
                        "default": 3,
                        "description": "Max refinement loops",
                    },
                },
                "required": ["task", "criteria"],
            },
        },
    }
]

# ──────────────────────────────────────────────────────────────
# State & Helpers
# ──────────────────────────────────────────────────────────────
@dataclass
class _ChildState:
    role: str
    conn: Any
    spawn_cm: Any
    session_id: str | None = None
    conversation: list[dict] = field(default_factory=list)
    _last_assistant: str = ""

def parse_critique(text: str) -> dict:
    m1 = re.search(r"<score>([\d.]+)</score>", text)
    m2 = re.search(r"<task_complete>([^<]+)</task_complete>", text)
    m3 = re.search(r"<summary>(.*?)</summary>", text, re.DOTALL)
    return {
        "score": float(m1.group(1)) if m1 else 0.0,
        "complete": m2.group(1).strip().upper() in ("COMPLETE", "TRUE") if m2 else False,
        "summary": m3.group(1).strip() if m3 else "(no summary)",
    }

class RefinementOrchestrator(Agent, Client):
    """Orchestrator agent that intercepts iterative_refine tool calls to spawn multi-agent loops."""

    def __init__(self):
        self._upstream: Client | None = None
        self._upstream_session_id: str | None = None
        self._upstream_caps: ClientCapabilities | None = None
        self._worker: _ChildState | None = None
        self._critic: _ChildState | None = None
        self._started = False
        self._cancel_event = asyncio.Event()

    def on_connect(self, conn: Client): self._upstream = conn

    async def initialize(self, protocol_version: int, client_capabilities: ClientCapabilities | None = None, client_info: Implementation | None = None, **kw: Any) -> InitializeResponse:
        self._upstream_caps = client_capabilities
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(self, cwd: str, mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None, **kw: Any) -> NewSessionResponse:
        self._upstream_session_id = str(uuid.uuid4())
        caps = ClientCapabilities(
            terminal=bool(self._upstream_caps and getattr(self._upstream_caps, "terminal", False)),
            fs=FileSystemCapabilities(
                read_text_file=bool(self._upstream_caps and self._upstream_caps.fs and getattr(self._upstream_caps.fs, "read_text_file", False)),
                write_text_file=bool(self._upstream_caps and self._upstream_caps.fs and getattr(self._upstream_caps.fs, "write_text_file", False)),
            ),
        )
        for role in ["worker", "critic"]:
            spawn_cm = spawn_agent_process(_ChildClient(self), *AGENT_CMD, cwd=cwd, env=None)
            conn, _ = await spawn_cm.__aenter__()
            await conn.initialize(protocol_version=1, client_capabilities=caps, client_info=Implementation(name="orchestrator", version="0.1"))
            session = await conn.new_session(cwd=cwd, mcp_servers=mcp_servers or [])
            if role == "worker": self._worker = _ChildState(role, conn, spawn_cm, session.session_id)
            else: self._critic = _ChildState(role, conn, spawn_cm, session.session_id)
        self._started = True
        return NewSessionResponse(session_id=self._upstream_session_id)

    async def prompt(self, prompt: list, session_id: str, **kw: Any) -> PromptResponse:
        self._cancel_event.clear()
        try:
            return await self._react_loop(prompt, session_id)
        except asyncio.CancelledError:
            return PromptResponse(stop_reason="cancelled")
        finally:
            if self._upstream and self._upstream_session_id:
                await self._upstream.session_update(session_id=self._upstream_session_id, update=CurrentModeUpdate(session_update="current_mode_update", current_mode_id="idle"))

    async def _react_loop(self, prompt: list, session_id: str) -> PromptResponse:
        client = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        messages = [{"role": "system", "content": "You are an orchestrator. Use iterative_refine for complex tasks."}]
        messages.append({"role": "user", "content": _extract_text(prompt)})

        while True:
            resp = await client.chat.completions.create(model="qwen2.5", messages=messages, tools=TOOLS)
            choice = resp.choices[0]
            msg = choice.message

            if msg.content:
                await self._upstream.session_update(session_id=self._upstream_session_id, update=AgentMessageChunk(content=text_block(msg.content), session_update="agent_message_chunk"))
                messages.append({"role": "assistant", "content": msg.content})
                return PromptResponse(stop_reason="end_turn")

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments)
                    messages.append({"role": "assistant", "tool_calls": [tc.model_dump()]})

                    # INTERCEPT: This is where we break into multi-agent mode
                    result = await self._execute_tool(tc.function.name, args, session_id)
                    messages.append({"role": "tool", "content": result, "tool_call_id": tc.id})
            else:
                return PromptResponse(stop_reason="end_turn")

    async def _execute_tool(self, name: str, args: dict, session_id: str) -> str:
        if name != "iterative_refine" or not self._worker or not self._critic:
            return "Unknown tool or agents not spawned"

        task = args["task"]
        criteria = args["criteria"]
        max_iter = args.get("max_iterations", 3)

        await self._upstream.session_update(session_id=self._upstream_session_id, update=AgentMessageChunk(content=text_block(f"▶ Starting refinement loop for: {task}"), session_update="agent_message_chunk"))

        # Worker initial
        await self._send(self._worker, f"Implement: {task}")
        await self._send(self._worker, COMPACT_PROMPT)
        summary = self._worker._last_assistant

        for i in range(1, max_iter + 1):
            if self._cancel_event.is_set(): break
            # Critic
            await self._send(self._critic, f"Evaluate against: {criteria}\nSummary: {summary}\n{CRITIC_XML}")
            critique = parse_critique(self._critic._last_assistant)
            await self._upstream.session_update(session_id=self._upstream_session_id, update=AgentMessageChunk(content=text_block(f"[{i}/{max_iter}] Score: {critique['score']} | {critique['summary']}"), session_update="agent_message_chunk"))

            if critique["complete"]: break
            # Worker refine
            await self._send(self._worker, f"Feedback: {critique['summary']}\nImprove.")
            await self._send(self._worker, COMPACT_PROMPT)
            summary = self._worker._last_assistant

        return f"Refinement complete. Final: {summary}"

    async def _send(self, child: _ChildState, prompt: str):
        child._last_assistant = ""
        await child.conn.prompt(session_id=child.session_id, prompt=[text_block(prompt)])

    async def session_update(self, session_id: str, update: Any, **kw: Any) -> None:
        if not self._upstream or not self._upstream_session_id: return
        if hasattr(update, "field_meta"): update.field_meta = {"agent_id": self._resolve_role(session_id)}
        await self._upstream.session_update(session_id=self._upstream_session_id, update=update)

    async def cancel(self, session_id: str, **kw: Any) -> None:
        self._cancel_event.set()
        for c in [self._worker, self._critic]:
            if c: try: await c.conn.cancel(session_id=c.session_id)
                  except: pass

    def _resolve_role(self, sid: str) -> str:
        if self._worker and self._worker.session_id == sid: return "worker"
        if self._critic and self._critic.session_id == sid: return "critic"
        return "unknown"

    # Stub Client methods for upstream forwarding
    async def request_permission(self, *a, **k): return await self._upstream.request_permission(*a, **k) if self._upstream else None
    async def read_text_file(self, *a, **k): return await self._upstream.read_text_file(*a, **k) if self._upstream else None
    async def write_text_file(self, *a, **k): return await self._upstream.write_text_file(*a, **k) if self._upstream else None
    async def create_terminal(self, *a, **k): return await self._upstream.create_terminal(*a, **k) if self._upstream else None
    async def terminal_output(self, *a, **k): return await self._upstream.terminal_output(*a, **k) if self._upstream else None
    async def wait_for_terminal_exit(self, *a, **k): return await self._upstream.wait_for_terminal_exit(*a, **k) if self._upstream else None
    async def release_terminal(self, *a, **k): return await self._upstream.release_terminal(*a, **k) if self._upstream else None
    async def kill_terminal(self, *a, **k): return await self._upstream.kill_terminal(*a, **k) if self._upstream else None
    async def ext_method(self, *a, **k): return await self._upstream.ext_method(*a, **k) if self._upstream else {}
    async def ext_notification(self, *a, **k): return await self._upstream.ext_notification(*a, **k) if self._upstream else None
    async def close_session(self, session_id: str, **kw: Any) -> None:
        for c in [self._worker, self._critic]:
            if c: await c.spawn_cm.__aexit__(None, None, None)

class _ChildClient(Client):
    def __init__(self, parent: RefinementOrchestrator): self._p = parent
    async def request_permission(self, *a, **k): return await self._p.request_permission(*a, **k)
    async def session_update(self, *a, **k): return await self._p.session_update(*a, **k)
    async def write_text_file(self, *a, **k): return await self._p.write_text_file(*a, **k)
    async def read_text_file(self, *a, **k): return await self._p.read_text_file(*a, **k)
    async def create_terminal(self, *a, **k): return await self._p.create_terminal(*a, **k)
    async def terminal_output(self, *a, **k): return await self._p.terminal_output(*a, **k)
    async def wait_for_terminal_exit(self, *a, **k): return await self._p.wait_for_terminal_exit(*a, **k)
    async def release_terminal(self, *a, **k): return await self._p.release_terminal(*a, **k)
    async def kill_terminal(self, *a, **k): return await self._p.kill_terminal(*a, **k)
    async def ext_method(self, *a, **k): return await self._p.ext_method(*a, **k)
    async def ext_notification(self, *a, **k): return await self._p.ext_notification(*a, **k)

def _extract_text(prompt: list) -> str:
    return "\n".join(b.text for b in prompt if isinstance(b, TextContentBlock)) or ""

import json

async def main():
    await run_agent(RefinementOrchestrator())

if __name__ == "__main__":
    asyncio.run(main())
