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

The third regression is not a crash but a divergence, and it is the reason the
user branch is capped like the other two: see
``test_the_handoff_cannot_compound``.
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


def test_the_handoff_cannot_compound():
    """A handoff 100x bigger produces a byte-identical tail.

    ``default_compactor`` hands the successor ``summary + last_messages(...)``
    as its first USER message, so the NEXT compaction's tail reads the previous
    handoff back. While the user branch was the one branch with no cap, each
    pass folded the previous handoff in whole and the size compounded — measured
    live at a 30k ceiling: 11k -> 32k -> 58k -> 92k -> 131k -> 172k chars over
    six generations. Each successor was born closer to the ceiling and then past
    it, each summary call took longer than the one before (2m00s -> 3m27s), and
    the turn never finished: ``tests/e2e/test_compact_continues_live.py`` timed
    out at 1200s with the dive one page from done.

    The assertion is the fixed point rather than a size limit, because a limit
    would pass on any cap and the bug is that the tail's size was a function of
    the history's at all. What the successor needs from the tail is texture, and
    the record is the summary.
    """
    def tail(handoff_chars: int) -> str:
        session = SimpleNamespace(
            messages=[
                {"role": "system", "content": "You are Crow agent."},
                {"role": "user", "content": "## Summary\n\n" + "s" * handoff_chars},
                {
                    "role": "assistant",
                    "content": "Picking up where the last generation left off.",
                },
                {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
            ]
        )
        return last_messages(session)

    small, large = tail(2_000), tail(200_000)

    assert small == large
    assert len(large) < 1_000, len(large)
    # The tail is still a tail: every role is represented, and the user's own
    # opening words survive the cap because the cap is a window, not a mute.
    assert large.startswith("USER:\n## Summary")
    assert "ASSISTANT:" in large and "TOOL RESULT:" in large


def test_unroll_content_flattens_every_shape_it_is_handed():
    assert unroll_content(None) == ""
    assert unroll_content("plain") == "plain"
    assert unroll_content([]) == ""
    assert unroll_content([{"type": "text", "text": "a"}, {"type": "image_url"}]) == "a"

