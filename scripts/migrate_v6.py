"""The v5 -> v6 schema migration.

v6 = v5 + session_tabs (TUI tab state consolidated into the shared store),
populated from the source db (if it already has the table) plus the legacy
TUI sqlite (~/.local/state/crow/tui.db), deduped on agent_session_id.

Non-destructive by construction: the source is only ever read; the dest is
a fresh file. Cutover is a db_uri swap in ~/.agents/crow/config.yaml for
dry runs, then your own backup + rename for real.

Usage:
  uv --project crow-cli run python scripts/migrate_v6.py SRC.db DST.db [--tui-db PATH] [--force]
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from crow_cli.memory import create_database  # noqa: E402
from crow_cli.memory.messages import message_text  # noqa: E402

DEFAULT_TUI_DB = Path("~/.local/state/crow/tui.db").expanduser()

TAB_COLS = (
    "agent, agent_identity, agent_session_id, title, protocol, "
    "prompt_count, created_at, last_used, meta_json"
)


def _table_cols(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _to_iso(ts: str) -> str:
    """tui.db used CURRENT_TIMESTAMP ('YYYY-MM-DD HH:MM:SS', naive UTC)."""
    if "T" in ts:
        return ts
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def migrate(src_path: Path, dst_path: Path, tui_path: Path | None) -> dict:
    src = sqlite3.connect(src_path)
    if "fork_idx" not in _table_cols(src, "agents"):
        sys.exit(f"error: {src_path} is not schema v5 — run migrate_v5.py first")

    create_database(f"sqlite:///{dst_path}")
    dst = sqlite3.connect(dst_path)

    prompts = src.execute("SELECT id, name, template, created_at FROM prompts").fetchall()
    agents = src.execute(
        "SELECT agent_id, session_id, agent_idx, fork_idx, forked_at, cwd, "
        "prompt_id, prompt_args, system_prompt, tool_definitions, mcp_servers, "
        "request_params, model_identifier, status, created_at FROM agents"
    ).fetchall()
    messages = src.execute(
        "SELECT id, agent_id, fork_idx, created_at, data, role, prompt_tokens, "
        "completion_tokens, total_tokens FROM messages ORDER BY id"
    ).fetchall()

    dst.execute("BEGIN")
    dst.executemany(
        "INSERT INTO prompts(id, name, template, created_at) VALUES (?, ?, ?, ?)",
        prompts,
    )
    dst.executemany(
        "INSERT INTO agents(agent_id, session_id, agent_idx, fork_idx, forked_at, "
        "cwd, prompt_id, prompt_args, system_prompt, tool_definitions, mcp_servers, "
        "request_params, model_identifier, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        agents,
    )
    dst.executemany(
        "INSERT INTO messages(id, agent_id, fork_idx, created_at, data, role, "
        "prompt_tokens, completion_tokens, total_tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        messages,
    )
    dst.executemany(
        "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (m[0], m[1], m[3], m[2], message_text(json.loads(m[4])))
            for m in messages
        ],
    )

    # session_tabs: carry over any the source already has, then import the
    # legacy TUI store, deduped on agent_session_id.
    tabs = 0
    if _table_cols(src, "session_tabs"):
        rows = src.execute(f"SELECT {TAB_COLS} FROM session_tabs").fetchall()
        dst.executemany(f"INSERT INTO session_tabs({TAB_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        tabs += len(rows)
    seen = {r[0] for r in dst.execute("SELECT agent_session_id FROM session_tabs")}

    imported = 0
    if tui_path is not None and tui_path.exists():
        tui = sqlite3.connect(f"file:{tui_path}?mode=ro", uri=True)
        if _table_cols(tui, "sessions"):
            rows = tui.execute(
                "SELECT agent, agent_identity, agent_session_id, title, protocol, "
                "prompt_count, created_at, last_used, meta_json FROM sessions"
            ).fetchall()
            for row in rows:
                if row[2] in seen:
                    continue
                seen.add(row[2])
                dst.execute(
                    f"INSERT INTO session_tabs({TAB_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row[0], row[1], row[2], row[3], row[4], row[5],
                        _to_iso(row[6]), _to_iso(row[7]), row[8],
                    ),
                )
                imported += 1
        tui.close()
    dst.execute("COMMIT")
    dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    counts = {
        "prompts": len(prompts),
        "agents": len(agents),
        "messages": len(messages),
        "session_tabs": tabs + imported,
    }
    verify(dst, counts)
    src.close()
    dst.close()
    counts["tabs_copied"] = tabs
    counts["tabs_imported"] = imported
    return counts


def verify(dst: sqlite3.Connection, counts: dict) -> None:
    def fail(msg: str):
        sys.exit(f"VERIFICATION FAILED: {msg}")

    for table, n in counts.items():
        got = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if got != n:
            fail(f"{table} count {got} != expected {n}")
    fts_n = dst.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
    if fts_n != counts["messages"]:
        fail(f"messages_fts count {fts_n} != {counts['messages']}")
    print(
        f"verified: {counts['prompts']} prompts, {counts['agents']} agents, "
        f"{counts['messages']} messages (+FTS), {counts['session_tabs']} session_tabs"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src", type=Path, help="v5/v6 source db (read, never written)")
    ap.add_argument("dst", type=Path, help="v6 destination db (created fresh)")
    ap.add_argument(
        "--tui-db",
        type=Path,
        default=DEFAULT_TUI_DB,
        help=f"legacy TUI sqlite to import (default {DEFAULT_TUI_DB})",
    )
    ap.add_argument("--force", action="store_true", help="overwrite an existing destination")
    args = ap.parse_args()

    if not args.src.exists():
        sys.exit(f"error: source {args.src} does not exist")
    if args.dst.exists():
        if not args.force:
            sys.exit(f"error: destination {args.dst} exists (use --force)")
        for suffix in ("", "-wal", "-shm"):
            Path(str(args.dst) + suffix).unlink(missing_ok=True)

    counts = migrate(args.src.resolve(), args.dst.resolve(), args.tui_db)
    print(
        f"migration complete: {args.src} -> {args.dst} (v6)\n"
        f"  session_tabs: {counts['tabs_copied']} copied + {counts['tabs_imported']} imported from tui.db"
    )


if __name__ == "__main__":
    main()
