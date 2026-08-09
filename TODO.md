# crow-cli-python TODO

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Context: Python is the future of crow-cli. The Rust rewrite (crow-cli repo,
main branch) was an experiment; its only survivors are the `crow-memory`
HTTP service and `crow-memory-types`. Everything else ported back on branch
`crow-cli-python` and LANDED on main via merge 9eb8533d (branch tree adopted
WHOLESALE as source of truth; only TASK-SYSTEM.md kept from old main).
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
  checked all suites), skills-dir mismatch (Python's `{config_dir}/skills` is
  the legacy v1 layout; the target is `~/.agents/skills` decoupled from the
  config dir — see the deferred note below, not a critique miss).

### ~/.agents layout — IMPLEMENTED 2026-08-09 (was deferred; user directive)
- Skills DECOUPLE from the config dir: `{config_dir}/skills` → `~/.agents/skills`
  (sibling of the config dir `~/.agents/crow`). Rust's `~/.agents/skills` scan
  (the critique's "wrong directory vs v1" item) was the future layout; v1/Python
  `{config_dir}/skills` was the legacy one. See Phase 7 below.

## ~/.agents layout adoption — DONE 2026-08-09
CONFIG_DIR ~/.crow → ~/.agents/crow; skills decoupled → ~/.agents/skills;
notes → ~/.agents/notes; global AGENTS.md → ~/.agents/AGENTS.md.
- [x] Code: configure.py constants (AGENTS_DIR / DEFAULT_CONFIG_DIR /
      SKILLS_DIR / NOTES_DIR / GLOBAL_AGENTS_MD); cli/main.py + init_cmd.py
      defaults; session.py context tree + get_skills + global AGENTS.md read
      from ~/.agents; defaults.py prompt texts + CONFIG_YAML memory_path;
      crow-mcp logger → ~/.agents/crow/logs; README + tests updated
- [x] Disk: skills rsynced ~/.crow → ~/.agents (newer Aug-4 updates landed;
      .venv excluded), stale ~/.crow/skills retired; notes moved;
      *.jinja2 prompts + compose.yaml + searxng/ copied to ~/.agents/crow;
      config.yaml merged (crow-mcp-dev http mcpServers + memory_path
      ~/.agents/crow/memory.lance + memory_port 27697 + embedding section);
      .env already a superset at the new location (verified key-by-key)
- [x] Verified: Config.load() on the new default dir end-to-end (incl.
      Phase-6 memory_port → CROW_MEMORY_URL export); `daemon status` from the
      new config dir sees all 4 daemons running/healthy, nothing restarted;
      full suites green (90 / 115 / 10)
      Legacy ~/.crow left in place (crow.db, state.db, old memory.lance,
      logs) — inert data, deliberately not deleted.

## Green-stack e2e (side-by-side with blue) — DONE 2026-08-09
Prove crow-cli-python runs a full agent turn completely independently of the
services the Rust main branch manages — blue and green live at the same time.
- [x] vendor submodules on this branch: .gitmodules was EMPTY + vendor/
      gitlinks missing (branch predates them on main) — brought from main
      (ollama 6970db8, llama.cpp 46deb9f crow-colqwen2-mv) (61cc829f)
- [x] daemon: crow-memory gets --config {config_dir}/config.yaml; memory_bin
      falls back to PATH (4e197f05)
- [x] Green env ~/.agents/crow-py: config.yaml cloned from blue with
      memory_port 27698 / own memory.lance / mcp :2771; .env copied with
      CROW_MEMORY_PORT=27698 (env beats config.yaml memory_port in the
      server's precedence — first start attempt bound 27697 because of the
      copied 27697 line)
- [x] Green daemons up beside blue: crow-memory :27698 + crow-mcp :2771
      managed; ollama-mv + searxng shared (stateless infra, unmanaged)
- [x] e2e caught + fixed 2 bugs (dc225e14): run --config-dir was DEAD
      (spawned agent loaded default config → 'green' turn persisted to blue
      store + used blue MCP); TOOL_ICONS/STATUS_ICONS NameError in the run
      client renderer
- [x] VERIFIED: full turn (LLM qwen3.8-max-preview + terminal tool + 5
      persisted messages) routes exclusively through green — green store has
      the session, blue store has zero agents for it, green crow-mcp log
      shows the tool execution. Spin down: crow-cli-dev daemon stop all
      --config-dir ~/.agents/crow-py

## Async memory path — DONE 2026-08-09
The agent's turn pipeline is fully async (AsyncOpenAI, react_loop, ACP
handlers) but memory I/O went through the SDK's SYNC client — every
persist/search blocked the event loop. Now async end to end:
- [x] SDK: SyncMemoryClient + sync_client.py RIPPED OUT; MemoryClient
      (httpx.AsyncClient) is the only flavor; wire-contract suite ported
      to async (concurrency test now asyncio.gather)
