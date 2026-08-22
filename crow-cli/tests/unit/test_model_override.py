"""-m/--model override on AcpAgent (run -m and acp -m)."""

import pytest
import yaml

from crow_cli.config import Config
from crow_cli.agent.main import AcpAgent
from crow_cli.agent.session import AgentSession, lookup_or_create_prompt


@pytest.fixture
def two_model_config(test_config_dir):
    """Config with two models so override-vs-first is distinguishable."""
    config_file = test_config_dir / "config.yaml"
    data = yaml.safe_load(config_file.read_text())
    data["models"]["second-model"] = {
        "provider": "test-provider",
        "model": "second-model-id",
    }
    # sort_keys=False: model ORDER is the feature under test (first = default)
    config_file.write_text(yaml.dump(data, sort_keys=False))
    return Config.load(test_config_dir)


def test_no_override_uses_first_model(two_model_config):
    agent = AcpAgent(config=two_model_config)
    assert agent._model_override is None
    assert agent._default_model_value() == "test-provider:test-model-id"
    assert agent._default_model_identifier() == "test-model-id"


def test_override_selects_named_model(two_model_config):
    agent = AcpAgent(config=two_model_config, model="second-model")
    assert agent._default_model_value() == "test-provider:second-model-id"
    assert agent._default_model_identifier() == "second-model-id"


def test_override_unknown_model_fails_fast(two_model_config):
    with pytest.raises(ValueError, match="not found in config.yaml"):
        AcpAgent(config=two_model_config, model="does-not-exist")


class TestOverrideIsTheModelConfigOption:
    """-m at load/fork time must apply the session's model config option
    exactly like session/set_config_option does: the option's currentValue
    AND session.model_identifier (what react.py sends to the API) both flip.

    Regression: loading a session saved under a model that is no longer
    reachable used to route the API request at the SAVED model (provider
    from -m, model string from the db) -> gateway 404 "Model not exist".
    """

    @pytest.fixture
    async def saved_session(self, memory_service):
        prompt_id = await lookup_or_create_prompt("You are a test.", name="t")
        return await AgentSession.create(
            prompt_id=prompt_id,
            prompt_args={"workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="saved-dead-model",
            cwd="/tmp",
            agent_idx=1,
            session_id="saved-session",
        )

    async def test_load_override_replaces_saved_model(
        self, two_model_config, saved_session
    ):
        agent = AcpAgent(config=two_model_config, model="second-model")
        resp = await agent.load_session(
            cwd="/tmp", session_id=saved_session.session_id, mcp_servers=[]
        )
        assert resp is not None
        loaded = agent._sessions[saved_session.agent_id]
        assert loaded.model_identifier == "second-model-id"
        model_opt = next(o for o in resp.config_options if o.id == "model")
        assert model_opt.current_value == "test-provider:second-model-id"

    async def test_load_without_override_keeps_saved_model(
        self, two_model_config, saved_session
    ):
        agent = AcpAgent(config=two_model_config)
        await agent.load_session(
            cwd="/tmp", session_id=saved_session.session_id, mcp_servers=[]
        )
        loaded = agent._sessions[saved_session.agent_id]
        assert loaded.model_identifier == "saved-dead-model"

    async def test_set_config_option_model_shares_the_same_path(
        self, two_model_config, saved_session
    ):
        agent = AcpAgent(config=two_model_config)
        await agent.load_session(
            cwd="/tmp", session_id=saved_session.session_id, mcp_servers=[]
        )
        resp = await agent.set_config_option(
            config_id="model",
            session_id=saved_session.session_id,
            value="test-provider:second-model-id",
        )
        loaded = agent._sessions[saved_session.agent_id]
        assert loaded.model_identifier == "second-model-id"
        model_opt = next(o for o in resp.config_options if o.id == "model")
        assert model_opt.current_value == "test-provider:second-model-id"

    async def test_fork_override_replaces_inherited_model(
        self, two_model_config, tmp_path
    ):
        # Fork needs the real sqlite store (message-id anchors), so run it
        # against a tmp v5 db instead of the in-memory fake.
        memory_path = f"sqlite:///{tmp_path / 'fork-override.db'}"
        prompt_id = await lookup_or_create_prompt(
            "You are {{name}}.", name="t", memory_path=memory_path
        )
        source = await AgentSession.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow"},
            tool_definitions=[],
            request_params={},
            model_identifier="saved-dead-model",
            memory_path=memory_path,
            cwd="/tmp",
            session_id="fork-source",
        )
        await source.add_message({"role": "user", "content": "turn zero"})
        await source.add_message({"role": "assistant", "content": "reply"})

        two_model_config.db_uri = memory_path
        agent = AcpAgent(config=two_model_config, model="second-model")
        resp = await agent.fork_session(
            session_id=source.session_id, cwd="/tmp", mcp_servers=[]
        )
        fork = agent._sessions[resp.session_id]
        assert fork.model_identifier == "second-model-id"
        model_opt = next(o for o in resp.config_options if o.id == "model")
        assert model_opt.current_value == "test-provider:second-model-id"
