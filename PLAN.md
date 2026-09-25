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

2.1 **[DONE 2026-09-24 — `tests/unit/test_goal_continuation.py`, 12 green;
    `tests/unit tests/memory` 913 passed. Prompt is 15 lines / 607 chars, and
    `test_the_prompt_stays_short` pins that so the cathedral cannot creep in.]**
    `src/crow_cli/agent2/goal.py`. Module docstring states the load-bearing
    decision (continuation is an ordinary `TaskDelivery`; §5.4 built at last)
    and why the stop condition lives in a status column rather than in this
    module: three different processes have to reach it.
    Contents: `CONTINUATION_PROMPT`, `continuation_text(goal, *, max_goal_turns)`,
    `Verdict(status, reason)`, `eligible(...) -> Verdict | None`.

    Four deviations from the draft, all deliberate:
    - `eligible` returns `Verdict | None`, not `str | None`. 4.2 has to persist
      "the terminal status it named", and a bare reason string leaves the driver
      guessing which status a given reason implies. `Verdict.status` is None
      when the row already says what it needs to say (paused by the user,
      completed by the model) so policy never overwrites a person's decision.
    - added `was_continuation: bool`. The no-tool rule must fire on a turn the
      GOAL caused and not on a turn the USER caused — otherwise interjecting
      "what's the status?" mid-goal blocks the goal, which punishes the person
      for using it. Only the driver knows which kind of turn just finished.
    - `max_turns` renamed `max_goal_turns` everywhere. `Deps.max_turns` is
      react's per-turn model-round-trip cap (50000); two different ceilings
      sharing a name is a footgun waiting for a maintainer.
    - the token budget is NOT re-checked in `eligible`. It lives in the `CASE`
      inside `account_goal_usage`'s single UPDATE, and a Python
      read-compare-write on top would reopen exactly the window that `CASE`
      closes. By idle, an over-budget goal is already `budget_limited` and
      `active_goal` has already returned None.

    Turn ceiling → `budget_limited` (the arithmetic decided). No-progress →
    `blocked` (needs a human). Checked in that order, because "stalled" invites
    a nudge and a nudge cannot buy more turns.

**Commit:** `feat(agent2): goal continuation text and eligibility`

## Phase 3 — the progress signal

3.1 **[DONE 2026-09-24 — `Gate.tools_used` asserted 1 on the gate's real-MCP
    tool round trip and 0 on its text-only lifecycle test. Mutation-checked:
    neutering the increment fails `assert 0 == 1`. 948 passed across
    tests/unit + tests/memory + test_agent2_gate.py.]**
    `LoopState.tools_used: int = 0`; incremented in `react._run_tools` AFTER
    the batch survives (a cancel re-raises out of `execute_tool_calls`, and a
    batch that never finished is not progress); `Done.tools_used: int = 0`
    populated at all three `return Done(...)` sites in `react()`. This is a
    fact the driver needs and cannot infer: a turn that only talked made no
    progress, and continuing it is the infinite loop.

    Two deviations:
    - the field counts CALLS, not batches, and is named `tools_used` on both
      `LoopState` and `Done`. The draft's `tool_batches` feeding a field called
      `tools_used` would have read as "3 tools" when it meant "3 rounds".
    - the test is in `tests/integration/test_agent2_gate.py`, not a new unit
      file. `Done` is observable only from the driver, and the gate already
      runs a real FastMCP subprocess round trip and a real text-only turn —
      building a second react harness to assert on a dataclass field would test
      the field rather than the behaviour. `Gate.tools_used` is the new
      read-only window; the driver gained `_last_tools_used` to feed it, which
      is 4.3's machinery pulled forward because it is the observable 3.1 needs.
      The slash-command early-return in `_run_turn` zeroes it too, so a
      previous turn's progress cannot vouch for a turn that ran no model.

**Commit:** `feat(agent2): report tool activity on Done`

## Phase 4 — the driver fires