- [x] Agent adapter (agent/memory.py) async over the SDK client
- [x] session.py async surface: get_session_by_cwd, lookup_or_create_prompt,
      make_agent_session, AgentSession add_message/add_tool_response/
      add_assistant_response/_save_messages/create/load/get_max_agent_idx/
      list_sessions/close
- [x] Call sites awaited: react.py (4 persist sites), compact.py,
      agent/main.py (8 sites), cli/main.py inspect → asyncio.run wrapper
- [x] Tests: conftest FakeMemoryClient async; test_compact fixtures async;
      crow-mcp cross-process test seeds via async client
- [x] Verified: suites green (crow-cli 99/101, sdk 10, crow-mcp 120) +
      live `inspect` smoke vs the real service (both branches)

## Daemon `all` commands + docker unmanaged tracking — DONE 2026-08-09
`daemon start|stop|restart|status all` already existed at the CLI layer
(name argument defaults to "all"; `list` = `status all`). Two fixes:
- [x] restart() on an unmanaged process daemon printed stop's refusal AND
      then start's no-op (confusing compound message) → single
      "running unmanaged — restart skipped (stop it yourself, then
      `daemon start`)"
- [x] Docker kind had NO unmanaged concept — `restart all` from a scratch
      config dir restarted the REAL searxng container. Now symmetric with
      processes: start() records the started container's id in the pidfile
      slot; status() sets managed iff recorded id == current container id
      (detail "unmanaged" otherwise); stop()/restart() refuse/skip when the
      record is absent or mismatched. Shared _unmanaged() helper; read_pid
      rebuilt on string-aware _read_record (pidfile holds a container id
      for docker daemons).
- [x] 11 new unit tests (tests/unit/test_daemon.py) — real lifecycle code,
      docker SDK boundary faked at _docker_container (real container never
      touched by tests)
- [x] Verified: scratch config dir — start/restart all correctly skip all 4
      real services and cycle only the scratch crow-mcp; real searxng
      untouched (still Up); scratch dir cleaned up after

## Phase 11 — daemon install ollama-mv (provisioning) — DONE 2026-08-09
- [x] daemon.py moved into crow_cli/cli/ (CLI functionality; top level keeps
      agent_runner only); all import sites updated; worktree_root() parents
      index fixed for the extra depth
- [x] New crow_cli/cli/embeddings.py (port of the main branch's
      embeddings.rs): find_go ($GO → ~/.local/go/bin/go → PATH); vendor
      checkouts prefer the worktree's vendor/ submodules, clone the forks
      into {config_dir}/vendor on a fresh machine; LLAMA_CPP_VERSION pin
      check vs the llama.cpp tag (bail with fix instructions); cmake Release
      build (-j min(cpus,8), offline via OLLAMA_LLAMA_CPP_SOURCE);
      provision() idempotent; repoint_command edits config.yaml surgically
      (comments survive; text-append when no daemons section yet);
      verify_embeddings (POST /api/embed colbert:true, 120s timeout,
      24 × 5s retries)
- [x] `daemon install <name>` command: provision → start (unmanaged-safe) →
      verify; --no-verify escape hatch; only ollama-mv has an installer
