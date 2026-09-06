"""Full-text search seam — the ONLY place dialect-specific search SQL lives.

SQLite: FTS5 virtual table + bm25 ranking.
PostgreSQL: messages_fts side table with a tsvector column + GIN index,
to_tsvector/plainto_tsquery under the 'simple' config (keyword parity with
FTS5 — no stemming surprises). The side table is maintained from Python in
the same transaction as the message row (see writes.add_message), NOT by a
trigger: the searchable text is computed by messages.message_text(), and
that extraction logic stays in Python.

Contract on both backends: search_fts returns (rowid, rank) best-first with
rank LOWER = better (postgres ts_rank is negated to hold the contract; the
MCP display layer negates it back).

Two entry points, and the difference is where filtering happens:
``search_fts`` returns ids and leaves the caller to filter afterwards, which
means filtering AFTER the LIMIT — a scoped search then comes back short or
empty even when the scope is full of matches, because the global top-N
crowded it out. ``search_rows`` joins messages and agents and puts the same
filters in the WHERE, so ``limit`` means "this many matches".
"""

import json

from sqlalchemy import bindparam, text

_SQLITE_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
    "agent_id UNINDEXED, role UNINDEXED, fork_idx UNINDEXED, text)"
)
_PG_DDL = (
    "CREATE TABLE IF NOT EXISTS messages_fts ("
    "rowid BIGINT PRIMARY KEY, tsv tsvector NOT NULL)"
)
_PG_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_messages_fts_tsv "
    "ON messages_fts USING gin(tsv)"
)


def _is_postgres(engine) -> bool:
    return engine.dialect.name == "postgresql"


def create_fts(conn, engine) -> None:
    """Create the keyword index (called from create_database)."""
    if _is_postgres(engine):
        conn.execute(text(_PG_DDL))
        conn.execute(text(_PG_INDEX))
    else:
        conn.execute(text(_SQLITE_DDL))


def insert_fts(
    conn, engine, row_id: int, agent_id: str, role: str, fork_idx: int, searchable: str
) -> None:
    """Index one message row — same transaction as the message insert."""
    if _is_postgres(engine):
        conn.execute(
            text(
                "INSERT INTO messages_fts(rowid, tsv) "
                "VALUES (:r, to_tsvector('simple', :t))"
            ),
            {"r": row_id, "t": searchable},
        )
    else:
        conn.execute(
            text(
                "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
                "VALUES (:r, :a, :role, :f, :t)"
            ),
            {"r": row_id, "a": agent_id, "role": role, "f": fork_idx, "t": searchable},
        )


def search_fts(conn, engine, query: str, limit: int) -> list[tuple[int, float]]:
    """(rowid, rank) best-first; rank lower = better on both backends."""
    if _is_postgres(engine):
        if not query.strip():
            return []
        # plainto_tsquery ANDs the lexemes and is safe on raw user input.
        rows = conn.execute(
            text(
                "SELECT rowid, -ts_rank(tsv, q) AS rank "
                "FROM messages_fts, plainto_tsquery('simple', :q) q "
                "WHERE tsv @@ q ORDER BY rank LIMIT :lim"
            ),
            {"q": query, "lim": limit},
        ).fetchall()
        return [(r[0], float(r[1])) for r in rows]
    # Quote each token so arbitrary user input stays a valid FTS5 query
    # (implicit AND of phrases).
    match = " ".join(f'"{t}"' for t in query.split() if t)
    if not match:
        return []
    rows = conn.execute(
        text(
            "SELECT rowid, bm25(messages_fts) AS rank FROM messages_fts "
            "WHERE messages_fts MATCH :q ORDER BY rank LIMIT :lim"
        ),
        {"q": match, "lim": limit},
    ).fetchall()
    return [(r[0], float(r[1])) for r in rows]


