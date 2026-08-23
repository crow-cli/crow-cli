"""The v5 -> taskmaster migration (scripts/migrate_taskmaster.py) — synthetic v5 db.

Builds a real v5 database (fork_idx/forked_at on agents, fork_idx on
messages + FTS, but NO task tables and NO agents.mcp_servers — the exact
shape of the live pre-task db), migrates it into a fresh taskmaster file,
and verifies: the additive delta landed (tasks, task_deliveries,
agents.mcp_servers), agent_id/fork_idx/message-ids/created_at preserved
byte-for-byte, FTS rebuilt on the current extractor, and BOTH the memory
read path and the task-state functions working against the result. The
source must stay untouched.
"""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

import crow_cli.memory as cm

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_taskmaster.py"
_spec = importlib.util.spec_from_file_location("migrate_taskmaster", SCRIPT)
migrate_taskmaster = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_taskmaster)


# The live v5 schema: fork-aware agents/messages/FTS, no task system yet.
V5_DDL = """
CREATE TABLE prompts (
    id TEXT NOT NULL, name TEXT NOT NULL, template TEXT NOT NULL,
    created_at TEXT NOT NULL, PRIMARY KEY (id)
);
CREATE TABLE agents (
    agent_id TEXT NOT NULL, session_id TEXT NOT NULL, agent_idx INTEGER NOT NULL,
    fork_idx INTEGER NOT NULL DEFAULT 1, forked_at TEXT,
    cwd TEXT NOT NULL, prompt_id TEXT, prompt_args JSON,
    system_prompt TEXT NOT NULL, tool_definitions JSON NOT NULL,
    request_params JSON NOT NULL, model_identifier TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (agent_id)
);
CREATE TABLE messages (
    id INTEGER NOT NULL, agent_id TEXT NOT NULL, fork_idx INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL, data JSON NOT NULL, role TEXT NOT NULL,
    prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER,
    PRIMARY KEY (id)
);
CREATE VIRTUAL TABLE messages_fts USING fts5(
    agent_id UNINDEXED, role UNINDEXED, fork_idx UNINDEXED, text);
"""


def _seed_v5(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(V5_DDL)
    db.execute(
        "INSERT INTO prompts VALUES ('p1', 'crow-default', 'You are Crow.', "
        "'2026-01-01T00:00:00')"
    )
    # (agent_id, session_id, agent_idx, fork_idx, forked_at)
    agents = [
        ("sess-alpha-1-1", "sess-alpha", 1, 1, None),
        ("sess-alpha-2-1", "sess-alpha", 2, 1, None),  # compacted successor
        ("sess-alpha-1-2", "sess-alpha", 1, 2, 4),      # fork at message 4
        ("sess-beta-1-1", "sess-beta", 1, 1, None),
    ]
    for aid, sid, idx, fork, forked_at in agents:
        db.execute(
            "INSERT INTO agents VALUES (?, ?, ?, ?, ?, '/tmp', 'p1', '{}', 'sys', "
            "'[]', '{}', 'test-model', 'active', '2026-01-01T00:00:00')",
            (aid, sid, idx, fork, forked_at),
        )
    # (id, agent_id, fork_idx, role, text)
    messages = [
        (1, "sess-alpha-1-1", 1, "user", "remember QUARTZ-77 please"),
        (2, "sess-alpha-1-1", 1, "assistant", "I will remember QUARTZ-77."),
        (3, "sess-alpha-2-1", 1, "user", "second agent turn"),
        (4, "sess-alpha-2-1", 1, "assistant", "second agent answer"),
        (5, "sess-alpha-1-2", 2, "user", "forked branch VELVET-9 question"),
        (6, "sess-beta-1-1", 1, "user", "beta says hello"),
        (7, "sess-beta-1-1", 1, "tool", "tool output for beta"),
    ]
    for mid, aid, fork, role, text in messages:
        data = json.dumps({"role": role, "content": text})
        db.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL)",
            (mid, aid, fork, f"2026-01-0{mid}T00:00:00", data, role),
        )
        db.execute(
            "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
            "VALUES (?, ?, ?, ?, ?)",
            (mid, aid, role, fork, text),
        )
    db.commit()
    db.close()


@pytest.fixture
def v5_env(tmp_path):
    src = tmp_path / "live-v5.db"
    dst = tmp_path / "taskmaster.db"
    _seed_v5(src)
    return src, dst


