#!/usr/bin/env python3
"""
Database layer integrity test — isolates SQLAlchemy JSON + Session.load().

Tests:
  #3: Does SQLite JSON column lose bytes? (compare SQLAlchemy write vs raw sqlite3 read)
  #4: Does Session.load() reconstruct messages faithfully? (compare in-memory vs loaded)

Run:
  cd crow-cli/sandbox/async-react && uv --project . run db_integrity_test.py
"""

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, create_engine
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Session as SQLAlchemySession
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TestMessage(Base):
    __tablename__ = "test_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, nullable=False, index=True)
    data = Column(JSON, nullable=False)
    role = Column(Text, nullable=False)


def sha256(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def char_count(obj) -> int:
    """Count total characters in a message's content fields."""
    total = 0
    for key in ("content", "reasoning_content"):
        val = obj.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            total += sum(
                len(b.get("text", "")) if isinstance(b, dict) else len(str(b))
                for b in val
            )
        else:
            total += len(str(val))
    return total


# High-entropy test messages covering all shapes
TEST_MESSAGES = [
    # System message
    {
        "role": "system",
        "content": "You are a test assistant. 🔥 Special chars: ñ ü 中文 emoji 🤖",
    },
    # User message
    {
        "role": "user",
        "content": "Write a 200-word story about a robot.",
    },
    # Assistant with thinking + content
    {
        "role": "assistant",
        "content": "Once upon a time, a robot named unit-7 discovered it could paint.\n"
        * 50,
        "reasoning_content": "The user wants a story. I'll write something creative.\n"
        * 30,
    },
    # Assistant with tool calls
    {
        "role": "assistant",
        "content": "I'll read that file for you.",
        "tool_calls": [
            {
                "id": "call_abc123def456",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path": "/tmp/test.txt", "encoding": "utf-8"}',
                },
            },
            {
                "id": "call_ghi789jkl012",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": '{"path": "/tmp/out.txt", "content": "hello world\\n"}',
                },
            },
        ],
    },
    # Tool result
    {
        "role": "tool",
        "tool_call_id": "call_abc123def456",
        "content": "File contents: " + "x" * 5000,
    },
    # Assistant with empty content but reasoning
    {
        "role": "assistant",
        "reasoning_content": "Hmm, let me think about this carefully.\n" * 20,
    },
    # Edge cases
    {
        "role": "assistant",
        "content": "",  # empty string
    },
    {
        "role": "assistant",
        "content": "   ",  # whitespace only
    },
    {
        "role": "assistant",
        "content": "unicode: "
        + "".join(chr(i) for i in range(0x2600, 0x2700)),  # misc symbols
    },
]

SESSION_ID = "integrity-db-test"


def test_sqlalchemy_json_vs_raw_sqlite(db_uri: str, tmpdir: Path):
    """
    Test #3: Write via SQLAlchemy, read back via raw sqlite3.
    If they differ, SQLAlchemy's JSON column is losing bytes.
    """
    print("=" * 60)
    print("TEST #3: SQLAlchemy JSON vs raw sqlite3")
    print("=" * 60)

    # Create tables
    engine = create_engine(db_uri)
    Base.metadata.create_all(engine)

    # Write via SQLAlchemy
    sa_session = SQLAlchemySession(engine)
    for msg in TEST_MESSAGES:
        db_msg = TestMessage(
            session_id=SESSION_ID,
            data=msg,
            role=msg.get("role", "unknown"),
        )
        sa_session.add(db_msg)
    sa_session.commit()

    # Read back via SQLAlchemy
    sa_rows = (
        sa_session.query(TestMessage)
        .filter_by(session_id=SESSION_ID)
        .order_by(TestMessage.id)
        .all()
    )
    sa_messages = [row.data for row in sa_rows]
    sa_session.close()

    # Read raw via sqlite3 (bypass SQLAlchemy entirely)
    db_path = db_uri.replace("sqlite:///", "")
    raw_conn = sqlite3.connect(db_path)
    raw_cursor = raw_conn.cursor()
    raw_cursor.execute(
        "SELECT data FROM test_messages WHERE session_id = ? ORDER BY id", (SESSION_ID,)
    )
    raw_messages = [json.loads(row[0]) for row in raw_cursor.fetchall()]
    raw_conn.close()

    # Compare SQLAlchemy vs raw sqlite3
    issues = []
    for i, (sa_msg, raw_msg) in enumerate(zip(sa_messages, raw_messages)):
        sa_hash = sha256(sa_msg)
        raw_hash = sha256(raw_msg)
        if sa_hash != raw_hash:
            issues.append(
                f"  [{i:02d}] role={sa_msg.get('role')} SA={sa_hash} vs RAW={raw_hash}"
            )

    if issues:
        print(f"✗ SQLAlchemy JSON LOST BYTES ({len(issues)} differences):")
        for issue in issues:
            print(issue)
        return False
    else:
        print(f"✓ SQLAlchemy JSON == raw sqlite3 ({len(sa_messages)} messages)")
        return True


