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

- [ ] crow-cli: SDK 1.0.0rc3 -> 1.1.0 (v1 schema 1.35.0, v2 exp alpha.7). Gate: unit + acp2 integration suites green.
- [ ] crow-cli: availableCommands in new/resume/fork responses (keep the notification too). Gate: assertion test + suites green.
- [ ] crow-cli: failure after prompt insertion ends as idle(stopReason="error") (alpha.7 open string allows it). Gate: new test + live smoke.
- [ ] crow-cli: audit reliance on silent validation drops (SDK now raises); fix stale usage_model docstring. Gate: audit note + suites green.
- [ ] crow Rust: crate 2.2.0 -> 5.6.1 behavior-preserving migration (features stdio/process, v1::schema/v2::schema paths, Option<ConnectionDriver>, Error conversions, drop unstable_session_compaction). Gate: cargo test green, no UX change.
- [ ] crow Rust: beta.4 adoption + alpha.7 tolerance: flat AvailableCommand shim, replay_complete closes ReplayWindow (response fallback kept), error stopReason string|object -> transcript, unknown state, availableCommands from setup responses, compaction status patch, paused/background tolerated. Gate: characterization tests incl. flat-command palette.
- [ ] crow TS: vendored v2 types alpha.2 -> beta.4 from @agentclientprotocol/sdk 2.12.0; typecheck green; acpThreadState handles error stopReason + tolerates new updates. Gate: bun typecheck + existing acp tests.
- [ ] vscode-acp: crowAcp.server paste-able JSON entry (spawn|external), existing settings remain fallback; backend keeps owning state + spawning. Gate: unit tests for parse/merge; build+typecheck green.
- [ ] chat webview: red error bubble, copy button top right copies error text; fed by v2 error idle + JSON-RPC errors. Gate: component/unit test + eyeball.
- [ ] Interop gate: worktree crow TUI <-> worktree crow-cli acp2 live (new/resume+replay/prompt/cancel/permission/compaction/error); webview via extension vs worktree daemon. Gate: observed transcripts/logs, not claims.
- [ ] Commit each coherent unit with Session-Id: economic-urchin-of-easy-pleasure trailer in BOTH worktrees.

## Deferred (reason: python-sdk main is still alpha.7; beta.4 agent-side bindings do not exist yet)

- replay_complete emission, subagent_update/session_message, background work methods (tool_call/cancel, terminal/cancel, paused, background lists), skill command union + skill content blocks, idempotencyKey, client systemPrompt, terminal size, structured ErrorStopReason object, _meta/cost patch semantics. Client side (Rust+TS) tolerates/renders these when they arrive. Revisit when python-sdk ships beta bindings or we vendor codegen.

## Environment facts

- Upstream: schema v2.0.0-beta.4 = Preview (Nov 20). Rust crate 5.6.1 = v1.35.0+beta.4. TS SDK 2.12.0 = same. Python SDK 1.1.0 = v1.35.0 + v2 alpha.7 (ceiling).
- alpha.7 StopReason is an open string; AvailableCommand is flat (no type). beta.4 AvailableCommand is a command|skill union; flat commands must be tolerated client-side.
- rustc 1.98.1, bun 1.4.2, uv-managed Python 3.13.
- crow repo's old TODO/PLAN (coordination backend sprint) is fully complete; replaced on this branch.
