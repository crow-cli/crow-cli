"""migrate_v6 — v5 + legacy tui.db -> v6 (session_tabs consolidated).

Builds a faithful v5 source (all v5 tables, NO session_tabs), a source that
already grew the table (the live-db case), and a legacy tui.db with
CURRENT_TIMESTAMP-style stamps; checks copy + import + dedup + conversion.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from crow_cli.memory.models import Base

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import migrate_v6  # noqa: E402

V5_TABLES = [t for t in Base.metadata.sorted_tables if t.name != "session_tabs"]


def make_v5(path: Path, with_tabs: bool = False) -> None:
    uri = f"sqlite:///{path}"
    tables = Base.metadata.sorted_tables if with_tabs else V5_TABLES
    Base.metadata.create_all(create_engine(uri), tables=tables)
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO agents(agent_id, session_id, agent_idx, fork_idx, cwd, "
        "system_prompt, tool_definitions, request_params, model_identifier, "
        "status, created_at) "
        "VALUES ('s1-1-1', 's1', 1, 1, '/tmp', '', '[]', '{}', 'm', 'active', '2026-08-01T10:00:00+00:00')"
    )
    db.execute(
        "INSERT INTO messages(agent_id, fork_idx, created_at, data, role) "
        "VALUES ('s1-1-1', 1, '2026-08-01T10:00:00+00:00', ?, 'user')",
        (json.dumps({"role": "user", "content": "hello world"}),),
    )
    if with_tabs:
        db.execute(
            "INSERT INTO session_tabs(agent, agent_identity, agent_session_id, "
            "title, protocol, prompt_count, created_at, last_used, meta_json) "
            "VALUES ('Crow', 'crowai.dev', 's1', 's1', 'acp', 0, '2026-08-01T10:00:00+00:00', '2026-08-01T10:00:00+00:00', '{}')"
        )
    db.commit()
    db.close()


def make_tui_db(path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "agent TEXT NOT NULL, agent_identity TEXT NOT NULL, "
        "agent_session_id TEXT NOT NULL, title TEXT NOT NULL, "
        "protocol TEXT NOT NULL, prompt_count INTEGER DEFAULT 0, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
        "last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
        "meta_json TEXT DEFAULT '{}')"
    )
    db.execute(
        "INSERT INTO sessions(agent, agent_identity, agent_session_id, title, "
        "protocol, created_at, last_used) VALUES "
        "('Crow', 'crowai.dev', 's1', 's1', 'acp', '2026-08-01 10:00:00', '2026-08-01 11:00:00'), "
        "('Crow', 'crowai.dev', 's2', 's2', 'acp', '2026-08-02 10:00:00', '2026-08-02 11:00:00')"
    )
    db.commit()
    db.close()


def test_v5_plus_tui_import(tmp_path):
    src = tmp_path / "crow.db"
    make_v5(src)
    tui = tmp_path / "tui.db"
    make_tui_db(tui)
    dst = tmp_path / "crow-v6.db"

    counts = migrate_v6.migrate(src, dst, tui)
    assert counts["messages"] == 1
    assert counts["tabs_copied"] == 0
    assert counts["tabs_imported"] == 2

    db = sqlite3.connect(dst)
    row = db.execute(
        "SELECT title, last_used FROM session_tabs WHERE agent_session_id = 's2'"
    ).fetchone()
    assert row[0] == "s2"
    assert "T" in row[1] and "+00:00" in row[1]
    # FTS rebuilt and searchable
    assert db.execute(
        "SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH 'hello'"
    ).fetchone()[0] == 1
    db.close()


def test_existing_tabs_copied_and_deduped(tmp_path):
    src = tmp_path / "crow.db"
    make_v5(src, with_tabs=True)
    tui = tmp_path / "tui.db"
    make_tui_db(tui)  # s1 already a tab in src; only s2 imports
    dst = tmp_path / "crow-v6.db"

    counts = migrate_v6.migrate(src, dst, tui)
    assert counts["tabs_copied"] == 1
    assert counts["tabs_imported"] == 1

    db = sqlite3.connect(dst)
    assert db.execute("SELECT COUNT(*) FROM session_tabs").fetchone()[0] == 2
    db.close()


def test_v4_source_rejected(tmp_path):
    src = tmp_path / "v4.db"
    sqlite3.connect(src).execute("CREATE TABLE agents (agent_id TEXT)")
    with pytest.raises(SystemExit):
        migrate_v6.migrate(src, tmp_path / "out.db", None)
