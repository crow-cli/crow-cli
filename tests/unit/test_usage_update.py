"""
UsageUpdate emission regression tests (hermetic — no LLM, no network).

Regression: the UsageUpdate sent from react_loop to expose context usage
(% of the compaction threshold) to the ACP client was constructed WITHOUT
the required ``sessionUpdate`` discriminator, so pydantic raised a
ValidationError and the best-effort try/except swallowed it — Zed never
received the update and its token-usage ring stayed empty.

The SDK now defaults the discriminator (``session_update:
Literal["usage_update"] = "usage_update"``), so the historical bug is no
longer reachable: omitting it produces the right payload instead of raising
into a best-effort try/except. What Zed depends on is the wire shape, and
that is what both tests below pin.
"""

from acp.schema import UsageUpdate


def test_usage_update_discriminator_is_defaulted():
    """Omitting sessionUpdate must still put it on the wire.

    This used to assert the opposite — that omitting it raised — because the
    generated model had no default and the ValidationError was swallowed by
    the best-effort try/except around it. The SDK gained the default, so the
    guarantee is now stronger: there is no way to construct the update the
    react loop sends and lose the discriminator.
    """
    payload = UsageUpdate(used=91266, size=190000).model_dump(
        by_alias=True, exclude_none=True
    )
    assert payload == {"used": 91266, "size": 190000, "sessionUpdate": "usage_update"}


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
