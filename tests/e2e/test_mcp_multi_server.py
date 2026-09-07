"""E2E: one codebase, several servers — the config.yaml multi-server story.

The point of ``--include-tools`` is not the flag. It is that config.yaml can
now declare several crow-mcp entries, each a slice of the same tool set, and an
agent handed all of them sees the UNION as one flat tool list. That is how one
codebase becomes a filesystem server and a web server without forking anything.

Each test declares slices, spawns a real agent subprocess, and reads the
provisioned tool set back out of the isolated sqlite's ``agents.tool_definitions``
— the exact bytes the react loop would hand the model. No prompt is ever sent:
provisioning happens at session/new, before any LLM call, so the assertion is
deterministic and costs no tokens.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

from crow_cli.agent.mcp_client import fastmcp_config_to_acp_servers
from crow_cli.client.subagent import SubagentDriver
from crow_cli.config import Config
from crow_cli.mcp import tool_names

pytestmark = pytest.mark.asyncio

PREFERRED_MODEL = "qwen3.8-max-preview"
CROW_CLI = str(Path(sys.executable).parent / "crow-cli")
ALL = sorted(tool_names())


def _live_config_or_skip():
    config = Config.load()
    if not config.is_configured:
        pytest.skip("No LLM provider configured")
    if not config.llm.models:
        pytest.skip("No models configured")
    return config


def _model_name(config) -> str:
    return (
        PREFERRED_MODEL
        if PREFERRED_MODEL in config.llm.models
        else next(iter(config.llm.models))
    )


def slice_server(name: str, tools: str) -> dict:
    return {
        name: {
            "transport": "stdio",
            "command": CROW_CLI,
            "args": ["mcp", "--include-tools", tools],
        }
    }


async def provisioned_tools(tmp_path: Path, servers: dict) -> list[str]:
    """Spawn a real agent with these mcpServers; return the tool names it
    persisted for the session — what the model would have been offered."""
    db = tmp_path / "multi-server.db"
    override = tmp_path / "override.yaml"
    override.write_text(yaml.safe_dump({"db_uri": f"sqlite:///{db}"}))

    config = _live_config_or_skip()
    driver = SubagentDriver()
    try:
        await driver.start(
            cwd=str(tmp_path), model=_model_name(config), config_file=override
        )
        await driver.new_session(
            cwd=str(tmp_path),
            mcp_servers=fastmcp_config_to_acp_servers(servers),
        )
    finally:
        await driver.close()

    with sqlite3.connect(db) as con:
        rows = con.execute("SELECT tool_definitions FROM agents").fetchall()
    assert len(rows) == 1, f"expected one provisioned agent, got {len(rows)}"
    definitions = json.loads(rows[0][0])
    return sorted(d["function"]["name"] for d in definitions)


async def test_two_slices_provision_their_union(tmp_path):
    got = await provisioned_tools(
        tmp_path,
        {
            **slice_server("crow-fs", "read,write,edit"),
            **slice_server("crow-web", "web_fetch,web_search"),
        },
    )
    assert got == ["edit", "read", "web_fetch", "web_search", "write"]
    # The whole point: the agent was NOT handed the omni-tool set.
    assert "execute" not in got and "terminal" not in got and "task" not in got


async def test_overlapping_slices_dedupe(tmp_path):
    # Two entries sharing a tool is a config.yaml typo waiting to happen; the
    # client merges by name, so the model must see `read` once, not twice.
    got = await provisioned_tools(
        tmp_path,
        {
            **slice_server("crow-a", "read,write"),
            **slice_server("crow-b", "read,edit"),
        },
    )
    assert got == ["edit", "read", "write"]


async def test_an_unsliced_entry_is_still_everything(tmp_path):
    # The default contract at agent level: no flag, no slice, all thirteen —
    # the server that existed before --include-tools did.
    got = await provisioned_tools(
        tmp_path,
        {"crow": {"transport": "stdio", "command": CROW_CLI, "args": ["mcp"]}},
    )
    assert got == ALL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
