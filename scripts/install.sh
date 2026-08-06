#!/usr/bin/env bash
# Install all crow binaries into ~/.cargo/bin from ONE shared release build.
#
# Why not `cargo install --path` per crate: --path is single-crate, and each
# invocation builds every dependency again in a scratch target dir. This
# builds the workspace once (deps compiled once, release cache reused) and
# installs the binaries — same result, a fraction of the time.
#
# Hermetic since 15.2: protobuf-src compiles protoc from source, so no
# PROTOC env var or system protobuf needed. Requires: cmake + C++ toolchain.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${DEST:-$HOME/.cargo/bin}"
JOBS="${JOBS:-2}"

cd "$ROOT"
cargo build --release -j "$JOBS"

mkdir -p "$DEST"
for bin in crow-cli crow-mcp crow-server crow-memory crow-verifier; do
    install -m 755 "$ROOT/target/release/$bin" "$DEST/$bin"
    echo "installed: $DEST/$bin"
done

echo
echo "Next: $DEST/crow-cli init   (writes config.yaml, prompts, searxng defaults)"
