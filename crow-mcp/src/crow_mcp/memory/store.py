"""Read-mostly sqlite accessor for the crow-cli memory database.

crow-mcp never imports crow-cli (MCP is a runtime protocol boundary; the
sqlite file is the only integration point). Plain sqlite3, no ORM: the
schema is the one crow_cli/agent/db.py creates (agents / messages /
messages_fts). Search is FTS5 + bm25 (keyword).
"""

import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DB = "~/.agents/crow/crow.db"


def db_path() -> Path:
    env = os.environ.get("CROW_MEMORY_DB")
    if env:
        return Path(os.path.expanduser(env))
    cfg = Path(os.path.expanduser("~/.agents/crow/config.yaml"))
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            if line.startswith("memory_path:"):
                return Path(os.path.expanduser(line.split(":", 1)[1].strip()))
    return Path(os.path.expanduser(DEFAULT_DB))


def _conn() -> sqlite3.Connection | None:
    path = db_path()
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


@dataclass
class Msg:
    id: int
    agent_id: str
    session_id: str
    agent_idx: int
    role: str
    created_at: str
    data: dict
    score: float | None = None


@dataclass
class SessionRow:
    session_id: str
    last_activity: str
    message_count: int
    agent_count: int
    agent_idxs: list[int] = field(default_factory=list)
    model_identifier: str = ""
    cwd: str = ""
    last_role: str = ""
    last_message: Msg | None = None


def _agent_map(conn) -> dict[str, tuple[str, int, str, str]]:
    """agent_id -> (session_id, agent_idx, model_identifier, cwd)."""
    return {
        r["agent_id"]: (r["session_id"], r["agent_idx"], r["model_identifier"], r["cwd"])
        for r in conn.execute("SELECT * FROM agents")
    }


def _msg(row: sqlite3.Row, agents: dict, score: float | None = None) -> Msg:
    sid, aidx, _, _ = agents.get(row["agent_id"], ("", 0, "", ""))
    return Msg(
        id=row["id"],
        agent_id=row["agent_id"],
        session_id=sid,
        agent_idx=aidx,
        role=row["role"],
        created_at=row["created_at"],
        data=json.loads(row["data"]),
        score=score,
    )


def list_sessions(limit: int = 50, offset: int = 0) -> list[SessionRow]:
    if (conn := _conn()) is None:
        return []
    with conn:
        agents = _agent_map(conn)
        rows = conn.execute(
            """
            SELECT a.session_id,
                   MAX(m.created_at) AS last_activity,
                   COUNT(DISTINCT m.id) AS message_count,
                   COUNT(DISTINCT a.agent_id) AS agent_count
            FROM agents a LEFT JOIN messages m ON m.agent_id = a.agent_id
            GROUP BY a.session_id
            ORDER BY last_activity DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        out = []
        for r in rows:
            sid = r["session_id"]
            mine = [a for a, (s, _, m, c) in agents.items() if s == sid]
            idxs = sorted(i for s, i, _, _ in (agents[a] for a in mine))
            _, _, model, cwd = next((agents[a] for a in mine), ("", 0, "", ""))
            last = conn.execute(
                "SELECT * FROM messages WHERE agent_id IN ({}) ORDER BY id DESC LIMIT 1".format(
                    ",".join("?" for _ in mine) or "''"
                ),
                mine,
            ).fetchone()
            out.append(
                SessionRow(
                    session_id=sid,
                    last_activity=r["last_activity"] or "",
                    message_count=r["message_count"],
                    agent_count=r["agent_count"],
                    agent_idxs=idxs,
                    model_identifier=model,
                    cwd=cwd,
                    last_role=last["role"] if last else "",
                    last_message=_msg(last, agents) if last else None,
                )
            )
        return out


def session_records(
    session_id: str,
    agent_idx: int | None = None,
    roles: list[str] | None = None,
    after: str | None = None,
    before: str | None = None,
) -> list[Msg]:
    if (conn := _conn()) is None:
        return []
    with conn:
        agents = _agent_map(conn)
        aids = [
            a for a, (s, i, _, _) in agents.items()
            if s == session_id and (agent_idx is None or i == agent_idx)
        ]
        if not aids:
            return []
        q = "SELECT * FROM messages WHERE agent_id IN ({})".format(",".join("?" for _ in aids))
        params: list = list(aids)
        if roles is not None:
            q += " AND role IN ({})".format(",".join("?" for _ in roles))
            params += roles
        if after is not None:
            q += " AND created_at > ?"
            params.append(after)
        if before is not None:
            q += " AND created_at < ?"
            params.append(before)
        q += " ORDER BY id ASC"
        return [_msg(r, agents) for r in conn.execute(q, params)]


def search(query: str, limit: int = 20, agent_ids: set[str] | None = None) -> list[Msg]:
    """BM25 keyword search, best match first. Quoted tokens = implicit AND."""
    match = " ".join(f'"{t}"' for t in query.split() if t)
    if not match or (conn := _conn()) is None:
        return []
    with conn:
        agents = _agent_map(conn)
        hits = conn.execute(
            """
            SELECT rowid, bm25(messages_fts) AS rank
            FROM messages_fts WHERE messages_fts MATCH ?
            ORDER BY rank LIMIT ?
            """,
            (match, limit * (4 if agent_ids else 1)),
        ).fetchall()
        out = []
        for h in hits:
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (h["rowid"],)).fetchone()
            if row is None:
                continue
            m = _msg(row, agents, score=h["rank"])
            if agent_ids is not None and m.agent_id not in agent_ids:
                continue
            out.append(m)
            if len(out) >= limit:
                break
        return out
