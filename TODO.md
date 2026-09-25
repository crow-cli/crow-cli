# TODO

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Sprint origin: 2026-09-24, session `worthy-conscious-rat-of-opportunity`.
Worktree `~/.agents/crow/src/worktrees/goal`, branch `goal`, off main @ 95cf5511.

## The mandate, in the user's words

> crow-cli has accumulated lots of garbage from all the AI agent sessions and
> needs some cleaning up. we either need to polish task and get it fully
> implemented, or pull out what's not useful to /goal
>
> let's create a worktree in ~/.agents/crow/src/worktrees and use the task guts
> to create a /goal system please. we can decide what if anything we want to do
> with redis/celery task system later

So: build `/goal` on the task system's guts. The redis/celery decision is
EXPLICITLY deferred — do not remove `timers.py`, do not rip out the broker, do
not relitigate §5.3. Leave both alone and say so in the summary.

## What /goal is

A persisted objective per wire session that turns "the turn ended" from a
terminal event into a loop-back edge. The agent keeps working until the goal
leaves `active`. This is codex's `/goal` (validated against
`~/src/crow-term/codex/codex-rs/ext/goal/` this session) rebuilt on crow's
mailbox instead of codex's extension hooks.

The mechanism is ACP_V2.md §5.4 — the state-triggered wake that was designed
and never built. §5.4's own code snippet cites `driver.py:419 _fire_deferred()`;
neither `remind` nor `_fire_deferred` exists in src/. This sprint builds it,
with the goal as the thing that defers.

**The load-bearing decision: continuation rides the EXISTING mailbox.** A goal
continuation is a `TaskDelivery` row. No new event type in `agent2/events.py`,
no second injection path, no client involvement, nothing for the watcher to
learn. §5.4: "by the time anything looks, it is an ordinary pending delivery."
`Delivery.task_id` has no FK, so it names the goal id honestly.

## Scope capture (unordered)

- [x] `Goal` model in `memory/models.py` — one row per wire session
      (`session_id` PK), `goal_id` uuid for stale-update protection, `objective`,
      `status`, `blocked_reason`, `token_budget`, `tokens_used`,
      `time_used_seconds`, `turns_used`, timestamps. `create_all` is idempotent
      so an existing crow.db gains the table with no migration script.
      *2026-09-24: shipped. Five statuses, not four — `active|paused|blocked|
      budget_limited|complete`, the codex vocabulary, because "the arithmetic
      stopped it" and "the model claims it finished" are different facts and
      collapsing them loses the only one the user can act on. Constants live in
      `models.py` (reads needs them, writes imports reads → circular otherwise).*
- [x] Reads: `get_goal`, `active_goal`. Writes: `set_goal`, `update_goal_status`,
      `clear_goal`, `account_goal_usage` (atomic add + budget flip in one commit,
      the `finish_task` discipline).
      *2026-09-24: shipped, `tests/memory/test_goal_state.py` 16 green,
      `tests/unit` 811 passed. `set_goal` ALWAYS mints a fresh id and zeroes the
      counters — codex preserves both on re-set, which suits a product that
      bills the goal; crow's goal is a loop guard, and a loop guard that
      inherits its predecessor's spend stops guarding.*
- [x] `agent2/goal.py` — the continuation prompt template and the eligibility
      rules, in one place, so the driver stays thin.
      *2026-09-24: shipped, `tests/unit/test_goal_continuation.py` 12 green.
      `CONTINUATION_PROMPT` is 15 lines / 607 chars and a test pins that.
      `eligible` returns `Verdict(status, reason) | None` rather than a bare
      reason string, because the driver has to persist the status the rule
      named. `Verdict.status is None` means "someone else already stopped this,
      do not overwrite their decision".*
- [x] Driver: `_park()` checks the goal BEFORE announcing idle (no spurious
      idle flicker), writes the delivery, returns True; the loop's existing
      `_mailbox_pending()` picks it up.
      *2026-09-24: shipped, `tests/integration/test_goal_driver.py` 11 green,
      seven mutations all detected. The no-flicker claim is proven on the wire:
      two turns produce `["idle","running","idle"]`, because `_set_state`
      dedupes a state that never changed. New primitive `queue_delivery` —
      `finish_task` built its delivery inline, and a goal has no task row.*
- [x] Progress signal: react counts tool CALLS on `LoopState`, reports on
      `Done.tools_used`, so "did this turn do anything" is a fact and not a
      guess.
      *2026-09-24: shipped, asserted through `Gate.tools_used` on the gate's
      real-MCP round trip (1) and text-only turn (0), mutation-checked. The
      driver keeps `_last_tools_used`; the slash-command early return zeroes it
      so `/goal <objective>` is never judged for progress.*
