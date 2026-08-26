"""crow_cli.memory: schema v5 — images in the ImageStore, FTS5 bm25, WAL
concurrency, db_uri as the only integration point."""

import base64
import os

import pytest

import crow_cli.memory as db
from crow_cli.memory.image_store import FsImageStore

PNG = base64.b64encode(bytes([0x89, 0x50, 0x4E, 0x47, 1, 2, 3])).decode()


@pytest.fixture()
def store(tmp_path):
    db_uri = f"sqlite:///{tmp_path / 'crow.db'}"
    db.create_database(db_uri)
    engine = db.get_engine(db_uri)
    db.create_agent(
        engine,
        agent_id="s1-1-1",
        session_id="s1",
        agent_idx=1,
        cwd="/tmp",
        system_prompt="sp",
        tool_definitions=[],
        request_params={},
        model_identifier="m",
    )
    return engine, FsImageStore(tmp_path / "images")


def _image_msg():
    return {
        "role": "tool",
        "tool_call_id": "c1",
        "content": [
            {"type": "text", "text": "look at the screenshot of the landing page"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}},
        ],
    }


def test_image_extract_and_hydrate_roundtrip(store):
    engine, images = store
    db.add_message(engine, "s1-1-1", _image_msg(), store=images)

    stored = db.load_messages(engine, "s1-1-1")
    ref = stored[0]["content"][1]
    assert ref["type"] == "image_ref"
    assert images.exists(ref["path"])

    hydrated = db.load_messages(engine, "s1-1-1", hydrate=True, store=images)
    url = hydrated[0]["content"][1]["image_url"]["url"]
    assert url == f"data:image/png;base64,{PNG}"


def test_image_dedupe(store):
    engine, images = store
    db.add_message(engine, "s1-1-1", _image_msg(), store=images)
    db.add_message(engine, "s1-1-1", _image_msg(), store=images)
    assert len(list(images.images_dir.iterdir())) == 1


def test_bm25_search(store):
    engine, images = store
    db.add_message(engine, "s1-1-1", _image_msg(), store=images)
    db.add_message(
        engine, "s1-1-1", {"role": "assistant", "content": "unrelated reply"}, store=images
    )
    hits = db.search_messages(engine, "landing screenshot")
    assert len(hits) == 1
    assert hits[0]["role"] == "tool"
    assert hits[0]["session_id"] == "s1"
    assert hits[0]["score"] is not None
    assert db.search_messages(engine, "zebra quantum") == []


def test_search_agent_ids_filter(store):
    engine, images = store
    db.create_agent(
        engine, agent_id="s2-1-1", session_id="s2", agent_idx=1,
        tool_definitions=[], request_params={},
    )
    db.add_message(engine, "s1-1-1", {"role": "user", "content": "needle talk"}, store=images)
    db.add_message(engine, "s2-1-1", {"role": "user", "content": "needle talk"}, store=images)
    hits = db.search_messages(engine, "needle", agent_ids={"s2-1-1"})
    assert [h["agent_id"] for h in hits] == ["s2-1-1"]


def test_list_sessions_counts(store):
    engine, images = store
    db.add_message(engine, "s1-1-1", {"role": "user", "content": "hi"}, store=images)
    db.add_message(engine, "s1-1-1", {"role": "assistant", "content": "yo"}, store=images)
    [s] = db.list_sessions(engine)
    assert s["session_id"] == "s1"
    assert s["message_count"] == 2
    assert s["agent_count"] == 1
    assert s["model_identifier"] == "m"


def test_concurrent_engines(store):
    engine, images = store
    db.add_message(engine, "s1-1-1", {"role": "user", "content": "one"}, store=images)
    engine2 = db.get_engine(f"sqlite:///{images.images_dir.parent / 'crow.db'}")
    db.add_message(engine2, "s1-1-1", {"role": "user", "content": "two"}, store=images)
    assert len(db.load_messages(engine, "s1-1-1")) == 2


def test_prompt_lookup_idempotent(store):
    engine, _ = store
    a = db.lookup_or_create_prompt(engine, "tpl", "x")
    b = db.lookup_or_create_prompt(engine, "tpl", "x")
    assert a == b
    assert db.get_prompt(engine, a).template == "tpl"


def test_readonly_engine_reads_but_cannot_write(store):
    """The crow-mcp pattern: mode=ro engine sees the data, writes fail."""
    engine, images = store
    db.add_message(engine, "s1-1-1", {"role": "user", "content": "visible"}, store=images)
    engine.dispose()

    path = images.images_dir.parent / "crow.db"
    ro = db.get_engine(f"sqlite:///file:{path}?mode=ro&uri=true")
    assert [m["content"] for m in db.load_messages(ro, "s1-1-1")] == ["visible"]
    assert db.search_messages(ro, "visible")
    with pytest.raises(Exception):
        db.add_message(ro, "s1-1-1", {"role": "user", "content": "nope"})
    ro.dispose()


def test_agent_id_build_parse():
    aid = db.build_agent_id("lumpy-energetic-hyrax", 3, 2)
    assert aid == "lumpy-energetic-hyrax-3-2"
    assert db.parse_agent_id(aid) == ("lumpy-energetic-hyrax", 3, 2)
    # trunk default
    assert db.build_agent_id("s", 1) == "s-1-1"
    # coolnames contain hyphens — parsing goes from the right
    assert db.parse_agent_id("s-1-1") == ("s", 1, 1)
    with pytest.raises(ValueError):
        db.parse_agent_id("unmigrated-two")


