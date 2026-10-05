# TODO — M6: ACP v2 wire layer in the web frontend

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Sprint: M6 (ACP v2) in the vendored `@assistant-ui/acp` package. Backend v2 is
already merged (`acp2 --http`, commit `3fcf7fd7`). This is the frontend client
half: a NEW code path for protocol version 2, leaving v1 `AcpClient` intact.

**COMPLETE — all items verified.** Evidence below; see PLAN.md for the phase
trajectory.

## Items (unordered)

- [x] Add v2 reducer arms (`state_update`, `user_message`, `agent_message`,
      `agent_thought`, `tool_call_content_chunk`) — `9a4ad3fc`.
- [x] Commit the reducer/types/AcpClientLike work as one coherent unit —
      `9a4ad3fc` `feat(acp): add v2 reducer arms, session-update types, and AcpClientLike`.
- [x] `AcpClientV2` (new file, never touching v1 `AcpClient`) —
      `1a7d445f`:
      - `initialize` sends `{ protocolVersion: 2, info }` (NOT `clientInfo`).
      - `prompt()` resolves on the matching idle `state_update` (or cancel),
        NOT the `session/prompt` ack — v2 `PromptResponse` is only `{messageId}`.
      - `session/new`, `session/list`, `session/resume` (replaces `session/load`),
        `session/set_config_option` with `{sessionId, configId, value, type}`.
      - `session/delete` and `session/close` per v2 capability surface.
      - routes `state_update` into controller run-end handling.
      - cancel via `session/cancel` notification.
      - maps v2 `InitializeResponse`/`NewSessionResponse`/`ResumeSessionResponse`
        to the v1-shaped `AcpInitializeResponse`/`AcpSessionResponse` the
        controller already consumes.
- [x] Negotiate/probe v1 vs v2: choose `AcpClientV2` for `acp2 --http` (`:2771`)
      or when `protocol` option says 2; otherwise keep `AcpClient` v1 —
      `33db5ddc` (useAcpRuntime `protocol?: "auto" | 1 | 2`, `wantsV2`).
- [x] `AcpThreadController` + `useAcpRuntime` accept `AcpClientLike` instead of
      concrete `AcpClient` — `33db5ddc`.
- [x] Verify: `bun run web:typecheck` exit 0, `bun run web:build` exit 0,
      `cargo test -p crow-web` passes (64 tests), backend `uv run pytest
      tests/integration/test_acp2_http.py` passes (1 test). All green this sprint.
- [x] Commit v2 client + negotiation + controller rewiring (Session-Id trailer)
      — `1a7d445f` + `33db5ddc`.

## Verification criteria (the floor for every item)

- [x] `bun run web:typecheck` exit 0 (from MAIN).
- [x] `bun run web:build` exit 0 (from MAIN).
- [x] `cargo test -p crow-web` passes — 64 passed, 0 failed.
- [x] `uv run pytest tests/integration/test_acp2_http.py` passes — 1 passed.
- [x] v1 `AcpClient.ts` behavior is unchanged — diff `9cdd623a..HEAD` on
      `AcpClient.ts` is purely additive (the `AcpClientLike` type export); no
      edits to v1 request/response logic.
