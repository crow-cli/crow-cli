"""EXPERIMENT (taskmaster PLAN 3.1): a synthetic prompt round OUTSIDE any
client session/prompt.

The bg-only task system needs an emission with NO outstanding client
request: when a completion lands in the mailbox of a QUIESCENT session,
the delivery watcher wakes the agent via `_run_internal_round` — it
emits user_message_chunk + its own reaction exactly like a client-
prompted turn, and the round persists in sqlite. (The in-loop consults
cover the ACTIVE case; this covers the idle case.)

This experiment drives a real AcpAgent in process with a recording conn
(the production shape — _conn is exactly what session/update goes
through) and proves the round works end to end: wire updates in the
right order, model reacts, history persisted.
"""

import logging
from typing import Any

import pytest

from crow_cli.agent.main import AcpAgent
from crow_cli.config import Config
from crow_cli.memory import get_engine, list_agents, load_agent_messages

logger = logging.getLogger(__name__)

MODEL = "qwen3.8-max-preview"
COMPLETION = (
    "[task-1: subagent shy-fox-of-glass finished]\n"
    "The date is Sat Aug 23 01:00:00 UTC 2026."
)


class RecordingConn:
    """Records every session_update the agent emits — the client's view."""

    def __init__(self):
        self.updates: list[Any] = []

    async def session_update(self, session_id: str, update: Any) -> None:
        self.updates.append(update)


def _provider_available() -> bool:
    try:
        config = Config.load()
        model = config.llm.models.get(MODEL)
        if model is None:
            return False
        return config.llm.providers.get(model.provider_name) is not None
    except Exception:
        return False


@pytest.mark.asyncio
async def test_synthetic_round_without_a_client_prompt(tmp_path):
    if not _provider_available():
        pytest.skip(f"{MODEL} / its provider is not configured")

    config = Config.load()
    config.db_uri = f"sqlite:///{tmp_path / 'wake.db'}"
    config.system_prompt_path = None
    config.system_prompt = (
        "You are a worker. When you receive a bracketed task-completion "
        "notice, acknowledge it in one short sentence. No tools needed."
    )

    agent = AcpAgent(config=config, model=MODEL)
    conn = RecordingConn()
    agent._conn = conn  # no client request will ever come through

    ns = await agent.new_session(cwd=str(tmp_path), mcp_servers=[])
    session_id = ns.session_id

    # THE EXPERIMENT: no session/prompt in flight — the agent wakes itself.
    await agent._run_internal_round(session_id, COMPLETION)

    # --- wire: synthetic user message first, then the agent's reaction
    kinds = [getattr(u, "session_update", None) for u in conn.updates]
    assert "user_message_chunk" in kinds, f"no synthetic user message: {kinds}"
    first_user = next(
        u for u in conn.updates if getattr(u, "session_update", None) == "user_message_chunk"
    )
    assert "shy-fox-of-glass" in first_user.content.text
    # The synthetic user message must LEAD the agent's reaction (setup
    # noise like available_commands_update may precede both).
    first_agent = next(
        i
        for i, k in enumerate(kinds)
        if k in ("agent_message_chunk", "agent_thought_chunk")
    )
    assert kinds.index("user_message_chunk") < first_agent, (
        "user message must lead the round"
    )
    assert "agent_message_chunk" in kinds, f"agent never reacted: {kinds}"

    reaction = "".join(
        u.content.text
        for u in conn.updates
        if getattr(u, "session_update", None) == "agent_message_chunk"
        and getattr(u, "content", None) is not None
    )
    assert reaction.strip(), "agent reaction is empty"

    # --- state: the round persisted in sqlite (memory is the authority)
    engine = get_engine(config.db_uri)
    agents = list_agents(engine, session_id)
    assert agents, "no agent row for the session"
    messages = load_agent_messages(engine, agents[-1])
    roles = [m.get("role") for m in messages]
    assert "user" in roles and "assistant" in roles
    user_texts = [
        m.get("content") for m in messages if m.get("role") == "user"
    ]
    assert any(
        "shy-fox-of-glass" in str(t) for t in user_texts
    ), f"synthetic message not in history: {user_texts}"
