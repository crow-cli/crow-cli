"""Engine factory + database creation. The caller-supplied ``db_uri`` is the
only integration point — this package reads NO config."""

import os
from pathlib import Path

from sqlalchemy import create_engine, event

from . import fts
from .models import Base


def normalize_db_uri(value: str) -> str:
    """Normalize a config value to a SQLAlchemy database URI.

    Accepts either a full URI (``sqlite:///...``, ``postgresql://...``) which
    passes through unchanged, or a plain filesystem path which becomes a
    sqlite URI. ``~`` is expanded in both forms.
    """
    value = value.strip()
    if "://" in value:
        scheme, _, rest = value.partition("://")
        if scheme == "sqlite" and rest.lstrip("/").startswith("~"):
            # sqlite:///~/.agents/x.db — expanduser only expands a LEADING
            # tilde, so strip the path slashes first. expanduser("~/...")
            # returns an absolute path; "sqlite:///" + "/home/..." keeps
            # sqlite's 4-slash absolute form.
            return f"{scheme}:///{os.path.expanduser(rest.lstrip('/'))}"
        return f"{scheme}://{os.path.expanduser(rest)}"
    return f"sqlite:///{Path(os.path.expanduser(value)).resolve()}"


def _set_pragmas(dbapi_conn, _record):
    # Tolerant per-pragma: on a read-only connection (an MCP consumer) the WAL
    # pragma fails, and that's fine — busy_timeout still applies.
    for pragma in ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL", "PRAGMA busy_timeout=5000"):
        try:
            dbapi_conn.cursor().execute(pragma)
        except Exception:
            pass


def get_engine(db_uri: str):
    """Engine with WAL + busy_timeout so multiple processes (the agent
    writing, an MCP consumer reading) coexist without lock errors. For a
    read-only handle use get_ro_engine (dialect-aware)."""
    engine = create_engine(db_uri)
    if db_uri.startswith("sqlite"):
        event.listen(engine, "connect", _set_pragmas)
    return engine


def _set_pg_readonly(dbapi_conn, _record):
    dbapi_conn.cursor().execute(
        "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
    )


def get_ro_engine(db_uri: str):
    """Read-only engine, dialect-aware. sqlite: the URI is rewritten to the
    ``mode=ro`` file form so the OS refuses writes; postgres: every session
    gets READ ONLY transaction characteristics so the server refuses them.
    Used by the MCP query tools — they must never write."""
    if db_uri.startswith("sqlite"):
        path = db_uri.removeprefix("sqlite:///")
        return get_engine(f"sqlite:///file:{path}?mode=ro&uri=true")
    engine = create_engine(db_uri)
    event.listen(engine, "connect", _set_pg_readonly)
    return engine


def _require_v5(engine) -> None:
    """Fail fast on an unmigrated v4 database (no fork_idx column)."""
    from sqlalchemy import inspect

    cols = {c["name"] for c in inspect(engine).get_columns("agents")}
    if cols and "fork_idx" not in cols:
        raise RuntimeError(
            "schema v4 database detected (agents.fork_idx missing) — run the "
            "schema-v5 migration (crow-cli/scripts/migrate_v5.py) before using it"
        )


def create_database(db_uri: str) -> None:
    """Create tables + the keyword index (schema v5). Dialect-aware: FTS5
    on sqlite, tsvector+GIN on postgres (see memory/fts.py)."""
    engine = get_engine(db_uri)
    Base.metadata.create_all(engine)
    _require_v5(engine)
    with engine.connect() as conn:
        fts.create_fts(conn, engine)
        conn.commit()
    engine.dispose()