**[PHASE 4 DONE 2026-09-24 — `tests/integration/test_goal_driver.py`, 11 tests
green over the real gate harness (real agent, real transport, real sqlite, real
FastMCP subprocess; only the model is scripted). Seven mutations applied and
ALL SEVEN detected: drop the `_park` hook, drop `was_continuation`, drop the
no-progress rule, drop error->blocked, drop cancel->paused, charge every turn,
drop the turn ceiling. Full tier: 1132 passed, 1 pre-existing flake
(`test_run_screenshot_rides_the_row`, a playwright/browser test that passes in
isolation and on re-run; untouched by this work).]**

4.1 **[DONE]** `SessionDriver._park()`: BEFORE `_set_state("idle")`, call
    `self._goal_continuation()`. If it wrote a delivery, return True without
    announcing idle — the loop re-iterates, `_mailbox_pending()` is now true,
    `_run_turn([])` runs, and react's prompt-start `consult` injects it. No
    spurious idle, no new wake path. Proven on the wire, not inferred:
    two turns produce `["idle", "running", "idle"]` and ONE running, because
    `_set_state` dedupes a state that never changed.
4.2 **[DONE]** `_goal_continuation() -> bool`: read `active_goal`; call
    `goal.eligible` with the last turn's `tools_used`, `was_continuation` and
    the configured max; if ineligible, persist the status the `Verdict` named
    (or nothing, when it named none) and return False; if eligible, insert the
    `TaskDelivery` (task_id = `goal_id`, priority "low", content = the
    continuation text) and bump `turns_used`.
    Engine may be None (`config.db_uri` empty) — then goals are unavailable and
    this returns False silently, matching `_mailbox_pending`'s existing guard.

    New primitive: `writes.queue_delivery(engine, session_id, *, task_id,
    content, priority="low") -> int`. `finish_task` built its delivery inline
    because a task was the only thing with a reason to wake a session; a goal
    continuation has no task row, and §5.4's deferred wake needed somewhere to
    go. It pokes nothing, deliberately — the driver writes the row to ITSELF
    and the loop re-iterates on it, so a redis round trip would be a message to
    the sender.

    Two commits (delivery, then counter) with a benign window: a crash between
    them leaves one continuation queued against a counter one low, which is a
    rounding error on a loop guard and not a way to loop forever.
