"""Generate pydantic wire models from the crow-memory-types JSON Schema.

The rust crate crow-memory-types is the SINGLE SOURCE OF TRUTH for the
crow-memory HTTP contract. Pipeline:

  rust structs --(cargo run --bin gen-schema)--> crow-memory-types/schema.json
  schema.json  --(this script)-----------------> crow_memory_sdk/types_wire.py

Both hops are drift-tested:
  - rust:  cargo test -p crow-memory-types  (schema_json_up_to_date)
  - python: pytest crow-memory-sdk/tests/test_schema_drift.py

Usage: uv --project crow-memory-sdk run python scripts/gen_wire_types.py
"""

from __future__ import annotations

import re
from pathlib import Path

from datamodel_code_generator import DataModelType, InputFileType, generate
from datamodel_code_generator.format import Formatter

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "crow-memory-types" / "schema.json"
OUT = Path(__file__).resolve().parents[1] / "src" / "crow_memory_sdk" / "types_wire.py"

HEADER = '''"""GENERATED from crow-memory-types/schema.json — do not edit by hand.

Regenerate: uv --project crow-memory-sdk run python scripts/gen_wire_types.py
Source of truth: the rust structs in crow-memory-types/src/lib.rs.
"""

'''

# The schema root (a $defs-only document) codegens into this noise class.
_ROOT_CLASS = re.compile(
    r"class CrowMemoryWireTypes\(RootModel\[Any\]\):.*?\n\n\n", re.DOTALL
)


def render() -> str:
    """Generate the types_wire.py body from the committed schema.json."""
    body = generate(
        input_=SCHEMA,
        input_file_type=InputFileType.JsonSchema,
        output_model_type=DataModelType.PydanticV2BaseModel,
        disable_timestamp=True,
        formatters=[Formatter.BLACK, Formatter.ISORT],
    )
    return HEADER + re.sub(r"\n{4,}", "\n\n\n", _ROOT_CLASS.sub("", body))


def main() -> None:
    OUT.write_text(render())
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
