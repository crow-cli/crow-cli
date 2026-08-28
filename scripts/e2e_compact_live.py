#!/usr/bin/env python
"""Live e2e drill: the /compact slash command against a REAL conversation.

Takes a real transcript out of the production crow.db, runs the actual
``/compact`` handler through ``Agent.prompt`` with the actual configured LLM, and
reads the result back over raw sqlite. The production database is copied to a
temp file first — every write lands on the copy, never on ~/.agents/crow/crow.db.

Real data is the point: transcripts contain tool calls, multi-block content and
giant terminal dumps, which is exactly the shape compaction has to survive. A
single oversized message (one 4.7 MB terminal capture was seen) is capped so the
slice fits a context window — structure stays as written, only payload length is
bounded, and the cap is reported.

Usage:
  uv --project . run python scripts/e2e_compact_live.py
  uv --project . run python scripts/e2e_compact_live.py --model qwen3.8-flash-next --messages 40
  uv --project . run python scripts/e2e_compact_live.py --agent some-session-3-1
"""

import argparse
import asyncio
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from acp.schema import TextContentBlock

from crow_cli.agent.main import AcpAgent
from crow_cli.agent.session import AgentSession
from crow_cli.config import Config, get_default_config_dir

PROD_DB = Path.home() / ".agents" / "crow" / "crow.db"
CHAR_CAP = 1200  # per message, so a single tool dump cannot eat the context


class Recorder:
    """ACP client surface: collect what the agent sends back."""

    def __init__(self):
        self.text: list[str] = []

    async def session_update(self, session_id, update):
        content = getattr(update, "content", None)
        for block in content if isinstance(content, list) else [content] if content else []:
            text = getattr(block, "text", "") or ""
            if text.strip():
                self.text.append(text)


def pick_agent(db: Path) -> tuple[str, int]:
    """The busiest agent in the database — most messages."""
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "select agent_id, count(*) from messages group by agent_id"
            " order by count(*) desc limit 1"
        ).fetchone()
    if not row:
        sys.exit(f"No messages found in {db}")
    return row[0], row[1]


