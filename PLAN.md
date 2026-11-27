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

- [ ] 1.1 Bump pyproject to agent-client-protocol[http]>=1.1.0, uv sync, run unit + acp2 integration gates; fix fallout (validation now raises; module loggers; removed NES/PlanUpdateFile/connect_mcp — none used, verified).
  Verify: gates green; commit.
- [ ] 1.2 availableCommands in new_session/resume_session/fork responses alongside the existing notification.
  Verify: new assertion in integration test; gates green; commit.
- [ ] 1.3 Turn failure after insertion -> idle(stop_reason="error") from the driver failure path (pre-insertion failures stay JSON-RPC errors).
  Verify: new test drives a failing turn and observes idle error; gates green; commit.
- [ ] 1.4 Audit silent-drop reliance + stale docstrings (emitter.usage_model), note findings in TODO.
  Verify: grep audit + gates green; commit if edits.

## Phase 2 — crow Rust crate 5.6.1 migration (worktree crow-v2-preview)

- [ ] 2.1 Cargo.toml: agent-client-protocol 5.6.1, features stdio, process, unstable_protocol_v2, unstable_end_turn_token_usage (+ unstable_session_fork if fork is called); drop unstable_session_compaction. cargo check.
- [ ] 2.2 Import migration schema::v1 -> v1::schema, schema::v2 -> v2::schema (8 files); ProtocolVersion + Error paths/conversions.
- [ ] 2.3 ConnectTo::into_channel_and_future -> (Channel, Option<ConnectionDriver>) in acp.rs runners; AcpAgent config non-exhaustive; raw response type if touched.
  Verify (2.1-2.3 together): cargo test green incl. fixtures/layout; commit. No UX change.

## Phase 3 — crow Rust beta.4 adoption + alpha.7 tolerance

- [ ] 3.1 AvailableCommand union parsing + flat-command tolerance (missing type -> command). Characterization test: alpha.7 flat commands populate the palette.
- [ ] 3.2 replay_complete closes ReplayWindow; resume-response fallback kept for alpha.7 agents. Test both paths.
- [ ] 3.3 error stopReason (string "error" or {error:{...}} object) -> TurnOutcome error surfaced in transcript; unknown state tolerated. Tests.
- [ ] 3.4 availableCommands from setup responses; compaction status patch (omitted unchanged, null -> in_progress); paused status + background lists tolerated without crash. Tests.
  Verify: cargo test green; commit per item.

## Phase 4 — crow TS types beta.4

- [ ] 4.1 Vendor types.gen.ts from @agentclientprotocol/sdk v2.12.0 into packages/aui/acp/src/v2/; update index.ts header; fix compile fallout behavior-preserving.
  Verify: bun typecheck (aui/acp + chat + vscode-acp) green; existing acp unit tests green; commit.
- [ ] 4.2 acpThreadState/conversions: error stopReason -> message status error carrying the error text; tolerate replay_complete/unknown/new updates.
  Verify: new/existing unit tests green; commit.

## Phase 5 — vscode-acp entry + error bubble

- [ ] 5.1 crowAcp.server paste-able JSON setting (spawn: {command,args,model,port,cwd,mcpServers} | external: {endpoint}); existing per-field settings remain fallback; backend.ts architecture unchanged.
  Verify: new unit tests (parse/merge/fallback); build+typecheck+unit green; commit.
- [ ] 5.2 Red error bubble in chat webview with copy button top right (copies error text), fed by turn errors (v2 error idle + JSON-RPC errors).
  Verify: unit/component test + eyeball via integration or e2e; commit.

## Phase 6 — interop gate (both worktrees together)

- [ ] 6.1 Live: worktree crow TUI spawns worktree crow-cli acp2 — new, resume+replay, prompt, cancel, permission, compaction, error turn. Evidence: captured transcript/log.
- [ ] 6.2 Webview via extension against worktree daemon: prompt round-trip + error bubble eyeball.
- [ ] 6.3 Final: re-run all gates, mark files, commit leftovers, goal_done + summary.
