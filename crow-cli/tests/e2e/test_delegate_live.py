"""Live delegate wire-contract test (end-to-end, real provider, real sqlite).

Runs the REAL launch_delegate path with a REAL subagent LLM and records every
session_update emitted on the wire. Asserts the Bug-1 contract: every delegate
tool_call_id gets a tool_call CREATION event before any tool_call_update, so a
client can never render "tool call not found" for an id it never saw born.

Opt-in e2e tier: live calls cost money and take time. Uses the alibaba
provider's qwen3.8-max-preview (the default llamacpp host may be down).
"""

import asyncio
import logging

import pytest

from crow_cli.config import Config
from crow_cli.agent.delegate import launch_delegate
from crow_cli.agent.session import AgentSession, lookup_or_create_prompt
from crow_cli.agent.tasks import TaskRegistry

logger = logging.getLogger(__name__)

E2E_MODEL = "qwen3.8-max-preview"


class RecordingConn:
    def __init__(self):
        self.events = []

    async def session_update(self, session_id, update):
        self.events.append(update)


def _provider_available() -> bool:
    try:
        config = Config.load()
        model = config.llm.models.get(E2E_MODEL)
        if model is None:
            return False
        return config.llm.providers.get(model.provider_name) is not None
    except Exception:
        return False


@pytest.mark.asyncio
async def test_delegate_emits_creation_before_updates(tmp_path):
    if not _provider_available():
        pytest.skip(f"{E2E_MODEL} / its provider is not configured")

    config = Config.load()
    config.db_uri = f"sqlite:///{tmp_path / 'e2e.db'}"
    config.system_prompt_path = None
    config.system_prompt = "You are a worker. Answer briefly."

    prompt_id = await lookup_or_create_prompt(
        "Parent prompt.", name="parent", memory_path=config.db_uri
    )
    parent = await AgentSession.create(
        prompt_id=prompt_id,
        prompt_args={},
        tool_definitions=[],
        request_params={},
        model_identifier=E2E_MODEL,
        memory_path=config.db_uri,
        cwd=str(tmp_path),
        session_id="parent-sess",
    )

    registry = TaskRegistry()
    conn = RecordingConn()
    result = await launch_delegate(
        conn=conn,
        parent_session=parent,
        turn_id="turn-e2e",
        tool_call_id="call-1",
        acp_tool_call_id="turn-e2e/call-1",
        args={"prompt": "Reply with exactly: SUBAGENT-DONE", "model": E2E_MODEL},
        config=config,
        mcp_servers=None,
        registry=registry,
        logger=logger,
    )
    assert result.startswith("Launched task-1:")

    (info,) = registry.pending("parent-sess")
    await asyncio.wait_for(info.handle, timeout=120)

    # The subagent really ran and its answer landed on the wake queue.
    done = registry.get(info.task_id)
    assert done.status == "done"
    assert "SUBAGENT-DONE" in (done.result or "")

    # Wire contract: for every tool_call_id the FIRST event is a tool_call
    # creation and everything after is tool_call_update.
    tool_call_ids = []
    for u in conn.events:
        tcid = getattr(u, "tool_call_id", None)
        if tcid and tcid not in tool_call_ids:
            tool_call_ids.append(tcid)
    assert set(tool_call_ids) == {"turn-e2e/call-1", "turn-e2e/task-1"}
    for tcid in tool_call_ids:
        evs = [u for u in conn.events if getattr(u, "tool_call_id", None) == tcid]
        assert getattr(evs[0], "session_update", None) == "tool_call", (
            f"{tcid}: first event must be a tool_call creation, got "
            f"{getattr(evs[0], 'session_update', None)!r}"
        )
        assert all(
            getattr(u, "session_update", None) == "tool_call_update" for u in evs[1:]
        ), f"{tcid}: events after creation must be tool_call_update"

    await parent.close()
