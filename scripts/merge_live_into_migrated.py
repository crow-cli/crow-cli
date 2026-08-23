"""One-off: merge the LIVE v5 db (crow-98.db) into crow-migrated.db so the
cutover loses nothing. Message ids are shifted by the destination's max id;
FTS rows for the merged messages are rebuilt with the CURRENT extractor."""

import json
import sqlite3
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from crow_cli.memory.messages import message_text  # noqa: E402

LIVE = Path.home() / ".agents/crow/crow-98.db"
DST = Path.home() / ".agents/crow/crow-migrated.db"

src = sqlite3.connect(f"file:{LIVE}?mode=ro", uri=True)
dst = sqlite3.connect(DST)

src.execute("BEGIN")  # pin one snapshot — the live db keeps writing

offset = dst.execute("SELECT MAX(id) FROM messages").fetchone()[0]

prompts = src.execute(
    "SELECT id, name, template, created_at FROM prompts"
).fetchall()
agents = src.execute(
    "SELECT agent_id, session_id, agent_idx, fork_idx, forked_at, cwd, "
    "prompt_id, prompt_args, system_prompt, tool_definitions, request_params, "
    "model_identifier, status, created_at FROM agents"
).fetchall()
messages = src.execute(
    "SELECT id, agent_id, fork_idx, created_at, data, role, prompt_tokens, "
    "completion_tokens, total_tokens FROM messages ORDER BY id"
).fetchall()

# refuse on any collision rather than guessing
if dst.execute(
    "SELECT COUNT(*) FROM agents WHERE agent_id IN (%s)"
    % ",".join("?" * len(agents)),
    [a[0] for a in agents],
).fetchone()[0]:
    sys.exit("agent_id collision between live and migrated dbs")
if dst.execute(
    "SELECT COUNT(*) FROM prompts WHERE id IN (%s)"
    % ",".join("?" * len(prompts)),
    [p[0] for p in prompts],
).fetchone()[0]:
    sys.exit("prompt id collision between live and migrated dbs")

dst.execute("BEGIN")
dst.executemany(
    "INSERT INTO prompts(id, name, template, created_at) VALUES (?, ?, ?, ?)",
    prompts,
)
dst.executemany(
    "INSERT INTO agents(agent_id, session_id, agent_idx, fork_idx, forked_at, "
    "cwd, prompt_id, prompt_args, system_prompt, tool_definitions, "
    "request_params, model_identifier, status, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    agents,
)
dst.executemany(
    "INSERT INTO messages(id, agent_id, fork_idx, created_at, data, role, "
    "prompt_tokens, completion_tokens, total_tokens) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    [(m[0] + offset,) + m[1:] for m in messages],
)
dst.executemany(
    "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
    "VALUES (?, ?, ?, ?, ?)",
    [
        (m[0] + offset, m[1], m[5], m[2], message_text(json.loads(m[4])))
        for m in messages
    ],
)
dst.execute("COMMIT")
dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")

# verify
n_msg = dst.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
n_fts = dst.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
n_ag = dst.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
n_pr = dst.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
assert n_fts == n_msg, f"FTS {n_fts} != messages {n_msg}"
print(
    f"merged {len(prompts)} prompts, {len(agents)} agents, {len(messages)} "
    f"messages (ids +{offset}) from crow-98.db\n"
    f"crow-migrated.db now: {n_pr} prompts, {n_ag} agents, {n_msg} messages "
    f"(+FTS {n_fts})"
)
src.close()
dst.close()
