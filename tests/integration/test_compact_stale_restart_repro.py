"""Faithful reproduction of the stale-generation compaction collision.

Real sqlite scratch store (never crow.db), real compact(), and the real
SessionManager.resolve() reload path. After a restart the client still names
the original full agent_id (...-1-1); resolve rehydrates that STALE generation
while newer ones already exist in the store. Buggy compact() computes
session.agent_idx + 1 == 2, which exists -> sqlite3.IntegrityError on
agents.agent_id (the OOM-restart crash). Fixed compact() advances past the DB
head. Run against the buggy line to see the real IntegrityError; against the
fix it yields generation 5.
"""

from unittest.mock import MagicMock

import pytest

import crow_cli.memory as db
from crow_cli.agent.compact import CompactResponse, compact
from crow_cli.agent.session import AgentSession, lookup_or_create_prompt
from crow_cli.agent2.sessions import SessionRegistry
from crow_cli.config import Config
from crow_cli.memory import build_agent_id


@pytest.mark.asyncio
async def test_stale_restart_compaction_collision(tmp_path):
    db_uri = f"sqlite:///{tmp_path / 'crow.db'}"
    db.create_database(db_uri)
    config = Config.load()
    config.db_uri = db_uri
    config.config_dir = tmp_path / "crow"
    config.system_prompt = "You are {{name}}. Workspace: {{workspace}}."

    async def no_llm(ctx):
        return CompactResponse(
            system_template="Successor.", system_args={}, prompt="carry on"
        )

    prompt_id = await lookup_or_create_prompt(
        config.system_prompt, name="repro", memory_path=db_uri
    )
    project = tmp_path / "project"
    project.mkdir()
    session = await AgentSession.create(
        prompt_id=prompt_id,
        prompt_args={"name": "Crow", "workspace": str(project), "display_tree": "p/"},
        tool_definitions=[],
        request_params={},
        model_identifier="m",
        memory_path=db_uri,
        cwd=str(project),
        agent_idx=1,
        session_id="repro-session",
    )
    for i in range(5):
        await session.add_message({"role": "user", "content": f"msg {i}"})

    # Three compactions -> generations 2, 3, 4 in the real store.
    gen = session
    for _ in range(3):
        gen = await compact(gen, MagicMock(), config, logger=MagicMock(), compactor=no_llm)
    assert gen.agent_idx == 4

    # RESTART: a fresh registry (empty cache) resolves the stale full agent_id
    # the client still names -- exactly sessions.resolve on a cache miss.
    fresh = SessionRegistry(config)
    stale = await fresh.resolve(build_agent_id("repro-session", 1, 1))
    assert stale.agent_idx == 1

    # Buggy: new idx 2 (exists) -> sqlite3.IntegrityError. Fixed: head(4)+1 == 5.
    result = await compact(stale, MagicMock(), config, logger=MagicMock(), compactor=no_llm)
    assert result.agent_idx == 5
    assert result.agent_id == build_agent_id("repro-session", 5, 1)
