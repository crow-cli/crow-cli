"""
UsageUpdate emission regression tests (hermetic — no LLM, no network).

Regression: the UsageUpdate sent from react_loop to expose context usage
(% of the compaction threshold) to the ACP client was constructed WITHOUT
the required ``sessionUpdate`` discriminator, so pydantic raised a
ValidationError and the best-effort try/except swallowed it — Zed never
received the update and its token-usage ring stayed empty.

The SDK's generated model requires the discriminator explicitly (no
default), exactly like ToolCallProgress ("tool_call_update") and friends.
"""

import pytest
from pydantic import ValidationError

from acp.schema import UsageUpdate


def test_usage_update_requires_discriminator():
    """The historical bug: omitting sessionUpdate must fail validation."""
    with pytest.raises(ValidationError):
        UsageUpdate(used=91266, size=190000)


def test_usage_update_wire_format_matches_zed():
    """Constructed as react_loop does, the payload must match what Zed's
    agent-client-protocol-schema deserializes:
    {"sessionUpdate": "usage_update", "used": N, "size": M}."""
    update = UsageUpdate(
        session_update="usage_update",
        used=91266,
        size=190000,
    )
    payload = update.model_dump(by_alias=True, exclude_none=True)
    assert payload == {
        "sessionUpdate": "usage_update",
        "used": 91266,
        "size": 190000,
    }
