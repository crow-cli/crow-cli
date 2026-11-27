## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

# TODO — v2-preview sprint (master; crow-side mirror in ../crow-v2-preview/TODO.md)

Worktrees: /home/thomas/.agents/crow/src/crow-cli-v2-preview (branch v2-preview)
and /home/thomas/.agents/crow/src/crow-v2-preview (branch v2-preview).
User mandate: implement the ACP v2 Preview upgrade in both, keep behavior as
close to current as possible, make the two worktrees work together. The
vscode-acp extension stays backend-owns-state/spawns-agent with a lightweight
webview; add a paste-able settings entry like an MCP server. Errors render as
a red bubble with copy-click top right.

## Scope

- [x] crow-cli: SDK 1.0.0rc3 -> 1.1.0 (v1 schema 1.35.0, v2 exp alpha.7). Gate: unit + acp2 integration suites green.
- [x] crow-cli: availableCommands in new/resume/fork responses (keep the notification too). Gate: assertion test + suites green.
- [x] crow-cli: failure after prompt insertion ends as idle(stopReason="error") (alpha.7 open string allows it). Gate: new test + live smoke.
- [x] crow-cli: audit reliance on silent validation drops (SDK now raises); fix stale usage_model docstring. Gate: audit note + suites green.
- [x] crow Rust: crate 2.2.0 -> 5.6.1 behavior-preserving migration. DONE crow 4d96115: features stdio/process/unstable_protocol_v2/unstable_end_turn_token_usage (dropped unstable_session_compaction), v1::schema/v2::schema, Option<ConnectionDriver>, Error conversions, StopReason Error arm, Malformed-frame batch scan, raw Builder::new; profile.dev split-debuginfo=unpacked fixes >4GiB DWARF link overflow. cargo test -j 2: 960 passed, no UX change.
- [x] crow Rust: beta.4 adoption + alpha.7 tolerance. DONE crow c60e32b: replay_complete closes ReplayWindow (response fallback kept), error stopReason string|object -> error, unknown/paused/background states never settle, setup-response availableCommands, compaction status patch (omitted unchanged/null->in_progress), typed+flat palette. 6 characterization tests; cargo test -j 2: 966 passed.
- [x] crow TS: vendored v2 types alpha.2 -> beta.4 from @agentclientprotocol/sdk 2.12.0; typecheck green; acpThreadState handles error stopReason + tolerates new updates. Gate: bun typecheck + existing acp tests. DONE crow ba3d8f8: stable beta.4 types (fork tolerance cast for alpha.7 peers), error stopReason -> incomplete/error with crash text lifted into status.error; chat typecheck clean, 110/110 (8 new).
- [x] vscode-acp: crowAcp.server paste-able JSON entry (spawn|external), existing settings remain fallback; backend keeps owning state + spawning. Gate: unit tests for parse/merge; build+typecheck green. DONE crow fb23db0: resolveServerEntry in backend.ts, field-by-field override, configError fails start; 6 new tests, unit 70/70, build+typecheck green.
- [x] chat webview: red error bubble, copy button top right copies error text; fed by v2 error idle + JSON-RPC errors. Gate: component/unit test + eyeball. DONE crow c4b8646 (message-error.aui.tsx): copy button top right, full text pre-wrap; 3 component tests, chat 113/113. Eyeball DONE Phase 6 (/tmp/error_bubble.png).
- [x] Interop gate: DONE Phase 6. beta.4 client <-> alpha.7 agent wire (/tmp/interop_wire.jsonl): new/resume+replay/prompt/error turn; real crow-agent TUI PTY spawns worktree crow-cli acp2 (/tmp/tui_pane.txt PONG). Web e2e error bubble 7/7 x3, /tmp/error_bubble.png red bubble + copy top right (light+dark).
- [x] Commit each coherent unit with Session-Id: economic-urchin-of-easy-pleasure trailer in BOTH worktrees.

## Deferred (reason: python-sdk main is still alpha.7; beta.4 agent-side bindings do not exist yet)

- replay_complete emission, subagent_update/session_message, background work methods (tool_call/cancel, terminal/cancel, paused, background lists), skill command union + skill content blocks, idempotencyKey, client systemPrompt, terminal size, structured ErrorStopReason object, _meta/cost patch semantics. Client side (Rust+TS) tolerates/renders these when they arrive. Revisit when python-sdk ships beta bindings or we vendor codegen.

## Environment facts

- Upstream: schema v2.0.0-beta.4 = Preview (Nov 20). Rust crate 5.6.1 = v1.35.0+beta.4. TS SDK 2.12.0 = same. Python SDK 1.1.0 = v1.35.0 + v2 alpha.7 (ceiling).
- alpha.7 StopReason is an open string; AvailableCommand is flat (no type). beta.4 AvailableCommand is a command|skill union; flat commands must be tolerated client-side.
- rustc 1.98.1, bun 1.4.2, uv-managed Python 3.13.
- crow repo's old TODO/PLAN (coordination backend sprint) is fully complete; replaced on this branch.
