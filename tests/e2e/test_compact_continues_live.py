"""E2E regression: compaction mid-turn must CONTINUE the react loop.

The stock crow agent — no project callables, crow's own system prompt and
crow's own compactor — spawned as a real ACP subprocess over a real provider,
in a near-empty cwd, with a compaction ceiling low enough that one web search
crosses it.

The claim under test is the one that broke: crossing the threshold mid-turn
summarizes the history into a new generation AND KEEPS GOING. The successor
answers the user's original question in the same turn. A compaction that
mints the row and then stalls leaves the client waiting on a
``session/prompt`` that never returns, which is indistinguishable from a hang
— and the database still looks perfectly healthy, because the summary landed.

So the assertions are about what happens AFTER the handoff, not about the
handoff: the prompt response comes back, the successor generation carries an
assistant message, and the client saw agent text on the far side of the
compaction notice.

Live: needs a configured provider; skips otherwise.
"""

import asyncio
from pathlib import Path

import pytest
from acp import PROTOCOL_VERSION, connect_to_agent, text_block
from acp.schema import ClientCapabilities, Implementation

from crow_cli.agent.mcp_client import fastmcp_config_to_acp_servers
from crow_cli.client.subagent import HeadlessClient
from crow_cli.config import Config
from crow_cli.memory import get_engine, list_agents, load_agent_messages

pytestmark = pytest.mark.asyncio

REPO = Path(__file__).resolve().parents[2]
AGENT_SCRIPT = Path(__file__).resolve().parent / "custom_compactor_agent.py"

MODEL = "qwen3.8-max"
# Must sit ABOVE the irreducible floor with room to spare. Measured live:
# crow's system prompt is ~6.5k tokens and COMPACTION_PROMPT asks for a
# thorough summary, which qwen3.8-max writes at 7-11k — so a successor is born
# at ~14-18k. A ceiling below that re-compacts on every tool round (progress,
# thanks to the guard in react.py, but it never finishes); a ceiling the deep
# dive never reaches does not test anything. 30k is crossed mid-dive — gen1
# measured 25k tokens over 26 messages — and leaves the successor ~12k to
# finish in.
THRESHOLD = 30_000
BLANK = Path("/tmp/blank")
HANDSHAKE_TIMEOUT = 240
TURN_TIMEOUT = 1200


def _live_config_or_skip() -> Config:
    config = Config.load()
    if not config.is_configured:
        pytest.skip("No LLM provider configured")
    if MODEL not in config.llm.models:
        pytest.skip(f"{MODEL} not in config.yaml")
    if not config.mcp_servers:
        pytest.skip("No mcpServers configured — the agent would come up toolless")
    return config


def _agent_text(updates) -> str:
    out = []
    for u in updates:
        if getattr(u, "session_update", None) != "agent_message_chunk":
            continue
        content = getattr(u, "content", None)
        if getattr(content, "type", None) == "text":
            out.append(content.text)
    return "".join(out)


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content or [] if isinstance(b, dict))


async def test_compaction_mid_turn_continues_the_react_loop(tmp_path):
    config = _live_config_or_skip()
    BLANK.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "continues.db"

    proc = await asyncio.create_subprocess_exec(
        "uv", "--project", str(REPO), "run", "python", str(AGENT_SCRIPT),
        "--db", str(db_path),
        "--model", MODEL,
        "--compact-threshold", str(THRESHOLD),
        "--stock",
        "--debug",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(BLANK),
        limit=10 * 1024 * 1024,
    )
    stderr_chunks: list[bytes] = []

    async def _drain() -> None:
        assert proc.stderr is not None
        async for line in proc.stderr:
            stderr_chunks.append(line)

    draining = asyncio.create_task(_drain())
    client = HeadlessClient()

    try:
        conn = connect_to_agent(client, proc.stdin, proc.stdout, use_unstable_protocol=True)
        await asyncio.wait_for(
            conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(terminal=False),
                client_info=Implementation(
                    name="compact-continues-e2e",
                    title="Compact Continues E2E",
                    version="0.1.0",
                ),
            ),
            timeout=HANDSHAKE_TIMEOUT,
        )
        session_id = (
            await conn.new_session(
                cwd=str(BLANK),
                mcp_servers=fastmcp_config_to_acp_servers(config.mcp_servers),
            )
        ).session_id

        response = await asyncio.wait_for(
            conn.prompt(
                session_id=session_id,
                prompt=[text_block(
                    "Do a deep dive on the Agent Client Protocol. Fetch "
                    "https://agentclientprotocol.com/llms.txt, then fetch five "
                    "of the documentation pages it lists. Also search the web "
                    "for crow-cli. Finish with one sentence on what crow-cli is."
                )],
            ),
            timeout=TURN_TIMEOUT,
        )
        updates = list(client.updates)
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        draining.cancel()

    agent_stderr = b"".join(stderr_chunks).decode(errors="replace")
    said = _agent_text(updates)

    # The turn came back. This is the assertion that fails on the hang: the
    # client waits on session/prompt forever and wait_for raises instead.
    assert response.stop_reason == "end_turn", (
        f"stop_reason={response.stop_reason}\nagent said:\n{said[-2000:]}\n"
        f"agent stderr:\n{agent_stderr[-4000:]}"
    )

    engine = get_engine(f"sqlite:///{db_path}")
    generations = list_agents(engine, session_id)
    assert len(generations) >= 2, (
        f"compaction never fired at {THRESHOLD} tokens; "
        f"{[g.agent_id for g in generations]}\nagent said:\n{said[-2000:]}"
    )
    assert f"Compaction threshold of {THRESHOLD} reached" in said, said[-2000:]

    # ...and the loop KEPT GOING: the successor answered in the same turn.
    successor = generations[-1]
    messages = load_agent_messages(engine, successor)
    roles = [m["role"] for m in messages]
    assert "assistant" in roles, (
        f"{successor.agent_id} holds {roles} — compaction minted the generation "
        f"and the react loop never resumed it.\nagent said:\n{said[-2000:]}\n"
        f"agent stderr:\n{agent_stderr[-4000:]}"
    )

    # The answer reached the client on the far side of the compaction notice.
    notice = f"Compaction threshold of {THRESHOLD} reached"
    after = said.split(notice, 1)[1]
    assert len(after.strip()) > 20, f"nothing was streamed after compaction: {said[-1000:]}"
