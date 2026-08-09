#!/usr/bin/env python3
"""
Crow DB Inspector - View sessions and events from ~/.crow/crow.db

Usage:
    python crow_inspect.py                    # Summary stats
    python crow_inspect.py sessions           # List all sessions
    python crow_inspect.py session <id>       # View session details
    python crow_inspect.py events <id>        # View events for a session
    python crow_inspect.py replay <id>        # Replay conversation
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


DB_PATH = Path.home() / ".crow" / "crow.db"


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def summary():
    """Show summary stats."""
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 60)
    print("CROW DB SUMMARY")
    print("=" * 60)
    print(f"DB Path: {DB_PATH}")
    print()

    # Table counts
    cursor.execute("SELECT COUNT(*) FROM prompts")
    prompts = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sessions")
    sessions = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM events")
    events = cursor.fetchone()[0]

    print(f"Prompts:  {prompts}")
    print(f"Sessions: {sessions}")
    print(f"Events:   {events}")
    print()

    # List prompts
    print("PROMPTS:")
    cursor.execute("SELECT id, name, created_at FROM prompts")
    for row in cursor.fetchall():
        print(f"  - {row[0]}: {row[1]} ({row[2]})")
    print()

    # Recent sessions
    print("RECENT SESSIONS (last 5):")
    cursor.execute("""
        SELECT s.session_id, s.model_identifier, s.created_at, COUNT(e.id) as event_count
        FROM sessions s
        LEFT JOIN events e ON s.session_id = e.session_id
        GROUP BY s.session_id
        ORDER BY s.created_at DESC
        LIMIT 5
    """)
    for row in cursor.fetchall():
        sid = row[0][:20] + "..."
        print(f"  - {sid} | {row[1]} | {row[2]} | {row[3]} events")

    conn.close()


def list_sessions():
    """List all sessions."""
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 80)
    print("ALL SESSIONS")
    print("=" * 80)

    cursor.execute("""
        SELECT s.session_id, s.model_identifier, s.created_at, COUNT(e.id) as event_count
        FROM sessions s
        LEFT JOIN events e ON s.session_id = e.session_id
        GROUP BY s.session_id
        ORDER BY s.created_at DESC
    """)

    for row in cursor.fetchall():
        sid = row[0]
        print(f"{sid}")
        print(f"  Model: {row[1]} | Created: {row[2]} | Events: {row[3]}")

    conn.close()


def view_session(session_id: str):
    """View session details."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT session_id, prompt_id, model_identifier, request_params, created_at
        FROM sessions
        WHERE session_id = ?
    """, (session_id,))

    row = cursor.fetchone()
    if not row:
        print(f"Session not found: {session_id}")
        return

    print("=" * 60)
    print("SESSION DETAILS")
    print("=" * 60)
    print(f"ID:       {row[0]}")
    print(f"Prompt:   {row[1]}")
    print(f"Model:    {row[2]}")
    print(f"Created:  {row[4]}")
    print(f"Params:   {row[3]}")

    # Event summary
    cursor.execute("""
        SELECT role, COUNT(*)
        FROM events
        WHERE session_id = ?
        GROUP BY role
    """, (session_id,))

    print()
    print("EVENTS BY ROLE:")
    for row in cursor.fetchall():
        print(f"  - {row[0]}: {row[1]}")

    conn.close()


def view_events(session_id: str, limit: int = 50):
    """View events for a session."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT conv_index, role, content, tool_call_name, timestamp
        FROM events
        WHERE session_id = ?
        ORDER BY conv_index
        LIMIT ?
    """, (session_id, limit))

    print("=" * 80)
    print(f"EVENTS FOR {session_id[:30]}...")
    print("=" * 80)

    for row in cursor.fetchall():
        conv_idx, role, content, tool_name, timestamp = row
        content_preview = (content[:60] + "...") if content and len(content) > 60 else content
        tool_info = f" [{tool_name}]" if tool_name else ""
        print(f"{conv_idx:3d} | {role:12s} | {content_preview}{tool_info}")

    conn.close()


def replay_session(session_id: str):
    """Replay conversation from a session."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT role, content, reasoning_content
        FROM events
        WHERE session_id = ?
        ORDER BY conv_index
    """, (session_id,))

    print("=" * 80)
    print(f"REPLAY: {session_id[:30]}...")
    print("=" * 80)
    print()

    for row in cursor.fetchall():
        role, content, reasoning = row

        if role == "user":
            print(f"USER: {content}")
            print()
        elif role == "assistant":
            if reasoning:
                print(f"[thinking: {reasoning[:100]}...]")
            if content:
                print(f"ASSISTANT: {content[:200]}...")
            print()
        elif role == "tool":
            print(f"[tool result: {content[:100] if content else 'none'}...]")
            print()

    conn.close()


def main():
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        sys.exit(1)

    if len(sys.argv) == 1:
        summary()
    elif sys.argv[1] == "sessions":
        list_sessions()
    elif sys.argv[1] == "session" and len(sys.argv) > 2:
        view_session(sys.argv[2])
    elif sys.argv[1] == "events" and len(sys.argv) > 2:
        view_events(sys.argv[2])
    elif sys.argv[1] == "replay" and len(sys.argv) > 2:
        replay_session(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