def test_fork_schema_v5(store):
    engine, images = store
    # fixture created trunk s1-1-1; add fork 2 at the same agent_idx
    db.create_agent(
        engine, agent_id="s1-1-2", session_id="s1", agent_idx=1, fork_idx=2,
        forked_at="1", tool_definitions=[], request_params={},
    )
    db.add_message(
        engine, "s1-1-2", {"role": "user", "content": "forked question"}, store=images
    )
    # HEAD resolution follows the trunk by default
    assert db.get_max_agent_idx(engine, "s1") == 1
    # compaction inside the fork advances idx within the fork only
    db.create_agent(
        engine, agent_id="s1-2-2", session_id="s1", agent_idx=2, fork_idx=2,
        tool_definitions=[], request_params={},
    )
    assert db.get_max_agent_idx(engine, "s1") == 1
    assert db.get_max_agent_idx(engine, "s1", fork_idx=None) == 2
    # search exposes the fork dimension
    hits = db.search_messages(engine, "forked question")
    assert hits[0]["fork_idx"] == 2
    assert hits[0]["agent_id"] == "s1-1-2"


def test_get_max_fork_idx(store):
    engine, images = store
    # trunk only -> 1
    assert db.get_max_fork_idx(engine, "s1", 1) == 1
    db.create_agent(
        engine, agent_id="s1-1-2", session_id="s1", agent_idx=1, fork_idx=2,
        forked_at="1", tool_definitions=[], request_params={},
    )
    assert db.get_max_fork_idx(engine, "s1", 1) == 2
    # unknown (session, agent_idx) pair -> 1, so the next fork becomes 2
    assert db.get_max_fork_idx(engine, "s1", 99) == 1


def test_load_agent_messages_fork_view(store):
    """Fork view = trunk PREFIX (id <= forked_at) + fork's own rows; the
    prefix is shared, never copied, and the trunk stays unpolluted."""
    engine, images = store
    for i in range(4):
        db.add_message(engine, "s1-1-1", {"role": "user", "content": f"trunk {i}"}, store=images)
    anchor = db.query_messages(engine, ["s1-1-1"])[1].id  # keep trunk msgs 0-1

    db.create_agent(
        engine, agent_id="s1-1-2", session_id="s1", agent_idx=1, fork_idx=2,
        forked_at=str(anchor), tool_definitions=[], request_params={},
    )
    db.add_message(engine, "s1-1-2", {"role": "user", "content": "fork own"}, store=images)

    fork_view = db.load_agent_messages(engine, db.get_agent(engine, "s1-1-2"))
    assert [m["content"] for m in fork_view] == ["trunk 0", "trunk 1", "fork own"]

    # trunk view is its own rows only — no fork pollution
    trunk_view = db.load_agent_messages(engine, db.get_agent(engine, "s1-1-1"))
    assert [m["content"] for m in trunk_view] == [f"trunk {i}" for i in range(4)]

    # forked_at=None means "whole trunk" (fork at HEAD)
    db.create_agent(
        engine, agent_id="s1-1-3", session_id="s1", agent_idx=1, fork_idx=3,
        forked_at=None, tool_definitions=[], request_params={},
    )
    head_view = db.load_agent_messages(engine, db.get_agent(engine, "s1-1-3"))
    assert [m["content"] for m in head_view] == [f"trunk {i}" for i in range(4)]


def test_list_sessions_include_forks(store):
    """list_sessions hides the fork dimension by default: trunk agents and
    their messages only (fork rows are keyed by fork agent_ids, so dropping
    the fork agent rows drops their messages from the join)."""
    engine, images = store
    for i in range(3):
        db.add_message(engine, "s1-1-1", {"role": "user", "content": f"t{i}"}, store=images)
    db.create_agent(
        engine, agent_id="s1-1-2", session_id="s1", agent_idx=1, fork_idx=2,
        forked_at=None, tool_definitions=[], request_params={},
    )
    db.add_message(engine, "s1-1-2", {"role": "user", "content": "fork msg"}, store=images)

    (s1,) = [s for s in db.list_sessions(engine) if s["session_id"] == "s1"]
    assert s1["agent_count"] == 1
    assert s1["message_count"] == 3

    (s1,) = [s for s in db.list_sessions(engine, include_forks=True) if s["session_id"] == "s1"]
    assert s1["agent_count"] == 2
    assert s1["message_count"] == 4


def test_add_message_rejects_v4_agent_id(store):
    engine, images = store
    with pytest.raises(ValueError, match="malformed agent_id"):
        db.add_message(engine, "s1-1", {"role": "user", "content": "x"})


def test_v4_database_fails_fast(tmp_path):
    import sqlalchemy as sa

    uri = f"sqlite:///{tmp_path / 'old.db'}"
    eng = sa.create_engine(uri)
    with eng.connect() as conn:
        conn.execute(sa.text("CREATE TABLE agents (agent_id TEXT PRIMARY KEY)"))
        conn.commit()
    eng.dispose()
    with pytest.raises(RuntimeError, match="schema v4"):
        db.create_database(uri)


def test_normalize_db_uri(tmp_path):
    assert db.normalize_db_uri("sqlite:////tmp/crow.db") == "sqlite:////tmp/crow.db"
    assert db.normalize_db_uri("postgresql://u:p@host/db") == "postgresql://u:p@host/db"
    expected = f"sqlite:///{(tmp_path / 'crow.db').resolve()}"
    assert db.normalize_db_uri(str(tmp_path / "crow.db")) == expected
    assert db.normalize_db_uri("~/crow.db").endswith("/crow.db")
    assert db.normalize_db_uri("~/crow.db").startswith("sqlite:///")
    # tilde inside the URI form expands too
    home = os.path.expanduser("~")
    assert (
        db.normalize_db_uri("sqlite:///~/.agents/crow.db")
        == f"sqlite:///{home}/.agents/crow.db"
    )
