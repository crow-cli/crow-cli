"""Regression test for list content in tool/assistant messages.

The OpenAI API (and some providers via litellm) can return tool message
content as a list of content parts like:

    [{"type": "text", "text": "..."}, {"type": "image_url", ...}]

This previously caused a TypeError in last_messages() because the
string-slicing logic returned a list instead of a string.
"""

import json
from pathlib import Path
from types import SimpleNamespace

from crow_cli.agent.compact import last_messages


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
