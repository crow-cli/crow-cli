"""E2E: a project's OWN ACP agent, with its OWN compaction, driven over the wire.

Two scripts, because that is what building on top of crow-cli actually looks
like:

* ``custom_compactor_agent.py`` — the AGENT. A standalone file that loads the
  standard config dir, replaces the system prompt and the compaction strategy
  with its own callables, and serves ACP over stdio.
* this file — the CLIENT. Spawns that script the way a client spawns any ACP
  agent (``uv --project <repo> run python <script>``, JSON-RPC over stdin/
  stdout), handshakes, opens a session with the real MCP tool supply, and
  drives two turns. The only thing it tells the child is where to put its
  database, so this process can read the transcript back.

The first turn does real work — reads two files, fetches a URL — against a
5000-token compaction ceiling, so the react loop crosses it and compacts with
the project's strategy mid-turn. The second turn is ``/compact``, the
user-initiated path through the same callable.

Nothing is mocked: real provider, real MCP servers, real subprocess, real
sqlite. The assertion surface is the database the agent wrote, read back from
here — every generation's system prompt, its prompt args, and the handoff
message that opened it.
"""

import asyncio
import importlib.util
from pathlib import Path

import pytest
from acp import PROTOCOL_VERSION, connect_to_agent, text_block
from acp.schema import ClientCapabilities, Implementation

from crow_cli.agent.mcp_client import fastmcp_config_to_acp_servers
from crow_cli.client.subagent import HeadlessClient
from crow_cli.config import Config
from crow_cli.memory import get_engine, get_prompt, list_agents, load_agent_messages

pytestmark = pytest.mark.asyncio

REPO = Path(__file__).resolve().parents[2]
AGENT_SCRIPT = Path(__file__).resolve().parent / "custom_compactor_agent.py"

MODEL = "qwen3.8-max"
THRESHOLD = 5000
URL = "https://agentclientprotocol.com/llms.txt"
HANDSHAKE_TIMEOUT = 240
TURN_TIMEOUT = 600
COMPACT_TIMEOUT = 300


