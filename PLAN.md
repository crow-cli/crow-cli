# PLAN — M6: ACP v2 frontend client path

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Scope capture: `TODO.md`. Repo root = MAIN (`~/.agents/crow/src/crow-cli`).

**Gate (floor for every item):** `bun run web:typecheck` — PASS
**Gate (before declaring the phase done):** `bun run web:build` — PASS
**Backend regression:** `uv run pytest tests/integration/test_acp2_http.py` — PASS (1 passed)
**Rust regression:** `cargo test -p crow-web` — PASS (64 passed)

Trajectory is numeric: 1 → 2 → 3 → 4. Committed at each phase boundary with the
`Session-Id:` trailer.

---

## Phase 1 — commit the reducer/types/AcpClientLike groundwork — DONE

1. `git status` + `git diff` confirmed the only changes were
   `packages/aui/acp/src/types.ts`, `acpThreadState.ts`, `AcpClient.ts`, and the
   untracked `v2/` files.
2. `bun run web:typecheck` green.
3. Committed — `9a4ad3fc` `feat(acp): add v2 reducer arms, session-update types, and AcpClientLike`.

## Phase 2 — implement `AcpClientV2` — DONE

1. New file `packages/aui/acp/src/AcpClientV2.ts`, sharing the JSON-RPC plumbing
   shape of v1 but with v2 request/response shapes.
2. `initialize` → `{ protocolVersion: 2, info }`; maps `info`→`agentInfo`,
   `capabilities`→`agentCapabilities`.
3. `session/new` → `{ cwd, mcpServers }` → `{ sessionId, configOptions }`.
4. `session/list` → `{ cwd?, cursor? }` → `{ sessions, nextCursor }`.
5. `session/resume` → `{ sessionId, cwd, mcpServers, replayFrom: {type:"start"} }`
   → `{ configOptions }` (replaces v1 `session/load`).
6. `session/set_config_option` → `{ sessionId, configId, value, type: "id" }`
   → `{ configOptions }`.
7. `session/delete` → capability-gated; crow does NOT claim it, so refuses with a
   clear error (same shape as v1's delete gate).
8. `prompt()` → send `session/prompt`, await ack, then resolve on the next
   idle `state_update` (or `stopReason: "cancelled"`); FIFO-queue idle edges so
   steers resolve in send order.
9. `cancel()` → `session/cancel` notification.
10. `releaseSession()` → local clear only (server keeps the thread for
    `session/list`), matching v1 semantics.
11. Exported `AcpClientV2` from `index.ts`.

Committed — `1a7d445f` `feat(acp): add AcpClientV2 — the protocol-2 client path, v1 untouched`.

## Phase 3 — negotiation + controller takes `AcpClientLike` — DONE

1. `AcpThreadControllerOptions.client` and `private client` became `AcpClientLike`.
2. `useAcpRuntime` gained `protocol?: "auto" | 1 | 2` (default "auto"); `"auto"`
   constructs `AcpClientV2` when the URL looks like `acp2`/`:2771`, else v1.
3. Typecheck + build green.

Committed — `33db5ddc` `feat(acp): controller/runtime speak AcpClientLike with v1/v2 negotiation`.

## Phase 4 — full verification + final commit — DONE

1. `bun run web:typecheck` — exit 0; `bun run web:build` — exit 0.
2. `cargo test -p crow-web` — 64 passed, 0 failed.
3. `uv run pytest tests/integration/test_acp2_http.py` — 1 passed.
4. Remaining work committed — `33db5ddc`.
