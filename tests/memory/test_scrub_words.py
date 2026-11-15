"""scripts/scrub_words.py — rewrite words out of stored message history.

Synthetic crow.db (v6 shape: agents + messages + messages_fts), then the
script's real main() against it. What has to hold: only the named roles are
touched, case survives, longest key wins, base64 payloads are inviolate, the
rest of the JSON text is byte-identical, messages_fts is re-indexed so the
old word stops being searchable, --dry-run writes nothing, and the words
never reach stdout.
"""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "scrub_words.py"
_spec = importlib.util.spec_from_file_location("scrub_words", SCRIPT)
scrub_words = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scrub_words)


DDL = """
CREATE TABLE agents (
    agent_id TEXT NOT NULL, session_id TEXT NOT NULL, agent_idx INTEGER NOT NULL,
    fork_idx INTEGER NOT NULL, forked_at TEXT, cwd TEXT NOT NULL, prompt_id TEXT,
    prompt_args JSON, system_prompt TEXT NOT NULL, tool_definitions JSON NOT NULL,
    mcp_servers JSON, request_params JSON NOT NULL, model_identifier TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (agent_id)
);
CREATE TABLE messages (
    id INTEGER NOT NULL, agent_id TEXT NOT NULL, fork_idx INTEGER NOT NULL,
    created_at TEXT NOT NULL, data JSON NOT NULL, role TEXT NOT NULL,
    prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER,
    PRIMARY KEY (id)
);
CREATE VIRTUAL TABLE messages_fts USING fts5(
    agent_id UNINDEXED, role UNINDEXED, fork_idx UNINDEXED, text
);
"""


def _seed(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(DDL)
    for aid, sid in (("sess-a-1-1", "sess-a"), ("sess-b-1-1", "sess-b")):
        db.execute(
            "INSERT INTO agents VALUES (?, ?, 1, 1, NULL, '/tmp', NULL, '{}', "
            "'sys prompt', '[]', NULL, '{}', 'test-model', 'active', "
            "'2026-01-01T00:00:00')",
            (aid, sid),
        )
    rows = [
        # (id, agent_id, role, data)
        (1, "sess-a-1-1", "user", {"role": "user", "content": "you punk, PUNK, Punk"}),
        (2, "sess-a-1-1", "assistant", {"role": "assistant", "content": "sorry punk"}),
        (3, "sess-a-1-1", "tool", {"role": "tool", "tool_call_id": "c1", "content": "punk output"}),
        (4, "sess-b-1-1", "user", {"role": "user", "content": "other session punk"}),
        (
            5,
            "sess-a-1-1",
            "user",
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look at this punk"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORpunkAAAA"}},
                ],
            },
        ),
        # non-ASCII + an escaped codepoint: the row must survive verbatim
        (6, "sess-a-1-1", "user", {"role": "user", "content": "punk — ✅ done"}),
    ]
    for mid, aid, role, data in rows:
        raw = json.dumps(data, ensure_ascii=False)
        db.execute(
            "INSERT INTO messages VALUES (?, ?, 1, '2026-01-01T00:00:00', ?, ?, NULL, NULL, NULL)",
            (mid, aid, raw, role),
        )
        db.execute(
            "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
            "VALUES (?, ?, ?, 1, ?)",
            (mid, aid, role, scrub_words.message_text(data)),
        )
    db.commit()
    db.close()


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / "crow.db"
    _seed(path)
    return path


def _data(db: Path, mid: int) -> str:
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT data FROM messages WHERE id = ?", (mid,)).fetchone()[0]
    finally:
        conn.close()


def test_dry_run_reports_and_writes_nothing(db: Path, capsys):
    scrub_words.main(["--db", str(db), "--dry-run"], {"punk": "chump"})
    out = capsys.readouterr().out
    assert "Would modify 4 row(s)" in out  # ids 1, 4, 5, 6
    assert "Run without --dry-run to apply." in out
    assert _data(db, 1) == '{"role": "user", "content": "you punk, PUNK, Punk"}'
    assert "chump" not in _data(db, 1)
    assert "punk" not in out  # masked


def test_user_role_only(db: Path, capsys):
    scrub_words.main(["--db", str(db)], {"punk": "chump"})
    capsys.readouterr()
    assert json.loads(_data(db, 1))["content"] == "you chump, CHUMP, Chump"
    assert json.loads(_data(db, 2))["content"] == "sorry punk"  # assistant untouched
    assert json.loads(_data(db, 3))["content"] == "punk output"  # tool untouched
    assert json.loads(_data(db, 4))["content"] == "other session chump"  # all sessions


def test_base64_and_unicode_survive(db: Path, capsys):
    scrub_words.main(["--db", str(db)], {"punk": "chump"})
    capsys.readouterr()
    blocks = json.loads(_data(db, 5))["content"]
    assert blocks[0]["text"] == "look at this chump"
    assert blocks[1]["image_url"]["url"] == "data:image/png;base64,iVBORpunkAAAA"
    assert json.loads(_data(db, 6))["content"] == "chump — ✅ done"
    assert "—" in _data(db, 6) and "✅" in _data(db, 6)  # not re-escaped


def test_longest_key_wins(db: Path, capsys):
    scrub_words.main(["--db", str(db)], {"ass": "butt", "asshole": "jerk"})
    capsys.readouterr()
    assert "punk" in _data(db, 1)  # nothing matched these keys
    conn = sqlite3.connect(db)
    conn.execute("UPDATE messages SET data = ? WHERE id = 1",
                 ('{"role": "user", "content": "ass and asshole"}',))
    conn.commit()
    conn.close()
    scrub_words.main(["--db", str(db)], {"ass": "butt", "asshole": "jerk"})
    capsys.readouterr()
    assert json.loads(_data(db, 1))["content"] == "butt and jerk"


def test_session_and_roles_flags(db: Path, capsys):
    scrub_words.main(["--db", str(db), "--session", "sess-a"], {"punk": "chump"})
    capsys.readouterr()
    assert "chump" in _data(db, 1)
    assert "punk" in _data(db, 4)  # other session left alone

    scrub_words.main(["--db", str(db), "--roles", "user,assistant,tool"], {"punk": "chump"})
    capsys.readouterr()
    assert json.loads(_data(db, 2))["content"] == "sorry chump"
    assert json.loads(_data(db, 3))["content"] == "chump output"
    assert json.loads(_data(db, 4))["content"] == "other session chump"


def test_fts_reindexed(db: Path, capsys):
    scrub_words.main(["--db", str(db)], {"punk": "chump"})
    capsys.readouterr()
    conn = sqlite3.connect(db)
    try:
        text = conn.execute("SELECT text FROM messages_fts WHERE rowid = 1").fetchone()[0]
        assert text == "you chump, CHUMP, Chump"
        assert conn.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH '\"punk\"'"
        ).fetchall() == [(2,), (3,)]  # only the rows we did not scrub
        assert conn.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH '\"chump\"'"
        ).fetchall() == [(1,), (4,), (5,), (6,)]  # every scrubbed user row
    finally:
        conn.close()


def test_empty_replacements_exits(db: Path):
    with pytest.raises(SystemExit):
        scrub_words.main(["--db", str(db)], {})
