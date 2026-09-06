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
├── feedback/                       inbox/ validated/ accepted/ rejected/ landed/
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

Compaction produces critique; critique lands in files; a maintainer agent
validates and patches; the patched harness runs the next session.

- `feedback/inbox/` — `{ts}_{session_id}-{agent_idx}_analysis.xml` and
  `..._ideas.xml`, written by the compaction hooks. Global
  (`~/.agents/crow/feedback/`) and project-local (`<cwd>/.agents/crow/feedback/`).
- Lifecycle **is** directories: `inbox/ → validated/ → accepted/ | rejected/ →
  landed/`. `mv` is the state transition, `ls` is the dashboard. Rejected items
  keep a reason file — rejections teach too.
- Precedence when triaging: **user corrections** (query the memory db for USER
  MESSAGES — user feedback outranks agent suggestions absolutely) > recurring
  friction across N sessions > single-session evidenced items > blue-sky ideas.
- The `learn` skill drives this. Bench instances come from crow-cli's actual
  workload distribution (self-development tasks), not SWE-bench shapes.

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
