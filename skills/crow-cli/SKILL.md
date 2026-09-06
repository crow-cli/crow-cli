---
name: crow-cli
description: The crow-cli map — where the source lives, how a running agent was
  spawned, and how to change, upgrade, or repair crow-cli itself. Use when the
  task touches crow-cli's own code or install ("fix crow-cli", "upgrade
  crow-cli", "reinstall", "where is the source", "the checkout", "crow-cli
  init", "project agent", "why is my change not live", "self-heal", "the TUI
  spawns"), when a crow-cli spawn failed, or when you are an agent asked to
  repair a broken crow-cli. Also the entry point for the feedback loop
  (analysis/ideas files, the learn skill).
---

# crow-cli: the map

Crow is **source-first**. `uv tool install crow-cli && crow-cli init` installs
a bootloader and then clones the program:

```
~/.agents/crow/                     the config dir (--config-dir relocates all of it)
├── config.yaml  .env  crow.db      config, secrets, memory
├── prompts/system_prompt.jinja2    the character
├── ideas/                          harness analysis, one {agent-id}.md per compaction
└── src/
    ├── crow-cli/                   THE SOURCE. a git checkout of crow-cli/crow-cli
    └── crow-cli.github.io/         the site + skills source (sync-skills.py)

~/.agents/skills/crow-cli/          this skill, copied from src/crow-cli/skills/
```

## How the agent you are talking to was spawned

Resolution is project-first, exactly like skills
(`crow_cli.agent.prompt.skill_roots`):

1. `<cwd>/.agents/crow/agent.py` — the project's own agent (the repl-agent
   pattern: imports `crow_cli`, mutates `Config`, wires hooks, calls
   `run_agent`). Different compaction is a different creature.
