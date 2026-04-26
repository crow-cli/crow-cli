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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SQLAlchemySession

from crow_cli.agent.db import Agent as AgentModel
from crow_cli.agent.db import Message as MessageModel
from crow_cli.agent.session import Session

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


def _collect_tool_call_ids(messages: list[dict]) -> set[str]:
    """Extract all tool_call_ids from assistant messages."""
    ids = set()
    for msg in messages:
        if msg.get("role") == "assistant" and "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                tool_call_id = (
                    tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                )
                if tool_call_id:
                    ids.add(tool_call_id)
    return ids


def _collect_tool_response_ids(messages: list[dict]) -> set[str]:
    """Extract all tool_call_ids from tool response messages."""
    ids = set()
    for msg in messages:
        if msg.get("role") == "tool":
            tcid = msg.get("tool_call_id")
            if tcid:
                ids.add(tcid)
    return ids


def _fill_missing_tool_responses(messages: list[dict]) -> list[dict]:
    """
    For every tool_call_id in assistant messages that has no matching
    tool response, append a fake tool response.
    """
    call_ids = _collect_tool_call_ids(messages)
    response_ids = _collect_tool_response_ids(messages)
    missing = call_ids - response_ids

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


def _clean_messages(messages: list[dict]) -> list[dict]:
    """Normalize messages for LLM input - handle multimodal content blocks."""
    cleaned = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, list):
            # Normalize multimodal content blocks
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                else:
                    parts.append(str(block))
            content = "\n".join(parts)
        cleaned.append(
            {
                "role": role,
                "content": content,
                **({k: v for k, v in msg.items() if k not in ("role", "content")}),
            }
        )
    return cleaned


async def compact(
    session: Session,
    llm: AsyncOpenAI,
    cwd: str,
    on_compact: callable = None,
    logger: Logger = None,
) -> Session:
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

    # 1. Fill missing tool responses so LLM sees consistent state
    messages = _fill_missing_tool_responses(session.messages)
    messages = _clean_messages(messages)

    # 2. Append compaction prompt
    messages.append({"role": "user", "content": COMPACTION_PROMPT})

    # 3. Send to LLM
    request_params = dict(session.request_params)
    request_params["max_tokens"] = MAX_OUTPUT_TOKENS

    response = await llm.chat.completions.create(
        model=session.model_identifier,
        messages=messages,
        tools=session.tools if session.tools else None,
        tool_choice="none",
        **request_params,
    )
    summary = response.choices[0].message.content
    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
        "completion_tokens": getattr(response.usage, "completion_tokens", None),
        "total_tokens": getattr(response.usage, "total_tokens", None),
    }
    if logger:
        logger.info(f"Compact usage: {usage}")

    # 4. Create new agent record: same session_id, next agent_idx
    new_agent_idx = original_agent_idx + 1
    new_agent_id = f"{original_session_id}-{new_agent_idx}"

    system_msg = session.messages[0]
    compacted_messages = [
        system_msg,
        {"role": "user", "content": summary},
    ]

    engine = create_engine(session.db_uri)
    with SQLAlchemySession(engine) as db:
        new_agent = AgentModel(
            agent_id=new_agent_id,
            session_id=original_session_id,
            agent_idx=new_agent_idx,
            prompt_id=session.prompt_id,
            prompt_args=session.prompt_args,
            system_prompt=system_msg.get("content", ""),
            tool_definitions=session.tools,
            request_params=session.request_params,
            model_identifier=session.model_identifier,
        )
        db.add(new_agent)

        for msg in compacted_messages:
            db_msg = MessageModel(
                agent_id=new_agent_id,
                data=msg,
                role=msg.get("role", "unknown"),
            )
            db.add(db_msg)

        db.commit()

    # 5. Create fresh Session object (avoids stale _db/_model from old agent)
    new_session = Session(
        agent_id=new_agent_id,
        session_id=original_session_id,
        agent_idx=new_agent_idx,
        db_uri=session.db_uri,
        cwd=session.cwd,
    )
    new_session.model_identifier = session.model_identifier
    new_session.tools = session.tools
    new_session.request_params = session.request_params
    new_session.prompt_id = session.prompt_id
    new_session.prompt_args = session.prompt_args
    new_session.messages = compacted_messages

    if logger:
        logger.info(
            f"Compacted: agent {session.agent_id} -> {new_agent_id}, "
            f"{len(session.messages)} messages -> {len(compacted_messages)}"
        )

    # Callback for async task contexts
    if on_compact:
        on_compact(session.agent_id, new_session)

    return new_session
