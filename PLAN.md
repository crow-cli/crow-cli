# PLAN — /goal on the task guts

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Worktree `~/.agents/crow/src/worktrees/goal`, branch `goal`.

**Gate (floor for every item):** `uv --project . run pytest tests/unit -q`
**Gate (full, before declaring done):** `./run_tests.sh`
Commit at every phase boundary with the `Session-Id:` trailer.

Trajectory is numeric: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8.

---

## Phase 1 — the row

1.1 **[DONE 2026-09-24 — `Goal.__tablename__ == "goals"`, all 11 columns
    present; status constants `GOAL_ACTIVE|PAUSED|BLOCKED|BUDGET_LIMITED|
    COMPLETE` live in `models.py`, not `writes.py`, because `reads` needs them
    and `writes` imports `reads`]**
    `Goal` in `memory/models.py`. `session_id` Text PK (wire id — never
    `agent_id`, which changes under compaction; `agent/slash.py`'s module
    docstring already states this rule). `goal_id` Text uuid, `objective` Text,
    `status` Text default "active", `token_budget` Integer nullable,
    `tokens_used` Integer default 0, `time_used_seconds` Integer default 0,
    `turns_used` Integer default 0, `created_at`/`updated_at` via `now_iso`.
    Docstring in house style: say WHY one row per session and WHY `goal_id`
    exists separately from the PK.
    *Verify:* `uv --project . run python -c "from crow_cli.memory.models import Goal; print(Goal.__tablename__)"`

1.2 **[DONE 2026-09-24 — `tests/memory/test_goal_state.py`, 16 tests green]**
    Writes in `memory/writes.py`: `set_goal` (upsert; ALWAYS mints a fresh
    `goal_id` and zeroes the counters — no special case for re-setting the same
    objective. Deviation from the draft, deliberate: one rule rather than two,
    and preserving a spent budget would make a restart gesture a no-op that
    looks like a fresh start. Codex does the opposite — `update_thread_goal`
    preserves `goal_id` and the accrued usage when the objective changes — and
    that is a defensible choice for a product that bills the goal; crow's goal
    is a loop guard, and a loop guard that inherits its predecessor's spend
    stops guarding),
    `update_goal_status(engine, session_id, status, *,
    expected_goal_id=None)` returning bool, `clear_goal`, `account_goal_usage`
    (one commit: add tokens + seconds + turns, and flip to `complete`-adjacent
    `budget_limited`-style terminal in the SAME statement when the budget is
    crossed — the codex `CASE WHEN` discipline, so a concurrent writer cannot
    observe an over-budget goal still marked active).
    *Verify:* unit test `tests/memory/test_goal_state.py` (repo convention is
    `tests/memory/`, not `tests/unit/memory/`; style model
    `tests/memory/test_task_state.py`) — set/show/replace-resets-usage/
    status-transition-with-stale-goal-id-rejected/budget-flip-in-one-commit,
    plus `active_goal` returning None for every non-active status, negative
    clamping, no-budget-means-no-ceiling, and two-engines-on-one-file
    visibility. 16 tests, green; `tests/unit` 811 passed.

1.3 **[DONE 2026-09-24 — covered by `test_active_goal_is_the_row_the_driver_asks_for`,
    which walks all four non-active statuses]**
    Reads in `memory/reads.py`: `get_goal(engine, session_id) -> Goal | None`,
    `active_goal(engine, session_id) -> Goal | None` (None unless status is
    exactly "active" — the only status that continues). The driver asks
    `active_goal` and never `get_goal`, so "should I keep going" is one column
    compare in one place rather than a status switch repeated at every call site.
    *Verify:* covered by 1.2's test file.

**Commit:** `feat(memory): the goal row`

## Phase 2 — the continuation, as a module

2.1 `src/crow_cli/agent2/goal.py`. Module docstring that states the load-bearing
    decision (continuation is an ordinary `TaskDelivery`; §5.4 built at last)
    and why the goal lives in the row's status rather than in a new event type.
    Contents: `CONTINUATION_PROMPT` template, `continuation_text(goal) -> str`,
    and `eligible(goal, *, last_turn_used_tools, max_turns) -> str | None`
    returning None when it may continue or the reason it may not.
    Keep the prompt SHORT. codex's `continuation.md` is 56 lines of audit
    ritual; crow's first cut states the objective, the budget position, and
    "call goal_done when it is actually finished, goal_blocked when it is
    genuinely stuck." Do not import codex's completion-audit cathedral.
    *Verify:* unit test `tests/unit/test_goal_continuation.py` — every branch of
    `eligible` (no active goal / paused / blocked / complete / turn budget spent
    / token budget spent / no-tool suppression / may-continue), and the rendered
    prompt for a budgeted and an unbudgeted goal.

**Commit:** `feat(agent2): goal continuation text and eligibility`

## Phase 3 — the progress signal

