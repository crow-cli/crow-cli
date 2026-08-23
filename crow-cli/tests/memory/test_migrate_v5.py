"""The ONE v4->v5 migration (scripts/migrate_v5.py) — synthetic v4 db.

Builds a real v4 database (the exact DDL of the pre-migration crow.db),
migrates it into a fresh v5 file, and verifies: three-part ids everywhere,
message ids + created_at preserved, FTS rebuilt on the current extractor,
and the memory read path (list_sessions / load_agent_messages /
search_messages) working against the result. The source must stay untouched.
"""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

import crow_cli.memory as cm

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_v5.py"
_spec = importlib.util.spec_from_file_location("migrate_v5", SCRIPT)
migrate_v5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_v5)


V4_DDL = """
CREATE TABLE prompts (
    id TEXT NOT NULL, name TEXT NOT NULL, template TEXT NOT NULL,
    created_at TEXT NOT NULL, PRIMARY KEY (id)
);
CREATE TABLE agents (
    agent_id TEXT NOT NULL, session_id TEXT NOT NULL, agent_idx INTEGER NOT NULL,
    cwd TEXT NOT NULL, prompt_id TEXT, prompt_args JSON,
    system_prompt TEXT NOT NULL, tool_definitions JSON NOT NULL,
    request_params JSON NOT NULL, model_identifier TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (agent_id)
);
CREATE TABLE messages (
    id INTEGER NOT NULL, agent_id TEXT NOT NULL, created_at TEXT NOT NULL,
    data JSON NOT NULL, role TEXT NOT NULL, prompt_tokens INTEGER,
    completion_tokens INTEGER, total_tokens INTEGER, PRIMARY KEY (id)
);
CREATE VIRTUAL TABLE messages_fts USING fts5(agent_id UNINDEXED, role UNINDEXED, text);
"""


def _seed_v4(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(V4_DDL)
    db.execute(
        "INSERT INTO prompts VALUES ('p1', 'crow-default', 'You are Crow.', '2026-01-01T00:00:00')"
    )
    agents = [
        ("sess-alpha-1", "sess-alpha", 1),
        ("sess-alpha-2", "sess-alpha", 2),  # compacted successor
        ("sess-beta-1", "sess-beta", 1),
    ]
    for aid, sid, idx in agents:
        db.execute(
            "INSERT INTO agents VALUES (?, ?, ?, '/tmp', 'p1', '{}', 'sys', '[]', "
            "'{}', 'test-model', 'active', '2026-01-01T00:00:00')",
            (aid, sid, idx),
        )
    messages = [
        (1, "sess-alpha-1", "user", "remember QUARTZ-77 please"),
        (2, "sess-alpha-1", "assistant", "I will remember QUARTZ-77."),
        (3, "sess-alpha-2", "user", "second agent turn"),
        (4, "sess-alpha-2", "assistant", "second agent answer"),
        (5, "sess-beta-1", "user", "beta says hello"),
        (6, "sess-beta-1", "tool", "tool output for beta"),
    ]
    for mid, aid, role, text in messages:
        data = json.dumps({"role": role, "content": text})
        db.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)",
            (mid, aid, f"2026-01-0{mid}T00:00:00", data, role),
        )
        db.execute(
            "INSERT INTO messages_fts(rowid, agent_id, role, text) VALUES (?, ?, ?, ?)",
            (mid, aid, role, text),
        )
    db.commit()
    db.close()


@pytest.fixture
def v4_env(tmp_path):
    src = tmp_path / "old.db"
    dst = tmp_path / "new.db"
    _seed_v4(src)
    return src, dst


def test_migrate_counts_ids_and_timestamps(v4_env):
    src, dst = v4_env
    src_sha = src.read_bytes()

    counts = migrate_v5.migrate(src, dst)
    assert counts == {"prompts": 1, "agents": 3, "messages": 6}

    # source untouched (byte-identical — it was opened read-only)
    assert src.read_bytes() == src_sha

    db = sqlite3.connect(dst)
    # three-part ids everywhere, trunk fork
    assert {r[0] for r in db.execute("select agent_id from agents")} == {
        "sess-alpha-1-1",
        "sess-alpha-2-1",
        "sess-beta-1-1",
    }
    assert db.execute("select distinct fork_idx from agents").fetchall() == [(1,)]
    assert db.execute("select distinct fork_idx from messages").fetchall() == [(1,)]
    assert db.execute("select count(*) from agents where forked_at is null").fetchone()[0] == 3
    # message ids + created_at preserved, agent_id = v4 + '-1'
    rows = db.execute(
        "select id, agent_id, created_at from messages order by id"
    ).fetchall()
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5, 6]
    assert rows[0] == (1, "sess-alpha-1-1", "2026-01-01T00:00:00")
    assert rows[5] == (6, "sess-beta-1-1", "2026-01-06T00:00:00")
    # FTS rebuilt completely
    assert db.execute("select count(*) from messages_fts").fetchone()[0] == 6
    db.close()


def test_migrated_db_is_v5_and_readable_by_memory_layer(v4_env):
    src, dst = v4_env
    migrate_v5.migrate(src, dst)

    uri = f"sqlite:///{dst}"
    # create_database is idempotent on v5 (and _require_v5 passes)
    cm.create_database(uri)
    engine = cm.get_engine(uri)

    sessions = cm.list_sessions(engine)
    ids = {s["session_id"] for s in sessions}
    assert ids == {"sess-alpha", "sess-beta"}

    # trunk view: sess-alpha's CURRENT agent (idx 2) sees its own rows
    msgs = cm.load_agent_messages(engine, cm.get_agent(engine, "sess-alpha-2-1"))
    assert [m["content"] for m in msgs] == ["second agent turn", "second agent answer"]

    # search over the rebuilt FTS finds migrated content
    hits = cm.search_messages(engine, "QUARTZ-77")
    assert hits and hits[0]["agent_id"] == "sess-alpha-1-1"
    engine.dispose()


def test_migrate_refuses_v5_source(v4_env):
    src, dst = v4_env
    migrate_v5.migrate(src, dst)
    with pytest.raises(SystemExit, match="already schema v5"):
        migrate_v5.migrate(dst, v4_env[0].parent / "another.db")


def test_migrate_refuses_non_crow_db(tmp_path):
    src = tmp_path / "empty.db"
    sqlite3.connect(src).close()
    with pytest.raises(SystemExit, match="not a crow database"):
        migrate_v5.migrate(src, tmp_path / "out.db")