2. `<cwd>/.agents/crow/src/crow-cli` — the project's own checkout. `crow-cli
   acp` **re-execs** into it (`uv --project <checkout> run crow-cli acp`), so
   the agent that answers is the one the repo ships.
3. `~/.agents/crow/src/crow-cli` — the global checkout. What the TUI spawns by
   default.
4. The installed crow-cli — a frozen binary's `acp`, or `-m crow_cli.agent.main`.

`--system` forces 4. `CROW_ACP_REEXEC=1` in the environment means "this
process IS the re-exec" and stops the walk. All of this lives in
`src/crow_cli/cli/source.py`; the TUI's launch string is built by
`crow_cli.tui.agent_servers.crow_agent`.

**Every fallback is loud.** If you see `crow-cli: No source checkout at ...` or
`... needs uv, which is not on PATH` on stderr, the agent you got is NOT the
one you asked for. Fix the cause; do not shrug at it.

## Changing crow-cli

Edit the checkout, not the installed tool:

```bash
cd ~/.agents/crow/src/crow-cli
git pull --ff-only origin main      # upgrade == git pull
$EDITOR src/crow_cli/...
uv --project . run pytest tests/unit -q
```

Pure-Python changes are **live immediately** for anything spawned via
`uv --project` — no reinstall, because uv runs the checkout in place.

Reinstalling only matters for the **global installed bootloader** (and for
`--system` runs):

```bash
uv tool install crow-cli --from ~/.agents/crow/src/crow-cli --python 3.14 --reinstall
```

Two reload boundaries inside a running agent, because they are different
processes:

| you changed | lives in | to pick it up |
|---|---|---|
| `src/crow_cli/tools/*.py` (the execute subtools) | the kernel subprocess | kernel **reset** |
| `src/crow_cli/mcp/execute/`, `src/crow_cli/agent/` | the agent/server process | full **restart** |

## When a spawn is broken

This skill is the BIOS: it is installed **globally** on purpose, because you
cannot fetch a skill from the broken thing you are repairing.

1. Reproduce the failure and capture the exact stderr.
2. Work in the checkout that failed — `<cwd>/.agents/crow/src/crow-cli` if
   there is one, else `~/.agents/crow/src/crow-cli`.
3. `uv --project . run pytest tests/unit -q` — is it the tree or the
   environment? Missing `uv`? Missing deps? A dirty checkout that will not
   fast-forward (`git status --porcelain`)?
4. Fix it, commit with the `Session-Id:` trailer, and only then fall back.
5. **One fix attempt.** Still broken → run the system agent (`--system`) and
   say so loudly. Never silently fall back forever; we would never know.

`crow-cli init` is idempotent and is always a safe repair for the global
scope: it fast-forwards both checkouts (leaving a dirty one alone), re-runs
`uv sync`, and reinstalls this skill.

## The feedback loop

Compaction produces critique; critique lands in files; something validates and
patches; the patched harness runs the next session. **The first half is built.
Nothing reads the files yet.**

Every compaction makes THREE LLM calls over the same history, not one. They
share a byte-identical message prefix (`compact._history_prefix`) and differ
only in the trailing prompt, so the provider's prompt-prefix cache pays for
passes two and three. All in `src/crow_cli/agent/compact.py`:

- **summary** — `COMPACTION_PROMPT`. Becomes the new generation's first
  message. The only one that touches the conversation.
- **analysis** — `ANALYSIS_PROMPT`, about **crow-cli itself**: the system
  prompt, the tools and their schemas, skills, compaction, memory, config,
  ACP, the TUI. Four sections: What worked well / What did not work / Bugs /
  Ideas. Evidence is mandatory — an item with no evidence gets deleted, not
  softened. Written to `~/.agents/crow/ideas/{agent-id}.md`.
- **ideas** — `IDEAS_PROMPT`, about **the project in cwd**: assumptions worth
  attacking, prior art to steal (named, real systems), directions nobody
  pointed at, what would make it obsolete, cheapest decisive experiments.
  Every idea must say what would prove it wrong. Written to
  `<cwd>/.agents/crow/ideas/{agent-id}.md`.

`{agent-id}` is the generation being **compacted**, not the new one — that is
the history the notes describe, and the id that joins them back to it in
`crow.db`. Each file opens with YAML frontmatter written by code, not by the
model: `kind`, `session`, `agent`, `model`, `cwd`, `generated`.

`write_reflections` **never raises**. By the time it runs the summary is
durable and the new agent row is in the db, so a provider timeout on a
critique must not cost the user their compaction. Each pass fails alone and is
logged. If a note is missing, look for `Compaction {kind} pass failed` in the
log — do not go hunting for a crash.

Two things worth knowing before you build on this:

- **Compaction is ~3× slower than it was.** Measured live at ~7 minutes for
  all three passes on a fast hosted model; a slow local model is worse, and
  the react loop emits no keepalive during it. If that ever needs fixing, the
  fix is to background the two reflections — NOT to add a hook fabric.
- **There is no lifecycle yet.** A note is written and never moves, so nothing
  distinguishes an untriaged critique from one that already landed. The
  planned `feedback/inbox/ → validated/ → accepted/ | rejected/ → landed/`
  tree (mv = state transition, ls = dashboard) is NOT BUILT, and the shipped
  paths are `ideas/`, not `feedback/`. Whoever builds the reader has to decide
  whether that convention replaces these paths or wraps them.

Precedence when triaging: **user corrections** (query the memory db for USER
MESSAGES — user feedback outranks agent suggestions absolutely) > recurring
friction across N sessions > single-session evidenced items > blue-sky ideas.
The `learn` skill is supposed to drive this and still needs rewriting; bench
instances come from crow-cli's actual workload distribution
(self-development tasks), not SWE-bench shapes.

## Reading the past

The memory db (`~/.agents/crow/crow.db`) is queryable with real SQL through the
`memory` subtool inside `execute`. For a long-running agent, keyword search is
the wrong tool — **pull everything the user said in a time range**:

```python
r = await memory("sql", """
SELECT m.id, m.created_at, json_extract(m.data,'$.content') AS content
FROM messages m JOIN agents a ON a.agent_id = m.agent_id
WHERE a.session_id = 'that-session-id' AND m.role = 'user'
ORDER BY m.id ASC
""")
print(r.rows)
for row in r.df.iter_rows(named=True):
    print(f"\n===== [{row['id']} {row['created_at'][:16]}] =====\n{row['content']}")
```

`mode="sql"` takes a raw statement — no bound parameters, so inline the id.
Users have far fewer messages than agents; that one query is usually the whole
brief. To find WHICH session, aggregate instead of keyword-searching — BM25
cannot answer "which session was huge and ended at 4am Friday":

```python
r = await memory("sql", """
SELECT a.session_id, a.cwd, count(*) n, min(m.created_at) first, max(m.created_at) last
FROM messages m JOIN agents a ON a.agent_id = m.agent_id
WHERE m.created_at >= '2026-09-04' AND m.created_at < '2026-09-06'
GROUP BY 1,2 ORDER BY n DESC LIMIT 15
""")
```
