# crow-cli-python PLAN

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Work the first unchecked item. Verify it. Mark it done in TODO.md AND here.
Commit at each item (`git add -A && git commit`). Never ask "want me to proceed".

## Build/test commands
- Python (per package): `cd <pkg> && uv sync && uv run pytest -x -q` (crow-cli also has `./run_tests.sh`)
- Rust (from worktree root): `cargo build --release`
- Install for live checks: `cd crow-cli && uv sync` then `uv run crow-cli-dev --help`

## Phase 1 — Renames (kill the PATH collisions) — DONE 2026-08-09 (f9b29066)
1.1 [x] crow-cli → crow-cli-dev; `crow-cli-dev --help` exits 0 (eyeballed).
1.2 [x] crow-mcp → crow-mcp-dev; `crow-mcp-dev --help` exits 0 (eyeballed).
1.3 [x] ~/.crow/config.yaml key crow-mcp → crow-mcp-dev; yaml intact.

## Phase 2 — crow-memory consolidation — DONE 2026-08-09 (f917368d; 2.3 verified 2026-08-09 after -j2 build)
2.1 Copy `crow-memory-types/` and `crow-memory/` crate sources from crow-cli main
    branch (~/src/crow-team/crow-cli) into this worktree root. Do NOT copy the Rust
    crow-memory-sdk. Create root `Cargo.toml` workspace with those members.
    VERIFY: `cargo metadata` resolves.
2.2 Remove crow-memory's dependency on Rust crow-memory-sdk (delete/replace the code
    that used it — the Python sdk is the client now). Fix any other dangling deps.
    VERIFY: `cargo build --release -p crow-memory -p crow-memory-types` green.
2.3 Boot the service, hit its health endpoint, kill it.
    VERIFY: HTTP 200 from health route (eyeball response).
    DONE 2026-08-09: release build finished (-j2, 30m22s); booted on scratch
    config/port 27698, `/healthz` -> {"ok":true}; wire-contract e2e
    (test_wire_contract.py) 10/10 against the real binary.
2.4 Type sharing: research options (schemars→JSON Schema→datamodel-code-generator,
    contract tests, etc.), pick one, implement: generate/validate the pydantic models
    in Python crow-memory-sdk from crow-memory-types, with a test that FAILS on drift.
    VERIFY: generator/contract test runs red-on-drift, green now; decision written down
    in crow-memory-sdk/README.md.
2.5 Delete old Python `crow-memory` package; migrate lingering imports
    (crow_cli/agent/memory.py, crow_mcp/memory/main.py) to crow-memory-sdk.
    VERIFY: `grep -r "from crow_memory\b\|import crow_memory\b"` empty outside sdk;
    crow-cli + crow-mcp test suites pass. COMMIT per sub-item.

## Phase 3 — ACP upgrade — DONE 2026-08-09 (84634b3f)
3.1 [x] Bumped to 0.12.0 (pinned >=0.12,<0.13); lock + sync clean.
3.2 [x] No code fixes needed — schema v1.19 extensible unions + lenient
        deserialization kept our usage intact; unit 69 green.
3.3 [x] e2e: integration handshake 2/2, live-LLM e2e 5/5, full
        `crow-cli-dev run` turn eyeballed (ACP-UPGRADE-OK).

## Phase 4 — Daemon management — DONE 2026-08-09 (be8a1e4a)
4.1 Design runstate layout (pid/port files under ~/.crow/run or similar) + service
    registry (config-driven): crow-memory, crow-mcp, ollama-mv, searxng.
4.2 Implement `crow-cli-dev daemon start|stop|restart|status|list` for process
    services (crow-memory binary, crow-mcp-dev HTTP, ollama-mv binary).
    VERIFY: start→status(running)→stop→status(stopped) for crow-memory and crow-mcp.
4.3 Docker-backed services via python docker SDK: searxng container control
    (start/stop/status; compose file checked into repo).
    VERIFY: daemon start searxng brings container up; status shows it; stop kills it.
4.4 e2e: `daemon start` everything, run a memory round-trip through crow-mcp-dev,
    `daemon stop` everything. COMMIT per sub-item.

