# TODO — M6: ACP v2 wire layer in the web frontend

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Sprint: M6 (ACP v2) in the vendored `@assistant-ui/acp` package. Backend v2 is
already merged (`acp2 --http`, commit `3fcf7fd7`). This is the frontend client
half: a NEW code path for protocol version 2, leaving v1 `AcpClient` intact.

Committed so far: `9cdd623a` (consume acp as source), plus uncommitted
`types.ts` / `acpThreadState.ts` v2-reducer additions and `AcpClient.ts`
`AcpClientLike` — typechecking now (verified `bun run web:typecheck` exit 0).

## Items (unordered)

- [x] Add v2 reducer arms (`state_update`, `user_message`, `agent_message`,
      `agent_thought`, `tool_call_content_chunk`) — done, typechecks.
- [ ] Commit the reducer/types/AcpClientLike work as one coherent unit.
- [ ] `AcpClientV2` (new file, never touching v1 `AcpClient`):
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
- [ ] Negotiate/probe v1 vs v2: choose `AcpClientV2` for `acp2 --http` (`:2771`)
      or when `protocol` option says 2; otherwise keep `AcpClient` v1.
- [ ] `AcpThreadController` + `useAcpRuntime` accept `AcpClientLike` instead of
      concrete `AcpClient`.
- [ ] Verify: `bun run web:typecheck` exit 0, `bun run web:build` exit 0,
      `cargo test -p crow-web` passes, backend `uv run pytest
      tests/integration/test_acp2_http.py` still passes.
- [ ] Commit v2 client + negotiation + controller rewiring (Session-Id trailer).

## Verification criteria (the floor for every item)

- `bun run web:typecheck` exit 0 (from MAIN).
- `bun run web:build` exit 0 (from MAIN).
- `cargo test -p crow-web` passes.
- `uv run pytest tests/integration/test_acp2_http.py` passes (backend v2 intact).
- v1 `AcpClient.ts` behavior is unchanged — the diff must be additive, no
  edits to v1 request/response logic beyond the shared `AcpClientLike` type.
