# TODO

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Sprint origin: 2026-09-05 planning session (this session:
intrepid-shaggy-bloodhound-from-venus). The pivot: crow-cli's revealed
preference (2886 agents, ~80% in crow's own repos, 144 agent-authored
commits joined to full session traces via Session-Id trailers) is that it
is an agent built for working on itself. Everything below makes that loop
self-driving: compaction produces critique, critique lands in files, a
maintainer agent validates and patches, the patched harness runs the next
session. Prior TUI sprint is COMPLETE (see git history); its two deferred
items are parked at the bottom.

## Items (unordered)

- [ ] **Three default compaction hooks** — callable hooks (the
      compact.py/main.py pattern of extension — NOT inheritance), all three
      fire at compaction, sharing the summary's prefix cache:
      1. `compact` — the existing summary handoff, promoted to be the FIRST
         default hook — co-equal with the other two, replaceable/extensible
         like any of them. Shipping as today's default is NOT protected
         status: the point of the refactor is that compaction is a hook
         surface (character of compaction = character of the agent, and
         project-level agents get to redefine it).
      2. `analysis` — introspective session critique. Same context as the
         summary, different task (NOT summary-minded). Evidence-mandatory
         items (quote/point at the moment in-session), taxonomy of
         surface-area × quality-type with escape hatches, impact,
         actionable+proposal. XML items, one file per agent generation
         (`{session_id}-{agent_idx}-analysis.xml` — compaction already cuts
         history into addressable agent rows; that is the natural unit,
         dedupe/incrementality are free).
      3. `ideas` — PROJECT-LEVEL strategic ideation. Get feedback from a
         smart model on what the PROJECT should be doing — interrogate the
         user's deeper desires/goals, NOT surface-level regurgitation of
         what the user said at every granular level. May run 1-2 forked
         queries ("how does the user feel about X") against memory to ground
         itself. Project-scoped: about the project, not crow-cli — unless
         the project IS crow-cli (likely, lol). Frontmatter on all
         ideas/critiques/suggestions files so they can be enumerated and
         regenerated fresh.
      Hooks are CORE DEFAULTS (like uv_project_hook: `hooks=None →
      defaults`, scripts opt out with `[]`) — this is too important to be
      background or opt-in. Promote `on_compact` from single callback to
      the constructor hook idiom; plumb through TurnCtx like
      hooks/snapshot_hooks already are.
- [ ] **Two-layer compaction** — soft compact hook at ~160k: inject "you now
      have ~20k tokens of context and ~15 tool calls of budget remaining"
      and fire off a react loop with existing tools for 5-7 turns where the
      agent chains terminal calls to analyze/ideate/wind down. Hard
      compaction endpoint at 180k (MAX_COMPACT_TOKENS). The analysis/ideas
      forks rely on PROMPT INSTRUCTIONS to stay read-only.
- [ ] **Feedback directory** — `~/.agents/crow/feedback/` global +
      project-local `$cwd/.agents/crow/feedback/` following the skill_roots
      resolution pattern (project scopes first, user scope last — already
      implemented for skills in prompt.py; copy it). Lifecycle as
      directories: inbox/ → validated/ → accepted/ | rejected/ → landed/
      (mv = state transition, ls = dashboard). Files carry frontmatter
      (surface, type, impact, evidence pointer, session/agent provenance).
      Rejected items keep a reason file — rejections teach too.
- [ ] **Bump web_search** — 1.6% of all tool calls is too low (terminal is
      50.5%, read 18.4%, edit 16.5%; query_memory family 3.3%, web_search
      548 calls total). Research must be a CORE part of learning/rubrics/
      meta-analysis: prompt mutation + an analysis-hook rubric dimension
      ("did the agent research before guessing?").
