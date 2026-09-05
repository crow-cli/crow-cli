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
      1. `compact` — the existing summary handoff. Untouchable. The user is
         extremely happy with the compaction prompt/algorithm; riff AROUND
         it, never mutate it casually.
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
- [ ] **Project-level agent surface** — syntactical sugar for creating
      project-level crow-cli repos. Discovery: `crow-cli acp` checks
      `$cwd/.agents/crow/` for a custom agent (repl-agent/main.py pattern:
      script sources crow_cli, mutates Config, wires hooks, `run_agent`)
      and/or `$cwd/.agents/crow/src/crow-cli` source checkout (spawn via
      `uv --project ... run crow-cli acp` — effectively editable, pure-code
      changes need no reinstall). `--system` flag forces the installed
      binary (default: prefer local when present). Re-exec sentinel env var
      so the spawned process doesn't re-spawn. Init pre-creates the venv
      (uv sync) so first open isn't a dep install.
- [ ] **Self-healing spawn** — project-level spawn fails → boot SYSTEM
      crow-cli whose entire prompt is "load the crow-cli skill and fix this
      error: {error}" + write a report to the bug directory. On end-turn,
      retry the ORIGINAL prompt against the project-level agent. ONE fix
      attempt: still broken → boot system with a loud note (never silently
      fall back forever — we'd never know). The skill is the BIOS: init
      must ALWAYS install it globally, because you can't fetch the skill
      from the broken thing you're fixing.
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
- [ ] **Maintainer/evaluator agent** — a Python script in the repl-agent
      pattern: sources crow_cli, points at the GLOBAL db, custom compact
      hook that compresses into a DECISION LOG (verdicts pending/rendered/
      in-flight) instead of task state — different compaction = different
      creature. Accepted feedback items get git worktrees (evidence →
      verdict → branch → PR as one walkable directory tree). First product
      of the programmable-agent surface AND maintainer of it.
- [ ] **init clones + skill** — `crow-cli init` clones
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
