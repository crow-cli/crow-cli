"""
Compaction - summarize conversation history to reduce context window.

Simplified approach:
1. Find unexecuted tool calls (tool_call_ids with no matching tool response)
2. Append fake "tool call failed - reason: compaction" for each
3. Append compaction prompt to the message history
4. Send to LLM with tool_choice="none"
5. Create new agent record with same session_id, incremented agent_idx
6. Insert compacted messages (system + summary) under new agent
7. Old agent and its messages remain untouched - full history preserved

Nothing is ever deleted.

Compaction is a CALLABLE, not a fixed pipeline. :func:`compact` owns the
mechanics every strategy needs — minting the next agent row inside the same
wire session, writing the handoff message, firing ``on_compact`` — and delegates
the two decisions to whoever is installed:

* what to ask the model, and what the next generation's first message says
  (the :class:`Compactor`, returning a :class:`CompactResponse`);
* what the next generation's SYSTEM PROMPT is (the system-prompt callable on
  :class:`CompactCtx`, returning a
  :class:`~crow_cli.agent.prompt.SystemPromptResponse`).

The second is why compaction and system-prompt creation are one contract and
not two. A compacted generation is a fresh agent row with a fresh system
prompt, so a compactor that cannot reach prompt creation cannot do anything
interesting — it cannot tell the successor it is generation four, cannot fold
the summary into the system message instead of a user turn, cannot narrow the
skills catalog for a session that has already found what it needs. The callable
it is handed defaults to the same standard prompt ``session/new`` uses, and a
project can pass a different one.

``default_compactor`` is the strategy above: ONE pass, ``COMPACTION_PROMPT``,
summary plus the flattened tail of the conversation handed over as a user
message. It used to run two more passes over the same warm history — a
harness-level analysis and a set of project ideas, each written to its own
markdown file. Those are gone from the default path: on a local model they
roughly tripled compaction time, on a token plan they tripled the cost, and
because the passes cannot read what earlier sessions already wrote they
produced the same observations over and over. They are a good example of what a
custom compactor is for — see ``examples/custom_compactor.py``.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from logging import Logger
from typing import Any

from openai import AsyncOpenAI

from crow_cli.agent.prompt import SystemPromptResponse, default_system_prompt
from crow_cli.agent.session import AgentSession, make_agent_session
from crow_cli.config import Config, sampling_params_for
from crow_cli.memory import build_agent_id

MAX_OUTPUT_TOKENS = 30000

COMPACTION_PROMPT = """Please summarize the entire conversation up to this point.
Include:
- What the user asked for
- What you attempted and the results
- What files were created/modified
- Current state of the work
- Any errors encountered
- What still needs to be done