- [x] Loop guards — the part that decides whether this is a feature or a
      token fire: a no-tool CONTINUATION turn ends the goal (`blocked`);
      `turns_used` against a configured max (`budget_limited`); `tokens_used`
      against `token_budget` (the SQL `CASE` in `account_goal_usage`, not a
      Python re-check); turn error → `blocked`; cancel → `paused`.
      *2026-09-24: shipped. Only a turn the GOAL caused is charged, turns and
      tokens alike — billing a user-prompted turn to the goal makes the ceiling
      fire on conversation length rather than on autonomy. And it charges
      `Done.tokens_spent` (new, summed over every model call in the turn), not
      `done.usage`, which is the LAST call's totals and undercounts a
      multi-round turn by roughly the number of rounds.*
      *Scope found while building the policy: the no-tool rule needs
      `was_continuation`, so the DRIVER must remember whether the turn it just
      ran was one it caused. Without that distinction a user interjecting
      "what's the status?" mid-goal gets a text-only answer and blocks their
      own goal. Phase 4 carries a `_continuation_in_flight` flag: set when the
      delivery is written, consumed when that turn settles. Lost on restart,
      which costs one extra continuation and self-corrects.*
      *Config landed with it, pulled forward from the docs phase:
      `goal: {max_turns: 25, max_tokens: null}` as a typed `GoalConfig`,
      unknown keys rejected. `max_tokens` has no consumer yet — `/goal` passes
      it to `set_goal` as the default budget.*
- [ ] `/goal` slash command: bare = show, `<objective>` = set, plus
      `clear|pause|resume`. Needs the engine on `_SlashView` (v2) and on v1's
      `AcpAgent`, because `agent/slash.py` is shared by both.
- [x] Model-facing tools so the loop can END: `goal_done` and `goal_blocked` as
      two subtools, not one mode dispatcher — `tools/task.py`'s house rule is
      explicit that "a capability behind a mode-string dispatcher is a
      capability that does not get reached."
      *2026-09-24: shipped in `_LAZY_V2`, not `_LAZY` — v1 runs no continuation
      loop, so an exit bound there is a call that succeeds, changes a row and
      means nothing. `goal_done()` takes no arguments (the achievement is the
      model's reply, not a wire payload); `goal_blocked(reason)` refuses an
      empty reason, because codex captures none at all and a blocked goal that
      cannot say why is a dead end with no exit sign. Both idempotent, neither
      raises on a goal somebody else already stopped, both read the row BACK
      after writing it. Shipped with the driver guard that makes an exit hold:
      `_settle_goal` only moves a goal that is still `active`, so a `goal_done`
      followed by an unrelated error in the same turn stays `complete` instead
      of coming back `blocked`.*
- [x] Tests: unit for the store and the eligibility rules; integration for the
      driver actually continuing, actually stopping, and actually not looping
      forever. Real code paths, no mocks.
      *2026-09-24: 16 store + 12 policy + 19 subtool + 14 driver = 61 goal
      tests, no mocks anywhere — temp sqlite files, a real FastMCP subprocess,
      a real agent and transport, and a scripted model because a gate that
      needs a provider is not a gate. 18 mutations applied and every one
      detected, across Phases 3-5 (1 + 7 + 10); Phases 1-2 are store and
      pure-policy code, asserted directly rather than mutated. Full tier 1387
      passed. What is left is Phase 8: `./run_tests.sh` including e2e, and the
      manual eyeball.*
- [ ] The `crow_cli.tools` facade wart, found by Phase 5's registration check:
      `import crow_cli.tools.task` anywhere in the process leaves the MODULE on
      the package attribute, which shadows `__getattr__`, so `T.task` is
      afterwards a module and not the callable. `reload()` purges exactly this
      (and says so in a comment), so a real kernel is fine — but any in-process
      consumer that imports a submodule and then reaches for the facade by name
      gets something uncallable. Either stop setting the parent attribute or
      make `__getattr__` win. NOT this sprint: it predates /goal, nothing in
      production hits it, and the fix touches the one module every kernel
      starts with.
- [ ] Cleanup found along the way: `agent/slash.py:134-140` is an orphaned copy
      of `register_slash_command`'s body sitting after `stop_command`'s
      `return` — unreachable, and it references `name`/`description` that do
      not exist in that scope. Delete it.
- [ ] ACP_V2.md: §5.4 stops being a proposal; `:28`'s status table and `:811`
      ("timers.py, celery | Not involved") get corrected to match what shipped.

## Explicitly deferred (write the reason, do not do the work)

- redis/celery: the user said later. `timers.py` stays as built — correct,
  tested, no production caller. §5.3's argument survives this sprint intact,
  because a goal continuation is state-triggered and never wanted a clock.
- Pulling unused surface out of `task`: the "polish or amputate" question is
  answered AFTER /goal lands, because landing it reveals which guts are load
  bearing. Do not delete task features on spec.
- TUI rendering of goal state. The agent advertises `/goal` through the
  existing `available_commands_update`; a status-bar widget is crow-term's
  business, not this repo's.
