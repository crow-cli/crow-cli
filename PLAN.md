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
- The existing compaction prompt/algorithm is protected — riff around it.
- Analysis/ideas output is FOREGROUND (never background — too important),
  files over db rows (ls is the interface), evidence mandatory.
- User corrections outrank agent suggestions absolutely.

## Phase 1 — compaction hook fabric + the analysis/ideas passes

1.1 Promote `on_compact` from single callback to the constructor hook
    idiom: `AcpAgent(config, hooks=..., compact_hooks=...)`, plumbed
    through react_loop/TurnCtx exactly like hooks/snapshot_hooks. The two
    existing call sites (react threshold, /compact) keep working.
    Verify: existing tests green + unit test asserting multiple hooks fire
    in order with (old_agent_id, new_session).
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
1.3 `ideas` default hook: project-level strategic ideation prompt —
    interrogate deeper goals, not surface regurgitation; frontmatter for
    enumeration/regeneration; `{ts}_{session_id}-{agent_idx}_ideas.xml`.
    Verify: file lands with valid frontmatter; prompt includes the
    project-not-crow-cli scoping rule.
1.4 Two-layer thresholds: soft compact hook at ~160k (budget notice +
    5-7 turn wind-down react loop with existing tools), hard endpoint at
    MAX_COMPACT_TOKENS. Read-only behavior for analysis/ideas forks via
    prompt instructions.
    Verify: unit tests on threshold resolution (per-model
    max_compact_tokens still wins); live eyeball of the soft notice.

## Phase 2 — feedback directory + learn skill rewrite

2.1 Feedback dir convention: global `~/.agents/crow/feedback/` +
    project-local resolution copied from skill_roots (project scopes
    first, user scope last). Lifecycle dirs inbox/validated/accepted/
    rejected/landed. Frontmatter schema shared by analysis/ideas files.
    Verify: ls-able tree after a live compaction; schema doc in repo.
2.2 learn skill rewrite (in ~/.agents/skills/learn, then publish): stupid
    simple — read feedback dirs, precedence stack (user corrections from
    query_memory on USER MESSAGES > recurring friction > evidenced items >
    ideas), validate (evidence → reproduce → bench), patch, PR. Bench
    instances drawn from the real workload distribution.
    Verify: skill renders in catalog; one dry-run pass over existing
    inbox items produces sensible triage.
2.3 Bump web_search: prompt mutation + analysis rubric dimension
    ("did the agent research before guessing?").
    Verify: diff reviewed; next session's tool histogram shows movement
    (baseline: 548 calls / 1.6%).

## Phase 3 — memory SQL tool + skill

3.1 New MCP tool in crow-mcp (next to query_memory, augmenting not
    replacing): raw SQL over a REAL read-only connection (get_ro_engine).
    Tool description = parsimonious table descriptions + example queries
    that reveal structure (progressive disclosure).
    Verify: mcp tests; write attempts rejected at the connection level.
3.2 Companion skill (SQL-against-the-db-through-MCP = a way to run code).
    Verify: skill in catalog; a fresh agent can answer a schema question
    using only the skill + tool.
3.3 Design note for later: project/session-specific MCP servers and
    swapping MCP servers during compaction (probably slash command).
    Captured in TODO; not built this phase.

## Phase 4 — ipykernel tool

4.1 Transplant CrowKernel (gist 1cdba586d9d57422bad5d91d320b75ae) into
    crow-mcp: kernel launched on first call, owned by the MCP server
    process, reused across calls; python = sys.executable by default,
    project venv override; reset/reload subcommand.
    Verify: state persists across two tool calls (x=42; print(x));
    error-first formatting; `!` escape; reset clears state.
4.2 Transport lifetime: stdio = session-scoped (default); http mode
    ("one server, many clients") gets a session-keyed kernel registry
    (session id rides call _meta, the 39e65ebb pattern).
    Verify: two concurrent http sessions get isolated kernels.

## Phase 5 — project-level agent surface + self-healing

5.1 Discovery + spawn: `$cwd/.agents/crow/` custom agent script /
    `src/crow-cli` checkout → `uv --project ... run crow-cli acp`;
    `--system` opts out; re-exec sentinel; init pre-syncs the venv.
    Verify: project with a checkout runs from source; sentinel prevents
    re-spawn loop.
5.2 Self-healing: spawn fails → system agent with the fix prompt ("load
    the crow-cli skill and fix this error: {error}") + bug-dir report →
    retry original prompt ONCE → still broken = system boot with loud
    note. Verify: deliberately broken checkout exercises the full path.
5.3 More hook points: session-creation seams (template/skills/agents-
    context — hook the seams, never fork the factory), notes-to-self
    surfacing as a prompt_args block with priority/germaneness filtering.
    Verify: a repl-agent-pattern script overrides character without core
    changes.

## Phase 6 — maintainer agent + init clones + publishing

6.1 Maintainer/evaluator script (repl-agent pattern, global db, decision-
    log compact hook, worktrees under accepted/ items).
    Verify: it triages a real inbox and opens (or stages) a fix.
6.2 `crow-cli init` clones crow-cli + crow-cli.github.io into
    `~/.agents/crow/src/`, installs the crow-cli map skill globally
    (the BIOS — always global).
    Verify: fresh config dir exercises init end-to-end.
6.3 Publish skill: sync-skills.py → PR to crow-cli.github.io.
    Verify: crow-ai.dev/skills/<name>/SKILL.md resolves after deploy.

## Phase 7 — fork delegation pattern (read-only forks)

7.1 session/fork-based relevance checks: fork reads the maybe-relevant
    file, reports yes/no; parent context stays slim; fork FALLS BACK TO
    BEFORE THE FORKED TOOL CALL (no infinity mirror); warm-KV reuse.
    Verify: a forked interrogation completes with zero-tools and the
    parent history shows no mirror recursion.

## Parked
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
