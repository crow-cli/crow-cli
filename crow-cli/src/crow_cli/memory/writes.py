"""Write path: messages, agents, prompts."""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from .ids import parse_agent_id
from .messages import extract_images, message_text
from .models import Agent, Message, Prompt


def add_message(
    engine, agent_id: str, message: dict, images_dir: Path | None = None,
    usage: dict | None = None,
) -> int:
    """Persist one message. Inline images are extracted to disk first, so the
    row carries image_ref blocks. fork_idx is derived from the agent_id
    (schema v5 three-part format). Returns the new message id."""
    _, _, fork_idx = parse_agent_id(agent_id)
    stored = extract_images(message, images_dir) if images_dir else message
    usage = usage or {}
    with Session(engine) as db:
        row = Message(
            agent_id=agent_id,
            fork_idx=fork_idx,
            data=stored,
            role=message.get("role", ""),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        db.add(row)
        db.flush()
        db.execute(
            text(
                "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
                "VALUES (:r, :a, :role, :f, :t)"
            ),
            {
                "r": row.id,
                "a": agent_id,
                "role": row.role,
                "f": fork_idx,
                "t": message_text(stored),
            },
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
