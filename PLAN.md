# PLAN — the self-improving loop (tentative)

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Crow-cli's revealed preference (2886 agents, ~80% in crow's own repos, 144
agent-authored commits joined to full traces via Session-Id trailers): it
is an agent built for working on itself. This plan makes the improvement
loop self-driving: compaction produces critique → critique lands in files
→ maintainer agent validates and patches → patched harness runs the next
session. TODO.md has the unordered scope; this file orders it.

### Build/test gate
Floor after each step: `uv --project . run pytest tests/unit -q`.
Full gate: `./run_tests.sh` (unit + integration + e2e live LLM).
Commit at each green checkpoint with the Session-Id trailer.

### Ground rules carried by every phase
- Extension is HOOKS (callables passed at construction), never inheritance.
- Compaction is a hook surface: the existing summary pass becomes the
  FIRST default hook, co-equal and replaceable like the rest —
  extensible, never sclerotic.
- Analysis/ideas output is FOREGROUND (never background — too important),
  files over db rows (ls is the interface), evidence mandatory.
- User corrections outrank agent suggestions absolutely.

## Where we are (2026-09-06, verified against the code, not the docs)

Two tracks ran in parallel and only one of them is this plan's. The
**execute/omni-tool track** (EXECUTE_TODO.md, the `jupyter-kernel-tool`
branch's entire git log) is nearly done. The **self-improving loop track**
(Phases 1-2 below) has not been started: zero lines of code.

| Phase | Status | Evidence |
|---|---|---|
| 1 — compaction hooks, analysis, ideas | **NOT STARTED** | `compact.py:130` is still `on_compact: callable = None`, fired at `:211`. No `compact_hooks`, no `ANALYSIS_PROMPT`, no `IDEAS_PROMPT`, no soft threshold anywhere in `src/`. |
| 2 — feedback dir, learn rewrite, web_search | **NOT STARTED** (2.3's prompt half already existed) | `rg -l feedback src/crow_cli` → nothing. `~/.agents/skills/learn` is still the old bench-testing skill. |
| 3 — memory SQL tool + skill | **3.1 DONE, differently than planned**; 3.2/3.3 not started | Landed as the `memory` SUBTOOL (`tools/memory.py`, mode="sql", real read-only conn, polars), not as an MCP tool next to query_memory. No companion skill. |
| 4 — ipykernel tool | **DONE** | `mcp/execute/{kernel,main}.py`; EXECUTE_TODO steps 1-9 all `[x]`; `_kernels` session-keyed registry at `main.py:25`. |
| 5 — project agent surface, self-healing | **5.1 DONE, 5.2 PARTIAL, 5.3 NOT STARTED** | `cli/source.py` (6ab86502). No fix-agent boot, no bug report, no retry. No `notes_to_self`, no seams in `make_agent_session`. |
| 6 — maintainer, init clones, publishing | **6.2 DONE, 6.1 PARKED, 6.3 NOT STARTED** | init Step 5 → `source.bootstrap`; `skills/crow-cli/SKILL.md`. Never published. |
| 7 — fork delegation | **~80% DONE, unticked** | 10a/10b `[x]`; `tools/rlm.py` really calls `SubagentDriver.fork_session(message_offset=, rlm_depth=)` and was dogfooded live 4×. No e2e (10d). Two pieces designed-not-written (10e). |

**The gap that matters:** Phases 1-2 are the actual thesis — compaction
produces critique, critique lands in files, the patched harness runs the
next session. Everything built so far is the *instrumentation* (a REPL, a
memory db you can SQL, forks you can delegate to, a source checkout you can
patch). None of it yet produces a single byte of self-critique. Phase 1.1
is the keystone: it is small, it unblocks 1.2, 1.3, 1.4, 2.1 and 2.3, and
it is the only item that changes what a session LEAVES BEHIND.

**Documented vs not.** Documented: TODO.md (unordered scope), this file
(ordered), EXECUTE_TODO.md (~1500 lines, the execute track + the B1-B6 bug
section), `skills/crow-cli/SKILL.md` (the map/BIOS skill), AGENTS.md.
Documented only as of today: the REPL-token-savings position (TODO.md), the
"pull everything the user said in a time range" technique (TODO #12 + the
memory subtool docstring + the skill). Still undocumented anywhere but here:
the `MAX_COMPACT_TOKENS` disagreement below.

**Found while verifying, not yet fixed:** `MAX_COMPACT_TOKENS` has three
values. The `Config` dataclass default is 190000 (`config.py:286`),
`crow-cli init` writes 190000 (`init_cmd.py:444`), and the `CONFIG_YAML`
template that `config.py:48` writes for a bootstrapped-not-init'd dir says
180000 (`defaults.py:425`). TODO.md's two-layer plan names 180000 as the
hard endpoint. Two install paths, two ceilings. Pick one before building
1.4 on top of it.

## Phase 1 — compaction hook fabric + the analysis/ideas passes

**Status: NOT STARTED. This is the keystone — everything in Phase 2 depends
on 1.1/1.2, and nothing in `src/` implements any of it.**

1.1 Promote `on_compact` from single callback to the constructor hook
    idiom: `AcpAgent(config, hooks=..., compact_hooks=...)`, plumbed
    through react_loop/TurnCtx exactly like hooks/snapshot_hooks. The
    summary pass ITSELF becomes the first default compact_hook, with
    analysis/ideas as sibling hooks — three co-equal callables. The two
    existing call sites (react threshold, /compact) keep working.
    Verify: existing tests green + unit test asserting multiple hooks fire
    in order with (old_agent_id, new_session).
    **Status: NOT STARTED.** Verified shape today: `compact.py:130`
    `on_compact: callable = None`, fired once at `compact.py:211-212`;
    callers are `react.py:699/866`, `slash.py:71/89`, and the closure
    defined at `main.py:933`. Three call sites, not two — `slash.py`'s
    /compact path is the one the plan text misses.
1.2 `analysis` default hook: same message prefix as the summary pass
    (shared prefix cache, fired alongside it), ANALYSIS_PROMPT appended
    instead of COMPACTION_PROMPT. Output: XML items, each with surface
    ({system_prompt, tool, skill, compaction, memory, config, acp, tui,
    other}), type ({helpful, friction, bug, suggestion, idea, other}),
    impact, evidence (quote/turn pointer — NO evidence, no item),
    actionable+proposal. One file per agent generation:
    `feedback/inbox/{ts}_{session_id}-{agent_idx}_analysis.xml`.
    Verify: live compaction (or /compact on a real session) produces a
    parseable file; unit tests pin the XML schema.
    **Status: NOT STARTED.** No `ANALYSIS_PROMPT` in the tree. Blocked on
    1.1 and on 2.1 (it needs somewhere to write).
1.3 `ideas` default hook: project-level strategic ideation prompt —
    interrogate deeper goals, not surface regurgitation; frontmatter for
    enumeration/regeneration; `{ts}_{session_id}-{agent_idx}_ideas.xml`.
    Verify: file lands with valid frontmatter; prompt includes the
    project-not-crow-cli scoping rule.
    **Status: NOT STARTED.** Same blockers as 1.2. Note this is the hook
    that would use `rlm` — the fork machinery it needs is already built
    and dogfooded (Phase 7).
1.4 Two-layer thresholds: soft compact hook at ~160k (budget notice +
    5-7 turn wind-down react loop with existing tools), hard endpoint at
    MAX_COMPACT_TOKENS. Read-only behavior for analysis/ideas forks via
    prompt instructions.
    Verify: unit tests on threshold resolution (per-model
    max_compact_tokens still wins); live eyeball of the soft notice.
    **Status: NOT STARTED**, and see the `MAX_COMPACT_TOKENS`
    disagreement in "Where we are" above — settle it first. Per-model
    `max_compact_tokens` resolution already exists (`config.py:215-224`)
    and must keep winning.

## Phase 2 — feedback directory + learn skill rewrite

**Status: NOT STARTED. 2.1 is the precondition for 1.2/1.3 having anywhere
to write, so it is the cheapest useful thing to build next.**

2.1 Feedback dir convention: global `~/.agents/crow/feedback/` +
    project-local resolution copied from skill_roots (project scopes
    first, user scope last). Lifecycle dirs inbox/validated/accepted/
    rejected/landed. Frontmatter schema shared by analysis/ideas files.
    Verify: ls-able tree after a live compaction; schema doc in repo.
    **Status: NOT STARTED** — `rg -l feedback src/crow_cli` returns
    nothing. The resolution pattern to copy now has a second working
    example besides `skill_roots`: `cli/source.project_scope` (6ab86502)
    walks cwd → git root for `.agents/crow`, which is exactly the shape
    the feedback dirs want. Reuse `prompt.ancestors` (renamed from
    `_ancestors` today because it is the shared scope walk now).
2.2 learn skill rewrite (in ~/.agents/skills/learn, then publish): stupid
    simple — read feedback dirs, precedence stack (user corrections from
    query_memory on USER MESSAGES > recurring friction > evidenced items >
    ideas), validate (evidence → reproduce → bench), patch, PR. Bench
    instances drawn from the real workload distribution.
    Verify: skill renders in catalog; one dry-run pass over existing
    inbox items produces sensible triage.
    **Status: NOT STARTED.** `~/.agents/skills/learn/SKILL.md` is still
    the old bench-testing skill (two incidental "feedback" mentions); the
    brainstorm's own note stands — "the learn skill, which we've never
    actually loaded". The precedence stack's top rung now has a concrete
    shape, written into TODO #12, the memory subtool's docstring and the
    crow-cli skill: don't keyword-search a long-running agent, pull
    `role='user'` over the session or a `created_at` window. Blocked on
    2.1 (there is no inbox to read).
2.3 Bump web_search: prompt mutation + analysis rubric dimension
    ("did the agent research before guessing?").
    Verify: diff reviewed; next session's tool histogram shows movement
    (baseline: 548 calls / 1.6%).
    **Status: HALF-SPENT, and the half that is done did not work.** The
    prompt mutation ALREADY EXISTS — `defaults.py:136-143` is an
    `<EXTERNAL_SERVICES>` block reading "Use the web search tool for
    fucking everything / I PITY THE FOOL WHO DON'T USE WEB SEARCH", and it
    is in every live prompt right now. web_search is still 1.6%. Shouting
    is a spent lever; the rubric dimension is the untried one, and it is
    blocked on 1.2. Re-measure the baseline before claiming movement —
    one SQL query over `subtool_calls`/tool-call args.

## Phase 3 — memory SQL tool + skill

**Status: 3.1 DONE but by a different route than written here; 3.2/3.3 not
started. This phase's text is now partly wrong — read the status lines.**

3.1 New MCP tool in crow-mcp (next to query_memory, augmenting not
    replacing): raw SQL over a REAL read-only connection (get_ro_engine).
    Tool description = parsimonious table descriptions + example queries
    that reveal structure (progressive disclosure).
    Verify: mcp tests; write attempts rejected at the connection level.
    **Status: DONE, as a SUBTOOL, not an MCP tool.** `tools/memory.py` —
    `await memory("list"|"search"|"sql", ...)`, returns a `MemoryResult`
    with a polars `.df`, over a real read-only connection, with the
    progressive-disclosure docstring (v5 schema + example queries) exactly
    as specified. It is reachable only from inside an `execute` cell,
    which is the Phase-4 route rather than the crow-mcp route this step
    named; the old MCP `query_memory`/`query_session` tools are still
    registered, so "augments, does not replace" holds. Tests:
    `tests/unit/test_tools_memory.py`. This is the better outcome — it is
    the direction step 13 wants — but it means the SQL tool is invisible
    to any agent that has not been told `execute` exists.
3.2 Companion skill (SQL-against-the-db-through-MCP = a way to run code).
    Verify: skill in catalog; a fresh agent can answer a schema question
    using only the skill + tool.
    **Status: NOT STARTED.** No memory/SQL skill in `~/.agents/skills`.
    Partial cover arrived today inside `skills/crow-cli/SKILL.md` ("Reading
    the past": the user-message pull and the session-finding aggregate),
    but that is a section of the map skill, not the standalone skill this
    step asks for, and it is not published.
3.3 Design note for later: project/session-specific MCP servers and
    swapping MCP servers during compaction (probably slash command).
    Captured in TODO; not built this phase.
    **Status: NOT STARTED, correctly.** Note the coupling to 6ab86502:
    `get_session_mcp_servers` is now consulted on the parent's WIRE id by
    `rlm`'s child supply, so a project-specific agent that changes the MCP
    set has a working precedent to copy.

## Phase 4 — ipykernel tool

**Status: DONE — and it grew well past this text. EXECUTE_TODO.md is the
real record (~1500 lines); this phase is a stub of it.**

4.1 Transplant CrowKernel (gist 1cdba586d9d57422bad5d91d320b75ae) into
    crow-mcp: kernel launched on first call, owned by the MCP server
    process, reused across calls; python = sys.executable by default,
    project venv override; reset/reload subcommand.
    Verify: state persists across two tool calls (x=42; print(x));
    error-first formatting; `!` escape; reset clears state.
    **Status: DONE**, then some. `mcp/execute/{kernel,main}.py` plus a
    whole subtool ecosystem in `crow_cli/tools/` (edit, write, fs, web,
    vision, memory, rlm, register, results) with a per-cell identity rail,
    a `subtool_calls` table, and an ACP emission drain that renders one
    synthetic tool call per row. EXECUTE_TODO steps 1-9 are all `[x]`.
    Six bugs found by dogfooding `rlm` over it are fixed in 8210b39b
    (B1-B6, documented in EXECUTE_TODO.md).
    **Still open on this track:** 9b (the FTS index hole — `messages_fts`
    cannot see tool_calls, so ~21% of the live db is invisible to bm25),
    9d (leaked tasks in test_cancel_under_load), 10d (rlm e2e), 11 (`!`
    lines → the terminal backend directly), 12 (ACP v2 terminal-type
    streaming), 13 (THE ENDGAME: one tool, `help()` as the just-in-time
    schema, system prompt rewritten around it).
4.2 Transport lifetime: stdio = session-scoped (default); http mode
    ("one server, many clients") gets a session-keyed kernel registry
    (session id rides call _meta, the 39e65ebb pattern).
    Verify: two concurrent http sessions get isolated kernels.
    **Status: DONE.** `_kernels: dict[str, CrowKernel]` at
    `mcp/execute/main.py:25`, keyed by `_kernel_context(ctx)`, with
    `shutdown_all` and a reset path that pops the key.

## Phase 5 — project-level agent surface + self-healing

**Status: 5.1 DONE today (6ab86502), 5.2 PARTIAL, 5.3 NOT STARTED.**

5.1 Discovery + spawn: `$cwd/.agents/crow/` custom agent script /
    `src/crow-cli` checkout → `uv --project ... run crow-cli acp`;
    `--system` opts out; re-exec sentinel; init pre-syncs the venv.
    Verify: project with a checkout runs from source; sentinel prevents
    re-spawn loop.
    **Status: DONE** (6ab86502). `crow_cli/cli/source.py`:
    `project_scope` walks cwd → git root like `skill_roots`;
    `reexec_into_project` `os.execvp`s into `<scope>/agent.py` (inside the
    project's own uv env when it also has a checkout) or into the checkout;
    `CROW_ACP_REEXEC` is the sentinel and is CLEARED again if the exec
    fails, so a failed re-exec does not poison the caller; `--system` is on
    both `acp` and the bare TUI; `bootstrap` runs `uv sync`. The TUI's
    launch string now defaults to the GLOBAL checkout too. Every fallback
    is loud on stderr.
    Verify, and it is verified: `tests/unit/test_source.py` (21, incl. a
    real `execvp` in a real subprocess), `tests/integration/
    test_acp_project_reexec.py` (4, the real CLI), `tests/e2e/
    test_source_first_spawn.py` (init → clone → uv sync → spawn → ACP
    initialize against a checkout of this repo).
    **Still open:** nothing scaffolds a project agent. The "syntactical
    sugar for CREATING project-level crow-cli repos" half of TODO #7 — a
    `crow-cli init --project` that writes a starter `.agents/crow/agent.py`
    and optionally a checkout.
5.2 Self-healing: spawn fails → system agent with the fix prompt ("load
    the crow-cli skill and fix this error: {error}") + bug-dir report →
    retry original prompt ONCE → still broken = system boot with loud
    note. Verify: deliberately broken checkout exercises the full path.
    **Status: PARTIAL** (6ab86502). Built: the BIOS half — the skill is
    versioned in the repo at `skills/crow-cli/SKILL.md` and init installs
    it GLOBALLY, with a "when a spawn is broken" procedure and the
    one-fix-attempt rule written into it. Built: the loud-fallback half —
    no checkout, no `uv`, or a failed exec all print why to stderr and
    carry on in-process. NOT built: booting the fix-agent, the bug-dir
    report, and retrying the original prompt once. The bug dir does not
    exist yet either (that is 2.1's tree).
5.3 More hook points: session-creation seams (template/skills/agents-
    context — hook the seams, never fork the factory), notes-to-self
    surfacing as a prompt_args block with priority/germaneness filtering.
    Verify: a repl-agent-pattern script overrides character without core
    changes.
    **Status: NOT STARTED.** `make_agent_session` (`session.py:573`) takes
    no hooks; `notes_to_self` appears nowhere in `src/`. The verify clause
    is half-true by accident: a repl-agent-pattern script CAN already
    override character without core changes, because it builds its own
    `Config` and its own `AcpAgent` — that is what `sandbox/repl-agent`
    does and what 5.1 now spawns. What it cannot do is hook the SEAMS.

## Phase 6 — maintainer agent + init clones + publishing

**Status: 6.2 DONE today, 6.1 PARKED today, 6.3 NOT STARTED.**

6.1 Maintainer/evaluator script (repl-agent pattern, global db, decision-
    log compact hook, worktrees under accepted/ items).
    Verify: it triages a real inbox and opens (or stages) a fix.
    **Status: PARKED (2026-09-06), deliberately not now.** There is
    nothing to maintain: the feedback directories it would triage do not
    exist because 1.2/1.3/2.1 are unbuilt, so a maintainer agent would be
    a creature with no food. Revisit once there is a real inbox with real
    items in it. The decision-log compaction idea was also contested in
    the brainstorm itself ("I hate the decision-log compaction idea") — do
    not resurrect it unexamined.
6.2 `crow-cli init` clones crow-cli + crow-cli.github.io into
    `~/.agents/crow/src/`, installs the crow-cli map skill globally
    (the BIOS — always global).
    Verify: fresh config dir exercises init end-to-end.
    **Status: DONE** (6ab86502) as init Step 5 → `source.bootstrap`.
    Clones both repos on `main`, `uv sync`s the crow-cli checkout so the
    first spawn is not a dep install, copies `skills/crow-cli/` into the
    skills root (a SIBLING of the config dir, never inside it).
    Idempotent: a second run fast-forwards, a dirty checkout is left alone
    and reported `dirty`, an unreachable remote is `offline` and the
    checkout still counts. Never raises — a network blip must not throw
    away the config init just wrote; failures land in the report and on
    the console with a retry line. `--no-source` opts out.
    Verify, and it is verified: `tests/unit/test_init_source.py` (11, real
    git clones of local remotes + a real `uv sync`) and the e2e above.
6.3 Publish skill: sync-skills.py → PR to crow-cli.github.io.
    Verify: crow-ai.dev/skills/<name>/SKILL.md resolves after deploy.
    **Status: NOT STARTED.** The site checkout is cloned and
    `sync-skills.py` is in it, so the mechanism is on disk; nobody has run
    it. Note it publishes `~/.agents/skills`, so the skill has to be
    INSTALLED globally first (6.2 does that) before it can be published.

## Phase 7 — fork delegation pattern (read-only forks)

**Status: ~80% DONE and dogfooded live, but EXECUTE_TODO's 10c checkbox is
still unticked and 10d (the e2e) does not exist.**

7.1 session/fork-based relevance checks: fork reads the maybe-relevant
    file, reports yes/no; parent context stays slim; fork FALLS BACK TO
    BEFORE THE FORKED TOOL CALL (no infinity mirror); warm-KV reuse.
    Verify: a forked interrogation completes with zero-tools and the
    parent history shows no mirror recursion.
    **Status: MOSTLY DONE, as `rlm`.** EXECUTE_TODO 10a `[x]` is the
    message-granular cut plus the snap that keeps a delegate from
    inheriting its own delegation (the "no infinity mirror" clause);
    10b `[x]` is the depth budget riding the identity rail's `prompt_args`
    (not a column — `create_database` is `create_all`, so a column means a
    migration against the live 1.3GB db). 10c's code EXISTS and works:
    `tools/rlm.py` calls `SubagentDriver.fork_session(message_offset=,
    rlm_depth=)`, blocking and async, and was dogfooded live four times
    (one fork at 6.5 min on the local model, one at 46s on
    `qwen3.8-max-preview`). Warm-KV reuse is not a separate feature — it
    is what forking the prefix gets you.
    **Still open:** 10c's checkbox is unticked; 10d (a real child-agent
    subprocess e2e asserting the delegation group is ABSENT from the
    child's own view) does not exist; 10e is partial — B1-B6 are fixed
    (8210b39b) but the two DEFERRED pieces are designed-not-written:
    view-side redaction of delegations deeper than the cut, and
    fork-of-fork (the `forked_at` = `"{source_agent_id}:{message_id}"`
    format extension that would let the depth budget rise above 1).
    Read-only-ness of the fork is by PROMPT INSTRUCTION, not enforcement.

## Parked
- **Maintainer/evaluator agent** (was Phase 6.1) — parked 2026-09-06. No
  inbox to triage until 1.2/1.3/2.1 exist; the decision-log compaction
  idea was contested in the brainstorm itself.
- v2 heartbeat janitor (needs ACP v2 persistent servers; TaskDelivery is
  the poke).
- TUI items from the prior sprint (see TODO.md parked section).

## Research notes — what the world is doing (2026-09-05, don't redo)

Every capability in this plan is in the air; none of it is ours by
invention. That's the point — the claim is composition + self-application,
not novelty.

- **Self-improving harnesses are THE 2026 topic.** Lilian Weng, "Harness
  Engineering for Self-Improvement" (lilianweng.github.io, Jul 2026);
  arXiv 2606.09498 "Self-Harness: Harnesses That Improve Themselves"
  (harness design is model-specific; human expert engineering scales
  poorly); leezythu/Awesome-Harness-Self-Improvement reading list frames
  harness engineering as the substrate for recursive self-improvement.
- **GEPA went official** (gepa-ai/gepa): reflective prompt evolution,
  Pareto-aware selection, "90x cheaper" than RL-style optimization. It is
  a library you wrap around a system. Our stance stays as documented in
  the learn skill: the AGENT is the optimizer, no adapters — the
  optimization loop is a crow-cli session reading its own traces.
- **Persistent Jupyter kernels for agents exist as bolt-ons**:
  jupyter-live-kernel skills on the skill marketplaces (May 2026:
  "stateful Python REPL via a live Jupyter kernel, variables persist
  across executions") and rwollman/persistent_jupyter ("explore an API
  interactively instead of generating a 200-line script and hoping").
  All of them are tools/skills bolted onto an agent. None of them are
  transport-aware fabric: kernel owned by the MCP server, lifetime
  decided by stdio-vs-http the way memory's is decided by
  sqlite-vs-postgres.
- **Progressive disclosure is a named agentic technique** — LangChain's
  SQL-assistant tutorial literally teaches "skills via progressive
  disclosure" for a SQL assistant; prdeving.wordpress.com explores it for
  tools generally. Our memory SQL tool is the same idea applied to the
  agent's OWN memory db.

How crow-cli differs, without bombast: (1) introspection rides the
compaction pass it already pays for — prefix-cached, foreground, free;
(2) feedback is ls-able files and git PRs, not another store; (3) hooks
not inheritance, transport decides lifetime; (4) the fixed point — the
harness's dominant workload is the harness itself (2886 agents, ~80% in
crow repos, commits joined to traces by Session-Id trailers, prompts
table already versioning character). Anyone can build these capabilities;
the loop that improves the thing running the loop, inside one product, is
the part that compounds.