def test_additive_delta_and_identity_preservation(v5_env):
    src, dst = v5_env
    src_sha = src.read_bytes()

    counts = migrate_taskmaster.migrate(src, dst)
    assert counts == {"prompts": 1, "agents": 4, "messages": 7}

    # source untouched (opened read-only)
    assert src.read_bytes() == src_sha

    db = sqlite3.connect(dst)
    # the additive delta landed
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "tasks" in tables and "task_deliveries" in tables
    agent_cols = {r[1] for r in db.execute("PRAGMA table_info(agents)")}
    assert "mcp_servers" in agent_cols

    # agent_id is IDENTITY (no rewriting in this migration)
    assert {r[0] for r in db.execute("SELECT agent_id FROM agents")} == {
        "sess-alpha-1-1", "sess-alpha-2-1", "sess-alpha-1-2", "sess-beta-1-1",
    }
    # fork_idx preserved, including the fork (>1) and its forked_at anchor
    assert db.execute(
        "SELECT fork_idx, forked_at FROM agents WHERE agent_id='sess-alpha-1-2'"
    ).fetchone() == (2, "4")
    assert db.execute(
        "SELECT DISTINCT fork_idx FROM messages ORDER BY fork_idx"
    ).fetchall() == [(1,), (2,)]
    # migrated rows predate the column -> mcp_servers NULL (never supplied)
    assert db.execute(
        "SELECT COUNT(*) FROM agents WHERE mcp_servers IS NULL"
    ).fetchone()[0] == 4

    # message ids + created_at preserved
    rows = db.execute(
        "SELECT id, agent_id, created_at FROM messages ORDER BY id"
    ).fetchall()
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5, 6, 7]
    assert rows[0] == (1, "sess-alpha-1-1", "2026-01-01T00:00:00")
    assert rows[4] == (5, "sess-alpha-1-2", "2026-01-05T00:00:00")
    # FTS rebuilt completely
    assert db.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0] == 7
    db.close()


def test_migrated_db_readable_by_memory_layer(v5_env):
    src, dst = v5_env
    migrate_taskmaster.migrate(src, dst)

    uri = f"sqlite:///{dst}"
    cm.create_database(uri)  # idempotent on taskmaster schema
    engine = cm.get_engine(uri)

    sessions = cm.list_sessions(engine)
    assert {s["session_id"] for s in sessions} == {"sess-alpha", "sess-beta"}

    # trunk HEAD of sess-alpha is agent_idx 2
    msgs = cm.load_agent_messages(engine, cm.get_agent(engine, "sess-alpha-2-1"))
    assert [m["content"] for m in msgs] == ["second agent turn", "second agent answer"]

    # search over the rebuilt FTS finds migrated content (trunk + fork)
    hits = cm.search_messages(engine, "QUARTZ-77")
    assert hits and hits[0]["agent_id"] == "sess-alpha-1-1"
    fork_hits = cm.search_messages(engine, "VELVET-9")
    assert fork_hits and fork_hits[0]["agent_id"] == "sess-alpha-1-2"
    engine.dispose()


def test_task_system_runs_against_migrated_db(v5_env):
    """The whole point of the migration: the task tables are usable on top of
    the pre-existing v5 data — launch, finish, deliver, claim, and the
    mcp_servers round trip all work against the migrated file."""
    src, dst = v5_env
    migrate_taskmaster.migrate(src, dst)

    engine = cm.get_engine(f"sqlite:///{dst}")
    owner = "sess-alpha"  # a wire id that already exists in the migrated data

    # mcp_servers round trip on a MIGRATED agent row (pre-task provisioning)
    cm.set_agent_mcp_servers(engine, "sess-alpha-2-1", [{"name": "x", "command": "y"}])
    assert cm.get_session_mcp_servers(engine, owner) == [{"name": "x", "command": "y"}]

    # task lifecycle lands in the NEW tables
    cm.launch_task(engine, task_id="task-1", owner_session=owner, prompt="go",
                   priority="high")
    assert cm.get_task(engine, "task-1").status == "running"
    assert [t.task_id for t in cm.running_tasks(engine, owner)] == ["task-1"]

    cm.finish_task(engine, "task-1", result="done", status="completed",
                   content="[task-1: done]")
    deliveries = cm.pending_deliveries(engine, owner)
    assert len(deliveries) == 1 and deliveries[0].priority == "high"

    claimed = cm.claim_deliveries(engine, owner)
    assert [c["task_id"] for c in claimed] == ["task-1"]
    assert cm.pending_deliveries(engine, owner) == []  # exactly-once
    engine.dispose()


def test_migrate_refuses_already_taskmaster_source(v5_env):
    src, dst = v5_env
    migrate_taskmaster.migrate(src, dst)
    with pytest.raises(SystemExit, match="already taskmaster-schema"):
        migrate_taskmaster.migrate(dst, v5_env[0].parent / "another.db")


def test_migrate_refuses_v4_source(tmp_path):
    """A v4 db (no fork_idx) must be sent to migrate_v5.py first."""
    src = tmp_path / "v4.db"
    db = sqlite3.connect(src)
    db.executescript(
        "CREATE TABLE agents (agent_id TEXT PRIMARY KEY, session_id TEXT);\n"
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, agent_id TEXT);"
    )
    db.commit()
    db.close()
    with pytest.raises(SystemExit, match="schema v4"):
        migrate_taskmaster.migrate(src, tmp_path / "out.db")


def test_migrate_refuses_non_crow_db(tmp_path):
    src = tmp_path / "empty.db"
    sqlite3.connect(src).close()
    with pytest.raises(SystemExit, match="not a crow database"):
        migrate_taskmaster.migrate(src, tmp_path / "out.db")
