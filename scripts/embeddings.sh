#!/usr/bin/env bash
# Bring up crow's embedding service under crow-cli management and verify it
# end-to-end with a real ColBERT embed call (generous CPU warm-up timeouts).
set -euo pipefail

CROWCTL="${CROWCTL:-$(cd "$(dirname "$0")/.." && pwd)/target/debug/crow-cli}"
PORT=11392
MODEL="hf.co/LiquidAI/LFM2.5-ColBERT-350M-GGUF:LFM2.5-ColBERT-350M-BF16.gguf"

"$CROWCTL" daemon install ollama-mv # idempotent

for _ in $(seq 1 24); do # up to 2 min: cold runner load
  if curl -sf -m 120 -X POST "http://127.0.0.1:$PORT/api/embed" \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"$MODEL\",\"input\":\"crow warmup\",\"colbert\":true}" \
    | grep -q embeddings; then
    echo "embeddings: OK (http://127.0.0.1:$PORT)"
    exit 0
  fi
  sleep 5
done

echo "embeddings: FAILED — see ~/.agents/crow/logs/ollama-mv.log" >&2
exit 1