# Same query, joined to messages and agents so the filters below can live in
# the WHERE instead of in Python after the LIMIT. bm25() needs the FTS table
# in the FROM; postgres negates ts_rank to hold the lower-is-better contract.
_SEARCH_ROWS = {
    "sqlite": (
        "SELECT m.id, m.agent_id, a.session_id, a.agent_idx, a.fork_idx, "
        "m.role, m.created_at, m.data, bm25(messages_fts) AS rank "
        "FROM messages_fts "
        "JOIN messages m ON m.id = messages_fts.rowid "
        "JOIN agents a ON a.agent_id = m.agent_id "
        "WHERE messages_fts MATCH :q{filters} ORDER BY rank LIMIT :lim"
    ),
    "postgresql": (
        "SELECT m.id, m.agent_id, a.session_id, a.agent_idx, a.fork_idx, "
        "m.role, m.created_at, m.data, -ts_rank(f.tsv, q) AS rank "
        "FROM messages_fts f "
        "JOIN messages m ON m.id = f.rowid "
        "JOIN agents a ON a.agent_id = m.agent_id "
        "CROSS JOIN plainto_tsquery('simple', :q) q "
        "WHERE f.tsv @@ q{filters} ORDER BY rank LIMIT :lim"
    ),
}


def search_rows(
    conn,
    engine,
    query: str,
    limit: int,
    roles: list[str] | tuple[str, ...] | None = None,
    session_id: str | None = None,
    agent_idx: int | None = None,
    agent_ids: set[str] | None = None,
    include_forks: bool = True,
) -> list[dict]:
    """Full message rows for a keyword query, best-first, filters in the SQL.

    Every filter is a WHERE clause, so ``limit`` is the number of MATCHES
    returned and never the number of rows scanned — the difference between a
    session-scoped search that works and one that returns the intersection of
    "top 20 globally" with "in this session", which for a common term is
    usually empty.

    ``include_forks=False`` drops fork agents' own rows (``a.fork_idx = 1``);
    a fork reads the trunk's prefix through the view in reads.py, it does not
    copy it, so this hides only what the fork itself said.

    Returns dicts of id, agent_id, session_id, agent_idx, fork_idx, role,
    created_at, data (always a dict — sqlite hands back the JSON column as
    text, postgres as jsonb) and score, lower = better on both backends.
    """
    clauses: list[str] = []
    params: dict[str, object] = {"lim": limit}
    expanding: list[str] = []
    if roles:
        clauses.append("m.role IN :roles")
        params["roles"] = tuple(roles)
        expanding.append("roles")
    if session_id is not None:
        clauses.append("a.session_id = :sid")
        params["sid"] = session_id
    if agent_idx is not None:
        clauses.append("a.agent_idx = :aidx")
        params["aidx"] = agent_idx
    if agent_ids is not None:
        clauses.append("m.agent_id IN :aids")
        params["aids"] = tuple(agent_ids)
        expanding.append("aids")
    if not include_forks:
        clauses.append("a.fork_idx = 1")

    if _is_postgres(engine):
        if not query.strip():
            return []
        sql = _SEARCH_ROWS["postgresql"]
        params["q"] = query
    else:
        # Quote each token so arbitrary input stays a valid FTS5 query
        # (implicit AND of phrases) — same escaping as search_fts.
        match = " ".join(f'"{t}"' for t in query.split() if t)
        if not match:
            return []
        sql = _SEARCH_ROWS["sqlite"]
        params["q"] = match

    stmt = text(
        sql.format(filters=(" AND " + " AND ".join(clauses)) if clauses else "")
    ).bindparams(*(bindparam(name, expanding=True) for name in expanding))
    out = []
    for row in conn.execute(stmt, params):
        data = row.data
        out.append(
            {
                "id": row.id,
                "agent_id": row.agent_id,
                "session_id": row.session_id,
                "agent_idx": row.agent_idx,
                "fork_idx": row.fork_idx,
                "role": row.role,
                "created_at": row.created_at,
                # Raw SQL bypasses the ORM's JSON type, so sqlite returns the
                # column as text while postgres returns jsonb already decoded.
                "data": json.loads(data) if isinstance(data, str) else (data or {}),
                "score": float(row.rank),
            }
        )
    return out
