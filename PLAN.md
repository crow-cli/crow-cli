# PLAN — M6: ACP v2 frontend client path

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Scope capture: `TODO.md`. Repo root = MAIN (`~/.agents/crow/src/crow-cli`).

**Gate (floor for every item):** `bun run web:typecheck`
**Gate (before declaring the phase done):** `bun run web:build`
**Backend regression:** `uv run pytest tests/integration/test_acp2_http.py`
**Rust regression:** `cargo test -p crow-web`

Trajectory is numeric: 1 → 2 → 3 → 4. Commit at each phase boundary with the
`Session-Id:` trailer.

---

## Phase 1 — commit the reducer/types/AcpClientLike groundwork

1. `git status` + `git diff` to confirm the only changes are
   `packages/aui/acp/src/types.ts`, `acpThreadState.ts`, `AcpClient.ts`, and the
   untracked `v2/` files.
2. Run `bun run web:typecheck` (already green).
3. Commit with the Session-Id trailer.

## Phase 2 — implement `AcpClientV2`

1. New file `packages/aui/acp/src/AcpClientV2.ts`, sharing the JSON-RPC plumbing
   shape of v1 but with v2 request/response shapes.
2. `initialize` → `{ protocolVersion: 2, info }`; map `info`→`agentInfo`,
   `capabilities`→`agentCapabilities`.
3. `session/new` → `{ cwd, mcpServers }` → `{ sessionId, configOptions }`.
4. `session/list` → `{ cwd?, cursor? }` → `{ sessions, nextCursor }`.
5. `session/resume` → `{ sessionId, cwd, mcpServers, replayFrom: {type:"start"} }`
   → `{ configOptions }` (this replaces v1 `session/load`).
6. `session/set_config_option` → `{ sessionId, configId, value, type: "id" }`
   → `{ configOptions }`.
7. `session/delete` → capability-gated; crow does NOT claim it, so refuse with a
   clear error (same shape as v1's delete gate).
8. `prompt()` → send `session/prompt`, await ack, then resolve on the next
   idle `state_update` (or `stopReason: "cancelled"`); FIFO-queue idle edges so
   steers resolve in send order.
9. `cancel()` → `session/cancel` notification.
10. `releaseSession()` → local clear only (server keeps the thread for
    `session/list`), matching v1 semantics.
11. Export `AcpClientV2` from `index.ts`.

## Phase 3 — negotiation + controller takes `AcpClientLike`

1. `AcpThreadControllerOptions.client` and `private client` become `AcpClientLike`.
2. `useAcpRuntime` gains a `protocol?: "auto" | 1 | 2` option (default "auto");
   when `2` (or URL looks like `acp2`/`:2771`), construct `AcpClientV2`.
3. Typecheck + build green.

## Phase 4 — full verification + final commit

1. `bun run web:typecheck`, `bun run web:build`.
2. `cargo test -p crow-web`.
3. `uv run pytest tests/integration/test_acp2_http.py`.
4. Commit remaining work.
