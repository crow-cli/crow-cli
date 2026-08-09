# crow-cli-python TODO

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Context: Python is the future of crow-cli. The Rust rewrite (crow-cli repo,
main branch) was an experiment; its only survivors are the `crow-memory`
HTTP service and `crow-memory-types`. Everything else ports back to this
worktree (branch `crow-cli-python`; lands on main via REBASE, not merge).
Dynamic language = fast OODA loop; the heavy lifting lives in the Rust
crow-memory service behind HTTP, spoken to by the PYTHON crow-memory-sdk.

## Renames + config
- [x] Rename console script `crow-cli` → `crow-cli-dev` (pyproject + all internal refs) — 2026-08-09, `crow-cli-dev --help` verified
- [x] Rename console script `crow-mcp` → `crow-mcp-dev` (pyproject + refs) — 2026-08-09, `crow-mcp-dev --help` verified
- [x] Update `~/.crow/config.yaml` MCP setting for the crow-mcp-dev rename — 2026-08-09, key renamed, http url intact
  (criteria: `uv sync` clean; `crow-cli-dev --help` and `crow-mcp-dev --help` run;
  no collision with the Rust binaries in ~/.cargo/bin)

## crow-memory consolidation
- [x] Bring `crow-memory-types` crate from crow-cli main into this worktree (repo root layout) — 2026-08-09
- [x] Bring `crow-memory` crate (axum+LanceDB HTTP service); Rust crow-memory-sdk NOT brought over (dev-dep removed; its tests ported to python e2e) — 2026-08-09
- [x] Root `Cargo.toml` workspace over those two crates — 2026-08-09, `cargo metadata` + crow-memory-types build/test green; release build done (-j2, 30m22s), booted + /healthz ✓
- [x] Type sharing: rust structs = single source → schema.json (schemars, drift-tested in cargo) → types_wire.py (datamodel-code-generator, drift-tested in pytest) + port-const cross-check — 2026-08-09, both drift tests green
- [x] Delete old Python `crow-memory` (in-process lancedb) package; imports were already migrated to crow-memory-sdk (verified no `crow_memory` imports remain) — 2026-08-09
  (criteria: service binary builds + boots + answers /healthz or equivalent;
  crow-cli + crow-mcp pass their memory tests against the HTTP service;
  zero `crow_memory` imports remain outside the sdk)

## ACP upgrade
- [x] Bump `agent-client-protocol` >=0.9.0 → 0.12.0 (latest on PyPI, v1 schema;
      v2 does not exist for Python and we are NOT using it) — 2026-08-09, pinned >=0.12,<0.13
- [x] Fix agent + client code against the new SDK; e2e ACP handshake + a real turn work
      — 2026-08-09: no code changes needed (v1.19 extensible unions + lenient deser kept
      our surface intact); unit 69 ✓, integration 2 ✓, e2e 5 live ✓, `crow-cli-dev run` full turn ✓
  (NOT in scope: HTTP agent daemons, conductors, proxies)

## Daemon management
- [x] `crow-cli-dev daemon start|stop|restart|status|list` managing:
      crow-memory, crow-mcp (HTTP transport), ollama-mv, searxng (docker) — 2026-08-09 (be8a1e4a)
- [x] Docker control via the python docker SDK for searxng (compose file = definition source,
      SDK operates; `docker compose up -d` creates missing containers) — 2026-08-09
- [x] Runstate convention (pidfiles {config_dir}/run, logs {config_dir}/logs w/ 5MB×4 rotation,
      rust CLI conventions) + `daemons:` config overrides — 2026-08-09
      Verified live: status detects all 4 (unmanaged); crow-mcp full start→status→stop cycle on
      scratch config/port; searxng docker stop→start cycle. Refuses to kill unmanaged processes.

## init
- [x] `crow-cli-dev init`: existing wizard + ollama-mv build-from-source step
      (scripts/build-ollama.sh ported, OLLAMA_DIR/LLAMACPP_DIR/GO overridable) +
      daemon startup step (crow-memory, crow-mcp, ollama-mv, searxng) — 2026-08-09,
      verified `init --yes` on scratch dir: config/prompts/.env/compose written,
      binary detected, running daemons detected and left untouched

## Critique pass — DONE 2026-08-09
Notes live at `~/.crow/notes/dev/crow-cli-critique*.md` (moved with the notes).
Context: all 6 Rust top priorities were already fixed on the main branch
(6f5c12a1, c6b42b3e, ad786a75, a0e013c0, 08babc92, b8df9607) and our
consolidated crow-memory copy includes them. Triage below is about what the
critique means for the PYTHON code.

### Applies → implemented
- [x] `${VAR}` unset → silent empty string (critique config.rs:267). Rust main
      kept `unwrap_or_default`; Python now collects unset refs during
      `resolve_env_vars` and logs a config-load warning naming each one
      (configure.py). .env/shell still wins where set.
- [x] `.env` written world-readable (secrets file). init now chmods it 0600
      (init_cmd.py).
- [x] crow-mcp ignores config.yaml `memory_port` (critique crow-mcp/main.rs:71).
      In Python the whole stack resolved only via CROW_MEMORY_URL-or-27697 —
      including the CLI's own MemoryClient. Fix: Config.load exports
      CROW_MEMORY_URL from `memory_port` when not explicitly set (covers CLI
      client, stdio-spawned MCP servers via fastmcp env merge, and daemons via
      {**os.environ, **spec.env}); daemon crow-mcp spec also gets an explicit
      CROW_MEMORY_URL env. Verified: fastmcp stdio transport merges os.environ.
