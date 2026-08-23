"""CLI telemetry surfaces — list-sessions / query-memory / query-session.

Same functions, two facades: these commands call the exact functions the
MCP server exposes as tools (crow_cli.mcp.memory.main), so the store/tool
semantics are already covered by tests/mcp — here we verify the CLI facade
itself: --config-file db override, markdown output, include_forks parity.

Real tmp sqlite v5 db (the store needs real FTS5 + id anchors).
"""

import asyncio

import pytest
from typer.testing import CliRunner

from crow_cli.agent.session import AgentSession, lookup_or_create_prompt
from crow_cli.cli.main import app

runner = CliRunner()

FORK_SECRET = "FORK-ONLY-PLATYPUS-9"


async def invoke(*args: str):
    """Run the (sync) typer command in a worker thread: the command calls
    asyncio.run(), which needs NO running loop — the test's loop stays on
    the main thread."""
    return await asyncio.to_thread(runner.invoke, app, list(args))


@pytest.fixture
async def telemetry_env(tmp_path, monkeypatch):
    """Seeded tmp v5 db + a config file pointing at it."""
    monkeypatch.delenv("CROW_DB_URI", raising=False)
    monkeypatch.delenv("CROW_MEMORY_DB", raising=False)
    yield_env = {}

    db_path = tmp_path / "telemetry.db"
    memory_path = f"sqlite:///{db_path}"
    prompt_id = await lookup_or_create_prompt(
        "You are a probe.", name="probe", memory_path=memory_path
    )
    session = await AgentSession.create(
        prompt_id=prompt_id,
        prompt_args={},
        tool_definitions=[],
        request_params={},
        model_identifier="test-model",
        memory_path=memory_path,
        cwd="/tmp",
        session_id="telemetry-sess",
    )
    await session.add_message({"role": "user", "content": "remember XYZZY-42 please"})
    await session.add_message(
        {"role": "assistant", "content": "I will remember XYZZY-42."}
    )
    await session.close()

    config_file = tmp_path / "telemetry-crow.yaml"
    config_file.write_text(f"db_uri: {memory_path}\n")

    yield_env["config_file"] = str(config_file)
    yield_env["memory_path"] = memory_path
    yield yield_env

    monkeypatch.delenv("CROW_DB_URI", raising=False)


def _cfg(env):
    return ["--config-file", env["config_file"], "--raw"]


async def test_list_sessions_shows_seeded_session(telemetry_env):
    env = telemetry_env
    result = await invoke("list-sessions", *_cfg(env))
    assert result.exit_code == 0, result.output
    assert "telemetry-sess" in result.output
    assert "test-model" in result.output


async def test_query_session_browse(telemetry_env):
    env = telemetry_env
    result = await invoke(
        "query-session", "telemetry-sess", "--limit", "10", "--order", "asc", *_cfg(env)
    )
    assert result.exit_code == 0, result.output
    assert "remember XYZZY-42 please" in result.output
    assert "I will remember XYZZY-42." in result.output


async def test_query_session_search(telemetry_env):
    env = telemetry_env
    result = await invoke("query-session", "telemetry-sess", "-q", "XYZZY-42", *_cfg(env))
    assert result.exit_code == 0, result.output
    assert "XYZZY-42" in result.output


async def test_query_memory_finds_session(telemetry_env):
    env = telemetry_env
    result = await invoke("query-memory", "XYZZY-42", *_cfg(env))
    assert result.exit_code == 0, result.output
    assert "telemetry-sess" in result.output


async def test_query_memory_no_match(telemetry_env):
    env = telemetry_env
    result = await invoke("query-memory", "NO-SUCH-TERM-ANYWHERE", *_cfg(env))
    assert result.exit_code == 0, result.output
    assert "No matches" in result.output


async def test_include_forks_parity(telemetry_env):
    """Fork rows are hidden by default and folded in with --include-forks —
    same semantics as the MCP tools, verified at the CLI surface."""
    env = telemetry_env
    fork = await AgentSession.fork(
        "telemetry-sess", memory_path=env["memory_path"], cwd="/tmp"
    )
    await fork.add_message({"role": "user", "content": FORK_SECRET})
    await fork.close()

    hidden = await invoke("query-memory", FORK_SECRET, *_cfg(env))
    assert hidden.exit_code == 0, hidden.output
    assert "No matches" in hidden.output

    shown = await invoke("query-memory", FORK_SECRET, "--include-forks", *_cfg(env))
    assert shown.exit_code == 0, shown.output
    assert FORK_SECRET in shown.output


async def test_invalid_mode_rejected(telemetry_env):
    env = telemetry_env
    result = await invoke("query-session", "telemetry-sess", "--mode", "bogus", *_cfg(env))
    assert result.exit_code == 1
    assert "Invalid --mode" in result.output
