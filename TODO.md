# crow-cli TODO

## [v2] Retry + capability-aware fallback on transient provider 400s

**Symptom (user-visible):** `Internal error: {"error":"data: {\"error\":{\"code\":\"invalid_parameter_error\",...,\"message\":\"Download multimodal file timed out\",...}}"}` — sporadic, mid-turn, kills the react loop.

**Diagnosis (from `~/.crow/logs/crow-cli-successful-wild-fulmar-of-awe.log:40-72`, 5 occurrences):**
- It is a provider-side **HTTP 400** (`openai.BadRequestError`), NOT a local network error.
  Stack: `main.py:725 await task` → `main.py:667 _execute_turn` → `react.py:632 send_request` → `openai/_base_client.py:1669` raises.
- The openai SDK auto-retries 429 / 5xx / connection resets, but **never 4xx**. So a
  transient server error propagates straight out of `react_loop` and aborts the turn.
- `Download multimodal file timed out` is DashScope/Alibaba's **server-side** multimodal
  ingest step timing out while processing the image payload. Sporadic ⇒ transient, not
  deterministic. Correlates with the lance image split: hydration now re-inlines full
  base64 images every turn (observed 130k-token prompts carrying image blocks), so the
  multimodal payload is large and occasionally exceeds their ingest deadline.
- **Not a correctness bug on our side.** It's a missing retry on a transient 400 plus,
  longer-term, no fallback when a model chokes on multimodal content.

**Plan — DEFERRED to crow-cli v2 (v1 react loop / store.py are FROZEN, do not patch here):**
1. **Retry this error class.** Treat `invalid_parameter_error` / `Download multimodal file timed out`
   (and sibling transient ingest errors) as retryable *despite* the 400 status: bounded
   exponential backoff inside `send_request`, distinct from the SDK's own retry policy.
2. **Capability-aware model registry.** Tag each model with capabilities (vision, audio,
   tool-use, context window). A fallback chain must NEVER land on a text-only model while
   the conversation carries image/audio blocks.
3. **Auto-strip on downgrade.** If we do fall back to a model lacking a modality, strip the
   unsupported content blocks (image/audio → `[image omitted: model has no vision]` placeholder)
   automatically instead of hard-failing. Bans on image/audio data are derived from capabilities,
   not hardcoded per provider.
4. **Round-robin / fallback chain, no litellm.** We don't run litellm today; keep it out of the
   stack. Build the retry+fallback+capability routing in-process (Rust in v2).

**Status:** not fixing in v1. Revisit when the v2 ACP client/agent is built.
