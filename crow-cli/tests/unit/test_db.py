"""db.py: sqlite schema v4 — images on disk, FTS5 bm25, WAL concurrency."""

import base64

import pytest

from crow_cli.agent import db

PNG = base64.b64encode(bytes([0x89, 0x50, 0x4E, 0x47, 1, 2, 3])).decode()


@pytest.fixture()
def store(tmp_path):
    db_uri = f"sqlite:///{tmp_path / 'crow.db'}"
    db.create_database(db_uri)
    engine = db.get_engine(db_uri)
    db.create_agent(
        engine,
        agent_id="s1-1",
        session_id="s1",
        agent_idx=1,
        cwd="/tmp",
        system_prompt="sp",
        tool_definitions=[],
        request_params={},
        model_identifier="m",
    )
    return engine, tmp_path / "images"


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
    db.add_message(engine, "s1-1", _image_msg(), images_dir=images)

    stored = db.load_messages(engine, "s1-1")
    ref = stored[0]["content"][1]
    assert ref["type"] == "image_ref"
    assert (images / ref["path"]).exists()

    hydrated = db.load_messages(engine, "s1-1", hydrate=True, images_dir=images)
    url = hydrated[0]["content"][1]["image_url"]["url"]
    assert url == f"data:image/png;base64,{PNG}"


def test_image_dedupe(store):
    engine, images = store
    db.add_message(engine, "s1-1", _image_msg(), images_dir=images)
    db.add_message(engine, "s1-1", _image_msg(), images_dir=images)
    assert len(list(images.iterdir())) == 1


def test_bm25_search(store):
    engine, images = store
    db.add_message(engine, "s1-1", _image_msg(), images_dir=images)
    db.add_message(
        engine, "s1-1", {"role": "assistant", "content": "unrelated reply"}, images_dir=images
    )
    hits = db.search_messages(engine, "landing screenshot")
    assert len(hits) == 1
    assert hits[0]["role"] == "tool"
    assert hits[0]["session_id"] == "s1"
    assert db.search_messages(engine, "zebra quantum") == []


def test_list_sessions_counts(store):
    engine, images = store
    db.add_message(engine, "s1-1", {"role": "user", "content": "hi"}, images_dir=images)
    db.add_message(engine, "s1-1", {"role": "assistant", "content": "yo"}, images_dir=images)
    [s] = db.list_sessions(engine)
    assert s["session_id"] == "s1"
    assert s["message_count"] == 2
    assert s["agent_count"] == 1
    assert s["model_identifier"] == "m"


def test_concurrent_engines(store):
    engine, images = store
    db.add_message(engine, "s1-1", {"role": "user", "content": "one"}, images_dir=images)
    engine2 = db.get_engine(f"sqlite:///{images.parent / 'crow.db'}")
    db.add_message(engine2, "s1-1", {"role": "user", "content": "two"}, images_dir=images)
    assert len(db.load_messages(engine, "s1-1")) == 2


def test_prompt_lookup_idempotent(store):
    engine, _ = store
    a = db.lookup_or_create_prompt(engine, "tpl", "x")
    b = db.lookup_or_create_prompt(engine, "tpl", "x")
    assert a == b
    assert db.get_prompt(engine, a).template == "tpl"
