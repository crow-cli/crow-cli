"""Agent store — user-editable TOMLs in <config dir>/agents.

Bundled TOMLs seed the dir on first access; the user dir is then the
authority (override by identity, active=false hides, ${VAR} expansion
shares resolve_env_vars with config.yaml's mcpServers).
"""

import pytest

from crow_cli.tui.agents import AgentReadError, agents_dir, read_agents

BUNDLED_IDENTITY = "crowai.dev"


async def test_seeds_bundled_agents_on_first_access(tmp_path):
    agents = await read_agents(tmp_path)
    assert BUNDLED_IDENTITY in agents
    assert (agents_dir(tmp_path) / f"{BUNDLED_IDENTITY}.toml").exists()


async def test_seeding_does_not_clobber_user_edits(tmp_path):
    store = agents_dir(tmp_path)
    custom = store / f"{BUNDLED_IDENTITY}.toml"
    custom.write_text(custom.read_text().replace('name = "crow-cli"', 'name = "mine"'))
    agents = await read_agents(tmp_path)
    assert agents[BUNDLED_IDENTITY]["name"] == "mine"


async def test_new_agent_and_active_false(tmp_path):
    store = agents_dir(tmp_path)
    (store / "example.com.toml").write_text(
        'identity = "example.com"\nname = "Example"\nshort_name = "ex"\n'
        'url = "https://example.com"\nprotocol = "acp"\ntype = "coding"\n'
        'run_command."*" = "example-agent"\n'
    )
    (store / "ghost.toml").write_text(
        'identity = "ghost"\nname = "Ghost"\nshort_name = "g"\nurl = "https://g"\n'
        'protocol = "acp"\ntype = "chat"\nactive = false\nrun_command."*" = "ghost"\n'
    )
    agents = await read_agents(tmp_path)
    assert "example.com" in agents
    assert "ghost" not in agents


async def test_env_var_resolution(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CMD", "my-agent")
    store = agents_dir(tmp_path)
    (store / "env.toml").write_text(
        'identity = "env"\nname = "Env"\nshort_name = "e"\nurl = "https://e"\n'
        'protocol = "acp"\ntype = "coding"\nrun_command."*" = "${AGENT_CMD} --serve"\n'
    )
    agents = await read_agents(tmp_path)
    assert agents["env"]["run_command"]["*"] == "my-agent --serve"


async def test_bad_toml_fails_fast(tmp_path):
    store = agents_dir(tmp_path)
    (store / "broken.toml").write_text("identity = [")
    with pytest.raises(AgentReadError):
        await read_agents(tmp_path)
