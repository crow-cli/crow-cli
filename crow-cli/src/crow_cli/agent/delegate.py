"""Native delegate tool — blocking delegation (Milestone A).

The delegate tool is a NATIVE tool of the react loop (a Python callable),
not an MCP tool: the subagent is our task and our session, so launch,
cancel and result are plain Python — no protocol in the middle.

Blocking semantics: the delegate call awaits the subagent's react loop and
returns its final answer as the tool result. Parallel delegate calls in one
assistant message run concurrently (asyncio.gather in react.py). Because
the subagent runs inside the parent's await chain, cancelling the parent's
prompt task cancels the whole stack — the house of cards falls together.

The client only knows the parent session, so the subagent's updates are
swallowed by _DelegateConn; its work is still fully observable through the
shared database (query_session on the subagent's session id).
"""

import asyncio
import contextlib
from contextlib import AsyncExitStack
from logging import Logger
from typing import Any

from acp.interfaces import Client
from acp.schema import ToolCallUpdate
from crow_cli.config import Config
from crow_cli.agent.llm import configure_llm
from crow_cli.agent.mcp_client import create_mcp_client_from_acp, get_tools
from crow_cli.agent.session import AgentSession, make_agent_session
from crow_cli.agent.tasks import TaskRegistry
from crow_cli.memory import wire_session_id

DELEGATE_TOOL_NAME = "delegate"

DELEGATE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": DELEGATE_TOOL_NAME,
        "description": (
            "Delegate a self-contained task to a subagent. The subagent is a "
            "fresh Crow session with its own history and the same tools; it "
            "runs to completion and its final answer is returned here. Use "
            "this for work that is separable from the current conversation "
            "(research, a focused refactor, a verification pass). Multiple "
            "delegate calls in one message run in parallel. The subagent's "
            "full transcript persists in its own session and can be read "
            "with query_session."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "The complete task for the subagent. Must be "
                        "self-contained: the subagent does NOT see this "
                        "conversation, so include all context it needs."
                    ),
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Optional model name (from config.yaml models:) for "
                        "the subagent. Defaults to the current session's model."
                    ),
                },
            },
            "required": ["prompt"],
        },
    },
}


class _DelegateConn:
    """ACP conn shim for a subagent's react loop.

    The client has no knowledge of the subagent session, so its
    session_updates cannot be forwarded as-is. Milestone A swallows them:
    the parent's still-open delegate tool call is the client-side surface,
    and the subagent's transcript is readable from the shared database.
    """

    async def session_update(self, session_id: str, update: Any) -> None:
        return None


def _last_assistant_text(messages: list[dict]) -> str:
    """The subagent's final answer: last assistant message with content."""
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if any(t.strip() for t in texts):
                return " ".join(texts)
    return "(the subagent produced no final answer)"


def _resolve_provider(config: Config, model_identifier: str | None):
    """Provider for a stored model_identifier, falling back to the first
    configured provider (same fallback as the prompt path)."""
    provider_name = ""
    if model_identifier:
        match = next(
            (
                m
                for m in config.llm.models.values()
                if m.model_id == model_identifier
            ),
            None,
        )
        if match is not None:
            provider_name = match.provider_name
    provider = config.llm.providers.get(provider_name)
    if provider is None and config.llm.providers:
        provider = next(iter(config.llm.providers.values()))
    return provider


