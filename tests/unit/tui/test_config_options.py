"""Client-side ACP session config options — how `-m` reaches ANY agent.

Model choice is the client's job: it travels over `session/set_config_option`
after the session exists, never in the agent's argv. That is the one path that
works for crow's own agent and for a `type: custom` agent_servers entry alike.

Regression: `crow-cli -m MODEL` used to be dropped on the floor whenever
config.yaml had an `agent_servers` block, because the top entry won and
`resolve_agent_server` had no `model` parameter — so every request went to the
first model in config.yaml (a local llama.cpp one) with no warning anywhere.

The agent half is covered by tests/unit/test_model_override.py; this is the
client half.
"""

import asyncio
import json

import pytest

from crow_cli.tui.acp import api
from crow_cli.tui.acp import protocol
from crow_cli.tui.acp.agent import Agent


# --------------------------------------------------------------------------
# Pure resolution helpers


def crow_model_option(current="llamacpp:gguf-flash", category="model"):
    """The option exactly as crow's own agent publishes it (agent/main.py)."""
    option = {
        "type": "select",
        "id": "model",
        "name": "Model",
        "currentValue": current,
        "options": [
            {"value": "llamacpp:gguf-flash", "name": "qwen3.8-flash-next",
             "description": "unsloth/Qwen3.8-Flash-Next-GGUF"},
            {"value": "alibaba:qwen3.8-max-preview", "name": "qwen3.8-max-preview",
             "description": "qwen3.8-max-preview"},
        ],
    }
    if category is not None:
        option["category"] = category
    return option


class TestFindConfigOption:
    def test_finds_by_category(self):
        found = protocol.find_config_option([crow_model_option()], category="model")
        assert found is not None and found["id"] == "model"

    def test_falls_back_to_id_when_category_absent(self):
        """Categories are UX hints — MUST NOT be required for correctness."""
        found = protocol.find_config_option(
            [crow_model_option(category=None)], category="model", option_id="model"
        )
        assert found is not None and found["id"] == "model"

    def test_category_wins_over_an_earlier_id_match(self):
        decoy = {"id": "model", "name": "Decoy", "type": "select",
                 "currentValue": "x", "options": [{"value": "x", "name": "x"}]}
        found = protocol.find_config_option(
            [decoy, crow_model_option()], category="model", option_id="model"
        )
        assert found.get("category") == "model"

    def test_no_options_no_option(self):
        assert protocol.find_config_option([], category="model", option_id="model") is None


class TestMatchConfigValue:
    def test_matches_the_display_name_the_user_types(self):
        """`-m qwen3.8-max-preview` is a config.yaml NAME, not a wire value."""
        assert protocol.match_config_value(
            crow_model_option(), "qwen3.8-max-preview"
        ) == "alibaba:qwen3.8-max-preview"

    def test_matches_the_wire_value_too(self):
        assert protocol.match_config_value(
            crow_model_option(), "alibaba:qwen3.8-max-preview"
        ) == "alibaba:qwen3.8-max-preview"

    def test_unknown_name_is_none_not_a_guess(self):
        assert protocol.match_config_value(crow_model_option(), "gpt-9") is None

    def test_names_are_listed_for_the_error(self):
        assert protocol.config_value_names(crow_model_option()) == [
            "qwen3.8-flash-next", "qwen3.8-max-preview",
        ]

    def test_current_name_resolves_to_the_display_name(self):
        assert protocol.config_current_name(crow_model_option()) == "qwen3.8-flash-next"


# --------------------------------------------------------------------------
# The wire request


def test_set_config_option_request_is_spec_shaped():
    """sessionId/configId/value — the exact params the v1 spec names."""
    async def build():
        with api.API.request():
            return api.session_set_config_option(
                "sess_abc123", "model", "alibaba:qwen3.8-max-preview"
            )

    call = asyncio.run(build())
    assert call.method == "session/set_config_option"
    assert json.loads(json.dumps(call.parameters)) == {
        "sessionId": "sess_abc123",
        "configId": "model",
        "value": "alibaba:qwen3.8-max-preview",
    }


# --------------------------------------------------------------------------
# Applying -m to a live session


class Recorder:
    """Stand-in message sink: the Agent only ever calls post_message on it."""

    def __init__(self):
        self.messages = []

    def post_message(self, message):
        self.messages.append(message)
        return True


def make_agent(model, options):
    agent = Agent.__new__(Agent)          # no subprocess, no Textual mount
    agent._model_request = model
    agent.config_options = options
    agent._message_target = Recorder()
    agent.sent = []

    async def record(config_id, value):
        agent.sent.append((config_id, value))
        return None

    agent.set_config_option = record
    return agent


def errors(agent):
    from crow_cli.tui.acp import messages as acp_messages
    return [m.message for m in agent._message_target.messages
            if isinstance(m, acp_messages.ConfigOptionError)]


class TestApplyModelRequest:
    def test_sends_the_resolved_value(self):
        agent = make_agent("qwen3.8-max-preview", [crow_model_option()])
        asyncio.run(agent._apply_model_request())
        assert agent.sent == [("model", "alibaba:qwen3.8-max-preview")]
        assert errors(agent) == []

    def test_nothing_to_do_when_already_current(self):
        agent = make_agent("qwen3.8-flash-next", [crow_model_option()])
        asyncio.run(agent._apply_model_request())
        assert agent.sent == []
        assert errors(agent) == []

    def test_unknown_model_warns_and_lists_the_valid_names(self):
        """The old behaviour was silence; this is the whole point of the fix."""
        agent = make_agent("gpt-9", [crow_model_option()])
        asyncio.run(agent._apply_model_request())
        assert agent.sent == []
        assert len(errors(agent)) == 1
        assert "Unknown model 'gpt-9'" in errors(agent)[0]
        assert "qwen3.8-max-preview" in errors(agent)[0]

    def test_agent_with_no_model_selector_warns(self):
        agent = make_agent("qwen3.8-max-preview", [])
        asyncio.run(agent._apply_model_request())
        assert agent.sent == []
        assert "no model selector" in errors(agent)[0]

    def test_the_request_is_consumed_exactly_once(self):
        """A name that does not resolve must not be retried on every later
        config_option_update — one warning, then the agent's default stands."""
        agent = make_agent("gpt-9", [crow_model_option()])
        asyncio.run(agent._apply_model_request())
        asyncio.run(agent._apply_model_request())
        assert len(errors(agent)) == 1


class TestIngestConfigOptions:
    def test_replaces_rather_than_merges(self):
        """Every carrier holds the COMPLETE state; an agent-side model
        fallback must show up as current, not linger beside the old one."""
        agent = make_agent(None, [crow_model_option()])
        agent._ingest_config_options(
            {"configOptions": [crow_model_option(current="alibaba:qwen3.8-max-preview")]}
        )
        assert len(agent.config_options) == 1
        assert agent.config_options[0]["currentValue"] == "alibaba:qwen3.8-max-preview"

    def test_publishes_to_the_ui(self):
        from crow_cli.tui.acp import messages as acp_messages
        agent = make_agent(None, [])
        agent._ingest_config_options({"configOptions": [crow_model_option()]})
        posted = [m for m in agent._message_target.messages
                  if isinstance(m, acp_messages.SetConfigOptions)]
        assert len(posted) == 1 and len(posted[0].config_options) == 1

    def test_absent_key_clears(self):
        agent = make_agent(None, [crow_model_option()])
        agent._ingest_config_options({})
        assert agent.config_options == []