def _agent_module():
    """The agent script, imported for its constants — the test asserts against
    the strings the agent really renders, not a copy of them."""
    spec = importlib.util.spec_from_file_location("custom_compactor_agent", AGENT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    return "".join(
        b.get("text", "") for b in content or [] if isinstance(b, dict)
    )


async def test_project_agent_compacts_with_its_own_callable(tmp_path):
    config = _live_config_or_skip()
    agent_mod = _agent_module()

    # The child loads the standard config dir itself; all this does is hand it
    # a database to write to, so the run never touches the live crow.db and
    # this process can read the transcript back.
    db_path = tmp_path / "custom-compactor.db"

    readme = REPO / "README.md"
    pyproject = REPO / "pyproject.toml"
    # The standard config supplies exactly ONE tool — `execute` — so the work
    # is one cell. Code given verbatim keeps the turn's shape, and therefore
    # its token load and where compaction lands, deterministic run to run.
    code = (
        f"readme = await fs('read', {str(readme)!r})\n"
        f"pyproject = await fs('read', {str(pyproject)!r})\n"
        f"spec = await web('fetch', {URL!r})\n"
        "print(readme.text)\n"
        "print(pyproject.text)\n"
        "print(spec.text[:8000])\n"
    )
    work_prompt = (
        "Call the `execute` tool EXACTLY ONCE, with this code verbatim:\n\n"
        f"{code}\n"
        "Do not call any other tool. Then reply with the single word DONE."
    )

    # THE SPAWN. A client boots its agent as a subprocess and speaks JSON-RPC
    # over its stdio — `uv --project` so the child runs THIS tree's crow_cli.
    proc = await asyncio.create_subprocess_exec(
        "uv", "--project", str(REPO), "run", "python", str(AGENT_SCRIPT),
        "--db", str(db_path),
        "--model", MODEL,
        "--compact-threshold", str(THRESHOLD),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(tmp_path),
        limit=10 * 1024 * 1024,
    )
    # An undrained stderr pipe fills and deadlocks the child mid-turn.
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
                    name="custom-compactor-e2e",
                    title="Custom Compactor E2E",
                    version="0.1.0",
                ),
            ),
            timeout=HANDSHAKE_TIMEOUT,
        )

        # The client owns the tool supply: config's real mcpServers, so the
        # child gets execute/fs/web from this tree's crow-mcp.
        session_id = (
            await conn.new_session(
                cwd=str(tmp_path),
                mcp_servers=fastmcp_config_to_acp_servers(config.mcp_servers),
            )
        ).session_id

        # Turn 1: real work, real tokens, over a 5000-token ceiling.
        first = await asyncio.wait_for(
            conn.prompt(session_id=session_id, prompt=[text_block(work_prompt)]),
            timeout=TURN_TIMEOUT,
        )
        assert first.stop_reason == "end_turn", first.stop_reason
        turn_one_text = _agent_text(client.updates)
        assert f"Compaction threshold of {THRESHOLD} reached" in turn_one_text, (
            "the react loop never compacted; agent said:\n" + turn_one_text[-2000:]
        )

        # Turn 2: the user-initiated path through the same callable.
        mark = len(client.updates)
        second = await asyncio.wait_for(
            conn.prompt(session_id=session_id, prompt=[text_block("/compact")]),
            timeout=COMPACT_TIMEOUT,
        )
        assert second.stop_reason == "end_turn", second.stop_reason
        slash_text = _agent_text(client.updates[mark:])
        assert slash_text.startswith("Conversation compacted:"), slash_text
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        draining.cancel()

    agent_stderr = b"".join(stderr_chunks).decode(errors="replace")

    # ------------------------------------------------------------------
    # The database the agent wrote is the proof.
    # ------------------------------------------------------------------
    engine = get_engine(f"sqlite:///{db_path}")
    generations = list_agents(engine, session_id)
    assert len(generations) >= 3, (
        f"expected the react-threshold compaction AND /compact to each mint a "
        f"generation, got {[g.agent_id for g in generations]}\n"
        f"agent stderr:\n{agent_stderr[-4000:]}"
    )
    assert [g.agent_idx for g in generations] == list(range(1, len(generations) + 1))

    # One template, content-addressed into ONE prompts row, for every
    # generation: the static/dynamic split is what makes that true.
    prompt_ids = {g.prompt_id for g in generations}
    assert len(prompt_ids) == 1, prompt_ids
    stored = get_prompt(engine, generations[0].prompt_id)
    assert stored.template == agent_mod.TEMPLATE

    for gen in generations:
        # OUR prompt, not crow's default — and re-rendered per generation from
        # template_args, which is the coupled half of the contract.
        assert gen.system_prompt.startswith("You are DUMMY-AGENT"), gen.system_prompt[:200]
        assert f"generation: {gen.agent_idx}" in gen.system_prompt
        assert gen.prompt_args["generation"] == gen.agent_idx
        # Load-bearing key: the session list is filtered on it.
        assert gen.prompt_args["workspace"] == str(tmp_path)

    # The work really happened: the cell ran, and what it printed — the two
    # files and the fetched page — is in the session's history.
    first_messages = load_agent_messages(engine, generations[0])
    first_size = sum(len(_message_text(m)) for m in first_messages)
    assert [m["role"] for m in first_messages].count("tool") >= 1, first_messages
    assert str(readme) in _message_text(first_messages[1])
    whole = "\n".join(
        _message_text(m)
        for gen in generations
        for m in load_agent_messages(engine, gen)
    )
    assert "crow-cli" in whole and "protocol/v1/overview.md" in whole, (
        "the cell's output never reached the transcript"
    )

    # Every successor opened with OUR handoff, not crow's.
    for gen in generations[1:]:
        messages = load_agent_messages(engine, gen)
        assert messages[0]["role"] == "system"
        handoff = messages[1]
        assert handoff["role"] == "user"
        text = _message_text(handoff)
        assert text.startswith(agent_mod.HANDOFF), text[:200]
        # Between the banner and the verbatim tail is the live model's summary.
        summary = text.removeprefix(agent_mod.HANDOFF).split("Last messages:")[0]
        assert len(summary.strip()) > 100, summary
        # The whole point: the raw tool output is gone from the successor's
        # context, replaced by the summary. Message COUNT is the wrong measure
        # — a compacted generation can carry as many rows and still be a
        # fraction of the size.
        size = sum(len(_message_text(m)) for m in messages)
        assert size < first_size, f"{gen.agent_id} did not shrink: {size} vs {first_size}"

    # The last generation is the one /compact minted, and it is the session's
    # live head — the harness, not the callable, did that arithmetic.
    assert generations[-1].agent_id in slash_text, slash_text
