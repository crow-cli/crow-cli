"""One-time recovery: consolidate the fragmented crow history into ONE
taskmaster-schema db.

The history had been fragmented across three files (the pre-August archive
was no longer referenced by the live config):

  ARCHIVE  ~/.crow/crow.db            v4   May 25 - Jul 27   2487 agents / 58377 msgs
  MIG      crow-migrated.db           v5   Aug 11 - Aug 23   120 agents / 6765 msgs
  LIVE     crow-98.db                 v5   Aug 22 - now       21 agents / 2109 msgs

Union rules (all verified before this runs):
  - ARCHIVE sessions are disjoint from MIG and LIVE (0 session_id overlap), so
    the whole archive is taken as-is.
  - For sessions present in LIVE, LIVE is authoritative (it is the current,
    continuing state). From MIG we therefore take ONLY the sessions that are
    NOT in LIVE (the Aug 11-21 history LIVE never had).
  - Message ids collide across sources (each starts at 1), so each source's
    message ids are OFFSET into a disjoint band; the single forked_at anchor
    (which references a message id) is offset with its source.
  - Prompts use globally-unique coolname ids; they union cleanly (INSERT OR
    IGNORE dedups the one shared id, whose template is identical).

The destination is created fresh via create_database (full taskmaster schema:
tasks, task_deliveries, agents.mcp_servers) and the FTS index is rebuilt with
the current message_text extractor. Sources are opened READ-ONLY.

Usage:
  uv --project . run python scripts/consolidate_history.py DST.db [--force] \
      [--archive PATH] [--mig PATH] [--live PATH]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from crow_cli.memory import create_database  # noqa: E402
from crow_cli.memory.messages import message_text  # noqa: E402

# Disjoint message-id bands per source (well above any source's max id).
MIG_OFFSET = 1_000_000
LIVE_OFFSET = 2_000_000

# v5 agent columns shared by MIG/LIVE (no mcp_servers -> left NULL).
_V5_AGENT_COLS = (
    "agent_id, session_id, agent_idx, fork_idx, forked_at, cwd, prompt_id, "
    "prompt_args, system_prompt, tool_definitions, request_params, "
    "model_identifier, status, created_at"
)
_MSG_COLS = (
    "id, agent_id, fork_idx, created_at, data, role, prompt_tokens, "
    "completion_tokens, total_tokens"
)


def _ro(path: Path) -> str:
    return f"file:{path}?mode=ro"


def consolidate(dst: Path, archive: Path, mig: Path, live: Path) -> dict:
    for name, p in (("archive", archive), ("mig", mig), ("live", live)):
        if not p.exists():
            sys.exit(f"error: {name} source {p} does not exist")

    create_database(f"sqlite:///{dst}")
    # uri=True so the ATTACH 'file:...?mode=ro' sources open read-only
    d = sqlite3.connect(f"file:{dst}", uri=True)
    d.execute(f"ATTACH '{_ro(archive)}' AS arch")
    d.execute(f"ATTACH '{_ro(mig)}' AS mig")
    d.execute(f"ATTACH '{_ro(live)}' AS live")

    print("source sizes (agents / msgs):")
    for alias in ("arch", "mig", "live"):
        a = d.execute(f"SELECT COUNT(*) FROM {alias}.agents").fetchone()[0]
        m = d.execute(f"SELECT COUNT(*) FROM {alias}.messages").fetchone()[0]
        print(f"  {alias}: {a} agents / {m} msgs")

    d.execute("BEGIN")

    # ---- prompts: clean union, dedup on coolname id ----
    d.executemany(
        "INSERT OR IGNORE INTO prompts(id, name, template, created_at) "
        "VALUES (?, ?, ?, ?)",
        d.execute(
            "SELECT id, name, template, created_at FROM arch.prompts "
            "UNION SELECT id, name, template, created_at FROM mig.prompts "
            "UNION SELECT id, name, template, created_at FROM live.prompts"
        ).fetchall(),
    )

    # ---- ARCHIVE (v4): 2-part ids -> append '-1', fork_idx=1, id band 0 ----
    d.execute(
        "INSERT INTO agents(agent_id, session_id, agent_idx, fork_idx, forked_at, "
        "cwd, prompt_id, prompt_args, system_prompt, tool_definitions, "
        "request_params, model_identifier, status, created_at) "
        "SELECT agent_id || '-1', session_id, agent_idx, 1, NULL, cwd, prompt_id, "
        "prompt_args, system_prompt, tool_definitions, request_params, "
        "model_identifier, status, created_at FROM arch.agents"
    )
    d.execute(
        "INSERT INTO messages(id, agent_id, fork_idx, created_at, data, role, "
        "prompt_tokens, completion_tokens, total_tokens) "
        "SELECT id, agent_id || '-1', 1, created_at, data, role, prompt_tokens, "
        "completion_tokens, total_tokens FROM arch.messages"
    )

    # ---- MIG-only sessions (not in LIVE): id band +MIG_OFFSET ----
    d.execute(
        "CREATE TEMP TABLE mig_only AS SELECT DISTINCT a.session_id AS sid "
        "FROM mig.agents a LEFT JOIN (SELECT DISTINCT session_id FROM live.agents) l "
        "ON a.session_id = l.session_id WHERE l.session_id IS NULL"
    )
    d.execute(
        "INSERT INTO agents(agent_id, session_id, agent_idx, fork_idx, forked_at, "
        "cwd, prompt_id, prompt_args, system_prompt, tool_definitions, "
        "request_params, model_identifier, status, created_at) "
        "SELECT agent_id, session_id, agent_idx, fork_idx, "
        "CASE WHEN forked_at IS NOT NULL THEN forked_at + ? ELSE NULL END, cwd, "
        "prompt_id, prompt_args, system_prompt, tool_definitions, request_params, "
        "model_identifier, status, created_at "
        "FROM mig.agents WHERE session_id IN (SELECT sid FROM mig_only)",
        (MIG_OFFSET,),
    )
    d.execute(
        "INSERT INTO messages(id, agent_id, fork_idx, created_at, data, role, "
        "prompt_tokens, completion_tokens, total_tokens) "
        "SELECT id + ?, agent_id, fork_idx, created_at, data, role, prompt_tokens, "
        "completion_tokens, total_tokens FROM mig.messages "
        "WHERE agent_id IN (SELECT agent_id FROM mig.agents "
        "WHERE session_id IN (SELECT sid FROM mig_only))",
        (MIG_OFFSET,),
    )

    # ---- LIVE (authoritative for its sessions): id band +LIVE_OFFSET ----
    d.execute(
        "INSERT INTO agents(agent_id, session_id, agent_idx, fork_idx, forked_at, "
        "cwd, prompt_id, prompt_args, system_prompt, tool_definitions, "
        "request_params, model_identifier, status, created_at) "
        f"SELECT {_V5_AGENT_COLS} FROM live.agents"
    )
    d.execute(
        "INSERT INTO messages(id, agent_id, fork_idx, created_at, data, role, "
        "prompt_tokens, completion_tokens, total_tokens) "
        "SELECT id + ?, agent_id, fork_idx, created_at, data, role, prompt_tokens, "
        "completion_tokens, total_tokens FROM live.messages",
        (LIVE_OFFSET,),
    )

    # ---- rebuild FTS on the current extractor ----
    d.executemany(
        "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (mid, aid, role, fork, message_text(json.loads(data)))
            for mid, aid, role, fork, data in d.execute(
                "SELECT id, agent_id, role, fork_idx, data FROM messages"
            )
        ],
    )

    d.execute("COMMIT")
    # scope to main: the attached sources are read-only and can't checkpoint
    d.execute("PRAGMA main.wal_checkpoint(TRUNCATE)")

    stats = verify(d)
    d.execute("DETACH arch"); d.execute("DETACH mig"); d.execute("DETACH live")
    d.close()
    return stats


def verify(d: sqlite3.Connection) -> dict:
    def fail(msg):
        sys.exit(f"VERIFICATION FAILED: {msg}")

    agents = d.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    msgs = d.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    prompts = d.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
    sessions = d.execute("SELECT COUNT(DISTINCT session_id) FROM agents").fetchone()[0]

    # message ids globally unique (no band collisions)
    dup = d.execute(
        "SELECT COUNT(*) FROM (SELECT id FROM messages GROUP BY id HAVING COUNT(*)>1)"
    ).fetchone()[0]
    if dup:
        fail(f"{dup} duplicate message ids after offset")

    # agent_ids unique
    adup = d.execute(
        "SELECT COUNT(*) FROM (SELECT agent_id FROM agents GROUP BY agent_id "
        "HAVING COUNT(*)>1)"
    ).fetchone()[0]
    if adup:
        fail(f"{adup} duplicate agent_ids")

    # every agent.prompt_id resolves
    dangling = d.execute(
        "SELECT COUNT(*) FROM agents WHERE prompt_id IS NOT NULL AND prompt_id != '' "
        "AND prompt_id NOT IN (SELECT id FROM prompts)"
    ).fetchone()[0]
    if dangling:
        fail(f"{dangling} agents reference a missing prompt_id")

    # the single fork's anchor still points at a real message
    badfork = d.execute(
        "SELECT COUNT(*) FROM agents WHERE forked_at IS NOT NULL "
        "AND forked_at NOT IN (SELECT id FROM messages)"
    ).fetchone()[0]
    if badfork:
        fail(f"{badfork} forked_at anchors dangle")

    # FTS complete
    fts = d.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
    if fts != msgs:
        fail(f"messages_fts {fts} != messages {msgs}")

    integ = d.execute("PRAGMA main.integrity_check").fetchone()[0]
    if integ != "ok":
        fail(f"integrity_check: {integ}")

    print(
        f"verified: {agents} agents / {msgs} msgs / {prompts} prompts / "
        f"{sessions} sessions; ids unique; prompts+forks resolve; FTS complete; "
        f"integrity ok"
    )
    return {"agents": agents, "messages": msgs, "prompts": prompts, "sessions": sessions}


def main():
    home = Path.home()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dst", type=Path)
    ap.add_argument("--archive", type=Path,
                    default=home / ".agents/crow/crow.db.full-v4-archive")
    ap.add_argument("--mig", type=Path,
                    default=home / ".agents/crow/crow-migrated.db")
    ap.add_argument("--live", type=Path,
                    default=home / ".agents/crow/crow-98.db")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.dst.exists():
        if not args.force:
            sys.exit(f"error: destination {args.dst} exists (use --force)")
        for s in ("", "-wal", "-shm"):
            Path(str(args.dst) + s).unlink(missing_ok=True)

    stats = consolidate(args.dst.resolve(), args.archive.resolve(),
                        args.mig.resolve(), args.live.resolve())
    print(
        f"consolidation complete -> {args.dst}\n"
        f"  {stats['agents']} agents, {stats['messages']} messages, "
        f"{stats['prompts']} prompts, {stats['sessions']} sessions"
    )


if __name__ == "__main__":
    main()