- [ ] **session/fork delegation pattern** — fork-of-self for context
      protection: instead of the parent reading a maybe-relevant file
      (always maximally increasing context), fork reads it and reports
      yes/no on relevance. Warm KV cache reuse (possible local model) for
      recursive language modeling instead of a fresh agent with cold cache.
      CRITICAL DETAIL (keep): the fork FALLS BACK TO BEFORE THE FORKED TOOL
      CALL — no infinity mirror. Read-only via prompt instructions. This is
      what we do in code already but not behind ACP — persist via the
      existing session/fork (UNSTABLE) path; fork_session's docstring
      already anticipates zero-tools interrogation forks.
- [ ] **More hook points in the codebase** — making more things hooks is the
      extension strategy. Known seams: session creation (make_agent_session
      is the single creation point — hook the seams it calls: template
      rendering, skills, agents-context; do NOT fork the factory), prompt
      assembly (notes-to-self surfacing = new prompt_args key + template
      block, selectively tagged to the waking agent by germaneness +
      priority), compaction (above), terminal guards (existing).
- [x] **Project-level agent surface** — syntactical sugar for creating
      project-level crow-cli repos. Discovery: `crow-cli acp` checks
      `$cwd/.agents/crow/` for a custom agent (repl-agent/main.py pattern:
      script sources crow_cli, mutates Config, wires hooks, `run_agent`)
      and/or `$cwd/.agents/crow/src/crow-cli` source checkout (spawn via
      `uv --project ... run crow-cli acp` — effectively editable, pure-code
      changes need no reinstall). `--system` flag forces the installed
      binary (default: prefer local when present). Re-exec sentinel env var
      so the spawned process doesn't re-spawn. Init pre-creates the venv
      (uv sync) so first open isn't a dep install.
      **BUILT** (6ab86502) in `crow_cli/cli/source.py`: `project_scope`
      walks `cwd` → git root exactly like `skill_roots` (nearest scope
      wins, a scope ABOVE the repo is somebody else's workspace);
      `reexec_into_project` `os.execvp`s into `agent.py` (inside the
      project's own uv env when it also has a checkout) or into the
      checkout; `CROW_ACP_REEXEC` is the sentinel; `--system` is on both
      `acp` and the bare TUI; `bootstrap` runs `uv sync`. The TUI's launch
      string (`tui/agent_servers.crow_agent`) now defaults to
      `uv --project <config_dir>/src/crow-cli run crow-cli acp`.
      **STILL OPEN:** the *creating* half of "syntactical sugar" — nothing
      scaffolds `$cwd/.agents/crow/agent.py` yet. Want a
      `crow-cli init --project` that writes a starter agent + a checkout.
- [ ] **Self-healing spawn** — project-level spawn fails → boot SYSTEM
      crow-cli whose entire prompt is "load the crow-cli skill and fix this
      error: {error}" + write a report to the bug directory. On end-turn,
      retry the ORIGINAL prompt against the project-level agent. ONE fix
      attempt: still broken → boot system with a loud note (never silently
      fall back forever — we'd never know). The skill is the BIOS: init
      must ALWAYS install it globally, because you can't fetch the skill
      from the broken thing you're fixing.
      **PARTIAL** (6ab86502): the BIOS half is done — `skills/crow-cli/`
      is versioned in the repo and init installs it globally, with a
      "when a spawn is broken" section and the one-fix-attempt rule. The
      loud-fallback half is done — every degradation (no checkout, no uv,
      failed exec) prints why to stderr, and a failed exec clears the
      sentinel so the caller can carry on. **NOT BUILT:** booting the
      fix-agent, the bug-directory report, and the retry-the-original-
      prompt-once loop.
- [ ] **Compaction × agent-creation coupling** — compaction and agent
      creation are inherently coupled (compaction mints agent rows; session
      creation defines their character) — couple them intelligently in the
      project-specific agent; configurable/pluggable through a
      repl-client-like script.
- [ ] **Memory SQL tool** — AUGMENTS query_memory, does not replace it.
      Progressive disclosure: parsimonious table descriptions in the tool
      description + a couple of example queries that say a LOT about table
      structure. Wrapper over the SQLAlchemy connection sending raw
      queries; READ-ONLY (get_ro_engine already exists in memory/db.py —
      use a real read-only connection, not just "pretty please"). Important
      enough to promote to a SKILL with code-running capabilities — it is a
      way to run SQL directly against the db through MCP. This also implies
      project-specific / session-specific MCP servers and a way to cleanly
      SWAP MCP servers during compaction (probably from a slash command).
- [ ] **ipykernel tool** — persistent Python execution. Launch an ipykernel
      on FIRST CALL (owned by the MCP server process — the client spawns
      and owns stdio MCP servers; transport decides lifetime: stdio =
      session-scoped kernel, http = persistent kernel host, "one server,
      many clients", multiplexed by session id riding call _meta like
      terminal cwd since 39e65ebb). Kernel re-used across calls; built-in
      RESET for fresh package installs / when importlib.reload won't cut
      it. Seed code: gist 1cdba586d9d57422bad5d91d320b75ae (CrowKernel —
      jupyter_client KernelManager, custom python path via
      kernel_spec.argv[0], persistent state, stdout/stderr/execute_result/
      error capture, ANSI-stripped tracebacks error-first, `!` shell
      escape). Default python = sys.executable of the crow-cli process (the
      uv tool venv — agent gets crow-cli's own deps); project venv
      override. Config mirrors the memory pattern: stdio default (like
      sqlite), http persistent host (like postgres db_uri).
- [ ] **learn skill rewrite** — stupid simple: "how to optimally update
      crow-cli and validate/test suggestions from agents' analysis/ideas."
      Reads feedback dirs; precedence stack: user corrections (query_memory
      on USER MESSAGES like crazy — user feedback outranks agent
      suggestions absolutely) > recurring friction (N sessions, same
      surface) > single-session evidenced items > blue-sky ideas. Bench
      instances drawn from crow-cli's actual workload distribution
      (self-development tasks), not SWE-bench shapes. Validates → patches
      source checkout → PR to crow-cli/crow-cli (code) or
      crow-cli.github.io (skills/docs).
      **"query_memory on USER MESSAGES like crazy" now has a concrete
      shape** (6ab86502, in the memory subtool's docstring and the
      crow-cli skill): for a long-running agent, don't keyword-search —
      pull EVERYTHING the user said, in order. A session has thousands of
      messages and its user has dozens; `role='user'` over one session (or
      a `created_at` window) is the whole brief in one query. And to find
      WHICH session, aggregate rather than search — bm25 cannot answer
      "which session was huge and ended at 4am Friday", `group by
      session_id` with min/max created_at answers it instantly. This is
      how the 2026-09-05 brainstorm was recovered after the harness's
      query_memory returned nothing.
- [ ] **Maintainer/evaluator agent** — **PARKED 2026-09-06, not now.**
      Nothing to maintain yet: the feedback directories it would triage
      do not exist (no analysis/ideas hooks write them), so a maintainer
      agent would be a creature with no food. Revisit after the
      compaction hooks and the feedback dir land and there is a real
      inbox with real items in it. The decision-log compaction idea was
      already contested in the brainstorm ("I hate the decision-log
      compaction idea") — do not resurrect it unexamined.
      Original scope: a Python script in the repl-agent
      pattern: sources crow_cli, points at the GLOBAL db, custom compact
      hook that compresses into a DECISION LOG (verdicts pending/rendered/
      in-flight) instead of task state — different compaction = different
      creature. Accepted feedback items get git worktrees (evidence →
      verdict → branch → PR as one walkable directory tree). First product
      of the programmable-agent surface AND maintainer of it.
- [x] **init clones + skill** — `crow-cli init` clones
      https://github.com/crow-cli/crow-cli into
      `~/.agents/crow/src/crow-cli` AND crow-cli/crow-cli.github.io (the
      skills source — sync-skills.py publishes ~/.agents/skills through
      it). Installs the crow-cli skill globally (map skill: where source
      lives, where feedback lives, resolution rule, reinstall command
      `uv tool install crow-cli --from ~/.agents/crow/src/crow-cli` —
      reinstall only matters for the GLOBAL agent; project-local uv-run
      agents are editable). Skill versioned inside the crow-cli repo so it
      evolves with the code; publish via sync-skills.py → PR to
      crow-cli.github.io.
      **BUILT** (6ab86502) as init Step 5 → `crow_cli.cli.source.bootstrap`:
      clones both repos on `main`, `uv sync`s the crow-cli checkout so the
      first spawn isn't a dep install, and copies `skills/crow-cli/` from
      the checkout into `~/.agents/skills/` (a SIBLING of the config dir,
      never inside it). Idempotent — a second run fast-forwards, a dirty
      checkout is left alone and reported `dirty`, an unreachable remote is
      `offline` and the checkout still counts. Never raises: a network blip
      must not throw away the config init just wrote; failures land in the
      report and on the console with a retry line. `--no-source` opts out.
      The skill is at `skills/crow-cli/SKILL.md` in the repo, so it evolves
      with the code and is published by the site's `sync-skills.py`.
      **STILL OPEN:** PLAN 6.3 — actually running sync-skills.py and
      opening the PR to crow-cli.github.io.
- [ ] **Long loops of work in the REPL are a TOKEN play, not just an
      expressiveness play** — the position, stated 2026-09-06: "now that
      we're pretty much abusing ACP to try to communicate edits and writes
      and things like that … an agent [could save] a lot of tokens by being
      able to do like long loops of work in the repl because it's so much
      more expressive than bash. c'mon."
      The accounting: every harness tool call costs a round trip — the
      model emits a JSON argument blob, waits, then reads a rendered
      result back. N edits to N files is N round trips and N renderings.
      One cell that loops over a glob, edits, and prints a summary is ONE
      round trip and one short rendering; the intermediate states never
      enter the context at all. Python has loops, conditionals, exception
      handling, dataframes and the whole stdlib; bash has `for f in *` and
      a hope. The subtool result objects (`EditResult.diff/.added`,
      `MemoryResult.df`) exist precisely so a cell can COMPUTE over them
      and print only the conclusion.
      This is the argument for the omni-tool endgame (#13) and it has a
      design consequence: **the ACP emission drain must stay cheap while
      the cell gets more expressive.** One row is still one synthetic tool
      call, so a 200-file loop is 200 ACP calls — the CLIENT sees every
      one even though the LLM does not. That is the right split (the human
      wants the audit trail, the model wants the summary) but it means the
      per-row emission cost is now on the hot path. Watch it.
      Counterweight, so this does not become a rant: a long cell is
      all-or-nothing. It cannot be interrupted mid-loop, cannot be
      permission-gated per file, and when it fails at iteration 190 the
      traceback is the only evidence. Bash's chattiness is partly a
      feature — it is 190 checkpoints. The answer is not "always loop", it
      is that the model should CHOOSE, and the system prompt should tell
      it the trade exists.
      **NOT BUILT.** Belongs with #13's system-prompt rewrite; the
      evidence to write it with is a token histogram of a real session
      (subtool_calls × messages.total_tokens, one SQL query).
- [ ] **v2 heartbeat janitor** (parked until ACP v2 persistent servers) —
      periodic maintenance agent over the feedback dirs: dedupe, merge,
      promote recurring items, cap counts, archive stale. TaskDelivery
      mailbox is the poke mechanism (already built; react_loop consult
      breakpoints pick deliveries up). v1 stdio agents die with their
      client; the janitor needs a pulse.

## Parked (from prior sprint, still open, explicitly not this sprint)

- [ ] Migrate the TUI's ACP client off the hand-rolled stack (tui/jsonrpc.py
      + tui/acp/ are toad legacy) onto the official acp SDK the way
      client/ already does. Cancel must preempt everything. User's call
      2026-08-29: fix it in the full python-sdk ACP-ification.
- [ ] TUI prompt attachments: image files must upload as ACP image content,
      not text (tui/prompt/resource.py mime branch bug; agent side already
      consumes image blocks).
