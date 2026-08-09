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
- [x] Root `Cargo.toml` workspace over those two crates — 2026-08-09, `cargo metadata` + crow-memory-types build/test green; release build of service pending (running -j2)
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
- [ ] `crow-cli-dev daemon start|stop|restart|status|list` managing:
      crow-memory, crow-mcp (HTTP transport), ollama-mv, searxng (docker)
- [ ] Docker control via the python docker SDK for searxng (compose-level control)
- [ ] Runstate convention (pidfiles/ports) + service registry in config

## init
- [ ] `crow-cli-dev init`: existing behavior (config.yaml, prompts, searxng defaults)
      PLUS build the ollama-mv fork (~/src/crow-team/ollama) + deps (llamacpp where
      needed), and start the daemons (crow-memory, crow-mcp, ollama-mv)

## Critique pass
- [ ] Triage the critique notes (~/src/crow-team/notes/dev/crow-cli-critique*.md):
      what applies to current crow-cli-python → implement; what doesn't → record why here
- [ ] Carried from the old v1 TODO (deferred-to-v2 item, now in scope):
      retry transient provider 400s (`invalid_parameter_error` / multimodal ingest
      timeouts) + capability-aware model fallback with auto-strip on downgrade

## Tests
- [ ] Keep unit/integration tests green AND meaningful throughout; fix stale assumptions
- [ ] Add e2e tests where they catch bugs unit/integration cannot (true usage paths)

## Deferred — captured, explicitly out of this sprint
- TASK-SYSTEM.md async long-running jobs / agent delegation (crow-task) — later
- ACP-over-HTTP agents, conductor, proxies — later
- ~/.agents directory adoption (skills → ~/.agents/skill, global AGENTS.md →
  ~/.agents/AGENTS.md, notes → ~/.agents/notes) — layout being driven by thomas
- The Rust crow-cli / crow-mcp / crow-server / crow-verifier crates die with the
  experiment; only crow-memory + crow-memory-types survive