def cap_message(message: dict, cap: int) -> tuple[dict, int]:
    """Bound one message's text payload; returns (message, chars saved)."""
    content = message.get("content")

    def clip(text: str) -> str:
        if len(text) <= cap:
            return text
        return text[:cap] + f"\n[… capped {len(text) - cap} chars by the drill]"

    saved = 0
    if isinstance(content, str):
        clipped = clip(content)
        saved = len(content) - len(clipped)
        message["content"] = clipped
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                clipped = clip(block["text"])
                saved += len(block["text"]) - len(clipped)
                block["text"] = clipped
    return message, saved


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="Model NAME from config.yaml")
    parser.add_argument("--agent", default=None, help="agent_id to compact (default: busiest)")
    parser.add_argument("--messages", type=int, default=30, help="History slice size")
    args = parser.parse_args()

    if not PROD_DB.exists():
        sys.exit(f"Production database not found at {PROD_DB}")

    tmpdir = Path(tempfile.mkdtemp(prefix="compact-drill-"))
    work_db = tmpdir / "crow.db"
    shutil.copy2(PROD_DB, work_db)
    print(f"[setup] copied {PROD_DB} -> {work_db} (prod is never written)")

    config = Config.load(get_default_config_dir())
    config.db_uri = f"sqlite:///{work_db}"

    agent_id, total = (args.agent, None) if args.agent else pick_agent(work_db)

    # Compaction always happens on the session HEAD: Agent.prompt resolves the
    # wire id to the newest agent_idx, so pointing the drill at an older
    # generation would compact something other than what we sliced. The agents
    # table gives us (session_id, agent_idx) without re-parsing the id.
    with sqlite3.connect(work_db) as conn:
        row = conn.execute(
            "select session_id, agent_idx from agents where agent_id=?", (agent_id,)
        ).fetchone()
        if not row:
            sys.exit(f"No agents row for {agent_id}")
        wire_id, idx = row
        head_idx = conn.execute(
            "select max(agent_idx) from agents where session_id=?", (wire_id,)
        ).fetchone()[0]
        if idx != head_idx:
            agent_id = next(
                r[0]
                for r in conn.execute(
                    "select agent_id from agents where session_id=? and agent_idx=?",
                    (wire_id, head_idx),
                )
                if r[0].endswith("-1")
            )
        total = conn.execute(
            "select count(*) from messages where agent_id=?", (agent_id,)
        ).fetchone()[0]

    session = await AgentSession.load(agent_id, memory_path=config.db_uri)
    print(f"[load ] {agent_id}: {total} stored messages ({session.model_identifier})")

    # Slice + cap: the newest `--messages` turns, each payload bounded.
    slice_ = list(session.messages[-args.messages :])
    saved = 0
    for index, message in enumerate(slice_):
        slice_[index], cut = cap_message(message, CHAR_CAP)
        saved += cut
    session.messages = slice_
    chars = sum(len(json.dumps(m, default=str)) for m in slice_)
    print(
        f"[slice] compacting the last {len(slice_)} messages: {chars:,} chars"
        + (f" ({saved:,} chars capped)" if saved else "")
    )
    roles = {}
    for message in slice_:
        roles[message.get("role")] = roles.get(message.get("role"), 0) + 1
    print(f"[slice] role mix: {roles}")

    model = config.llm.models.get(args.model) if args.model else next(
        iter(config.llm.models.values())
    )
    if model is None:
        sys.exit(f"Model {args.model!r} not in config.yaml")
    model_value = f"{model.provider_name}:{model.model_id}"

    agent = AcpAgent(config=config, hooks=[])
    recorder = Recorder()
    agent._conn = recorder
    agent._sessions[session.agent_id] = session
    agent._tools[session.session_id] = []
    agent._config_values[session.session_id] = {"model": model_value}
    print(f"[run  ] /compact with model {model_value}")

    response = await agent.prompt(
        [TextContentBlock(type="text", text="/compact")], session_id=session.session_id
    )
    for chunk in recorder.text:
        print(f"[agent] {chunk.strip()}")
    if response.stop_reason != "end_turn":
        print(f"[FAIL ] stop_reason={response.stop_reason}")
        return 1

    # Read the result back over raw sqlite, independent of the app's own reads.
    with sqlite3.connect(work_db) as conn:
        old_rows = conn.execute(
            "select count(*) from messages where agent_id=?", (agent_id,)
        ).fetchone()[0]
        new_id = f"{session.session_id}-{session.agent_idx + 1}-{session.fork_idx}"
        new_rows = conn.execute(
            "select role, data from messages where agent_id=? order by id", (new_id,)
        ).fetchall()

    # Dispatch appends the "/compact" message itself before running the handler,
    # so the old generation grows by exactly that one row — nothing else.
    print(f"[check] old generation: {total} -> {old_rows} rows on {agent_id}")
    if old_rows != total + 1:
        print("[FAIL ] compaction changed history beyond appending the /compact message")
        return 1
    if not new_rows:
        print(f"[FAIL ] no rows written for the new generation {new_id}")
        return 1

    def text_of(data: str) -> str:
        content = json.loads(data).get("content", "")
        if isinstance(content, list):
            return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
        return content or ""

    print(f"[check] new generation {new_id}: roles={[role for role, _ in new_rows]}")
    # The compacted history is the user message the summarizer produced; the
    # system row is the freshly rendered prompt and can be far longer.
    summary = "\n".join(text_of(data) for role, data in new_rows if role == "user")
    print(f"[check] summary: {len(summary):,} chars")
    print("[check] summary begins:")
    for line in summary.strip().splitlines()[:12]:
        print(f"    | {line}")

    ok = len(summary) > 100 and "Last messages:" in summary
    print(f"[{'PASS' if ok else 'FAIL'}] compaction produced a summary + recent-tail block")
    shutil.rmtree(tmpdir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
