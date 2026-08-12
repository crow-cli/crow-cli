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
"""

from logging import Logger

from openai import AsyncOpenAI

from crow_cli.agent.configure import Config, sampling_params_for
from crow_cli.agent.session import (
    AgentSession,
    make_agent_session,
)

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


async def compact(
    session: AgentSession,
    llm: AsyncOpenAI,
    config: Config,
    on_compact: callable = None,
    logger: Logger = None,
) -> AgentSession:
    """
    Compact the conversation by summarizing it into a single message.

    Creates a new agent record. Old agent and messages are preserved.

    Args:
        session: The session to compact
        llm: The LLM client for summarization
        cwd: Current working directory
        on_compact: Callback function(old_agent_id, compacted_session)
        logger: Logger instance

    Returns:
        The new session object with compacted history
    """
    original_session_id = session.session_id
    original_agent_idx = session.agent_idx

    if logger:
        logger.info(
            f"Compacting agent {session.agent_id} ({len(session.messages)} messages)..."
        )

    # 1. Fill missing tool responses on the last assistant message only
    messages = _fill_missing_tool_responses(session.messages)

    # 2. Guard against user+user: if last message is user, insert lightweight
    #    assistant placeholder so the compaction prompt doesn't break API rules
    if messages[-1].get("role") == "user":
        messages.append(
            {
                "role": "assistant",
                "content": "Ready to compact. Calling no tools.",
            }
        )

    # 3. Append compaction prompt
    messages.append({"role": "user", "content": COMPACTION_PROMPT})

    # 4. Send to LLM — same per-model sampling rule as the react loop: the
    # model's reasoning_effort XOR temperature. Never the provider default
    # (temp 1.0 makes the model ramble instead of compress) and never the
    # session's request_params temperature.
    response = await llm.chat.completions.create(
        model=session.model_identifier,
        messages=messages,
        tools=session.tools if session.tools else None,
        tool_choice="none",
        max_tokens=MAX_OUTPUT_TOKENS,
        **sampling_params_for(config, session.model_identifier),
    )
    summary = response.choices[0].message.content
    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
        "completion_tokens": getattr(response.usage, "completion_tokens", None),
        "total_tokens": getattr(response.usage, "total_tokens", None),
    }
    if logger:
        logger.info(f"Compact usage: {usage}")

    # 5. Create new agent record: same session_id, next agent_idx
    new_agent_idx = original_agent_idx + 1
    new_agent_id = f"{original_session_id}-{new_agent_idx}"
    new_session = await make_agent_session(
        config,
        session.tools,
        session.model_identifier if session.model_identifier else "",
        session.cwd,
        session_id=original_session_id,
        agent_idx=new_agent_idx,
    )

    last_msgs = last_messages(session)
    new_agent_prompt = f"{summary}\n\nLast messages:\n\n{last_msgs}"
    await new_session.add_message(
        {"role": "user", "content": new_agent_prompt},
    )

    if logger:
        logger.info(
            f"Compacted: agent {session.agent_id} -> {new_agent_id}, "
            f"{len(session.messages)} messages -> {len(new_session.messages)}"
        )

    # Callback for async task contexts
    if on_compact:
        on_compact(session.agent_id, new_session)

    return new_session


def unroll_content(content: str | list):
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
