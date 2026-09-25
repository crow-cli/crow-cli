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
      unknown keys rejected. `max_tokens` got its consumer in Phase 6: `_set`
      passes it to `set_goal` as the row's `token_budget`.*
- [x] `/goal` slash command: bare = show, `<objective>` = set, plus
      `clear|pause|resume`. Needs the engine on `_SlashView` (v2) and on v1's
      `AcpAgent`, because `agent/slash.py` is shared by both.
      *2026-09-24: shipped, `tests/integration/test_goal_slash.py` 20 green,
      ten mutations all detected. The v1 half of the note is WRONG and v1 is
      untouched: `_SLASH_COMMANDS` is one list both generations read AND
      advertise, so a command registered in `agent/slash.py` shows up in a v1
      session that runs no continuation loop and would answer "goal set" and
      then do nothing. The handler lives in a new `agent2/slash.py`, imported
      for its side effect from `agent2/agent.py`; the two generations are
      separate processes, so that reaches exactly the one that can honour it.
      Asserted in a fresh interpreter that imports only v1.*
      *Behaviour the draft did not anticipate: `/goal <objective>` on an idle
      session starts a turn IMMEDIATELY, because the handler runs no turn of its
      own and the loop reaches `_park` with an active goal and nothing in
      flight. Verified as codex parity, not a bug — `apply_external_goal_set`
      calls `continue_if_idle()` for a goal that is Active
      (ext/goal/src/runtime.rs:233), and codex's deferral table suppresses the
      pickup only for FORKED threads (one inserter, one caller:
      thread_fork_goal.rs:25). Now asserted in its own test.*
- [x] Model-facing tools so the loop can END: `goal_done` and `goal_blocked` as
      two subtools, not one mode dispatcher — `tools/task_tool.py`'s house rule is
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
      *2026-09-24: 16 store + 12 policy + 19 subtool + 14 driver + 20 slash =
      81 goal tests, no mocks anywhere — temp sqlite files, a real FastMCP
      subprocess, a real agent and transport, and a scripted model because a
      gate that needs a provider is not a gate. 28 mutations applied and every
      one detected, across Phases 3-6 (1 + 7 + 10 + 10); Phases 1-2 are store
      and pure-policy code, asserted directly rather than mutated. Full tier
      1407 passed, 0 failed.*
      *2026-09-25, Phase 8 closed: `./run_tests.sh -q` over every tier including
      the live e2e came back **1437 passed, 0 failed in 2154.88s (35m54s)**.
      81 goal tests became 83 (the eyeball's `progress()` fix and the
      compaction fixed-point test), and the manual eyeball ran for real and
      found a bug — see the two items below.*
- [x] The `crow_cli.tools` facade wart, found by Phase 5's registration check:
      `import crow_cli.tools.task` anywhere in the process left the MODULE on the
      package attribute, which shadows `__getattr__`, so `T.task` was afterwards
      a module and not the callable. `reload()` purged exactly this, so a real
      kernel was fine — but any in-process consumer that imported a submodule
      and then reached for the facade by name got something uncallable, and
      WHICH of the two you got depended on import order.
      *2026-09-25: fixed at the source, not papered over. Neither "stop setting
      the parent attribute" nor "make `__getattr__` win" was needed — both fight
      the import machinery. The names were the problem: every subtool module is
      now `<name>_tool.py`, so no submodule name is a binding name and there is
      nothing left to shadow. `crow_cli.tools.fs` is the function by exactly one
      route and `crow_cli.tools.fs_tool` is the module by exactly one route, in
      either order. Ten modules renamed (`edit fs memory rlm sg vision web write
      task goal`), 67 references updated, and three relative imports the first
      pass missed because they are call-time and indented — `sg_tool` from
      `.fs`, `fs_tool` from `.write`, `web_tool` from `.vision` — which is what
      the 23 failures in the first tier run were. The SUBTOOL names are
      untouched: `@subtool(tool="fs")` and the `_LAZY` keys are what the model
      calls, and only the module filenames moved.
      `reload()`'s purge stays, with its comment corrected: it still has one
      real job (a cached facade function surviving `importlib.reload` of the
      package in its own existing dict) and the shadowing job is gone.
      `tests/unit/test_tools_facade_names.py` pins the invariant three ways —
      the naming rule over the directory, every binding callable after every
      submodule is imported, and the original failure reproduced in a FRESH
      interpreter, which is the only state it can be reproduced in since
      anything that touched the facade first would cache the callable and hide
      it. Mutation-checked: adding `demo.py` bound as `demo` fails two of the
      three with `demo resolved to module`. Four test files carried
      workarounds and warnings for the old behaviour; all four are deleted.
      `crow-cli.spec` also gained `crow_cli.tools.goal_tool`, which Phase 5
      should have added next to `task_tool` — both are `_LAZY_V2` and both are
      resolved through importlib, so both are invisible to PyInstaller's static
      analysis. Four tiers: 1414 passed, 0 failed in 462.10s.*
- [ ] Objective length cap. codex enforces `MAX_THREAD_GOAL_OBJECTIVE_CHARS =
      4000` (protocol.rs:3957-3969) and crow enforces nothing: `/goal` will
      store a 200KB objective, and the objective is interpolated into
      `CONTINUATION_PROMPT` — whose size `test_the_prompt_stays_short` pins
      under 900 chars, with a comment reading "if this assertion fails,
      someone added a cathedral". An unbounded objective defeats that pin
      entirely, and it is re-sent on every
      continuation, so the cost is per turn rather than once. Belongs in
      `set_goal` (the store) and not in the slash handler, because a second
      entry point would need the same check and the store is the one place
      every writer passes through. NOT this sprint: it is a new rejection path
      with its own wording and its own test, and nothing in the shipped loop
      misbehaves without it.
