"""
file:           compact.py
description:    compact the middle over the conversation
"""

from openai import AsyncOpenAI

from crow_cli.agent.prompt import render_template
from crow_cli.agent.session import Session

MAX_OUTPUT_TOKENS = 8192


COMPACTION_PROMPT = """Please summarize everything in the conversation that happened AFTER the user's first message and before the current react turn began.
FIRST USER MESSAGE:
{{ first_message }}

[what we want you to summarize in one very long block of beautiful markdown that illustrates the conversation in the context of the task you and the user are trying to accomplish in such a way that it splines/interpolates/segues naturally upon compacting]

LAST USER MESSAGE:
{{ last_message }}
"""


def get_last_user_idx(messages: list[dict[str, str]]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            return i
    return -1


async def non_streaming_request(
    model: str,
    messages: list[dict],
    tools: list[dict],
    request_params: dict,
    llm: AsyncOpenAI,
) -> dict:
    response = await llm.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="none",
        **request_params,
    )
    usage = response.usage
    return dict(content=response.choices[0].message.content, usage=usage)


def construct_compact_prompt(messages: list[dict]) -> tuple[list[dict], int]:
    first_message = messages[1]
    last_usr_msg_idx = get_last_user_idx(messages)
    last_message = messages[last_usr_msg_idx]
    prompt = render_template(
        COMPACTION_PROMPT,
        first_message=first_message,
        last_message=last_message,
    )
    return (
        messages + [dict(role="user", content=prompt)],
        last_usr_msg_idx,
    )


async def get_middle_message(
    session: Session,
    llm: AsyncOpenAI,
) -> tuple[str, dict, int]:
    messages = session.messages
    model: str = session.model_identifier
    messages: list[dict] = session.messages
    tools: list[dict] = session.tools
    request_params: dict = session.request_params
    # Always step on the request param's max_completion_tokens
    # HAVING TO RENAME BECAUSE THERE IS NO STANDARD AND PROXY
    # IS STEPPING ON THE MAX_COMPLETION_TOKENS INPUT REQUESTS
    request_params["max_tokens"] = MAX_OUTPUT_TOKENS
    compact_prompt, last_usr_msg_idx = construct_compact_prompt(messages)
    middle_message, usage = await non_streaming_request(
        model=model,
        messages=compact_prompt,
        tools=tools,
        request_params=request_params,
        llm=llm,
    )
    return middle_message, usage, last_usr_msg_idx


async def compact(
    session: Session,
    llm: AsyncOpenAI,
    cwd: str,
    on_compact: callable = None,
    logger: Logger = None,
) -> Session:
    """
    Compact the conversation in-place.

    This updates the session object's state directly without creating a new
    session object, ensuring all references to the session see the updated state.

    Steps:
    1. Get the middle message (summary of conversation)
    2. Replace the middle of messages with the compacted message
    3. Create a new session in the database
    4. Swap session IDs in the database (old -> archive, new -> old_id)
    5. Update the session object in-place with the new state
    6. Call on_compact callback if provided (needed for async task contexts)

    Args:
        session: The session to compact
        llm: The LLM client for summarization
        cwd: Current working directory
        on_compact: Callback function(session_id, compacted_session) called after compaction

    Returns:
        The compacted session (same object, updated in-place)
    """
    # Summarize the conversation's middle
    logger.info("Compacting conversation...")
    middle_message, usage, last_usr_msg_idx = await get_middle_message(session, llm)
    logger.info(f"Compact usage: {usage}")

    logger.info("Summary generated, shuffling data")
    orig_messages = session.messages
    compacted_messages = (
        [orig_messages[1]]  # First user message (skipping system at 0)
        + [dict(role="assistant", content=middle_message)]
        + orig_messages[last_usr_msg_idx:]  # last user message is included
    )

    # Create a new session in the database with compacted messages
    new_session = Session.create(
        prompt_id=session.prompt_id,
        prompt_args=session.prompt_args,
        tool_definitions=session.tools,
        request_params=session.request_params,
        model_identifier=session.model_identifier,
        db_uri=session.db_uri,
        cwd=cwd,
        initial_messages=compacted_messages,
    )
    logger.info("Swapping out old session and new session ids for continuity")

    # Store the original session_id before swap
    original_session_id = session.session_id

    # Atomically swap out the old session with the new in the database
    Session.swap_session_id(
        old_session_id=original_session_id,
        new_session_id=new_session.session_id,
        db_uri=session.db_uri,
    )
    logger.info(f"Session previously with id {original_session_id} archived")
    logger.info(f"New Session now has id {original_session_id}")

    # Update the new session's ID to match the original (post-swap)
    new_session.session_id = original_session_id

    # NOW THE KEY PART: Update the original session object in-place
    # This ensures all references (local variables in other functions) see the new state
    session.update_from(new_session)
    logger.info("Session updated in-place - all references now see compacted state")

    # Callback for async task contexts where reference passing doesn't work
    if on_compact:
        on_compact(session.session_id, session)

    return session
