"""Native delegate tool — non-blocking delegation with park/wake (Milestone B).

The delegate tool is a NATIVE tool of the react loop (a Python callable),
not an MCP tool: the subagent is our task and our session, so launch,
cancel and result are plain Python — no protocol in the middle.

Non-blocking semantics: the delegate call provisions a subagent, launches
it as a background asyncio task, and returns the launch ack immediately.
The subagent's final answer does NOT come back as the tool result — the
wire contract is one result per call, and that result is the ack. The
completion lands on the owner's wake queue and the react loop injects it
as a synthetic plain message (react.park_until_completion). The client-side
surface for the running subagent is a per-task tool_call_update stream
(`<turn_id>/<task_id>`) that stays in_progress through the park and flips
to completed/failed when the subagent finishes.

Cancel tree: the background handle is registered on the TaskInfo, so
cancelling the owner's prompt task cancels every generation of delegates
(react.cancel_outstanding_delegates awaits each handle, so the subagents'
cancelled state is persisted before the cancel response returns).

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
from acp.schema import ToolCallProgress
from crow_cli.config import Config
from crow_cli.agent.llm import configure_llm
from crow_cli.agent.mcp_client import create_mcp_client_from_acp, get_tools
from crow_cli.agent.session import AgentSession, make_agent_session
from crow_cli.agent.tasks import TaskInfo, TaskRegistry
from crow_cli.memory import wire_session_id

DELEGATE_TOOL_NAME = "delegate"

DELEGATE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": DELEGATE_TOOL_NAME,
        "description": (
            "Delegate a self-contained task to a subagent. The subagent is a "
            "fresh Crow session with its own history and the same tools. "
            "This call is NON-BLOCKING: it launches the subagent and returns "
            "immediately with a task id. The subagent's result arrives later "
            "as a follow-up message in this conversation — do NOT try to "
            "fetch it yourself. Keep working on other things if you have "
            "any; when you have nothing left to do, simply end your turn "
            "(e.g. say you are waiting) and you will be woken with the "
            "result. Multiple delegate calls in one message launch in "
            "parallel. The subagent's full transcript persists in its own "
            "session and can be read with query_session."
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
    session_updates cannot be forwarded as-is. They are swallowed: the
    parent's per-task tool_call_update surface is the client-side view, and
    the subagent's transcript is readable from the shared database.
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


def synthetic_completion_message(info: TaskInfo) -> str:
    """The wake injection, as a plain message for the conversation.

    NEVER role=tool on the launch's tool_call_id: that call's one result was
    the launch ack. The completion is a fact that happened to the session,
    so it arrives as an ordinary (user-role) message the model reacts to.
    """
    label = info.task_id
    if info.sub_session:
        label += f": delegate {info.sub_session}"
    if info.status == "done":
        return f"[{label} finished]\n{info.result or '(no result)'}"
    if info.status == "cancelled":
        return f"[{label} cancelled]"
    return f"[{label} failed]\n{info.result or 'unknown error'}"


def _task_surface_id(turn_id: str, info: TaskInfo) -> str:
    return f"{turn_id}/{info.task_id}" if turn_id else info.task_id


async def launch_delegate(
    *,
    conn: Client,
    parent_session: AgentSession,
    turn_id: str,
    tool_call_id: str,
    acp_tool_call_id: str,
    args: dict[str, Any],
    config: Config,
    mcp_servers: list | None,
    registry: TaskRegistry,
    logger: Logger,
) -> str:
    """Provision a subagent, launch it as a background task, return at once.

    The returned string is the launch ack — the ONE result of the launch's
    tool_call_id. The subagent's answer arrives later on the owner's wake
    queue and is injected as a synthetic message by the react loop.
    """
    prompt = args.get("prompt")
    if not prompt or not str(prompt).strip():
        return "Error: delegate requires a non-empty 'prompt' argument."

    parent_wire = wire_session_id(parent_session.agent_id)
    model_id = args.get("model") or parent_session.model_identifier
    provider = _resolve_provider(config, model_id)
    if provider is None:
        return "Error: no LLM providers configured for the subagent."

    exit_stack = AsyncExitStack()
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
        await sub_session.add_message({"role": "user", "content": prompt})
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await exit_stack.aclose()
        raise
    except Exception as e:
        with contextlib.suppress(Exception):
            await exit_stack.aclose()
        logger.error("DELEGATE launch failed: %s", e, exc_info=True)
        return f"Error: delegate failed to launch: {e}"

    info = registry.launch(
        "delegate", parent_wire, tool_call_id, sub_session.session_id
    )
    sub_wire = wire_session_id(sub_session.agent_id)
    llm = configure_llm(provider=provider, debug=config.chunk_log, logger=logger)
    logger.info(
        "DELEGATE: %s launched subagent %s (%s, model=%s, %d tools)",
        parent_wire,
        sub_session.session_id,
        info.task_id,
        model_id,
        len(tools),
    )

    handle = asyncio.create_task(
        _run_subagent(
            info=info,
            conn=conn,
            parent_wire=parent_wire,
            turn_id=turn_id,
            sub_session=sub_session,
            sub_wire=sub_wire,
            llm=llm,
            tools=tools,
            mcp_client=mcp_client,
            mcp_servers=mcp_servers,
            config=config,
            registry=registry,
            logger=logger,
            exit_stack=exit_stack,
        ),
        name=f"delegate-{info.task_id}-{sub_session.session_id}",
    )
    info.handle = handle

    # Two client surfaces: the launch call COMPLETES (its one result is the
    # ack returned below); the per-task surface stays in_progress until the
    # subagent finishes — that stream keeps the delegation visible through
    # the parent's zero-token park.
    with contextlib.suppress(Exception):
        await conn.session_update(
            session_id=parent_wire,
            update=ToolCallProgress(
                session_update="tool_call_update",
                tool_call_id=acp_tool_call_id,
                status="completed",
                title=f"delegate: launched {sub_session.session_id}",
            ),
        )
    with contextlib.suppress(Exception):
        await conn.session_update(
            session_id=parent_wire,
            update=ToolCallProgress(
                session_update="tool_call_update",
                tool_call_id=_task_surface_id(turn_id, info),
                status="in_progress",
                title=f"delegate: {sub_session.session_id}",
            ),
        )

    return (
        f"Launched {info.task_id}: subagent {sub_session.session_id} is now "
        "working on the prompt. Its result will arrive later as a follow-up "
        "message in this conversation — do not try to fetch it yourself. "
        "Continue with other work if you have any; when you have nothing "
        "left to do, simply end your turn and you will be woken with the "
        "result."
    )


async def _run_subagent(
    *,
    info: TaskInfo,
    conn: Client,
    parent_wire: str,
    turn_id: str,
    sub_session: AgentSession,
    sub_wire: str,
    llm,
    tools: list[dict],
    mcp_client,
    mcp_servers: list | None,
    config: Config,
    registry: TaskRegistry,
    logger: Logger,
    exit_stack: AsyncExitStack,
) -> None:
    """The background lifetime of one delegate.

    Never raises except on cancellation: every outcome lands on the owner's
    wake queue via registry.finish. Cancellation re-raises after cleanup so
    the cancel tree's await of this handle observes it.
    """
    # Lazy import: react.py imports this module at module level.
    from crow_cli.agent.react import react_loop

    surface_id = _task_surface_id(turn_id, info)
    try:
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
        registry.finish(info.task_id, answer)
        with contextlib.suppress(Exception):
            await conn.session_update(
                session_id=parent_wire,
                update=ToolCallProgress(
                    session_update="tool_call_update",
                    tool_call_id=surface_id,
                    status="completed",
                    title=f"delegate: {sub_session.session_id}",
                ),
            )
    except asyncio.CancelledError:
        # No-op if cancel_all already marked us cancelled (the normal path) —
        # and crucially never puts on the wake queue: a cancelled owner must
        # not be woken.
        registry.finish(info.task_id, None, status="cancelled")
        with contextlib.suppress(Exception):
            await conn.session_update(
                session_id=parent_wire,
                update=ToolCallProgress(
                    session_update="tool_call_update",
                    tool_call_id=surface_id,
                    status="failed",
                    title="delegate cancelled",
                ),
            )
        raise
    except Exception as e:
        logger.error("DELEGATE %s failed: %s", info.task_id, e, exc_info=True)
        registry.finish(info.task_id, str(e), status="failed")
        with contextlib.suppress(Exception):
            await conn.session_update(
                session_id=parent_wire,
                update=ToolCallProgress(
                    session_update="tool_call_update",
                    tool_call_id=surface_id,
                    status="failed",
                    title=f"delegate: {sub_session.session_id}",
                ),
            )
    finally:
        with contextlib.suppress(Exception):
            await sub_session.close()
        with contextlib.suppress(Exception):
            await exit_stack.aclose()