- [x] Cleanup found along the way: `agent/slash.py:134-140` is an orphaned copy
      of `register_slash_command`'s body sitting after `stop_command`'s
      `return` — unreachable, and it references `name`/`description` that do
      not exist in that scope. Delete it.
      *2026-09-24: deleted, seven lines. `tests/integration/test_slash_commands.py`
      (v1's own nine) still green.*
- [x] ACP_V2.md: §5.4 stops being a proposal; `:28`'s status table and `:811`
      ("timers.py, celery | Not involved") get corrected to match what shipped.
      *2026-09-24: six edits, three of them beyond the item as written because
      the file was asserting things that are no longer true — §1's "a
      model-facing way to feed itself: does not exist", §5.5's "`TaskDelivery(`
      is constructed in exactly ONE place", and §5.8's "ship it without a
      budget". Every symbol named in the new text was grepped for in the file it
      is attributed to. §5.3's argument is now recorded as proven rather than
      predicted: the feature that looked most like it would need a scheduler
      needs no clock, no broker and no worker.*
- [x] `agent-client-protocol` 1.0.0rc2, and with it the end of the hardcoded
      `[tool.uv.sources]` path. Added mid-sprint on the user's instruction, and
      it turned out to be the fix for one of the gate's two failures:
      `test_source_first_spawn` clones this repo to a temp dir and runs `uv
      sync` there, and a relative path source cannot resolve in a clone.
      *2026-09-24: `7ae5438d`, 17 files, +538/−408. rc2 is the first PyPI
      release carrying `acp/experimental/v2/`, so the editable clone is no
      longer load-bearing and the `worktrees/python-sdk` symlink is deleted.
      Three separate breaks, of which only the first announces itself:
      (1) handlers now take the request's FIELDS as keywords with `_meta`
      spread among them; (2) `_dump` lost `exclude_none`, so an explicit `None`
      became a `null` on the wire and a `null` on an upsert is "cleared", not
      "unchanged" — found by the gate as `{'stopReason': None, 'usage': None}`
      in the idle update, fixed by `emitter.present()`; (3) `PromptResponse`
      gained a required `messageId`, so `events.Prompt` carries the id the
      handler minted and the driver echoes THAT one. v1 is untouched —
      `acp/router.py` adapts a legacy single-model handler with a
      DeprecationWarning. Before: 119 failed. After: 1409 passed, 0 failed in
      469.01s, plus `tests/e2e/test_agent2_live.py` 3 passed live. Recorded in
      ACP_V2.md §7 with the four stale facts it invalidated corrected.*

- [x] Phase 8's gate found two failures, and neither was allowed to stay
      labelled "pre-existing" without a diagnosis.
      *2026-09-25: both were reproduced in the reference checkout on main
      first, so neither was this sprint's. `test_source_first_spawn` was the
      `[tool.uv.sources]` path — a clone cannot resolve a relative path source —
      and the rc2 item above fixed it; the post-rc2 e2e tier shows it green.
      `test_compact_continues_live` was a `TimeoutError` at `TURN_TIMEOUT=1200`,
      and reading the failing run's own sqlite file turned it from a flake into
      a bug: the compaction handoff compounded, 11k -> 32k -> 58k -> 92k ->
      131k -> 172k chars over six generations, because `last_messages()` capped
      tool and assistant content and appended USER messages whole — and a
      successor's handoff IS a user message, so each compaction folded the
      previous one in whole. By generation five the successor was born over the
      30k ceiling. Fixed in `6ff6d2d3` (the cap) and `a1e3c9c2` (the prompt,
      because the growth then moved into the summary), the test's ceiling
      recalibrated against the timeout it has to fit in `7e1e177e`, and the
      whole thing green: 5 generations, 4 compactions, 864s.*
- [x] Phase 8.2's manual eyeball — the one check that sees a line the way a
      person does.
      *2026-09-25: run for real, `agent2.main` over stdio against the live
      model in a scratch dir. The loop works end to end: `/goal` advertised,
      objective accepted, continuation injected with the exact prompt text,
      eight `execute` rounds carrying four subtool calls, haiku.txt written and
      read back, `goal_done` moving the row to `complete` (turns 1, tokens
      75116, secs 54). And it found a bug that no test could have: the
      status line read "Turn 2 of at most 4" over the word "complete" on a row
      whose `turns_used` was 1, because `progress()` adds one for the
      continuation's benefit — correct there, where the turn is about to start,
      and wrong here, where nothing is in flight. Fixed in `2b0ed0cc` by letting
      the row's status decide. The 20 slash tests assert the strings the code
      produces and the code was self-consistent; only reading it made it look
      wrong.*

- [x] Cleanup, second pass: the residue the mandate names, found by looking at
      what sits in `tests/` that is not a test.
      *2026-09-25: `tests/analyze_payload_deep.py` and
      `tests/analyze_payload_cache_invalidation.py` deleted. Both were
      throwaway forensics for a llama.cpp KV-cache investigation —
      `#!/usr/bin/env python3`, reading `~/.agents/crow/logs` directly, never
      collected by pytest (the names are not `test_*`), and referenced by
      nothing in the repo, the docs, or git history outside the
      monorepo-flattening commit that moved them. `tests/` is the worst place
      for them: a directory that says "these are the checks" holding two
      scripts that check nothing. History keeps them.*

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
