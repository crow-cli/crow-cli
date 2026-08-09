"""Drift tests for the rust↔python type-sharing pipeline.

Chain of trust:
  rust structs ──(cargo test in crow-memory-types)──> schema.json
  schema.json  ──(this file)────────────────────────> types_wire.py

Also cross-checks constants the JSON Schema cannot carry (the default
port).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SDK_ROOT = Path(__file__).resolve().parents[1]
WORKTREE_ROOT = SDK_ROOT.parent
sys.path.insert(0, str(SDK_ROOT / "scripts"))

import gen_wire_types  # noqa: E402


def test_wire_types_match_schema() -> None:
    """types_wire.py must be exactly what schema.json codegens to.

    On failure: uv --project crow-memory-sdk run python scripts/gen_wire_types.py
    """
    committed = (
        SDK_ROOT / "src" / "crow_memory_sdk" / "types_wire.py"
    ).read_text()
    assert committed == gen_wire_types.render(), (
        "types_wire.py drifted from crow-memory-types/schema.json — "
        "regenerate with scripts/gen_wire_types.py"
    )


def test_default_port_matches_rust() -> None:
    """DEFAULT_MEMORY_PORT must match the rust const (schema can't carry it)."""
    from crow_memory_sdk import DEFAULT_MEMORY_PORT

    rust_src = (
        WORKTREE_ROOT / "crow-memory-types" / "src" / "lib.rs"
    ).read_text()
    m = re.search(r"pub const DEFAULT_MEMORY_PORT: u16 = (\d+);", rust_src)
    assert m, "DEFAULT_MEMORY_PORT const missing from crow-memory-types"
    assert DEFAULT_MEMORY_PORT == int(m.group(1)), (
        f"python DEFAULT_MEMORY_PORT={DEFAULT_MEMORY_PORT} != rust {m.group(1)}"
    )