3.1 `LoopState.tool_batches: int = 0`; increment in `react._run_tools`;
    `Done.tools_used: int = 0` populated from it at every `return Done(...)`
    site in `react()`. This is a fact the driver needs and cannot infer: a turn
    that only talked made no progress, and continuing it is the infinite loop.
    *Verify:* `uv --project . run pytest tests/unit -q` green, plus a unit test
    asserting a tool-running loop reports `tools_used > 0` and a text-only
    completion reports `0`.

**Commit:** `feat(agent2): report tool activity on Done`

## Phase 4 — the driver fires

4.1 `SessionDriver._park()`: BEFORE `_set_state("idle")`, call
    `self._goal_continuation()`. If it wrote a delivery, return True without
    announcing idle — the loop re-iterates, `_mailbox_pending()` is now true,
    `_run_turn([])` runs, and react's prompt-start `consult` injects it. No
    spurious idle, no new wake path.
4.2 `_goal_continuation() -> bool`: read `active_goal`; call `goal.eligible`
    with the last turn's `tools_used` and the configured max; if ineligible,
    persist the terminal status it named (blocked/complete) and return False;
    if eligible, insert the `TaskDelivery` (task_id = `goal_id`, priority
    "low", content = the continuation text) and bump `turns_used`.
    Engine may be None (`config.db_uri` empty) — then goals are unavailable and
    this returns False silently, matching `_mailbox_pending`'s existing guard.
4.3 Account the finished turn: in `_run_turn` after `done` is settled, fold
    `done.usage` tokens and wall-clock into `account_goal_usage`. Cancel →
    `paused`; `stop_reason == "error"` → `blocked` (codex does exactly this, to
    stop a continuation loop from eating tokens on a repeating failure).
    *Verify:* integration test `tests/integration/test_goal_driver.py` — a real
    driver over a temp sqlite db: (a) an active goal with a tool-using turn
    continues; (b) a text-only turn does NOT continue twice in a row;
    (c) `goal_done` ends it; (d) an errored turn blocks it; (e) a cancelled
    turn pauses it; (f) no goal → parks as before, no regression.

**Commit:** `feat(agent2): the driver continues an active goal at idle`

## Phase 5 — the model can end it

5.1 `tools/goal.py`: two subtools, `goal_done` and `goal_blocked`, each with a
    `@subtool` decorator, registered in `tools/__init__.py`'s `_LAZY`. They read
    the identity rail for the session id the same way `tools/task.py` does —
    never a model-supplied session id. `goal_done` → status complete;
    `goal_blocked(reason)` → status blocked, and the reason is stored so `/goal`
    can show it.
    *Verify:* unit test in the subtool style used by `tests/unit/` for task.py;
    `reload()`-equivalent registration check that both names resolve.

**Commit:** `feat(tools): goal_done and goal_blocked`

## Phase 6 — the slash command

6.1 Expose the engine to slash handlers: `_SlashView._engine` (v2, from
    `SessionRegistry.engine`) and the matching attribute on v1's `AcpAgent`,
    because `agent/slash.py` is shared and a handler that only works in v2 is a
    handler that breaks in v1.
6.2 `@register_slash_command("goal", ...)` in `agent/slash.py`: bare → a
    status block (objective, status, turns, tokens/budget, time);
    `clear|pause|resume` → the transition; anything else → set the objective.
    Return a string, never raise (the module docstring's rule: an exception
    becomes an ACP internal error the client reads as a failed turn).
6.3 Delete the orphaned dead code at `agent/slash.py:134-140`.
    *Verify:* unit test over `parse_slash_command` + the handler for each
    subcommand against a temp db; `uv --project . run pytest tests/unit -q` green.

**Commit:** `feat(agent): the /goal slash command`

## Phase 7 — config and docs

7.1 Config: `[goal] max_turns` (default 25) and `max_token_budget` optional,
    in `config/config.py` next to the existing redis/bus keys, plumbed to
    `Deps`/driver the way `max_turns` already is.
7.2 ACP_V2.md: §5.4 marked shipped with the real function names; the `:28`
    status table row for celery left accurate (still no production caller);
    `:811`'s "Not involved" confirmed still true and now *load-bearing* — the
    goal proves §5.3 right.
    *Verify:* prose matches code — grep every symbol named in the new §5.4 text.

**Commit:** `feat(config)!: goal limits` + `docs: §5.4 shipped`

## Phase 8 — the full gate

8.1 `./run_tests.sh` — all tiers. e2e hits a live LLM; if it cannot run here,
    say so explicitly in the summary rather than reporting green.
8.2 Manual eyeball: `crow-cli run` in a scratch dir, `/goal write a haiku about
    the sea`, watch it continue, `goal_done` it, `/goal` to see the row.
8.3 Final `git status` clean, every commit carrying
    `Session-Id: worthy-conscious-rat-of-opportunity`.

---

## Rules for this sprint

- Reuse before adding. If the mailbox can carry it, the mailbox carries it.
- No mocks where a temp sqlite db will do — the house rule is real code paths.
- A guard that cannot be tested is a guard that does not exist.
- Do not touch `timers.py`, `wake.py` or the redis config. Deferred by the user.
