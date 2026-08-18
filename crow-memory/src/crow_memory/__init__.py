"""
crow-memory — the one memory contract for crow.

SQLAlchemy over a caller-supplied ``db_uri`` (sqlite by default; the schema
is plain SQLAlchemy so postgres is a seam away — except FTS5 keyword search,
which is sqlite-specific and lives behind ``search_messages``).

This package reads NO config. Apps resolve their own db_uri and pass it in:

    engine = crow_memory.get_engine("sqlite:///~/.agents/crow/crow.db")

Schema v4: one row = one message, agent-centric. agent_id = "{session_id}-{idx}"
is the primary key; session_id is the logical parent (multiple agents per
session).

Images never live in the database: inline base64 blocks are extracted at
write time to ``<images_dir>/<sha256hex><ext>`` (content-addressed, so dupes
dedupe for free) and the stored message carries an ``image_ref`` block with
the file location. The in-memory conversation keeps the original data URL so
the LLM always sees base64; on load, ``hydrate`` swaps refs back to data URLs.

Search is SQLite FTS5 + bm25 (keyword). No embeddings, no service, no lance.
"""

import base64
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Column, Integer, Text, create_engine, event, func, text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Session, declarative_base

Base = declarative_base()

_MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class Prompt(Base):
    """System prompt templates - versioned, reusable."""

    __tablename__ = "prompts"

    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    template = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False, default=now_iso)


class Agent(Base):
    """A running agent instance. agent_id = "{session_id}-{agent_idx}" is the PK."""

    __tablename__ = "agents"

    agent_id = Column(Text, primary_key=True)
    session_id = Column(Text, nullable=False, index=True)
    agent_idx = Column(Integer, nullable=False, default=1)
    cwd = Column(Text, nullable=False, default="/tmp")
    prompt_id = Column(Text, nullable=True)
    prompt_args = Column(JSON, nullable=True)
    system_prompt = Column(Text, nullable=False, default="")
    tool_definitions = Column(JSON, nullable=False, default=list)
    request_params = Column(JSON, nullable=False, default=dict)
    model_identifier = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="active")
    created_at = Column(Text, nullable=False, default=now_iso)