Be thorough and detailed. This summary will replace the conversation history, so include everything a new agent would need to continue the work seamlessly.
"""


def _fill_missing_tool_responses(messages: list[dict]) -> list[dict]:
    """
    Only checks the LAST assistant message for dangling tool calls.
    All prior turns already have their tool responses.
    """
    # Walk backwards to find the last assistant message with tool_calls
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.get("role") == "assistant" and "tool_calls" in msg:
            call_ids = {
                tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                for tc in msg["tool_calls"]
            }
            # Scan trailing tool responses for matching IDs
            response_ids = set()
            for j in range(i + 1, len(messages)):
                if messages[j].get("role") == "tool":
                    tcid = messages[j].get("tool_call_id")
                    if tcid:
                        response_ids.add(tcid)

            missing = call_ids - response_ids
            if not missing:
                return list(messages)  # All responded, return as-is

            result = list(messages)
            for tool_call_id in sorted(missing):
                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": "Tool call was interrupted due to context compaction. Please retry if still needed.",
                    }
                )
            return result

    return list(messages)  # No tool calls found at all


def history_prefix(session: AgentSession) -> list[dict]:
    """The session's messages, made safe to append one more user turn to.

    Two repairs, needed by every pass that ends in a user message: dangling
    tool calls on the last assistant turn get a synthetic response (providers
    reject an unanswered tool_call), and a trailing user message gets a
    lightweight assistant placeholder (providers reject user+user).

    Returns a FRESH list, rebuilt from the session each call, so a strategy
    that asks several questions sends byte-identical bytes up to each of its
    own trailing prompts — which is what makes the provider's prompt-prefix
    cache hit on the second and later ones.
    """
    messages = _fill_missing_tool_responses(session.messages)
    if messages and messages[-1].get("role") == "user":
        messages.append(
            {
                "role": "assistant",
                "content": "Ready to compact. Calling no tools.",
            }
        )
    return messages


async def _stream_completion(
    llm: AsyncOpenAI,
    session: AgentSession,
    messages: list[dict],
    config: Config,
) -> tuple[str, dict]:
    """Send ``messages`` over a streamed request and accumulate the text.

    Streaming matters for slow (local) models: a non-streaming request has to
    generate the whole answer before the client's read timeout fires, while a
    streamed one only has to produce *a* chunk inside the timeout window.

    Returns the text and a usage dict — usage arrives on the final, choice-less
    chunk when ``include_usage`` is set, and some providers omit it.
    """
    stream = await llm.chat.completions.create(
        model=session.model_identifier,
        messages=messages,
        tools=session.tools if session.tools else None,
        tool_choice="none",
        max_tokens=MAX_OUTPUT_TOKENS,
        stream=True,
        stream_options={"include_usage": True},
        **sampling_params_for(config, session.model_identifier),
    )

    parts: list[str] = []
    usage = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            parts.append(chunk.choices[0].delta.content)
        if chunk.usage:
            usage = {
                "prompt_tokens": getattr(chunk.usage, "prompt_tokens", None),
                "completion_tokens": getattr(chunk.usage, "completion_tokens", None),
                "total_tokens": getattr(chunk.usage, "total_tokens", None),
            }

    return "".join(parts), usage


async def ask_over_history(
    llm: AsyncOpenAI,
    session: AgentSession,
    config: Config,
    prompt: str,
) -> tuple[str, dict]:
    """Ask ``prompt`` of the session's full history and stream the answer.

    The one function every compaction-time pass goes through: same history,
    same request shape, same sampling rule — only the trailing user message
    differs.
    """
    messages = history_prefix(session)
    messages.append({"role": "user", "content": prompt})
    return await _stream_completion(llm, session, messages, config)


@dataclass(frozen=True)
class CompactCtx:
    """What a compaction callable is handed: the generation being compacted, and
    the equipment to replace it.

    Frozen and built fresh per call, inside :func:`compact`, for the one session
    being compacted. An agent serves many sessions; nothing here is cached on
    the agent, so one session's compaction cannot see another's state.

    ``system_prompt`` is the coupling that makes this contract worth having. A
    compacted generation is a new agent row with a new system prompt, so a
    compactor that cannot reach prompt creation can say nothing to its successor
    beyond the handoff message. It is a callable rather than a finished
    :class:`~crow_cli.agent.prompt.SystemPromptResponse` because the interesting
    strategies compute the prompt FROM the summary they just made.
    """

    session: AgentSession
    llm_client: AsyncOpenAI
    config: Config
    system_prompt: Callable[["CompactCtx"], SystemPromptResponse]
    logger: Logger | None = None


@dataclass(frozen=True)
class CompactResponse:
    """A compaction callable's answer: the next generation, described.

    ``prompt`` becomes the new agent's first user message — the handoff. The
    other two fields are its system prompt, and are usually
    ``ctx.system_prompt(ctx)`` passed straight through; they ride on the response
    rather than being resolved by :func:`compact` so a strategy can override them
    per run — a summary that belongs in the system message, a generation that
    should not be shown the skills catalog again.

    The response carries no agent id, index or session id on purpose. That
    arithmetic is the harness's — same wire session, same fork, next
    ``agent_idx`` — and a strategy that had to get it right would be
    reimplementing :func:`compact`.
    """

    system_template: str
    system_args: dict[str, Any]
    prompt: str


#: The compaction seam. ``AcpAgent(compactor=...)`` installs one and every
#: session that agent serves compacts through it.
Compactor = Callable[[CompactCtx], Awaitable[CompactResponse]]

#: The system-prompt seam for a compacted generation. A successor is not a fresh
#: session, so this is not the ``session/new`` callable — but it defaults to
#: giving the same standard prompt.
CompactSystemPrompt = Callable[[CompactCtx], SystemPromptResponse]


def compact_system_prompt(ctx: CompactCtx) -> SystemPromptResponse:
    """The standard prompt for a compacted generation: what ``session/new`` would
    have given it, rebuilt against the cwd as it stands now rather than as it
    stood when the session opened."""
    return default_system_prompt(ctx.config, ctx.session.cwd, ctx.session.session_id)


async def default_compactor(ctx: CompactCtx) -> CompactResponse:
    """One pass: summarize the history, hand the summary plus the flattened tail
    of the conversation to the next generation as its first user message.

    Reusable on purpose — a strategy that wants the standard summary and then
    something extra calls this and keeps ``response.prompt``.
    """
    summary, usage = await ask_over_history(
        ctx.llm_client, ctx.session, ctx.config, COMPACTION_PROMPT
    )
    if ctx.logger:
        ctx.logger.info(f"Compact usage: {usage}")
    system_prompt = ctx.system_prompt(ctx)
    return CompactResponse(
        system_template=system_prompt.template,
        system_args=system_prompt.template_args,
        prompt=f"{summary}\n\nLast messages:\n\n{last_messages(ctx.session)}",
    )


async def compact(
    session: AgentSession,
    llm: AsyncOpenAI,
    config: Config,
    on_compact: callable = None,
    logger: Logger = None,
    compactor: Compactor | None = None,
    system_prompt: CompactSystemPrompt | None = None,
) -> AgentSession:
    """Compact ``session`` into a new agent generation.

    The mechanics live here and nowhere else. The strategy is asked what the
    next generation should look like; this builds it — same ``session_id``, same
    ``fork_idx``, ``agent_idx + 1``, the handoff written as the new agent's
    first user message, ``on_compact`` fired once the row is durable. The old
    agent and its messages are never touched. Nothing is ever deleted.

    Args:
        session: The generation to compact.
        llm: Client for this session's provider.
        config: Resolved config.
        on_compact: ``f(old_agent_id, new_session)`` — how the agent registers
            the new generation so later prompts resolve to it. Harness
            bookkeeping: fired here, never the strategy's problem.
        logger: Logger instance.
        compactor: The strategy. Defaults to :func:`default_compactor`.
        system_prompt: How the next generation's system prompt is built; handed
            to the compactor as ``ctx.system_prompt``. Defaults to
            :func:`compact_system_prompt`.

    Returns:
        The new session, holding ``[system, user(handoff)]``.
    """
    if logger:
        logger.info(
            f"Compacting agent {session.agent_id} ({len(session.messages)} messages)..."
        )

    ctx = CompactCtx(
        session=session,
        llm_client=llm,
        config=config,
        system_prompt=system_prompt or compact_system_prompt,
        logger=logger,
    )
    result = await (compactor or default_compactor)(ctx)

    # Same session_id AND fork, next agent_idx.
    new_agent_idx = session.agent_idx + 1
    new_agent_id = build_agent_id(session.session_id, new_agent_idx, session.fork_idx)
    new_session = await make_agent_session(
        config,
        session.tools,
        session.model_identifier if session.model_identifier else "",
        session.cwd,
        session_id=session.session_id,
        agent_idx=new_agent_idx,
        fork_idx=session.fork_idx,
        template=result.system_template,
        template_args=result.system_args,
    )
    await new_session.add_message({"role": "user", "content": result.prompt})

    if logger:
        logger.info(
            f"Compacted: agent {session.agent_id} -> {new_agent_id}, "
            f"{len(session.messages)} messages -> {len(new_session.messages)}"
        )

    if on_compact:
        on_compact(session.agent_id, new_session)

    return new_session


def unroll_content(content: str | list | None) -> str:
    """Flatten one message's content to text.

    ``None`` is not a defensive default here — it is the standard OpenAI shape
    for an assistant turn that did nothing but call tools, and ``add_message``
    persists whatever dict it is handed without normalizing it. Returning it
    unchanged made ``last_messages`` die on ``len(None)`` and took the whole
    compaction down with it.
    """
    if content is None:
        return ""
    if isinstance(content, list):
        new_content = [
            x.get("text", "")
            for x in content
            if isinstance(x, dict) and x.get("type") == "text"
        ]
        return " ".join(new_content)
    else:
        return content

def last_messages(session: AgentSession, n_messages: int = 20, max_chars: int = 300):
    if len(session.messages) > n_messages:
        last_msgs = session.messages[-n_messages:]
    else:
        last_msgs = session.messages
    last_msgs_list = []
    for msg in last_msgs:
        role = msg["role"]
        if role == "user":
            last_msgs_list.append("USER:")
            content = unroll_content(msg.get("content", ""))
            last_msgs_list.append(content)
        if role == "tool":
            last_msgs_list.append("TOOL RESULT:")
            content = unroll_content(msg.get("content", ""))
            new_content = content[:max_chars] if len(content) > max_chars else content
            last_msgs_list.append(new_content)
        if role == "assistant":
            last_msgs_list.append("ASSISTANT:")
            content = unroll_content(msg.get("content", ""))
            new_content = content[:max_chars] if len(content) > max_chars else content
            last_msgs_list.append(new_content)
            tool_calls = msg.get("tool_calls", [])
            for tool_call in tool_calls:
                tool_args = tool_call.get("function", {})
                name = tool_args.get("name", "")
                arguments = tool_args.get("arguments", "")
                last_msgs_list.append(f"TOOL — {name}:")
                new_args = (
                    arguments[:max_chars] if len(arguments) > max_chars else arguments
                )
                last_msgs_list.append(new_args)
    return "\n".join(last_msgs_list)