async def execute_delegate(
    *,
    conn: Client,
    parent_session: AgentSession,
    turn_id: str,
    tool_call_id: str,
    acp_tool_call_id: str,
    args: dict[str, Any],
    config: Config,
    mcp_servers: list | None,
    registry: TaskRegistry | None,
    logger: Logger,
) -> str:
    """Run a subagent to completion and return its final answer.

    Runs inside the parent's await chain — cancellation of the parent prompt
    task propagates straight through to the subagent's react loop (which
    persists its own cancelled state before re-raising).
    """
    prompt = args.get("prompt")
    if not prompt or not str(prompt).strip():
        return "Error: delegate requires a non-empty 'prompt' argument."

    # Lazy import: react.py imports this module for execute_delegate.
    from crow_cli.agent.react import react_loop

    parent_wire = wire_session_id(parent_session.agent_id)
    model_id = args.get("model") or parent_session.model_identifier
    provider = _resolve_provider(config, model_id)
    if provider is None:
        return "Error: no LLM providers configured for the subagent."

    exit_stack = AsyncExitStack()
    info = None
    sub_session: AgentSession | None = None
    try:
        # The subagent provisions its OWN MCP client from the parent's
        # server list (client-owned tool supply, same as any session).
        _, mcp_client = create_mcp_client_from_acp(
            mcp_servers=mcp_servers, cwd=parent_session.cwd, logger=logger
        )
        if mcp_client is not None:
            mcp_client = await exit_stack.enter_async_context(mcp_client)
        tools = await get_tools(mcp_client)
        tools = [*tools, DELEGATE_TOOL]  # recursion: delegates can delegate

        sub_session = await make_agent_session(
            config, tools, model_id, parent_session.cwd
        )
        sub_wire = wire_session_id(sub_session.agent_id)
        if registry is not None:
            info = registry.launch(
                "delegate", parent_wire, tool_call_id, sub_session.session_id
            )
        logger.info(
            "DELEGATE: %s launched subagent %s (model=%s, %d tools)",
            parent_wire,
            sub_session.session_id,
            model_id,
            len(tools),
        )

        # Keep the parent's still-open tool call alive on the client.
        with contextlib.suppress(Exception):
            await conn.session_update(
                session_id=parent_wire,
                update=ToolCallUpdate(
                    session_update="tool_call_update",
                    tool_call_id=acp_tool_call_id,
                    status="in_progress",
                    title=f"delegate: {sub_session.session_id}",
                ),
            )

        await sub_session.add_message({"role": "user", "content": prompt})

        llm = configure_llm(
            provider=provider, debug=config.chunk_log, logger=logger
        )
        final_messages: list[dict] | None = None
        async for chunk in react_loop(
            conn=_DelegateConn(),
            config=config,
            client_capabilities=None,  # self-contained: terminal/fs fall to MCP
            turn_id=f"{turn_id}/delegate-{sub_session.session_id}",
            mcp_clients={sub_wire: mcp_client},
            llm=llm,
            tools=tools,
            sessions={sub_session.agent_id: sub_session},
            agent_id=sub_session.agent_id,
            state_accumulators={},
            logger=logger,
            registry=registry,
            session_mcp_servers=mcp_servers,
        ):
            if chunk.get("type") == "final_history":
                final_messages = chunk["messages"]

        answer = _last_assistant_text(final_messages or sub_session.messages)
        if registry is not None and info is not None:
            registry.finish(info.task_id, answer)
        with contextlib.suppress(Exception):
            await conn.session_update(
                session_id=parent_wire,
                update=ToolCallUpdate(
                    session_update="tool_call_update",
                    tool_call_id=acp_tool_call_id,
                    status="completed",
                ),
            )
        await sub_session.close()
        return f"[delegate {sub_session.session_id} finished]\n{answer}"

    except asyncio.CancelledError:
        if registry is not None and info is not None:
            registry.finish(info.task_id, None, status="cancelled")
        with contextlib.suppress(Exception):
            await conn.session_update(
                session_id=parent_wire,
                update=ToolCallUpdate(
                    session_update="tool_call_update",
                    tool_call_id=acp_tool_call_id,
                    status="failed",
                    title="delegate cancelled",
                ),
            )
        raise
    except Exception as e:
        logger.error("DELEGATE failed: %s", e, exc_info=True)
        if registry is not None and info is not None:
            registry.finish(info.task_id, str(e), status="failed")
        with contextlib.suppress(Exception):
            await conn.session_update(
                session_id=parent_wire,
                update=ToolCallUpdate(
                    session_update="tool_call_update",
                    tool_call_id=acp_tool_call_id,
                    status="failed",
                ),
            )
        return f"Error: delegate failed: {e}"
    finally:
        await exit_stack.aclose()
