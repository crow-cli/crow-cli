//! Writes the wire-type JSON Schema for the python sdk's codegen.
//!
//! Usage: cargo run -p crow-memory-types --bin gen-schema [out.json]

fn main() {
    let schema = serde_json::to_string_pretty(&crow_memory_types::wire_schema()).unwrap();
    let out = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "schema.json".into());
    std::fs::write(&out, schema + "\n").unwrap_or_else(|e| panic!("write {out}: {e}"));
    eprintln!("wrote {out}");
}