- [x] `max_retries_per_step` was write-only (parsed into Config, never read).
      Now passed as `max_retries` to send_request in react_loop.
- [x] Silent model fallback on resume (critique agent.rs:500; never fixed in
      Rust either). load_session now warns when the saved model is not in
      config.yaml and falls back to default; prompt() warns when a provider
      name doesn't resolve and the first provider is substituted.
- [x] Terminal fixed 300ms+200ms startup sleeps (critique terminal.rs:213).
      backend.py now writes the PS1 setup immediately (pty queues it) and waits
      for the RENDERED metadata prompt (echoed command fails json.loads, so the
      match is unambiguous; 10s timeout → warn+continue). Measured: init 38ms
      vs fixed 500ms+, command capture verified live.
- [x] Carried v1 item: retry transient provider 400s + capability-aware
      fallback + auto-strip on downgrade — see next item.

### Carried from the old v1 TODO (deferred-to-v2 item, now in scope) — DONE
- [x] Retry transient provider 400s (`invalid_parameter_error` / "Download
      multimodal file timed out" — DashScope server-side multimodal ingest
      timeouts): `_is_transient_provider_400` marker detection in react.py;
      send_request's APIError branch retries that class with the same
      exponential backoff as 429/5xx. Permanent 400s still fail fast.
- [x] Capability-aware model registry: models in config.yaml take optional
      `capabilities:` (None/unset = permissive assume-capable; a set restricts)
      and `fallbacks:` (ordered model names). Parsed in configure.py LLModel.
- [x] Fallback chain + auto-strip on downgrade: new agent/model_routing.py —
      route_model() walks fallbacks (same-provider only: the LLM client is
      bound to one provider), never lands on an incapable model; when no
      capable model exists, strip_unsupported_blocks() replaces image/audio
      blocks with placeholders in the outgoing request only (session history
      never mutated). Wired into send_request.
- [x] Tests: tests/unit/test_model_routing.py — 19 tests (routing matrix,
      strip semantics, real openai BadRequestError/AuthenticationError objects
      for the transient detector, fake-LLM retry/no-retry/route/strip through
      send_request). No litellm, all in-process per the v1 plan.

### Doesn't apply → why
- compact.py "drops multimodal/array content during compaction" (Rust
  b8df9607-class bug): NOT applicable. Python's compaction is by design a
  flatten-to-summary: new agent record gets summary + text transcript
  (unroll_content extracts text parts — the critique itself cited Python's
  unroll_content as the fix model for Rust); old messages stay untouched in
  the DB ("Nothing is ever deleted"). Images dying in the LIVE message flow
  (persist/hydrate) was the Rust bug; the Python path never had it.
- react.py:254 `except json.JSONDecodeError, TypeError, ValueError:` looking
  like a Py2 syntax error: NOT a bug. PEP 758 (Python 3.14) allows
  unparenthesized except without `as`; all three pyprojects pin
  requires-python >=3.14. Verified: ast.parse + compile + runtime catch all
  green on 3.14.5. (Now also at react.py:305/321, context.py:28 after edits.)
- Rust-specific critique items with no Python counterpart: id-counter race +
  list_sessions projection (fixed in our crow-memory copy via c6b42b3e),
  foreground-guard panic brick (Rust-only state machine), reqwest no-timeout
  (Python SDK uses httpx with explicit timeout — and its wedged-server test
  exposed + fixed a real gap: ReadTimeout wasn't in the retry catch, now
  TimeoutException is, both clients), ensure_absolute path fabrication
  (Rust-only), non-hermetic load_from_real_config test (no Python equivalent;
  checked all suites), skills-dir mismatch (Python consistently uses
  {config_dir}/skills = v1 behavior; the actual ~/.crow→~/.agents move is the
  deferred adoption item below).

### Noted, deferred (part of the ~/.agents adoption item)
- Skills dir: Python reads {config_dir}/skills (~/.crow/skills today); thomas
  already moved the real skills to ~/.agents/skills. The config-dir move
  belongs to the deferred ~/.agents adoption item, not this pass.

## Tests — DONE 2026-08-09
- [x] Full sweep green across all packages after every change:
      crow-cli unit 88 ✓ (+integration 90 ✓, live e2e 5 ✓),
      crow-mcp 115 ✓, crow-memory-sdk 10 ✓ (incl. wire contract vs the real
      freshly-built binary + wedged-server timeout).
- [x] Stale-assumption scan: no lancedb leftovers in tests (one historical
      docstring), no old script names in test logic, no non-hermetic tests,
      analyze_payload_*.py are standalone scripts (not pytest-collected).
- [x] e2e coverage for touched paths: wire-contract suite IS the e2e for the
      consolidated memory stack (spawns the real binary); terminal startup fix
      verified live; model routing covered by 19 unit tests with real openai
      exception objects.

## Deferred — captured, explicitly out of this sprint
- TASK-SYSTEM.md async long-running jobs / agent delegation (crow-task) — later
- ACP-over-HTTP agents, conductor, proxies — later
- ~/.agents directory adoption (skills → ~/.agents/skill, global AGENTS.md →
  ~/.agents/AGENTS.md, notes → ~/.agents/notes) — layout being driven by thomas
- The Rust crow-cli / crow-mcp / crow-server / crow-verifier crates die with the
  experiment; only crow-memory + crow-memory-types survive
