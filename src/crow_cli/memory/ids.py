"""agent_id format — schema v5: "{session_id}-{agent_idx}-{fork_idx}".

All three parts are 1-based; the trunk carries fork_idx=1 (the "pointless
-1" that keeps every id uniform). Session ids are coolnames and CONTAIN
hyphens, so parsing always goes from the right.
"""


def build_agent_id(session_id: str, agent_idx: int, fork_idx: int = 1) -> str:
    return f"{session_id}-{agent_idx}-{fork_idx}"


def parse_agent_id(agent_id: str) -> tuple[str, int, int]:
    """Split an agent_id into (session_id, agent_idx, fork_idx).

    Raises ValueError on malformed ids — e.g. an unmigrated v4 two-part
    agent_id. Fail fast rather than route to the wrong session.
    """
    try:
        session_id, idx_s, fork_s = agent_id.rsplit("-", 2)
        return session_id, int(idx_s), int(fork_s)
    except (ValueError, AttributeError) as e:
        raise ValueError(
            f"malformed agent_id (want '<session>-<idx>-<fork>', got {agent_id!r}) — "
            "if this is a v4 database, run the schema-v5 migration first"
        ) from e


def wire_session_id(agent_id: str) -> str:
    """The ACP wire sessionId an agent is addressed by.

    The trunk (fork_idx=1) is addressed by its bare session_id; a fork is
    addressed by its full agent_id. State dicts, session_update tags and
    upstream ACP calls all key on this.
    """
    session_id, _, fork_idx = parse_agent_id(agent_id)
    return agent_id if fork_idx > 1 else session_id
