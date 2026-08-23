"""The v5 -> taskmaster schema migration (additive task-system delta).

The task system adds state WITHOUT reshaping anything that already exists:
two new tables (``tasks``, ``task_deliveries``) and one nullable column
(``agents.mcp_servers``). Every v5 identity is preserved as-is — agent_id,
fork_idx, message ids and created_at are copied byte-for-byte. This is why
the migration "shouldn't require much update": the delta is purely additive.

Safety model (same as migrate_v5.py):
- The source is opened READ-ONLY and never modified; cutover is a config
  swap (point config.yaml memory_path at the new file), done when no
  process is writing to the source.
- The destination is created fresh via create_database — which emits the
  FULL taskmaster schema (tasks, task_deliveries, agents.mcp_servers) — so
  this script never hand-rolls DDL and can't drift from the models.
- The FTS index is REBUILT with the current message_text extractor, so the
  migrated index matches the live write path exactly.
- After copying, the script verifies counts, id preservation, created_at
  fidelity, the new tables/column, and the FTS; exits non-zero on mismatch.

Usage:
  uv --project . run python scripts/migrate_taskmaster.py SRC.db DST.db [--force]
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

# v5 columns copied verbatim (taskmaster adds only mcp_servers, left NULL).
_AGENT_COLS = (
    "agent_id, session_id, agent_idx, fork_idx, forked_at, cwd, prompt_id, "
    "prompt_args, system_prompt, tool_definitions, request_params, "
    "model_identifier, status, created_at"
)
_MSG_COLS = (
    "id, agent_id, fork_idx, created_at, data, role, prompt_tokens, "
    "completion_tokens, total_tokens"
)


def _table_cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )


def _require_v5_src(conn: sqlite3.Connection, path: Path) -> None:
    cols = _table_cols(conn, "agents")
    if not cols:
        sys.exit(f"error: {path} has no agents table — not a crow database")
    if "fork_idx" not in cols:
        sys.exit(
            f"error: {path} is schema v4 — run migrate_v5.py first, then this"
        )
    if _has_table(conn, "tasks") and "mcp_servers" in cols:
        sys.exit(f"error: {path} is already taskmaster-schema — nothing to migrate")


def migrate(src_path: Path, dst_path: Path) -> dict:
    """Migrate src (v5, read-only) into dst (fresh taskmaster). Returns counts."""
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    _require_v5_src(src, src_path)

    # Fresh destination = the FULL taskmaster schema from the models. This is
    # the whole point: the new tables/column come from create_all, not DDL
    # hand-written here, so the migration can't drift from the code.
    create_database(f"sqlite:///{dst_path}")
    dst = sqlite3.connect(dst_path)

    # One explicit read transaction pins a single snapshot for the fetches
    # AND for verify() — the source may be LIVE (writer mid-WAL), and the
    # copy must be atomically consistent. Committed after verify.
    src.execute("BEGIN")
    prompts = src.execute(
        "SELECT id, name, template, created_at FROM prompts"
    ).fetchall()
    agents = src.execute(f"SELECT {_AGENT_COLS} FROM agents").fetchall()
    messages = src.execute(
        f"SELECT {_MSG_COLS} FROM messages ORDER BY id"
    ).fetchall()

    dst.execute("BEGIN")
    dst.executemany(
        "INSERT INTO prompts(id, name, template, created_at) VALUES (?, ?, ?, ?)",
        prompts,
    )
    # mcp_servers omitted -> NULL ("never supplied"), the correct default for
    # rows provisioned before the column existed.
    dst.executemany(
        f"INSERT INTO agents({_AGENT_COLS}) "
        f"VALUES ({', '.join('?' * len(_AGENT_COLS.split(', ')))})",
        agents,
    )
    dst.executemany(
        f"INSERT INTO messages({_MSG_COLS}) "
        f"VALUES ({', '.join('?' * len(_MSG_COLS.split(', ')))})",
        messages,
    )
    # Rebuild FTS with the CURRENT extractor; fork_idx rides each row now.
    dst.executemany(
        "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (m[0], m[1], m[5], m[2], message_text(json.loads(m[4])))
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
    src.execute("COMMIT")
    src.close()
    dst.close()
    return counts


def verify(src: sqlite3.Connection, dst: sqlite3.Connection, counts: dict) -> None:
    """Exits non-zero on any fidelity mismatch."""

    def fail(msg: str):
        sys.exit(f"VERIFICATION FAILED: {msg}")

    # The additive delta actually landed.
    if not _has_table(dst, "tasks"):
        fail("dst is missing the tasks table")
    if not _has_table(dst, "task_deliveries"):
        fail("dst is missing the task_deliveries table")
    if "mcp_servers" not in _table_cols(dst, "agents"):
        fail("dst agents table is missing the mcp_servers column")

    for table, n in counts.items():
        got = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if got != n:
            fail(f"{table} count {got} != source {n}")

    # agent_id set preserved EXACTLY (no rewriting in this migration).
    src_ids = {r[0] for r in src.execute("SELECT agent_id FROM agents")}
    dst_ids = {r[0] for r in dst.execute("SELECT agent_id FROM agents")}
    if dst_ids != src_ids:
        fail("agent_id sets do not match (v5 -> taskmaster is identity)")

    # Message ids preserved end-to-end.
    src_range = src.execute("SELECT MIN(id), MAX(id) FROM messages").fetchone()
    dst_range = dst.execute("SELECT MIN(id), MAX(id) FROM messages").fetchone()
    if src_range != dst_range:
        fail(f"message id range {dst_range} != source {src_range}")

    # Every dst message is its src twin — full scan, this migration must be right.
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
        if (aid, created, role) != want:
            fail(f"message {mid} drifted: {(aid, created, role)} vs {want}")

    # FTS rebuilt completely.
    fts_n = dst.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
    if fts_n != counts["messages"]:
        fail(f"messages_fts count {fts_n} != {counts['messages']}")

    print(
        f"verified: {counts['prompts']} prompts, {counts['agents']} agents, "
        f"{counts['messages']} messages (+FTS) — ids/created_at preserved; "
        f"tasks/task_deliveries/agents.mcp_servers present"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src", type=Path, help="v5 source db (read-only, untouched)")
    ap.add_argument("dst", type=Path, help="taskmaster destination db (created fresh)")
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
        f"migration complete: {args.src} (v5, untouched) -> {args.dst} (taskmaster)\n"
        f"  {counts['prompts']} prompts, {counts['agents']} agents, "
        f"{counts['messages']} messages"
    )


if __name__ == "__main__":
    main()
