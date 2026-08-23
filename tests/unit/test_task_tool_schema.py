"""Phase 1 — `task` tool schema prototype (FastMCP experiment, PLAN 1.1–1.3).

Prove the tool shape BEFORE any plumbing. The single `task` tool takes
``updates: list[PromptItem | CancelTurnItem]`` (no task_create, no
task_read — read is query_session on the session_id).

The two item types have OVERLAPPING fields — each carries the other's
payload as an optional — so a naive union is ambiguous: one wire dict can
be both "prompt an existing session" and "cancel, then re-prompt". The
experiment demonstrates the ambiguity, then proves the discriminated
variant yields a schema a model can follow and round-trips through real
FastMCP argument parsing (in-process client path, no mocks).
"""

from typing import Annotated, Literal, Union

import pytest
from fastmcp import FastMCP
from pydantic import BaseModel, Field, TypeAdapter

# ------------------------------------------------------------- naive union


class PromptItemNaive(BaseModel):
    prompt: str
    session_id: str | None = None


class CancelTurnNaive(BaseModel):
    session_id: str
    prompt: str | None = None


NAIVE_LIST = TypeAdapter(list[Union[PromptItemNaive, CancelTurnNaive]])

# ------------------------------------------------------- discriminated union


class PromptItem(BaseModel):
    """Send a prompt to a session. session_id omitted/None launches a NEW
    subagent; with session_id it re-prompts an existing (paused/cancelled/
    ended) session, resuming it if it is not live."""

    action: Literal["prompt"] = "prompt"
    prompt: str
    session_id: str | None = None
    priority: Literal["high", "low"] = "low"
    model: str | None = None


class CancelTurn(BaseModel):
    """session/cancel a running session mid-turn. The optional prompt sends
    a follow-up right after the cancel, in the same tool call."""

    action: Literal["cancel"] = "cancel"
    session_id: str
    prompt: str | None = None


TaskUpdate = Annotated[Union[PromptItem, CancelTurn], Field(discriminator="action")]
DISCRIMINATED_LIST = TypeAdapter(list[TaskUpdate])


@pytest.fixture
def task_mcp():
    mcp = FastMCP("task-proto")

    @mcp.tool
    async def task(updates: list[TaskUpdate]) -> str:
        """Create, re-prompt or cancel subagent sessions.

        updates is a list of items, each either:
          - {"action": "prompt", "prompt": ..., "session_id": null}  launch
          - {"action": "prompt", "prompt": ..., "session_id": "..."}  re-prompt
          - {"action": "cancel", "session_id": "...", "prompt": null} cancel
        """
        return repr(updates)

    return mcp


# ------------------------------------------------------------------ the flaw


class TestNaiveUnionIsAmbiguous:
    """The same wire dict validates as BOTH item types — intent is
    unrecoverable without a discriminator."""

    AMBIGUOUS = {"prompt": "fix the bug", "session_id": "swift-fox"}

    def test_both_variants_accept_the_same_payload(self):
        as_prompt = PromptItemNaive.model_validate(self.AMBIGUOUS)
        as_cancel = CancelTurnNaive.model_validate(self.AMBIGUOUS)
        assert as_prompt.prompt == as_cancel.prompt == "fix the bug"
        assert as_prompt.session_id == as_cancel.session_id == "swift-fox"

    def test_smart_union_silently_picks_one(self):
        parsed = NAIVE_LIST.validate_python([self.AMBIGUOUS])
        assert len(parsed) == 1
        # Whichever it picked, the OTHER reading was equally valid — the
        # model's intent ("re-prompt it" vs "cancel then re-prompt") is
        # lost. That is the flaw the discriminator fixes.
        assert isinstance(parsed[0], (PromptItemNaive, CancelTurnNaive))


# ------------------------------------------------------------- the fix


class TestDiscriminatedUnion:
    LAUNCH = {"action": "prompt", "prompt": "investigate crow-cli"}
    RE_PROMPT = {
        "action": "prompt",
        "prompt": "you went off course, do X instead",
        "session_id": "swift-fox",
        "priority": "high",
    }
    CANCEL_THEN_PROMPT = {
        "action": "cancel",
        "session_id": "swift-fox",
        "prompt": "start over, but gently",
    }

    def test_all_three_shapes_parse(self):
        parsed = DISCRIMINATED_LIST.validate_python(
            [self.LAUNCH, self.RE_PROMPT, self.CANCEL_THEN_PROMPT]
        )
        launch, re_prompt, cancel = parsed
        assert isinstance(launch, PromptItem) and launch.session_id is None
        assert launch.priority == "low"  # default
        assert isinstance(re_prompt, PromptItem)
        assert re_prompt.session_id == "swift-fox"
        assert re_prompt.priority == "high"
        assert isinstance(cancel, CancelTurn)
        assert cancel.prompt == "start over, but gently"

    def test_overlapping_payload_is_no_longer_ambiguous(self):
        """The ambiguous dict now REQUIRES a verdict via action."""
        with pytest.raises(Exception):
            DISCRIMINATED_LIST.validate_python(
                [{"prompt": "fix the bug", "session_id": "swift-fox"}]
            )


class TestSchemaTheModelSees:
    async def test_parameters_name_both_variants_and_the_discriminator(
        self, task_mcp
    ):
        tool = await task_mcp.get_tool("task")
        schema = tool.parameters
        blob = __import__("json").dumps(schema)

        # Both variants reachable from the updates parameter
        assert "PromptItem" in blob
        assert "CancelTurn" in blob
        # The discriminator is visible to the model
        assert '"action"' in blob
        assert '"prompt"' in blob and '"cancel"' in blob
        # Priority is plumbed day one
        assert '"high"' in blob and '"low"' in blob

    def test_json_schema_marks_action_const_per_variant(self):
        schema = PromptItem.model_json_schema()
        assert schema["properties"]["action"]["const"] == "prompt"
        schema = CancelTurn.model_json_schema()
        assert schema["properties"]["action"]["const"] == "cancel"


class TestFastMcpRoundTrip:
    """Through the real FastMCP call path (argument parsing included)."""

    async def test_mixed_batch_round_trips(self, task_mcp):
        result = await task_mcp.call_tool(
            "task",
            {
                "updates": [
                    {"action": "prompt", "prompt": "launch me"},
                    {
                        "action": "cancel",
                        "session_id": "swift-fox",
                        "prompt": "actually do this instead",
                    },
                ]
            },
        )
        text = str(result.data if hasattr(result, "data") else result)
        assert "PromptItem" in text
        assert "CancelTurn" in text
        assert "launch me" in text
        assert "actually do this instead" in text

    async def test_bad_action_is_rejected_not_guessed(self, task_mcp):
        with pytest.raises(Exception):
            await task_mcp.call_tool(
                "task",
                {"updates": [{"action": "yeet", "session_id": "x"}]},
            )