4.3 **[DONE]** `_settle_goal(done, elapsed)`, called from `_run_turn` after
    `done` settles and therefore BEFORE `_park` — so a turn that errored has
    already blocked the goal by the time the continuation is asked about it.
    Cancel → `paused`; `stop_reason == "error"` → `blocked` (codex does exactly
    this, to stop a continuation loop from eating tokens on a repeating
    failure). Both status writes carry the `goal_id` they read, so a goal the
    user replaced mid-turn is left alone.

    Two deviations, both about WHICH turns pay:
    - only a turn the GOAL caused is charged, turns and tokens alike. The draft
      said "fold `done.usage` and wall-clock" for every turn; billing a
      user-prompted turn to the goal makes the ceiling fire on conversation
      length rather than on autonomy, and a limit that stops you for talking to
      your own agent is a limit nobody leaves enabled.
    - it charges `Done.tokens_spent`, a NEW field, not `done.usage`. `usage` is
      the LAST model call's totals — how full the context is now, which is what
      a client's meter should draw — while a five-round tool turn re-sends a
      growing context five times and is billed for all five. Charging `usage`
      undercounts by roughly the number of rounds, and a ceiling that does not
      fire is not a ceiling. Accumulated on `LoopState` including the completion
      that triggers a compaction, because that call was billed whether or not
      its answer survived. The gate now pins both numbers side by side
      (`tokens_spent == 30` against an idle carrying `totalTokens: 20`).

    Config pulled forward from 7.1, because the driver reads it and the ceiling
    test has to vary it: `GoalConfig(max_turns=25, max_tokens=None)` under a
    `goal:` block in config.yaml, typed like `LLMConfig` rather than a loose
    dict like `image_store`, with unknown keys REJECTED — `goal: {max_turn: 25}`
    silently doing nothing is a ceiling the user believes they set.
    `max_tokens` is the default budget for a goal set without one, and Phase 6
    is what passes it to `set_goal`.

    *Verify:* `tests/integration/test_goal_driver.py`, 11 tests — (a) an active
    goal with a tool-using turn continues and the client sees no idle between;
    (b) a text-only CONTINUATION ends it blocked; (b') a text-only USER turn
    does not; (d) an errored turn blocks it; (e) a cancelled turn pauses it and
    charges nothing; (f) no goal → parks exactly as before; plus every
    non-active status is left untouched (parametrized ×4) and the token budget
    flips mid-run from the SQL `CASE`. (c) `goal_done` ends it is Phase 5's,
    where the subtool exists; the mechanism it uses — a non-active row is never
    continued — is covered here.

**Commit:** `feat(agent2): the driver continues an active goal at idle`

## Phase 5 — the model can end it

**[PHASE 5 DONE 2026-09-24 — `tests/unit/test_tools_goal.py` 19 green,
`tests/integration/test_goal_driver.py` 14 green (3 new), full tier
`tests/unit tests/memory tests/mcp tests/integration` = 1387 passed, 0 failed.
TEN mutations applied, all ten detected: drop the driver's error guard; drop
its cancel guard; make `goal_done` never write (integration AND unit); drop the
stored reason; accept an empty reason; resolve the engine before the identity;
delete `KIND_BY_RESULT["goal"]`; make the result promise a stop for a still
active goal; bind `goal_done` into `_LAZY`.]**

5.1 `tools/goal.py`: two subtools, `goal_done` and `goal_blocked`, each with a
    `@subtool` decorator, registered in `tools/__init__.py`'s **`_LAZY_V2`, not
    `_LAZY`** — CORRECTED FROM THE DRAFT. They are the exits from a
    continuation loop and only the agent2 driver runs one; v1 has no idle
    transition to hook, so binding them in a v1 kernel offers the model a way
    out of a loop it is not in. (`task` is in `_LAZY_V2` for a DIFFERENT reason
    — a name collision with v1's MCP tool — and both reasons are now written in
    the table's comment rather than one being left to inference.)
    They read the identity rail for the session id the same way `tools/task.py`
    does — never a model-supplied session id, and identity is resolved BEFORE
    the database so a caller with no rail is told who it failed to be rather
    than where it failed to write. `goal_done` → status complete;
    `goal_blocked(reason)` → status blocked, and the reason is stored so `/goal`
    can show it.
    *Verify:* unit test in the subtool style used by `tests/unit/` for task.py;
    `reload()`-equivalent registration check that both names resolve.
    **DONE, with four decisions the draft did not make:**
    - `goal_done()` takes NO arguments. codex's `update_goal` takes only
      `status` — not even a reason — and the achievement belongs in the model's
      reply, where the user reads prose. A `summary` argument would have the
      model write the same sentence twice, once to a wire tool call nobody
      reads as prose and once to the person.
    - `goal_blocked(reason)` REQUIRES the reason and refuses an empty or
      whitespace one with a `GoalError` that models the call it wants. codex
      captures no reason at all, so a blocked codex goal tells nobody why it
      stopped; ours stores it stripped, verbatim, because it is the only thing
      the user gets to read.
    - Both exits are IDEMPOTENT and neither raises on a goal somebody else
      already stopped — they return `GoalResult(changed=False)` and say so in
      `.text`. They are called at the end of a turn the model spent real
      reasoning on, and the right answer to "I already said that" is "yes, and
      nothing changed", not an exception that reads as though the work failed.
      Same rule as `agent2.goal.eligible` returning `Verdict(None, ...)`.
    - The status is READ BACK off the row after the write, not echoed from the
      call, because three processes write this row and the driver reads it at
      the idle transition — what the model is told has to be what the driver
      will find.

5.2 **NOT IN THE DRAFT — the driver guard, found while building 5.1.**
    `_settle_goal` now moves the goal only when the row it read is STILL
    `active` (`running = row.status == GOAL_ACTIVE`, guarding both the
    cancel→paused and the error→blocked writes). Without it an exit does not
    hold: `goal_done` followed by an unrelated failure later in the same turn
    came back `blocked`, telling the model its finished work was stuck and
    showing `/goal` a problem that does not exist. The spend is charged either
    way — those tokens were spent on that goal whatever its status, and the row
    is that goal's account.
    *Verify:* two integration tests, `..._errors_after_the_goal_was_ended_
    does_not_reopen_it` and `..._cancelling_a_turn_that_already_ended_the_goal_
    does_not_pause_it`, each mutation-detected by dropping one guard.

5.3 **NOT IN THE DRAFT — the other two channels.** The draft named the subtools
    and stopped; a subtool call produces three outputs and the plan only
    accounted for one. `GoalResult`/`GoalError` in `tools/results.py`
    (`result_kind = "goal"`, the objective as the ACP `subject` because it is
    the only part a person scanning a transcript recognizes, and the spend in
    `.text` because codex asks the model to report final usage and it can only
    report what the result carries), plus `"goal": "other"` in
    `agent2/tools.py`'s `KIND_BY_RESULT`. The mapping entry is not redundant:
    `tool_kind("goal_done")` reaches "other" only by falling through EVERY
    substring rule, so without it the kind is "other" by accident and the next
    rule added to that function could quietly reclassify it.
    *Verify:* `test_the_call_is_recorded_for_the_drain`,
    `test_a_refusal_is_recorded_as_a_failure`,
    `test_the_wire_kind_is_stated_not_fallen_into`.

5.4 Also discharged: PLAN 4.3's deferred case (c) — `goal_done` ends the goal
    and it is not continued. `test_goal_done_from_the_kernel_ends_the_loop`
    calls the REAL subtool with the rail pointed at the gate's database (its own
    engine on the same file, which is the cross-process situation) and asserts
    one llm call, an empty mailbox and one running between the idles. The turn
    is text-only on purpose: a text-only turn the USER caused DOES continue, so
    "no continuation" can only mean `active_goal` found nothing.

**Deviation in the registration check:** it resolves each `_LAZY_V2` entry
through `importlib.import_module(module).attr` — the way `reload()` does — and
NOT through `getattr(crow_cli.tools, name)`. Running the whole suite showed why:
an earlier `import crow_cli.tools.task` leaves the MODULE on the package
attribute, which shadows `__getattr__`, so `T.task` is a module and the facade
hands out something uncallable. That is the documented wart `reload()`'s purge
exists to undo, not a bug in this phase, but it is real and it is now in
TODO.md. The two NEW names are additionally asserted through the facade itself,
which nothing shadows. The live-kernel half of the check was already there:
`tests/mcp/test_mcp2_server.py::test_the_prelude_binds_the_whole_v2_facade`
reads `_names()` out of a running kernel, so it covered `goal_done` and
`goal_blocked` the moment they were added, with no edit.

**Commit:** `feat(tools): goal_done and goal_blocked`

## Phase 6 — the slash command

**[PHASE 6 DONE 2026-09-24 — `tests/integration/test_goal_slash.py` 20 green,
`tests/integration` plus the goal unit and store files 289 passed together,
full tier `tests/unit tests/memory tests/mcp tests/integration` = 1407
passed, 0 failed in 471s. TEN mutations applied, all ten detected: pause does not
write; resume does not write; `_set` drops the configured budget; the
subcommand check goes first-word-wins; `resume` accepts a finished goal;
`_show` renders its own progress instead of calling `progress()`; `clear`
always claims success; the no-engine guard is removed; the handler is allowed
to raise; agent2 never imports its slash module.]**

6.1 Expose the engine to slash handlers: `_SlashView._engine` (v2, from
    `SessionRegistry.engine`).
    **DONE, and the draft's second half is WRONG — v1 needs no attribute and
    got none.** The draft reasoned that `agent/slash.py` is shared, so a
    handler registered there must work in both generations. It IS shared, and
    that is exactly why `/goal` is not registered there: `_SLASH_COMMANDS` is
    one module-level list that both generations read AND advertise, so a
    command registered from `agent/slash.py` shows up in a v1 session, and v1
    runs no continuation loop — `/goal port the widget` would answer "goal set"
    and then nothing would ever happen. The same reasoning that put `goal_done`
    in `_LAZY_V2`. So the handler lives in a NEW `agent2/slash.py`, imported
    for its side effect from `agent2/agent.py`, and the two generations are
    separate processes (`cli/source.py:108-111 AGENT_ENTRY_POINTS`;
    `cli/main.py:178` imports `crow_cli.agent2.main` only inside the `acp2`
    subcommand), so registering it there reaches exactly the process that can
    honour it. v1 is untouched. It could not have been given the attribute
    anyway: v1's `AcpAgent` keeps no persistent engine, it has `_memory_db_uri`
    and builds and disposes one per call (`agent/main.py:741`).
    Asserted rather than argued — `test_a_v1_process_never_sees_it` runs a
    fresh interpreter that imports only v1 and prints the registry, because in
    the test process agent2 has already been imported and the table is shared:
    the claim is about what a v1 process sees, and only a v1 process can answer
    it.
    `_engine` returns the registry's long-lived write engine, the SAME one the
    driver settles goals through. The status a person writes has to be the one
    the driver reads at the idle transition, and two engines on one file would
    only be a way to get a stale read.
6.2 `@register_slash_command("goal", ...)`: bare → a status block;
    `clear|pause|resume` → the transition; anything else → set the objective.
    Returns a string, never raises.
    **DONE, in `agent2/slash.py`, with five decisions the draft did not make:**
    - A subcommand is recognized only when the word is the WHOLE argument, so
      `/goal clear the build cache` sets an objective called "clear the build
      cache". First-word-wins would make an ordinary imperative untypeable, and
      all three verbs start objectives people actually write.
    - `resume` refuses `complete` and `budget_limited`, and says which. Both
      would stop again at once — the turn ceiling and the token `CASE` read
      counters that resuming does not reset — and a command that appears to
      work and then does nothing reads as a bug. The gesture "start this over"
      is `/goal <objective>`, and the refusal names it. A divergence from
      codex, whose TUI `edit` reactivates a budget-limited or complete goal
      (`tui/src/chatwidget/goal_menu.rs`); codex can afford that because
      editing there goes through a menu that also lets you raise the budget.
    - The status block calls `agent2/goal.progress()` — the same function that
      builds the line the model is sent — so the person and the agent cannot be
      told two different ceilings. `_progress` became public for this, and a
      mutation that gives `_show` its own rendering is detected.
    - No `expected_goal_id` on any of the user's writes. The driver's automatic
      ones carry the id they read so a goal replaced mid-turn is left alone;
      the user's gesture means whatever row is there now.
    - `_set` passes `config.goal.max_tokens` as the row's `token_budget`, which
      discharges the remainder of 7.1: `max_tokens` now has a consumer.
    *Verify:* `tests/integration/test_goal_slash.py`, 20 tests, driven through
    the real prompt dispatch — text in at `session/prompt`, the reply the client
    saw out at `agent_message`, the row read back from the database the DRIVER
    reads. Dispatch and handler together, because a handler that works when
    called directly and raises through the dispatch is the failure this command
    must not have. The never-raises half is tested on a real broken row rather
    than a patched engine: SQLite gives an INTEGER column numeric AFFINITY and
    not a type, so a writer that put a string in `time_used_seconds` stored a
    string and `NOT NULL` is no defence.
6.3 Delete the orphaned dead code at `agent/slash.py:134-140`. **DONE** — seven
    unreachable lines after `stop_command`'s `return`, a duplicate of
    `register_slash_command`'s body referencing `name` and `description`, which
    do not exist in that scope.
6.4 **NOT IN THE DRAFT, and the thing the draft would have got wrong.**
    `/goal <objective>` on an idle session starts a turn IMMEDIATELY. The
    handler returns without running one, `_run_turn` returns early, the loop
    reaches `_park`, `_goal_continuation` finds an active goal on a session
    with nothing in flight, and the continuation is queued. Eight of the first
    draft's tests failed on this, and the failure was in the tests.
    Checked against codex before believing either side: `apply_external_goal_set`
    (`ext/goal/src/runtime.rs:184-248`) calls `self.continue_if_idle().await?`
    at line 233 for a goal whose status is Active. The table that suppresses a
    pickup, `thread_goal_continuation_deferrals`, is about FORKS and not about
    user-set goals — its only inserter, `replace_thread_goal_snapshot`
    (`state/src/runtime/goals.rs:109-118`, same transaction as the goal
    upsert), has exactly one caller,
    `app-server/src/request_processors/thread_fork_goal.rs:25`, and the
    deferral is cleared at `on_turn_start`. A forked thread that inherits a
    goal snapshot must not auto-continue before anyone has started a turn in
    it. crow has no fork-inherited goals, so it has no deferral and no reason
    to add one.
    Consequence for the tests: most run with `max_turns=0`, which stops the
    pickup before it reaches a model and leaves `budget_limited` in the row as
    the trace of an active one — a stronger assertion than `status == active`,
    because only an active row is continued and only a continuation consults
    the ceiling. Tests that need a particular status write the row directly.
    And the discovery is itself asserted, in
    `test_setting_a_goal_on_an_idle_session_starts_work_at_once`: a person who
    types `/goal` and walks away comes back to work that was done, not to a
    session sitting idle on the objective it was just handed.

**Commit:** `feat(agent): the /goal slash command`

## Phase 7 — config and docs

7.1 **[DONE 2026-09-24, pulled forward into Phase 4 — the driver reads it and
    the ceiling test has to vary it]** Config: `goal: {max_turns: 25,
    max_tokens: null}` parsed into a typed `GoalConfig`, exported from
    `crow_cli.config`, honored by `apply_config_overrides` too.
    REMAINING for 7.1: nothing. `max_tokens` got its consumer in Phase 6 —
    `_set` passes `config.goal.max_tokens` to `set_goal` as the row's
    `token_budget`, and `test_setting_a_goal_stores_the_row` asserts it lands.
7.2 ACP_V2.md: §5.4 marked shipped with the real function names; the `:28`
    status table row for celery left accurate (still no production caller);
    `:811`'s "Not involved" confirmed still true and now *load-bearing* — the
    goal proves §5.3 right.
    *Verify:* prose matches code — grep every symbol named in the new §5.4 text.
    **DONE. Every symbol in the new text was grepped for in the file it is
    attributed to and all were found.** Six edits, three of them beyond the
    draft's list because leaving them would have left the document asserting
    things that are no longer true:
    - §1's status table: "A model-facing way to feed **itself** | does not
      exist" was the stalest line in the file. Now three rows — the mechanism
      built, `/goal` built with its five modules named, `remind` explicitly not
      built. Test count 1326 → 1407.
    - §5's head: a status banner saying the MECHANISM shipped and the subtool
      did not, and that §5.1–§5.3 and §5.5–§5.9 are still the argument. The
      heading itself is unchanged so the TOC anchor still resolves.
    - §5.4 gains "What actually shipped, and where it differs": a three-row
      table of the deviations (a `Goal` row not a `Task` row; `queue_delivery`
      plus `account_goal_usage` rather than `finish_task`, because the row must
      SURVIVE firing; and `_park` consulting the goal BEFORE announcing idle
      rather than after, which the proposal's snippet gets the other way
      round), then the real names by file for grepping. The proposal's own
      snippet is kept and relabelled "as proposed".
    - §5.5's `TaskDelivery` row said the constructor appears in exactly ONE
      place. It appears in two now. Corrected rather than left, and the
      `timers.py`, celery row expanded into the load-bearing claim the draft
      asked for.
    - §5.8 recommended shipping without a budget and gave three reasons.
      `/goal` shipped with three brakes, so the section now records which
      reason failed — the third, "a budget has no obvious home"; the home is
      the row that persists the objective, which a one-shot note never had —
      and describes the brake the assessment could not have predicted, the
      no-tool continuation rule, which is not a budget at all.
    - §5.10 marked unstarted and smaller than written, §8's hole 1 reworded,
      and §9's git state flagged as a prior session's record rather than
      silently rewritten.

**Commit:** `docs: §5.4 shipped` (7.1 landed in Phase 4 and Phase 6, so there
is no config commit to make)

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
