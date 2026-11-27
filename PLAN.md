## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

# PLAN — v2-preview sprint (master)

Build/gates:
    crow-cli:  uv --project /home/thomas/.agents/crow/src/crow-cli-v2-preview run pytest tests/unit -q
               uv --project ... run pytest tests/integration/test_acp2_http.py tests/integration/test_cli_acp2.py tests/integration/test_agent2_gate.py -q
    crow Rust: cargo test   (from /home/thomas/.agents/crow/src/crow-v2-preview/crates/crow-client)
    crow TS:   bun run typecheck && bun test test/unit   (from packages/vscode-acp; aui/acp tests via bun test in packages/aui/acp)

Trajectory: 1 -> 2 -> 3 -> 4 -> 5 -> 6. Commit at each item boundary,
trailer Session-Id: economic-urchin-of-easy-pleasure. crow-side mirror of
items 2-5 lives in ../crow-v2-preview/PLAN.md — mark both when done.
Principle: behavior-preserving first (migration), then additive preview
adoption, then the interop gate. Keep v1 paths untouched.

## Phase 1 — crow-cli SDK 1.1.0 (worktree crow-cli-v2-preview)

- [x] 1.1 Bump pyproject to agent-client-protocol[http]>=1.1.0, uv sync, run unit + acp2 integration gates; fix fallout (validation now raises; module loggers; removed NES/PlanUpdateFile/connect_mcp — none used, verified).
  Verify: gates green; commit.
- [x] 1.2 availableCommands in new_session/resume_session/fork responses alongside the existing notification.
  Verify: new assertion in integration test; gates green; commit.
- [x] 1.3 Turn failure after insertion -> idle(stop_reason="error") from the driver failure path (pre-insertion failures stay JSON-RPC errors).
  Verify: new test drives a failing turn and observes idle error; gates green; commit.
- [x] 1.4 Audit silent-drop reliance + stale docstrings (emitter.usage_model), note findings in TODO.
  Verify: grep audit + gates green; commit if edits.

Phase 1 evidence (2026-11-27): commits 09cf9611 (SDK bump), cb4cc229
(palette responses), 528620a5 (crash-path gate), ce2d26d0 (audit note).
Unit 940/940; agent2 gate + client2 subagent 74/74; acp2 http/cli gate 45/45.

## Phase 2 — crow Rust crate 5.6.1 migration (worktree crow-v2-preview)

- [x] 2.1 DONE crow 4d96115: crate 5.6.1, features stdio/process/unstable_protocol_v2/unstable_end_turn_token_usage; dropped unstable_session_compaction (fork not called via typed Rust SDK).
- [x] 2.2 DONE crow 4d96115: v1::schema/v2::schema; root ErrorCode struct + consts; From<v1::Error>.
- [x] 2.3 DONE crow 4d96115: (Channel, Option<ConnectionDriver>); non_exhaustive configs; RawJsonRpcId/RawJsonRpcResponse; raw Builder::new guard-free entry.
  Verify (2.1-2.3 together): cargo test green incl. fixtures/layout; commit. No UX change.
  DONE crow 4d96115 (2026-11-27): cargo test -p crow-client -j 2 -> 960 passed,
  0 failed. profile.dev split-debuginfo=unpacked added: beta.4 schema grew test
  DWARF past the 4GiB 32-bit relocation limit (link overflow); split DWARF links
  cleanly, no codegen/runtime change. Build with -j 2 to bound core usage.

## Phase 3 — crow Rust beta.4 adoption + alpha.7 tolerance

- [x] 3.1 DONE crow c60e32b: palette reads name/description raw, so beta.4 typed command + alpha.7 flat both populate; characterization test.
- [x] 3.2 DONE crow c60e32b: is_replay_complete closes window; resume-response fallback kept; test.
- [x] 3.3 DONE crow c60e32b (Error arm in 4d96115): bare word + object -> error notice; unknown/future states never idle; tests.
- [x] 3.4 DONE crow c60e32b: apply_setup reads availableCommands; compaction patch semantics; paused/background tolerated; tests.
  Verify: cargo test green; commit per item.
  DONE crow c60e32b (2026-11-27): cargo test -p crow-client -j 2 -> 966 passed
  (+6 characterization), 0 failed. Structured ErrorStopReason object rendering
  and background-work methods remain Deferred (python-sdk still alpha.7); the
  client tolerates/parses them without crashing.

## Phase 4 — crow TS types beta.4

- [x] 4.1 Vendor types.gen.ts from @agentclientprotocol/sdk v2.12.0 into packages/aui/acp/src/v2/; update index.ts header; fix compile fallout behavior-preserving.
  Verify: bun typecheck (aui/acp + chat + vscode-acp) green; existing acp unit tests green; commit. DONE ba3d8f8 (crow): stable schema only, ClientOptions artifact stripped, session.fork read via tolerance cast (beta.4 moved fork to unstable; alpha.7 agents still send it). chat typecheck clean.
- [x] 4.2 acpThreadState/conversions: error stopReason -> message status error carrying the error text; tolerate replay_complete/unknown/new updates.
  Verify: new/existing unit tests green; commit. DONE ba3d8f8 (crow): AcpStopReason+"error"; settleErrorStatus lifts trailing 'agent error: …' into status.error on idle/run-end/run-handoff; unknown updates already fall through the default arm. 8 new tests, 110/110 chat tests.

## Phase 5 — vscode-acp entry + error bubble

- [x] 5.1 crowAcp.server paste-able JSON setting (spawn: {command,args,model,port,cwd,mcpServers} | external: {endpoint}); existing per-field settings remain fallback; backend.ts architecture unchanged.
  Verify: new unit tests (parse/merge/fallback); build+typecheck+unit green; commit. DONE fb23db0 (crow): resolveServerEntry (backend.ts, pure) + configError start seam; 6 new tests, unit 70/70, build+typecheck green.
- [x] 5.2 Red error bubble in chat webview with copy button top right (copies error text), fed by turn errors (v2 error idle + JSON-RPC errors).
  Verify: unit/component test + eyeball via integration or e2e; commit. DONE c4b8646 (crow): message-error.aui.tsx, copy top right, full text; 3 component tests, chat 113/113. Eyeball at Phase 6.

## Phase 6 — interop gate (both worktrees together)

- [x] 6.1 DONE: beta.4-shaped JSON-RPC client <-> real alpha.7 crow-cli agent (/tmp/interop_probe.py, wire /tmp/interop_wire.jsonl): initialize protocolVersion 2, session/new availableCommands in response, prompt ack(messageId)->running->thought/message chunks->usage_update->idle(end_turn,usage), resume+replay (replayFrom start), error turn idle stopReason="error" + "agent error: …" text. Real crow-agent TUI on PTY spawns worktree crow-cli acp2 (/tmp/tui_interop.py, pane /tmp/tui_pane.txt): prompt echo, thought, PONG, badge crow-cli acp2 · qwen3.8-max. KEY: beta.4 SetSessionConfigOptionRequest.value is serde(flatten) -> wire top-level type+bare value = alpha.7; do NOT nest.
- [x] 6.2 DONE: web e2e error-bubble test (stub fail() -> running -> "agent error: …" -> idle stopReason error) green 7/7 x3 runs; /tmp/error_bubble.png vision-judged: red destructive bubble, copy button top right, light + dark themes. Fixed bun:test expect (no toContainText) + new-thread composer-remount race (wait for session row).
- [x] 6.3 DONE: gates re-run (web e2e 7/7; chat/aui/ext unchanged by Phase 6), files marked, commits complete, goal_done + summary.