## Phase 5 — init — DONE 2026-08-09 (808adc87)
5.1 Extend `crow-cli-dev init`: keep config.yaml/prompts/searxng-defaults behavior;
    add ollama-mv fork build (~/src/crow-team/ollama) + llamacpp deps where needed
    (port the approach from crow-cli main's init).
    VERIFY: init on a scratch CROW_HOME writes config and builds/locates ollama-mv.
5.2 init starts the daemons (crow-memory, crow-mcp, ollama-mv) after setup.
    VERIFY: after init, `crow-cli-dev daemon status` shows them running. COMMIT.

## Phase 6 — Critique pass + test hardening — DONE 2026-08-09
6.1 Read ~/src/crow-team/notes/dev/crow-cli-critique*.md (+ related notes); produce a
    triage list in TODO.md: applies → implement as sub-items; doesn't apply → why.
    VERIFY: triage written; each applies-item done or explicitly deferred w/ reason.
    DONE: full triage in TODO.md ("Critique pass"); 7 applies-items implemented
    (${VAR} warn, .env 0600, memory_port wiring, max_retries_per_step, silent
    model-fallback warnings, terminal sentinel startup, SDK timeout retry gap).
6.2 Implement the carried v1 item: retry transient provider 400s + capability-aware
    fallback + auto-strip on downgrade.
    VERIFY: unit test simulating the 400 class passes; fallback never lands on a
    text-only model with image blocks present.
    DONE: react.py transient-400 retry (real BadRequestError objects in tests),
    model_routing.py (capabilities + fallbacks config, same-provider chain,
    auto-strip placeholders), 19 unit tests green.
6.3 Test sweep: fix stale assumptions, delete meaningless tests, add e2e coverage for
    the true usage paths touched in phases 2–5.
    VERIFY: full suite green across all packages; e2e count increased. COMMIT.
    DONE: crow-cli 88 unit / 90 w-integration / 5 live e2e ✓; crow-mcp 115 ✓;
    crow-memory-sdk 10 ✓ incl. wire contract against the freshly built binary.
    Stale-assumption scan clean (see TODO.md Tests section).

## Phase 7 — ~/.agents layout adoption — DONE 2026-08-09
Was deferred; pulled in by user directive (the file headers ARE the feedback).
Target: CONFIG_DIR ~/.crow → ~/.agents/crow; skills DECOUPLED from the config
dir → ~/.agents/skills (sibling); notes → ~/.agents/notes; global AGENTS.md →
~/.agents/AGENTS.md.
7.1 [x] Code: configure.py path constants (AGENTS_DIR/DEFAULT_CONFIG_DIR/
        SKILLS_DIR/NOTES_DIR/GLOBAL_AGENTS_MD); cli defaults (main.py typer
        options, init_cmd.py); session.py (context tree, get_skills, global
        AGENTS.md); defaults.py prompt texts + CONFIG_YAML; crow-mcp logger;
        README + tests. Zero `.crow` refs left in shipped src.
7.2 [x] Disk: skills rsynced (newer Aug-4 revisions landed; .venv excluded),
        stale ~/.crow/skills retired; notes moved; jinja2 prompts +
        compose.yaml + searxng/ copied; config.yaml merged (crow-mcp-dev http
        + memory_path ~/.agents/crow/memory.lance + memory_port + embedding);
        .env verified superset at new location.
7.3 [x] VERIFY: Config.load() end-to-end on new default dir; daemon status
        sees all 4 daemons from the new config dir (nothing restarted);
        suites green (crow-cli 90, crow-mcp 115, sdk 10). COMMIT.

## Phase 8 — daemon `all` polish + docker unmanaged tracking — DONE 2026-08-09
User asked for `daemon (re)start/stop all` — already existed (name defaults
to "all"); the work was making it SAFE.
8.1 [x] restart() unmanaged-skip for process daemons (single message instead
        of stop-refusal + start-noop compound).
8.2 [x] Docker unmanaged tracking: start() records container id in the
        pidfile slot; status() managed = recorded id matches; stop()/
        restart() refuse/skip unmanaged containers — fixes the incident
        where `restart all --config-dir <scratch>` restarted the live
        searxng container.
8.3 [x] VERIFY: 11 new unit tests (docker SDK boundary faked); scratch-dir
        `restart all` skips all real services, cycles only scratch crow-mcp;
        crow-cli suites green (99 unit / 101 w-integration). COMMIT.

## Phase 9 — async memory path, rip out sync httpx — DONE 2026-08-09
User directive: "let's change them both to be async ... then we can rip out
sync httpx code". The agent ran its memory I/O through the SDK's sync client
inside an otherwise-async turn pipeline (event-loop blocking, worst on
search).
9.1 [x] SDK async-only: sync_client.py deleted, SyncMemoryClient unexported;
        wire-contract suite ported to async (pytest-asyncio added to the sdk
        dev group; concurrency test uses asyncio.gather).
9.2 [x] Agent: memory.py adapter async; session.py surface async; call sites
        awaited in react.py / compact.py / agent/main.py; cli/main.py inspect
        gets an asyncio.run wrapper.
9.3 [x] VERIFY: crow-cli 99 unit / 101 w-integration ✓, sdk 10 ✓ (real
        binary), crow-mcp 120 ✓; live `inspect` smoke (list + session
        branches) against the real service. Zero SyncMemoryClient refs left.
        COMMIT.

Done = every box in TODO.md checked (or deferred with written reason) AND PLAN phases
all marked with evidence. Then report.
