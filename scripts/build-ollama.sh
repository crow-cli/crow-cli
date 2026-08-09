#!/usr/bin/env bash
# Build the ollama multivector fork against its pinned llama.cpp. Offline:
# cmake consumes the sibling llama.cpp checkout via OLLAMA_LLAMA_CPP_SOURCE
# instead of cloning GitHub. Output: $OLLAMA_DIR/ollama (Go binary) +
# $OLLAMA_DIR/build/lib/ollama/ (llama-server runner, found via cwd).
#
#   OLLAMA_DIR    ollama fork checkout   (default ~/src/crow-team/ollama)
#   LLAMACPP_DIR  llama.cpp checkout     (default ~/src/crow-team/llama.cpp)
#   GO            go toolchain           (default ~/.local/go/bin/go)
set -euo pipefail

OLLAMA="${OLLAMA_DIR:-$HOME/src/crow-team/ollama}"
LLAMACPP="${LLAMACPP_DIR:-$HOME/src/crow-team/llama.cpp}"
GO="${GO:-$HOME/.local/go/bin/go}"

[ -e "$OLLAMA/.git" ] || {
  echo "ollama fork missing at $OLLAMA — clone it or set OLLAMA_DIR" >&2
  exit 1
}
[ -e "$LLAMACPP/.git" ] || {
  echo "llama.cpp missing at $LLAMACPP — clone it or set LLAMACPP_DIR" >&2
  exit 1
}

pinned="$(tr -d '[:space:]' <"$OLLAMA/LLAMA_CPP_VERSION")"
at="$(git -C "$LLAMACPP" describe --tags --exact-match 2>/dev/null || git -C "$LLAMACPP" rev-parse --short HEAD)"
if [ "$at" != "$pinned" ]; then
  echo "warning: $LLAMACPP is at '$at' but the ollama fork pins '$pinned'." >&2
  echo "  If the build breaks: git -C $LLAMACPP fetch --depth 1 origin tag $pinned && git -C $LLAMACPP checkout $pinned" >&2
fi

# llama-server runner (CPU-only; OLLAMA_LLAMA_BACKENDS unset = no CUDA/ROCm)
# + Go binary. Offline llama.cpp via the sibling checkout.
OLLAMA_LLAMA_CPP_SOURCE="$LLAMACPP" cmake -B "$OLLAMA/build" -S "$OLLAMA" \
  -DCMAKE_BUILD_TYPE=Release -DGO_EXECUTABLE="$GO"
cmake --build "$OLLAMA/build" --parallel "${JOBS:-2}"

echo "built: $OLLAMA/ollama + $OLLAMA/build/lib/ollama/"
