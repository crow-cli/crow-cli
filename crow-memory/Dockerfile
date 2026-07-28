# crow-memory — LanceDB memory service (CPU-only by default)
# ColBERT text + ColQwen2 image multivector embeddings
#
# Build:  docker build -t crow-memory -f crow-memory/Dockerfile .
# Run:    docker run -p 8901:8901 -v ~/.crow/memory.lance:/data/memory.lance crow-memory
#
# For GPU acceleration, swap the FROM line to:
#   FROM nvidia/cuda:13.0.2-cudnn-runtime-ubuntu24.04
# and add --gpus all to docker run / deploy.resources in compose.

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install uv (manages its own Python 3.14 + CPU PyTorch)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# HF model cache inside /app so non-root runtime user can read it
ENV UV_NO_CACHE=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_INSTALL_DIR=/app/.python \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    HF_HUB_DISABLE_PROGRESS_BARS=1

WORKDIR /app

# ---- dependency layer (cached unless pyproject/lock change) ----
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

# ---- pre-download models at build time ----
RUN uv run python -c "\
from crow_memory.embed import Embedders; \
e = Embedders(); \
print('Models loaded OK on', e.device)"

# ---- make venv + model cache world-readable ----
# compose.yaml `user:` runs as host UID (not root). Without this the
# container crashes: "failed to canonicalize path /app/.venv/bin/python3"
RUN chmod -R a+rX /app/.venv /app/.cache /app/.python

# ---- runtime ----
EXPOSE 8901

ENV CROW_MEMORY_HOST=0.0.0.0 \
    CROW_MEMORY_PORT=8901 \
    CROW_MEMORY_PATH=/data/memory.lance \
    USER=crow \
    HOME=/tmp \
    TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor

VOLUME ["/data"]

# Direct venv entrypoint — NOT `uv run` — so runtime user needs no write access
ENTRYPOINT ["/app/.venv/bin/crow-memory"]
