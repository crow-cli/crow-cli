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

- [x] **Three default compaction passes** — **BUILT 2026-09-06, as three
      passes, NOT as three hooks.** All three fire on every compaction and
      all three share the summary's prefix cache: `compact()` builds its
      message prefix through `_history_prefix(session)` and asks through
      `_ask_over_history(llm, session, config, prompt)`, so the three
      requests are byte-identical up to the trailing user message. That is
      the whole requirement — prefix caching is provider-side, so identical
      bytes are what buys the cache hit, and no hook fabric is needed to get
      them. Both existing call sites (the react threshold and `/compact`)
      picked the passes up with zero edits to react.py, slash.py or main.py.
      1. `compact` — unchanged. Still the summary handoff, still mints the
         new agent row, still fires `on_compact` exactly once.
      2. `analysis` — HARNESS-level critique, `ANALYSIS_PROMPT` in
         compact.py. Four markdown sections (What worked well / What did not
         work / Bugs / Ideas). Evidence mandatory — the prompt says an item
         with no evidence gets deleted, not softened. Draws the
         harness-vs-project line with one example of each, which turned out
         to be the single most important instruction in it: without it the
         model writes a project retrospective. Written by code, not asked of
         the model: YAML frontmatter (kind/session/agent/model/cwd/generated)
         at `<config_dir>/ideas/{agent-id}.md`.
      3. `ideas` — PROJECT-level strategic ideation, `IDEAS_PROMPT`. Five
         sections (Assumptions worth attacking / Prior art you should steal
         from / Directions nobody has pointed at / What would make this
         obsolete / Cheapest decisive experiments). Explicitly forbidden from
         being a summary or a TODO list; every idea must say what would prove
         it WRONG; the model is told outright to reach into its own weights
         for prior art, which is what produced named real systems (LSP
         rootUri negotiation, git's GIT_CEILING_DIRECTORIES, pytest's rootdir
         algorithm, direnv's .envrc allow-list, Feathers' characterization
         tests) instead of generic advice. Lands at
         `<cwd>/.agents/crow/ideas/{agent-id}.md`.
      Both notes are named for the generation being COMPACTED, not the new
      one — that is the history they read and the id a reader joins them back
      to. Both run inline on the same client; neither uses `rlm`/a fork.
      `write_reflections` NEVER raises: by the time it runs the summary is
      durable and the new agent row is in the db, so losing a critique to a
      provider timeout must not cost the user their compaction. Each pass
      fails alone and is logged.
      **STILL OPEN — the hook fabric, deliberately not built.** The plan was
      to promote `on_compact` to `compact_hooks=[...]` and make the summary
      itself the first co-equal hook, so that project-level agents could
      redefine compaction. That is five files of plumbing to pass arguments
      (`session`, `llm`, `config`, `logger`) that are ALREADY in scope inside
      `compact()`. An attempt was started and reverted on 2026-09-06. Build
      it only when there is a second consumer that needs to REPLACE a pass —
      i.e. when project-level agents actually want their own compaction
      character, not before.
      **STILL OPEN — the taxonomy.** The plan wanted XML items with a
      surface × quality-type enum (system_prompt/tool/skill/compaction/
      memory/config/acp/tui × helpful/friction/bug/suggestion/idea). Shipped
      as markdown sections instead: enough structure for a human reader, and
      the learn skill can parse headings if it ever needs to machine-read
      them. Revisit only if 2.2 turns out to need per-item fields.
      **COST, stated plainly:** compaction now makes three LLM calls instead
      of one and takes roughly three times as long — measured live on
      qwen3.8-max-preview at ~7 minutes for all three over a small history.
      The react loop emits no keepalive during it. If that hurts, the fix is
      to background the two reflections, NOT to build the hook fabric.
- [ ] **Two-layer compaction** — soft compact hook at ~160k: inject "you now
      have ~20k tokens of context and ~15 tool calls of budget remaining"
      and fire off a react loop with existing tools for 5-7 turns where the
      agent chains terminal calls to analyze/ideate/wind down. Hard
      compaction endpoint at 180k (MAX_COMPACT_TOKENS). The analysis/ideas
      forks rely on PROMPT INSTRUCTIONS to stay read-only.
      **More load-bearing now than it was:** a soft threshold that warns
      before the hard one means the user sees a budget notice instead of a
      silent ~3×-longer compaction. Also still blocked on settling the
      MAX_COMPACT_TOKENS three-way disagreement (190000 in config.py:286 and
      init_cmd.py:444, 180000 in defaults.py:425) — see PLAN "Where we are".
- [ ] **Feedback directory** — `~/.agents/crow/feedback/` global +
      project-local `$cwd/.agents/crow/feedback/` following the skill_roots
      resolution pattern (project scopes first, user scope last — already
      implemented for skills in prompt.py; copy it). Lifecycle as
      directories: inbox/ → validated/ → accepted/ | rejected/ → landed/
      (mv = state transition, ls = dashboard). Files carry frontmatter
      (surface, type, impact, evidence pointer, session/agent provenance).
      Rejected items keep a reason file — rejections teach too.
      **PARTIALLY OVERTAKEN:** the writers already exist and already write
      frontmatter (kind/session/agent/model/cwd/generated, from
      `compact._note_header`) — but to `ideas/`, not `feedback/inbox/`, and
      with no lifecycle at all. A note is written and never moves, so there
      is no way to tell an untriaged critique from one that already landed.
      Decide whether this convention REPLACES the shipped paths or wraps
      them before building the learn skill on top; writer and reader have to
      agree on the tree.
- [ ] **Bump web_search** — 1.6% of all tool calls is too low (terminal is
      50.5%, read 18.4%, edit 16.5%; query_memory family 3.3%, web_search
      548 calls total). Research must be a CORE part of learning/rubrics/
      meta-analysis: prompt mutation + an analysis-hook rubric dimension
      ("did the agent research before guessing?").
      **The prompt half is spent and did not work** — `defaults.py:136-143`
      already shouts "Use the web search tool for fucking everything / I PITY
      THE FOOL WHO DON'T USE WEB SEARCH" in every live prompt, and the rate
      is still 1.6%. **The rubric half is now unblocked and is a concrete
      edit:** add "did you research before guessing, and where did you guess
      instead?" to ANALYSIS_PROMPT's *What did not work* section. Re-measure
      the baseline first.
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
      **UNBLOCKED 2026-09-06 — there is real input now.** Every compaction
      writes an analysis to `~/.agents/crow/ideas/{agent-id}.md` and ideas to
      `<cwd>/.agents/crow/ideas/{agent-id}.md` (markdown with code-written
      YAML frontmatter, NOT the XML/`feedback/inbox/` shape this item
      describes — see the compaction item above). The first live-verified
      analysis already contains four actionable harness findings: the edit
      tool's uniqueness default is rename-hostile, `replace_all` is advertised
      only through the error string and not the schema, FILE_SYSTEM_GUIDELINES'
      "consider using sed" is worse advice than edit+replace_all, and the
      crow-cli skill trigger misfires on ordinary edits to its own source
      tree. A dry-run triage of those four is the concrete first Verify.
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
