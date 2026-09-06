"""Regression tests for content shapes last_messages() has to survive.

The OpenAI API (and some providers via litellm) can return tool message
content as a list of content parts like:

    [{"type": "text", "text": "..."}, {"type": "image_url", ...}]

This previously caused a TypeError in last_messages() because the
string-slicing logic returned a list instead of a string.

The same function also died on ``content: None``, which is not an exotic
provider quirk but the standard OpenAI shape for an assistant turn that did
nothing except call tools. ``AgentSession.add_message`` persists whatever dict
it is handed without normalizing it, so any caller that builds messages in the
API's own shape produced a session whose compaction crashed — and compaction
crashing is the one failure the whole module exists to prevent.
"""

import json
from pathlib import Path
from types import SimpleNamespace

from crow_cli.agent.compact import last_messages, unroll_content


def test_last_messages_with_list_content():
    fixture = Path(__file__).with_suffix(".json")
    with open(fixture) as f:
        messages = json.load(f)

    session = SimpleNamespace(messages=messages)

    # This used to raise:
    #   TypeError: sequence item 41: expected str instance, list found
    result = last_messages(session)

    assert isinstance(result, str)
    assert len(result) > 0
    # The fixture contains a tool message with list content that includes
    # an image_url part; unroll_content should have extracted the text.
    assert "Ran Playwright code" in result


def test_last_messages_with_null_content_on_a_tool_calling_turn():
    """``{"role": "assistant", "content": None, "tool_calls": [...]}`` is what
    every OpenAI-compatible client sends for a pure tool call.

    This used to raise:
        TypeError: object of type 'NoneType' has no len()
    """
    session = SimpleNamespace(
        messages=[
            {"role": "user", "content": "rename the helper"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "edit", "arguments": '{"a": 1}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        ]
    )

    result = last_messages(session)

    assert isinstance(result, str)
    # The turn is still represented — by the tool call it made.
    assert "TOOL — edit:" in result
    assert '{"a": 1}' in result


def test_unroll_content_flattens_every_shape_it_is_handed():
    assert unroll_content(None) == ""
    assert unroll_content("plain") == "plain"
    assert unroll_content([]) == ""
    assert unroll_content([{"type": "text", "text": "a"}, {"type": "image_url"}]) == "a"

