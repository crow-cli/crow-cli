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
"""

from sqlalchemy import text

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