- [x] ollama-mv DaemonSpec: OLLAMA_MODELS env added
      (~/.local/share/ollama-mv-models — matches the running server);
      command chain OLLAMA_MV_BIN → worktree vendor → config-dir vendor →
      legacy dev checkout
- [x] init step 5 now routes through embeddings.provision (replaces the raw
      build-ollama.sh subprocess whose parents[3] script path was dead)
- [x] 14 new unit tests (tests/unit/test_embeddings.py); crow-cli 115 ✓
      w-integration, crow-mcp 115 ✓ (+5 tier-gated), sdk 10 ✓
- [x] Verified live: blue install idempotent no-op (finds the Aug-5
      ~/.agents/crow/vendor binary, unmanaged :11392 untouched, embeddings
      OK); forced build from a scratch config built the worktree submodules
      (ollama 0.30.8), repointed surgically, re-run idempotent; scratch
      cleaned up

## Tests — DONE 2026-08-09
- [x] Full sweep green across all packages after every change:
      crow-cli unit 99 ✓ (+integration 101 ✓, live e2e 5 ✓),
      crow-mcp 115 ✓, crow-memory-sdk 10 ✓ (incl. wire contract vs the real
      freshly-built binary + wedged-server timeout).
- [x] Stale-assumption scan: no lancedb leftovers in tests (one historical
      docstring), no old script names in test logic, no non-hermetic tests,
      analyze_payload_*.py are standalone scripts (not pytest-collected).
- [x] e2e coverage for touched paths: wire-contract suite IS the e2e for the
      consolidated memory stack (spawns the real binary); terminal startup fix
      verified live; model routing covered by 19 unit tests with real openai
      exception objects.

## Land on main — DONE 2026-08-09
- [x] Merge crow-cli-python into main treating the branch as single source
      of truth: `git merge -s ours --no-commit --no-ff` skeleton (dodges the
      delete/modify conflicts) → `git rm -rf .` → `git checkout
      crow-cli-python -- .` → restore keep-list → commit (9eb8533d, parents
      ee2cb032 + 5dfbbf6f). `git diff crow-cli-python main` = ONLY
      TASK-SYSTEM.md (+159). Keep-list: TASK-SYSTEM.md (reference for the
      task-system plan). vendor submodules initialized in main worktree.
      NOT pushed (no explicit request).

## Cancellation robustness — thinking-token audit + tests
The old `add_assistant_response` guard dropped thinking-only turns ("if it's
just thinking tokens don't add that shit") — fixed aacac95a + regression test
5dfbbf6f. User directive: audit ALL remaining assumptions about thinking
tokens and test cancellation thoroughly (unit + e2e).
- [ ] Audit: grep every thinking/reasoning_content/empty-content assumption
      in react.py, session.py, compact.py, send_request normalization, ACP
      update path; list findings.
- [ ] Unit tests: cancel during thinking (done: 5dfbbf6f); cancel during
      content streaming; cancel AFTER tool-call streaming (tool_calls must
      NOT be persisted — orphan tool_calls break the conversation);
      reconstruction round-trip keeps reasoning_content; send_request keeps
      reasoning_content in the outgoing payload.
- [ ] e2e (live LLM, sparingly): cancel a real turn mid-flight; assert the
      persisted turn carries reasoning_content and the next turn's
      reconstruction includes it.
      (criteria: suite green; audit findings written down; e2e ran once)

## Provider reasoning_content probe
User hypothesis: the provider (alibaba/dashscope) receives reasoning_content
in the request history but drops it — "it emits, but it doesn't actually
operate on it."
- [ ] Verify the harness actually SENDS reasoning_content: inspect a real
      outgoing request payload (request log / chunk log).
- [ ] A/B against the provider: same history with vs without
      reasoning_content on an assistant message; does the answer change?
      Report which side is dropping it (harness vs provider).

## Deferred — captured, explicitly out of this sprint
- TASK-SYSTEM.md async long-running jobs / agent delegation (crow-task) — later
- ACP-over-HTTP agents, conductor, proxies — later
- The Rust crow-cli / crow-mcp / crow-server / crow-verifier crates die with the
  experiment; only crow-memory + crow-memory-types survive
