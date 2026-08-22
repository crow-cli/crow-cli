"""Engine factory + database creation. The caller-supplied ``db_uri`` is the
only integration point — this package reads NO config."""

import os
from pathlib import Path

from sqlalchemy import create_engine, event, text

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
        return f"{scheme}://{os.path.expanduser(rest)}"
    return f"sqlite:///{Path(os.path.expanduser(value)).resolve()}"


def _set_pragmas(dbapi_conn, _record):
    # Tolerant per-pragma: on a read-only connection (crow-mcp) the WAL
    # pragma fails, and that's fine — busy_timeout still applies.
    for pragma in ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL", "PRAGMA busy_timeout=5000"):
        try:
            dbapi_conn.cursor().execute(pragma)
        except Exception:
            pass


def get_engine(db_uri: str):
    """Engine with WAL + busy_timeout so multiple processes (crow-cli
    writing, crow-mcp reading) coexist without lock errors. For a read-only
    sqlite handle pass ``sqlite:///file:<path>?mode=ro&uri=true``."""
    engine = create_engine(db_uri)
    if db_uri.startswith("sqlite"):
        event.listen(engine, "connect", _set_pragmas)
    return engine


def create_database(db_uri: str) -> None:
    """Create tables + the FTS5 keyword index."""
    engine = get_engine(db_uri)
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                "agent_id UNINDEXED, role UNINDEXED, text)"
            )
        )
        conn.commit()
    engine.dispose()
