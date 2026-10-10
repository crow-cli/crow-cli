"""``_meta`` arrives in two shapes and both have to read.

mcp 1.x handed the server a pydantic ``RequestParams.Meta``; mcp 2.x hands it a
``RequestParamsMeta`` TypedDict, which is a plain dict at runtime. ``getattr``
with a default answers None for every key of a dict, which is how the identity
rail went silently empty under fastmcp 4 — no exception anywhere, just no
session, no db, no images. These pin both shapes so the next SDK cannot do it
quietly again, and so the contract does not depend on which fastmcp the test
env happens to have resolved.
"""

from dataclasses import dataclass

from crow_cli.mcp_meta import meta_get, rail_unread


@dataclass
class ModelMeta:
    """The mcp 1.x shape: attributes, not keys."""

    session_id: str = "s-1"
    db_uri: str | None = None


def test_reads_a_dict_shaped_rail():
    meta = {"session_id": "s-1", "db_uri": "sqlite:///x.db"}
    assert meta_get(meta, "session_id") == "s-1"
    assert meta_get(meta, "db_uri") == "sqlite:///x.db"


def test_reads_a_model_shaped_rail():
    meta = ModelMeta(session_id="s-2", db_uri="sqlite:///y.db")
    assert meta_get(meta, "session_id") == "s-2"
    assert meta_get(meta, "db_uri") == "sqlite:///y.db"


def test_a_key_neither_shape_carries_is_the_default():
    assert meta_get({}, "session_id") is None
    assert meta_get(ModelMeta(), "images_dir", "fallback") == "fallback"


def test_no_rail_at_all_is_a_bare_caller_and_stays_quiet():
    assert meta_get(None, "session_id") is None
    assert rail_unread(None, None) is False


def test_a_rail_that_arrived_unread_is_loud():
    # Only the SDK's own keys survived: that is the shape change, and it must
    # not be mistaken for a bare caller that sent nothing.
    sdk_only = {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}
    assert rail_unread(sdk_only, None) is True
    assert rail_unread({"session_id": "s-1"}, "s-1") is False
    assert rail_unread(ModelMeta(), "s-1") is False
