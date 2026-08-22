"""The ONE v4 -> v5 schema migration (PLAN.md Phase 7).

v4 agent_id = "{session_id}-{agent_idx}"; v5 adds the fork part:
"{session_id}-{agent_idx}-{fork_idx}". Every v4 identity is a trunk, so
the migration appends "-1" to every agent_id (agents, messages, FTS),
adds fork_idx=1 / forked_at=NULL, and PRESERVES message ids + created_at.

Safety model:
- The source is opened READ-ONLY and never modified; cutover is a config
  swap (point config.yaml db_uri at the new file), done when no process is
  writing to the source.
- The destination is created fresh (schema v5 via create_database) and must
  not exist yet (--force to overwrite a previous attempt).
- The FTS index is REBUILT with the current message_text extractor, so the
  migrated index matches the live write path exactly.
- After copying, the script verifies counts, id preservation, created_at
  fidelity and the FTS, and exits non-zero on any mismatch.

Usage:
  uv --project crow-cli run python crow-cli/scripts/migrate_v5.py SRC.db DST.db [--force]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# Allow running as a plain script from the repo root (uv --project puts
# src/ on the path; direct python invocations may not).
_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from crow_cli.memory import create_database  # noqa: E402
from crow_cli.memory.messages import message_text  # noqa: E402


def _table_cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _require_v4(conn: sqlite3.Connection, path: Path) -> None:
    cols = _table_cols(conn, "agents")
    if not cols:
        sys.exit(f"error: {path} has no agents table — not a crow database")
    if "fork_idx" in cols:
        sys.exit(f"error: {path} is already schema v5 — nothing to migrate")


def migrate(src_path: Path, dst_path: Path) -> dict:
    """Migrate src (v4, read-only) into dst (fresh v5). Returns counts."""
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    _require_v4(src, src_path)

    create_database(f"sqlite:///{dst_path}")
    dst = sqlite3.connect(dst_path)

    prompts = src.execute("SELECT id, name, template, created_at FROM prompts").fetchall()
    agents = src.execute(
        "SELECT agent_id, session_id, agent_idx, cwd, prompt_id, prompt_args, "
        "system_prompt, tool_definitions, request_params, model_identifier, "
        "status, created_at FROM agents"
    ).fetchall()
    messages = src.execute(
        "SELECT id, agent_id, created_at, data, role, prompt_tokens, "
        "completion_tokens, total_tokens FROM messages ORDER BY id"
    ).fetchall()

    dst.execute("BEGIN")
    dst.executemany(
        "INSERT INTO prompts(id, name, template, created_at) VALUES (?, ?, ?, ?)",
        prompts,
    )
    dst.executemany(
        "INSERT INTO agents(agent_id, session_id, agent_idx, fork_idx, forked_at, "
        "cwd, prompt_id, prompt_args, system_prompt, tool_definitions, "
        "request_params, model_identifier, status, created_at) "
        "VALUES (?, ?, ?, 1, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(a[0] + "-1",) + a[1:] for a in agents],
    )
    dst.executemany(
        "INSERT INTO messages(id, agent_id, fork_idx, created_at, data, role, "
        "prompt_tokens, completion_tokens, total_tokens) "
        "VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)",
        [(m[0], m[1] + "-1", m[2], m[3], m[4], m[5], m[6], m[7]) for m in messages],
    )
    # Rebuild FTS with the CURRENT extractor so the index matches the live
    # write path (v4's index content is irrelevant after this).
    dst.executemany(
        "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
        "VALUES (?, ?, ?, 1, ?)",
        [
            (m[0], m[1] + "-1", m[4], message_text(json.loads(m[3])))
            for m in messages
        ],
    )
    dst.execute("COMMIT")
    dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    counts = {
        "prompts": len(prompts),
        "agents": len(agents),
        "messages": len(messages),
    }
    verify(src, dst, counts)
    src.close()
    dst.close()
    return counts


def verify(src: sqlite3.Connection, dst: sqlite3.Connection, counts: dict) -> None:
    """Exits non-zero on any fidelity mismatch."""
    def fail(msg: str):
        sys.exit(f"VERIFICATION FAILED: {msg}")

    for table, n in counts.items():
        got = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if got != n:
            fail(f"{table} count {got} != source {n}")

    # Every v5 agent_id is exactly one v4 agent_id + "-1".
    src_ids = {r[0] for r in src.execute("SELECT agent_id FROM agents")}
    dst_ids = {r[0] for r in dst.execute("SELECT agent_id FROM agents")}
    if dst_ids != {a + "-1" for a in src_ids}:
        fail("agent_id sets do not match (v5 = v4 + '-1')")

    # Message ids preserved end-to-end.
    src_range = src.execute("SELECT MIN(id), MAX(id) FROM messages").fetchone()
    dst_range = dst.execute("SELECT MIN(id), MAX(id) FROM messages").fetchone()
    if src_range != dst_range:
        fail(f"message id range {dst_range} != source {src_range}")

    # Every dst message is its src twin with '-1' appended — full scan, the
    # db is small enough and this is the one migration that must be right.
    src_msgs = {
        r[0]: (r[1], r[2], r[3])
        for r in src.execute("SELECT id, agent_id, created_at, role FROM messages")
    }
    for mid, aid, created, role in dst.execute(
        "SELECT id, agent_id, created_at, role FROM messages"
    ):
        want = src_msgs.get(mid)
        if want is None:
            fail(f"message {mid} has no source twin")
        if (aid, created, role) != (want[0] + "-1", want[1], want[2]):
            fail(f"message {mid} drifted: {(aid, created, role)} vs {want}")

    # FTS rebuilt completely.
    fts_n = dst.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
    if fts_n != counts["messages"]:
        fail(f"messages_fts count {fts_n} != {counts['messages']}")

    print(
        f"verified: {counts['prompts']} prompts, {counts['agents']} agents, "
        f"{counts['messages']} messages (+FTS) — ids/created_at preserved"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src", type=Path, help="v4 source db (read-only, untouched)")
    ap.add_argument("dst", type=Path, help="v5 destination db (created fresh)")
    ap.add_argument(
        "--force", action="store_true", help="overwrite an existing destination"
    )
    args = ap.parse_args()

    if not args.src.exists():
        sys.exit(f"error: source {args.src} does not exist")
    if args.dst.exists():
        if not args.force:
            sys.exit(f"error: destination {args.dst} exists (use --force)")
        for suffix in ("", "-wal", "-shm"):
            Path(str(args.dst) + suffix).unlink(missing_ok=True)

    counts = migrate(args.src.resolve(), args.dst.resolve())
    print(
        f"migration complete: {args.src} (v4, untouched) -> {args.dst} (v5)\n"
        f"  {counts['prompts']} prompts, {counts['agents']} agents, "
        f"{counts['messages']} messages"
    )


if __name__ == "__main__":
    main()
