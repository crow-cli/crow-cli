# AGENTS.md

instructions for agents to follow

# RULES
1. Make no mistakes

# RUNNING
Run with: `cd crow-cli && uv --project . run crow-cli`

# ARCHITECTURE — the wire contract
- `crow-memory-types` is the SINGLE contract between the crow-memory server
  and every client. Rust crate (crates.io) + PyO3 bindings (cargo feature
  `python`, built by maturin via crow-memory-types/pyproject.toml).
- `crow-memory-sdk` imports the `crow_memory_types` native module — the SAME
  serde impls the server uses. No codegen, no schema.json hop, no drift.
  SDK wrappers (MessageRecord/SessionInfo/ImageRecord in types.py) add only
  client-side ergonomics.
- Versions move in LOCKSTEP across crow-memory-types, crow-memory,
  crow-memory-sdk, crow-cli, crow-mcp. Release = git tag → GitHub release →
  publish workflows use whatever version the manifests carry (no
  auto-increment). crates.io publish order: crow-memory-types FIRST, then
  crow-memory (depends on types by version; path is stripped on publish).
- crow-orchestrator-mcp and crow-task-mcp are DEAD (deleted 2026-08-10).
  Do not resurrect.

# GOTCHAS
- cargo on this laptop: always `-j 2`.
- Local `cargo check -p crow-memory-types --features python` needs
  `PYO3_PYTHON=$PWD/crow-memory-sdk/.venv/bin/python` (system python is 3.12,
  abi3-py314 needs >= 3.14). uv-driven builds find the venv automatically.
- uv does NOT rebuild the crow-memory-types path-dep wheel when rust sources
  change. After rust edits: `uv sync --reinstall-package crow-memory-types`.
- crates.io already holds crow-memory/crow-memory-types 0.2.0 (an earlier
  ACP-agnostic publish); local manifests are 0.1.31. Reconcile at next tag.
