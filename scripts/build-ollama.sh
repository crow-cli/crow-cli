#!/usr/bin/env bash
# Build the vendored ollama fork (vendor/ollama) against its pinned llama.cpp
# (vendor/llama.cpp, tag from vendor/ollama/LLAMA_CPP_VERSION). Offline:
# cmake consumes the sibling submodule via OLLAMA_LLAMA_CPP_SOURCE instead of
# cloning GitHub. Output: vendor/ollama/ollama (Go binary) +
# vendor/ollama/build/lib/ollama/ (llama-server runner, found via cwd).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OLLAMA="$ROOT/vendor/ollama"
LLAMACPP="$ROOT/vendor/llama.cpp"
GO="${GO:-$HOME/.local/go/bin/go}"

[ -e "$OLLAMA/.git" ] || {
  echo "vendor/ollama missing — run: git submodule update --init vendor/ollama" >&2
  exit 1
}
[ -e "$LLAMACPP/.git" ] || {
  echo "vendor/llama.cpp missing — run: git submodule update --init vendor/llama.cpp" >&2
  exit 1
}

pinned="$(tr -d '[:space:]' <"$OLLAMA/LLAMA_CPP_VERSION")"
at="$(git -C "$LLAMACPP" describe --tags --exact-match 2>/dev/null || git -C "$LLAMACPP" rev-parse --short HEAD)"
if [ "$at" != "$pinned" ]; then
  echo "error: vendor/llama.cpp is at '$at' but vendor/ollama pins '$pinned':" >&2
  echo "  git -C vendor/llama.cpp fetch --depth 1 origin tag $pinned && git -C vendor/llama.cpp checkout $pinned" >&2
  exit 1
fi

# llama-server runner (CPU-only; OLLAMA_LLAMA_BACKENDS unset = no CUDA/ROCm)
# + Go binary (ollama-go target → vendor/ollama/ollama). Offline llama.cpp via
# the sibling submodule.
OLLAMA_LLAMA_CPP_SOURCE="$LLAMACPP" cmake -B "$OLLAMA/build" -S "$OLLAMA" \
  -DCMAKE_BUILD_TYPE=Release -DGO_EXECUTABLE="$GO"
cmake --build "$OLLAMA/build" --parallel 8

echo "built: $OLLAMA/ollama + $OLLAMA/build/lib/ollama/"