class Message(Base):
    """One row = One message; the message dict serialized into `data`."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Text, nullable=False, index=True)
    created_at = Column(Text, nullable=False, default=now_iso)
    data = Column(JSON, nullable=False)
    role = Column(Text, nullable=False, index=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)


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


# ---- images ----------------------------------------------------------------


def _block_bytes(block: dict) -> tuple[bytes, str] | None:
    """Decode an inline image block (OpenAI image_url or ACP image) to bytes."""
    btype = block.get("type")
    if btype == "image_url":
        url = (block.get("image_url") or {}).get("url", "")
        mime, _, b64 = url.partition(";base64,")
        if mime.startswith("data:") and b64:
            try:
                return base64.b64decode(b64), mime[5:]
            except ValueError:
                return None
    if btype == "image":
        b64 = block.get("data", "")
        if b64:
            try:
                return base64.b64decode(b64), block.get("mimeType", "image/png")
            except ValueError:
                return None
    return None


def extract_images(message: dict, images_dir: Path) -> dict:
    """Replace inline image blocks with image_ref blocks pointing at
    ``images_dir/<sha256hex><ext>``. Non-image blocks pass through."""
    content = message.get("content")
    if not isinstance(content, list):
        return message
    images_dir.mkdir(parents=True, exist_ok=True)
    cleaned = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") == "image_ref":
            cleaned.append(block)
            continue
        decoded = _block_bytes(block)
        if decoded is None:
            cleaned.append(block)
            continue
        raw, mime = decoded
        digest = hashlib.sha256(raw).hexdigest()
        path = images_dir / f"{digest}{_MIME_EXT.get(mime, '.png')}"
        if not path.exists():
            path.write_bytes(raw)
        cleaned.append({"type": "image_ref", "path": path.name, "mime": mime})
    out = dict(message)
    out["content"] = cleaned
    return out


def hydrate_message(message: dict, images_dir: Path) -> dict:
    """Swap image_ref blocks back to base64 data URLs (for the LLM).
    Missing files pass through untouched."""
    content = message.get("content")
    if not isinstance(content, list):
        return message
    out_blocks = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "image_ref":
            path = images_dir / block.get("path", "")
            if path.exists():
                b64 = base64.b64encode(path.read_bytes()).decode()
                out_blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{block.get('mime', 'image/png')};base64,{b64}"},
                    }
                )
                continue
        out_blocks.append(block)
    out = dict(message)
    out["content"] = out_blocks
    return out


def message_text(data: dict) -> str:
    """Searchable text of a message: content (str or text blocks) + reasoning."""
    parts = []
    content = data.get("content")
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        parts.extend(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if data.get("reasoning_content"):
        parts.append(data["reasoning_content"])
    return "\n".join(p for p in parts if p)


# ---- writes ------------------------------------------------------------------


def add_message(
    engine, agent_id: str, message: dict, images_dir: Path | None = None,
    usage: dict | None = None,
) -> int:
    """Persist one message. Inline images are extracted to disk first, so the
    row carries image_ref blocks. Returns the new message id."""
    stored = extract_images(message, images_dir) if images_dir else message
    usage = usage or {}
    with Session(engine) as db:
        row = Message(
            agent_id=agent_id,
            data=stored,
            role=message.get("role", ""),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        db.add(row)
        db.flush()
        db.execute(
            text("INSERT INTO messages_fts(rowid, agent_id, role, text) VALUES (:r, :a, :role, :t)"),
            {"r": row.id, "a": agent_id, "role": row.role, "t": message_text(stored)},
        )
        db.commit()
        return row.id


def create_agent(engine, **fields) -> None:
    with Session(engine) as db:
        db.add(Agent(**fields))
        db.commit()


def lookup_or_create_prompt(engine, template: str, name: str = "crow-default") -> str:
    from coolname import generate_slug

    with Session(engine) as db:
        existing = db.query(Prompt).filter_by(template=template).first()
        if existing:
            return existing.id
        prompt_id = generate_slug(4)
        db.add(Prompt(id=prompt_id, name=name, template=template))
        db.commit()
        return prompt_id


# ---- reads -------------------------------------------------------------------


def get_agent(engine, agent_id: str) -> Agent | None:
    with Session(engine) as db:
        return db.query(Agent).filter_by(agent_id=agent_id).first()


def list_agents(engine, session_id: str | None = None) -> list[Agent]:
    with Session(engine) as db:
        q = db.query(Agent)
        if session_id is not None:
            q = q.filter_by(session_id=session_id)
        return q.order_by(Agent.agent_idx).all()


def get_prompt(engine, prompt_id: str) -> Prompt | None:
    with Session(engine) as db:
        return db.query(Prompt).filter_by(id=prompt_id).first()


def get_max_agent_idx(engine, session_id: str) -> int:
    with Session(engine) as db:
        rows = db.query(Agent.agent_idx).filter_by(session_id=session_id).all()
    return max((r[0] for r in rows), default=1)


def load_messages(
    engine, agent_id: str, hydrate: bool = False, images_dir: Path | None = None,
) -> list[dict]:
    with Session(engine) as db:
        rows = db.query(Message).filter_by(agent_id=agent_id).order_by(Message.id).all()
        msgs = [dict(r.data) for r in rows]
    if hydrate and images_dir:
        msgs = [hydrate_message(m, images_dir) for m in msgs]
    return msgs


def query_messages(
    engine,
    agent_ids: list[str],
    roles: list[str] | None = None,
    after: str | None = None,
    before: str | None = None,
    order: str = "asc",
    limit: int = 1_000_000,
    offset: int = 0,
) -> list[Message]:
    with Session(engine) as db:
        q = db.query(Message).filter(Message.agent_id.in_(agent_ids))
        if roles is not None:
            q = q.filter(Message.role.in_(roles))
        if after is not None:
            q = q.filter(Message.created_at > after)
        if before is not None:
            q = q.filter(Message.created_at < before)
        q = q.order_by(Message.id.asc() if order == "asc" else Message.id.desc())
        return q.offset(offset).limit(limit).all()


def list_sessions(engine, limit: int = 50, offset: int = 0) -> list[dict]:
    """Sessions ordered by most recent message activity (desc)."""
    with Session(engine) as db:
        rows = (
            db.query(
                Agent.session_id,
                func.max(Message.created_at),
                func.count(func.distinct(Message.id)),
                func.count(func.distinct(Agent.agent_id)),
            )
            .join(Message, Message.agent_id == Agent.agent_id, isouter=True)
            .group_by(Agent.session_id)
            .order_by(func.max(Message.created_at).desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        models = {}
        for a in db.query(Agent).all():
            models.setdefault(a.session_id, a.model_identifier)
    return [
        {
            "session_id": sid,
            "last_activity": last or "",
            "message_count": n_msg,
            "agent_count": n_agent,
            "model_identifier": models.get(sid, ""),
        }
        for sid, last, n_msg, n_agent in rows
    ]


def search_messages(
    engine,
    query: str,
    limit: int = 20,
    session_id: str | None = None,
    agent_idx: int | None = None,
    agent_ids: set[str] | None = None,
) -> list[dict]:
    """BM25 keyword search over message text (SQLite FTS5). Returns
    {message fields + session_id/agent_idx + score} dicts, best match first.
    ``score`` is the raw bm25 rank (lower = better)."""
    idx = {}
    with Session(engine) as db:
        for a in db.query(Agent).all():
            idx[a.agent_id] = (a.session_id, a.agent_idx)
    # Quote each token so arbitrary user input stays a valid FTS5 query
    # (implicit AND of phrases).
    match = " ".join(f'"{t}"' for t in query.split() if t)
    if not match:
        return []
    with engine.connect() as conn:
        hits = conn.execute(
            text(
                "SELECT rowid, bm25(messages_fts) AS rank FROM messages_fts "
                "WHERE messages_fts MATCH :q ORDER BY rank LIMIT :lim"
            ),
            {"q": match, "lim": limit * 4},
        ).fetchall()
    with Session(engine) as db:
        rows = db.query(Message).filter(Message.id.in_([h[0] for h in hits])).all()
    by_id = {r.id: r for r in rows}
    out = []
    for rid, rank in hits:
        row = by_id.get(rid)
        if row is None:
            continue
        sid, aidx = idx.get(row.agent_id, ("", 0))
        if session_id is not None and sid != session_id:
            continue
        if agent_idx is not None and aidx != agent_idx:
            continue
        if agent_ids is not None and row.agent_id not in agent_ids:
            continue
        out.append(
            {
                "id": row.id,
                "agent_id": row.agent_id,
                "session_id": sid,
                "agent_idx": aidx,
                "role": row.role,
                "created_at": row.created_at,
                "data": dict(row.data),
                "score": rank,
            }
        )
        if len(out) >= limit:
            break
    return out
