"""The loop. It reports; it does not decide.

This is the one structural change agent2 exists to make. v1's ``react_loop``
was a generator that ended with a bare ``return`` when the model produced text
and no tool calls — conflating "the loop has no more foreground work" with
"the session is done". Everything that followed from that conflation was a
workaround: the delegation hold blocked *inside* the turn polling the mailbox
every two seconds, because a returned generator is a deaf one and there was no
out-of-loop watcher to wake it.

Here the loop body returns a :class:`Step` and the loop returns a
:class:`Done`. ``Done`` carries a stop reason and the final usage — it does
not mean the session is over, and this module has no opinion about what
happens next. :mod:`crow_cli.agent2.driver` decides: re-enter on queued work,
park on the inbox otherwise.

Also collapsed here: v1 had TWO output channels — it yielded
``{"type": ..., "token": ...}`` dicts that ``AcpAgent.prompt`` spent 230 lines
interleaving against its own direct ``conn.session_update`` calls. agent2 has
one emitter and the loop yields nothing.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from crow_cli.agent.session import AgentSession
from crow_cli.memory import get_engine

from . import compaction, deliveries
from .ctx import TurnCtx
from .emitter import Emitter
from .llm import StreamState, build_tool_calls, send_request, stream
# Re-exported: tools.py owns the cancelled-response contract (it is the one
#: that has to honour it mid-batch), and the loop persists the same shape when
#: a cancel lands between batches.
from .tools import (
    TOOL_CALL_CANCELLED_MESSAGE,
    cancelled_tool_results,
    execute_tool_calls,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Continue:
    """Tools ran (or a delivery landed). Loop again."""


@dataclass(frozen=True, slots=True)
class Restart:
    """Compaction swapped the agent row. Loop again against the new one."""


@dataclass(frozen=True, slots=True)
class Done:
    """No more foreground work. Why, and what it cost.

    Not "the session is done" — that is the driver's call. A session that
    just finished a turn with a subagent still running is Done and still very
    much alive.
    """

    stop_reason: str = "end_turn"
    usage: Optional[dict] = None
    #: How many tool calls this turn actually ran. The driver cannot infer it
    #: and the goal cannot do without it: a turn that only talked made no
    #: observable progress, and continuing one is the infinite loop.
    #: Stays 0 on the ``Done`` the driver builds for a cancel or a crash: the
    #: loop never reached a reporting site. Neither path consults it — a cancel
    #: pauses the goal and a crash blocks it, whatever progress was made.
    tools_used: int = 0


Step = Union[Continue, Restart, Done]


@dataclass
class Deps:
    """Per-session resources the loop needs but does not own.

    Kept out of :class:`TurnCtx` on purpose: a turn is frozen and these are
    shared, replaced on resume, and torn down by the agent's exit stack.
    """

    llm: Any
    tools: list[dict]
    mcp_clients: dict[str, Any]
    state: StreamState
    engine: Any
    max_turns: int = 50000
    compactor: Any = None
    compact_system_prompt: Any = None
    on_compact: Any = None
    chunk_log_dir: Optional[str] = None


@dataclass
class LoopState:
    """What survives from one iteration to the next."""

    ctx: TurnCtx
    #: Message count as of this turn's last compaction (None = none yet).
    #: See :func:`compaction.worth_compacting` for why this exists.
    compacted_at_len: Optional[int] = None
    #: Tool calls run so far this turn, carried to :attr:`Done.tools_used`.
    #: Lives here rather than in a local because the turn that reports it is
    #: not the iteration that ran them.
    tools_used: int = 0


async def react(ctx: TurnCtx, deps: Deps) -> Done:
    """Run foreground work until there is none, and report why it stopped."""
    state = LoopState(ctx=ctx)
    engine = deps.engine or get_engine(ctx.config.db_uri)

    # Prompt-start drain: completions that landed while this session was
    # parked — including everything queued while a cancelled turn was dead —
    # are waiting in the mailbox. Inject them ALL, priority order, before the
    # first model call, so this turn starts knowing its tasks finished.
    await deliveries.consult(engine, state.ctx.session, state.ctx.emitter)

    for turn in range(deps.max_turns):
        step = await _step(state, turn, deps, engine)
        if isinstance(step, Done):
            return step

    return Done(stop_reason="max_turn_requests", tools_used=state.tools_used)


async def _step(state: LoopState, turn: int, deps: Deps, engine: Any) -> Step:
    """One iteration: consult -> send -> stream -> threshold -> tools-or-Done."""
    ctx = state.ctx
    emitter: Emitter = ctx.emitter
    session: AgentSession = ctx.session
    log = ctx.logger or logger

    # Top-of-loop checkpoint: highs that landed since the last breakpoint
    # surface immediately; lows keep holding to end of turn by design.
    await deliveries.consult(engine, session, emitter, high_only=True)

    chunk_log_path = request_log_path = None
    if deps.chunk_log_dir:
        # The loop index belongs in the filename: turn_id is constant for the
        # whole prompt, so without it every iteration overwrites the same
        # request file and only the LAST payload survives — exactly the turns
        # where a delivery was injected would be lost.
        stem = Path(deps.chunk_log_dir) / f"turn-{turn:03d}-{ctx.turn_id}"
        chunk_log_path = f"{stem}.jsonl"
        request_log_path = f"{stem}-request.json"

    response = await send_request(
        deps.llm,
        session.messages,
        session.model_identifier,
        deps.tools,
        ctx.config.MAX_TOKENS,
        config=ctx.config,
        max_retries=ctx.config.max_retries_per_step,
        request_log_path=request_log_path,
    )

    # One assistant reply per LLM call, so one messageId per stream — but
    # thoughts are a separate message from the reply (a client keys its
    # markdown document by messageId), so each stream mints lazily on its
    # first token and an LLM call with no reasoning burns no id.
    mids: dict[str, Optional[str]] = {"thinking": None, "content": None}

    async def on_thought(token: str) -> None:
        if mids["thinking"] is None:
            mids["thinking"] = emitter.start_message()
        await emitter.thought_chunk(mids["thinking"], token)

    async def on_content(token: str) -> None:
        if mids["content"] is None:
            mids["content"] = emitter.start_message()
        await emitter.agent_chunk(mids["content"], token)

    deps.state.reset()
    try:
        completion = await stream(
            response,
            deps.state,
            on_thought=on_thought,
            on_content=on_content,
            chunk_log_path=chunk_log_path,
        )
    except asyncio.CancelledError:
        log.info("Cancelled mid-stream — persisting what arrived")
        await _persist_cancelled_stream(session, deps.state, log)
        raise

    threshold = compaction.threshold_for(ctx.config, session.model_identifier)
    if completion.usage and completion.usage.get("total_tokens"):
        await emitter.usage(int(completion.usage["total_tokens"]), threshold)

    if compaction.over_threshold(completion.usage, threshold):
        if not compaction.worth_compacting(session, state.compacted_at_len):
            log.warning(
                "Over the %s-token ceiling but nothing has been added since "
                "the last compaction (%d messages) — continuing without "
                "compacting. The floor is the system prompt plus the handoff: "
                "raise max_compact_tokens or shrink the system prompt.",
                threshold,
                len(session.messages),
            )
        else:
            log.info("Token threshold crossed. Initiating compaction...")
            new_session = await compaction.run(
                ctx,
                deps.llm,
                on_compact=deps.on_compact,
                compactor=deps.compactor,
                compact_system_prompt=deps.compact_system_prompt,
            )
            # Compaction mints a new agent row inside the SAME wire sessionId.
            # Rebind so every later write in this prompt lands on it.
            state.ctx = ctx.with_session(new_session)
            state.compacted_at_len = len(new_session.messages)
            log.info("Compaction complete — %d messages", len(new_session.messages))
            return Restart()

    if completion.has_tools:
        return await _run_tools(state, completion, deps, engine, log)

    if completion.content or completion.thinking:
        await session.add_assistant_response(
            deps.state.thinking, deps.state.content, [], log, completion.usage
        )
        # End of turn is a mailbox breakpoint: if a completion landed while
        # the model was talking, inject it and keep going rather than ending
        # the turn only to be woken a moment later.
        if await deliveries.consult(engine, session, emitter):
            return Continue()
        log.info("Final react turn usage: %s", completion.usage)
        return Done(
            stop_reason="end_turn",
            usage=completion.usage,
            tools_used=state.tools_used,
        )

    # No content, no tools: a provider that returned an empty completion.
    # Persisting an empty assistant row would pollute history, and looping
    # would spin to max_turns, so report it and let the driver go idle.
    log.warning("Empty completion — no content and no tool calls")
    return Done(
        stop_reason="end_turn", usage=completion.usage, tools_used=state.tools_used
    )


async def _run_tools(
    state: LoopState, completion: Any, deps: Deps, engine: Any, log: logging.Logger
) -> Step:
    """Execute the batch, persist both sides, then take the mid-turn checkpoint."""
    ctx = state.ctx
    tool_results: list[dict] = []
    try:
        await execute_tool_calls(
            ctx=ctx,
            mcp_clients=deps.mcp_clients,
            tool_call_inputs=completion.tool_calls,
            tool_results=tool_results,
        )
    except asyncio.CancelledError:
        # execute_tool_calls already filled "cancelled" placeholders for every
        # call with no result, so persist the assistant message WITH its tool
        # calls and the full response set — history stays valid.
        log.info("Cancelled during tool execution — persisting before re-raising")
        await ctx.session.add_assistant_response(
            deps.state.thinking, deps.state.content, completion.tool_calls, log, completion.usage
        )
        await ctx.session.add_tool_response(tool_results, log)
        # Background semantics: cancelling the parent does NOT touch its
        # subagents — they keep running and their completions still land in
        # the mailbox. The model cancels them itself if it wants to.
        raise

    # Counted after the batch survives, not before: a cancel re-raises out of
    # execute_tool_calls and a batch that never finished is not progress.
    state.tools_used += len(completion.tool_calls)
    await ctx.session.add_assistant_response(
        deps.state.thinking, deps.state.content, completion.tool_calls, log, completion.usage
    )
    await ctx.session.add_tool_response(tool_results, log)
    # Between-batch: inject HIGH-priority deliveries immediately so the model
    # sees cancels and urgencies next iteration; lows hold to end of turn.
    await deliveries.consult(engine, ctx.session, ctx.emitter, high_only=True)
    return Continue()


async def _persist_cancelled_stream(session: AgentSession, state: StreamState, log) -> None:
    """Persist a valid assistant message from a half-finished stream.

    Incomplete calls — no id or no name yet, cancelled very early — are
    filtered out, since they cannot be addressed in history.
    """
    tool_calls, _ = build_tool_calls(state)
    tool_calls = [tc for tc in tool_calls if tc["id"] and tc["function"]["name"]]
    await session.add_assistant_response(state.thinking, state.content, tool_calls, log, None)
    if tool_calls:
        await session.add_tool_response(cancelled_tool_results(tool_calls), log)
