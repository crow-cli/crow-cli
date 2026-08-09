# crow-cli-python PLAN

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Work the first unchecked item. Verify it. Mark it done in TODO.md AND here.
Commit at each item (`git add -A && git commit`). Never ask "want me to proceed".

## Build/test commands
- Python (per package): `cd <pkg> && uv sync && uv run pytest -x -q` (crow-cli also has `./run_tests.sh`)
- Rust (from worktree root): `cargo build --release`
- Install for live checks: `cd crow-cli && uv sync` then `uv run crow-cli-dev --help`

## Phase 1 — Renames (kill the PATH collisions)
1.1 Rename `crow-cli` console script → `crow-cli-dev` in crow-cli/pyproject.toml;
    update internal refs (README, docs, config templates, system prompts, tests).
    VERIFY: `uv sync` reinstalls; `uv run crow-cli-dev --help` exits 0; grep finds no
    leftover script named `crow-cli` in pyproject.
1.2 Rename `crow-mcp` console script → `crow-mcp-dev` in crow-mcp/pyproject.toml;
    update refs incl. any MCP client configs in-repo.
    VERIFY: `uv run crow-mcp-dev --help` (or module entry) exits 0.
1.3 Update `~/.crow/config.yaml` MCP setting to the crow-mcp-dev command.
    VERIFY: config parses (yaml load); command path in it exists.
    COMMIT.

## Phase 2 — crow-memory consolidation
2.1 Copy `crow-memory-types/` and `crow-memory/` crate sources from crow-cli main
    branch (~/src/crow-team/crow-cli) into this worktree root. Do NOT copy the Rust
    crow-memory-sdk. Create root `Cargo.toml` workspace with those members.
    VERIFY: `cargo metadata` resolves.
2.2 Remove crow-memory's dependency on Rust crow-memory-sdk (delete/replace the code
    that used it — the Python sdk is the client now). Fix any other dangling deps.
    VERIFY: `cargo build --release -p crow-memory -p crow-memory-types` green.
2.3 Boot the service, hit its health endpoint, kill it.
    VERIFY: HTTP 200 from health route (eyeball response).
2.4 Type sharing: research options (schemars→JSON Schema→datamodel-code-generator,
    contract tests, etc.), pick one, implement: generate/validate the pydantic models
    in Python crow-memory-sdk from crow-memory-types, with a test that FAILS on drift.
    VERIFY: generator/contract test runs red-on-drift, green now; decision written down
    in crow-memory-sdk/README.md.
2.5 Delete old Python `crow-memory` package; migrate lingering imports
    (crow_cli/agent/memory.py, crow_mcp/memory/main.py) to crow-memory-sdk.
    VERIFY: `grep -r "from crow_memory\b\|import crow_memory\b"` empty outside sdk;
    crow-cli + crow-mcp test suites pass. COMMIT per sub-item.

## Phase 3 — ACP upgrade (0.9.x → 0.12.0, v1 schema only)
3.1 Bump `agent-client-protocol` to 0.12.0 in crow-cli/pyproject.toml (and anywhere
    else it appears), `uv lock`, `uv sync`.
    VERIFY: lock resolves; import works.
3.2 Diff old vs new SDK surface used by our agent/client; fix breakage
    (schema models, transports, lifecycle helpers).
    VERIFY: crow-cli unit tests pass.
3.3 e2e: ACP initialize/handshake + one real turn through the agent.
    VERIFY: e2e script/test passes; evidence noted. COMMIT.

## Phase 4 — Daemon management
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

## Phase 5 — init
5.1 Extend `crow-cli-dev init`: keep config.yaml/prompts/searxng-defaults behavior;
    add ollama-mv fork build (~/src/crow-team/ollama) + llamacpp deps where needed
    (port the approach from crow-cli main's init).
    VERIFY: init on a scratch CROW_HOME writes config and builds/locates ollama-mv.
5.2 init starts the daemons (crow-memory, crow-mcp, ollama-mv) after setup.
    VERIFY: after init, `crow-cli-dev daemon status` shows them running. COMMIT.

## Phase 6 — Critique pass + test hardening
6.1 Read ~/src/crow-team/notes/dev/crow-cli-critique*.md (+ related notes); produce a
    triage list in TODO.md: applies → implement as sub-items; doesn't apply → why.
    VERIFY: triage written; each applies-item done or explicitly deferred w/ reason.
6.2 Implement the carried v1 item: retry transient provider 400s + capability-aware
    fallback + auto-strip on downgrade.
    VERIFY: unit test simulating the 400 class passes; fallback never lands on a
    text-only model with image blocks present.
6.3 Test sweep: fix stale assumptions, delete meaningless tests, add e2e coverage for
    the true usage paths touched in phases 2–5.
    VERIFY: full suite green across all packages; e2e count increased. COMMIT.

Done = every box in TODO.md checked (or deferred with written reason) AND PLAN phases
all marked with evidence. Then report.
