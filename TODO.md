# crow-cli TODO — fresh sprint 2026-08-10

Needle focus: crow-memory-types ships Python bindings (PyO3). ONE contract —
the rust serde impls — for the crow-memory server AND the python SDK. No
codegen, no schema.json filepath hop, no drift. Distribution (PyPI/wheels)
comes AFTER the bindings work locally.

## Bindings (local first)
- [x] crow-memory-types: `python` feature — pyo3 0.29 (abi3-py314) + pythonize,
      py.rs macro wrapping all 14 wire types (from_dict/from_json/to_dict/to_json/
      getters), module consts DEFAULT_MEMORY_PORT + SCHEMA_JSON, maturin pyproject.
      DONE 34e0e864: all three configs green (python feature, plain, crow-memory link).
- [x] crow-memory-sdk rewired: deps = httpx + crow-memory-types (uv.sources path
      for now); types.py re-exports binding classes + wrappers (MessageRecord
      session_id/agent_idx, ImageRecord bytes data, SessionInfo last_message);
      client.py model_validate → from_dict; DELETED types_wire.py,
      scripts/gen_wire_types.py, tests/test_schema_drift.py; dropped pydantic +
      datamodel-code-generator. DONE 76259511: 18 passed, 7 skipped.
- [x] Consumers: crow-cli cli/main.py model_dump → to_dict, react.py serializer
      to_dict-aware, conftest FakeMemory from_dict; crow-mcp untouched (green).
      DONE a7ade75f: crow-cli 126 passed / crow-mcp 115 passed.
- [x] Live smoke: sdk against the RUNNING crow-memory service (27697, read-only).
      DONE: health/list_sessions/last_message/query_messages all through the
      bindings against live data.

## Housekeeping (already approved, after bindings)
- [x] New .github/workflows/publish-crow-memory.yml → crates.io (cargo publish
      crow-memory-types FIRST, sleep, then crow-memory). NOT pypi.
- [x] Scrub crow-orchestrator/crow-task remnants: README table rows,
      crow-cli/README layout, deleted TASK-SYSTEM.md. (pipelines + package
      dirs deleted by thomas.)
- [x] Version lockstep 0.1.31: crow-cli 0.1.30 → 0.1.31; crow-mcp dep
      crow-memory-sdk>=0.31 (broken spec) → >=0.1.31. (in a7ade75f)
- [x] publish-crow-memory-sdk.yml: keep as-is (reviewed, correct).
- [x] crow-cli/crow-mcp keep [tool.uv.sources] crow-memory-sdk path until the
      sdk is actually on PyPI (distribution phase).

## Deferred (distribution phase — in progress)
- [x] crates.io: YANKED 0.2.0 (both crates), PUBLISHED 0.1.31 (both) —
      2026-08-10, from local (cargo logged in). types first, then memory.
- [ ] crow-memory-types wheels → PyPI (maturin, abi3-py314, 7 targets).
      Needs: workflow + new-project bootstrap (pending trusted publisher or token).
- [ ] crow-memory-sdk → PyPI (workflow exists, reviewed).
- [ ] drop [tool.uv.sources] in crow-cli/crow-mcp, re-lock against PyPI,
      republish both (kills the zombie `crow-memory>=0.1.30` dep on PyPI).
- [ ] crow-memory-types README (crates.io + PyPI pages are blank without it).
- [ ] old PyPI `crow-memory` 0.1.30 (dead python pkg): tombstone or leave.