def test_session_load_roundtrip(db_uri: str):
    """
    Test #4: Simulate Session.load() — does deserialization lose bytes?
    We mimic exactly what Session.load() does: query Message, extract .data column.
    """
    print()
    print("=" * 60)
    print("TEST #4: Session.load() roundtrip fidelity")
    print("=" * 60)

    engine = create_engine(db_uri)

    # Simulate Session.load() — just query and extract .data
    sa_session = SQLAlchemySession(engine)
    rows = (
        sa_session.query(TestMessage)
        .filter_by(session_id=SESSION_ID)
        .order_by(TestMessage.id)
        .all()
    )
    loaded_messages = [row.data for row in rows]
    sa_session.close()

    # Compare in-memory originals vs loaded
    issues = []
    for i, (orig, loaded) in enumerate(zip(TEST_MESSAGES, loaded_messages)):
        orig_hash = sha256(orig)
        loaded_hash = sha256(loaded)
        orig_chars = char_count(orig)
        loaded_chars = char_count(loaded)

        if orig_hash != loaded_hash:
            detail = f"  [{i:02d}] role={orig.get('role')}: hash mismatch"
            if orig_chars != loaded_chars:
                detail += f" chars: orig={orig_chars} loaded={loaded_chars} (delta={loaded_chars - orig_chars})"
            else:
                # Same char count but different hash — structural difference
                detail += f" (same chars, structural diff)"

                # Find which field differs
                for key in set(list(orig.keys()) + list(loaded.keys())):
                    ov = orig.get(key)
                    lv = loaded.get(key)
                    if ov != lv:
                        detail += f"\n       ['{key}'] differs"
                        if isinstance(ov, str) and isinstance(lv, str):
                            detail += f" orig_len={len(ov)} loaded_len={len(lv)}"

            issues.append(detail)

    if issues:
        print(f"✗ Session.load() LOST DATA ({len(issues)} differences):")
        for issue in issues:
            print(issue)
        return False
    else:
        print(f"✓ Session.load() roundtrip perfect ({len(TEST_MESSAGES)} messages)")
        return True


def test_json_dumps_loads_roundtrip():
    """
    Baseline: Does json.dumps → json.loads lose anything?
    (It shouldn't — this is a sanity check.)
    """
    print()
    print("=" * 60)
    print("TEST #0: json.dumps/loads baseline")
    print("=" * 60)

    issues = []
    for i, msg in enumerate(TEST_MESSAGES):
        dumped = json.dumps(msg, ensure_ascii=False)
        loaded = json.loads(dumped)
        if msg != loaded:
            issues.append(
                f"  [{i:02d}] json roundtrip failed for role={msg.get('role')}"
            )

    if issues:
        print(f"✗ json.dumps/loads baseline FAILED:")
        for issue in issues:
            print(issue)
        return False
    else:
        print(f"✓ json.dumps/loads perfect ({len(TEST_MESSAGES)} messages)")
        return True


def main():
    tmpdir = Path(tempfile.mkdtemp(prefix="crow-db-test-"))
    db_path = tmpdir / "test.db"
    db_uri = f"sqlite:///{db_path}"

    print(f"DB: {db_uri}")
    print()

    all_pass = True

    # Baseline
    if not test_json_dumps_loads_roundtrip():
        all_pass = False
        print("\n  ⚠ Python JSON is broken — this should never happen")

    # Test #3: SQLAlchemy vs raw sqlite3
    if not test_sqlalchemy_json_vs_raw_sqlite(db_uri, tmpdir):
        all_pass = False

    # Test #4: Session.load() roundtrip
    if not test_session_load_roundtrip(db_uri):
        all_pass = False

    print()
    print("=" * 60)
    if all_pass:
        print("ALL TESTS PASSED — DB layer is lossless")
        print("The token leak is NOT in SQLite, SQLAlchemy JSON, or Session.load()")
    else:
        print("TESTS FAILED — found data loss in DB layer")
    print("=" * 60)

    # Cleanup
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
