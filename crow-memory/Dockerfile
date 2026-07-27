# crow-memory — GPU-accelerated LanceDB memory service
# ColBERT text + ColQwen2 image multivector embeddings
#
# Build:  docker build -t crow-memory -f crow-memory/Dockerfile .
# Run:    docker run --gpus all -p 8901:8901 -v ~/.crow/memory.lance:/data/memory.lance crow-memory

FROM nvidia/cuda:13.0.2-cudnn-runtime-ubuntu24.04 AS base

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

# Install uv (manages its own Python 3.14)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_NO_CACHE=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    HF_HUB_DISABLE_PROGRESS_BARS=1

WORKDIR /app

# ---- dependency layer (cached unless pyproject/lock change) ----
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

# ---- pre-download models at build time ----
# This bakes ~5GB of model weights into the image so the container
# starts instantly without hitting HuggingFace at runtime.
RUN uv run python -c "\
from crow_memory.embed import Embedders; \
e = Embedders(); \
print('Models loaded OK on', e.device)"

# ---- runtime ----
EXPOSE 8901

ENV CROW_MEMORY_HOST=0.0.0.0 \
    CROW_MEMORY_PORT=8901 \
    CROW_MEMORY_PATH=/data/memory.lance

VOLUME ["/data"]

ENTRYPOINT ["uv", "run", "crow-memory"]
