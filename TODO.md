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
- [ ] `agent2/goal.py` — the continuation prompt template and the eligibility
      rules, in one place, so the driver stays thin.
- [ ] Driver: `_park()` checks the goal BEFORE announcing idle (no spurious
      idle flicker), writes the delivery, returns True; the loop's existing
      `_mailbox_pending()` picks it up.
- [ ] Progress signal: react counts tool batches on `LoopState`, reports on
      `Done`, so "did this turn do anything" is a fact and not a guess.
- [ ] Loop guards — the part that decides whether this is a feature or a
      token fire: a no-tool turn suppresses the next continuation; `turns_used`
      against a configured max; `tokens_used` against `token_budget`; turn error
      → `blocked`; cancel → `paused`.
- [ ] `/goal` slash command: bare = show, `<objective>` = set, plus
      `clear|pause|resume`. Needs the engine on `_SlashView` (v2) and on v1's
      `AcpAgent`, because `agent/slash.py` is shared by both.
- [ ] Model-facing tools so the loop can END: `goal_done` and `goal_blocked` as
      two subtools, not one mode dispatcher — `tools/task.py`'s house rule is
      explicit that "a capability behind a mode-string dispatcher is a
      capability that does not get reached."
- [ ] Tests: unit for the store and the eligibility rules; integration for the
      driver actually continuing, actually stopping, and actually not looping
      forever. Real code paths, no mocks.
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
