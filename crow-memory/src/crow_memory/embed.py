"""Ollama-backed embedders: ColBERT (text) + ColQwen2 (images).

All embedding is delegated to our ollama instance (127.0.0.1:11392).
No resident PyTorch models — text uses LFM2.5-ColBERT (128-dim), images
use ColQwen2 (128-dim per patch). Both served through /api/embed?colbert=true.
"""

import base64
import hashlib
import io
import os

import httpx
import numpy as np
from PIL import Image

EMBED_DIM = 128

OLLAMA_HOST = os.environ.get("CROW_OLLAMA_HOST", "http://127.0.0.1:11392")
TEXT_MODEL = os.environ.get(
    "CROW_TEXT_MODEL",
    "hf.co/LiquidAI/LFM2.5-ColBERT-350M-GGUF:LFM2.5-ColBERT-350M-BF16.gguf",
)
IMAGE_MODEL = os.environ.get(
    "CROW_IMAGE_MODEL",
    "hf.co/odellus/colqwen2-v1.0-gguf:colqwen2-llm-f16.gguf",
)
DEFAULT_MAX_DIM = 1024


class Embedders:
    """Ollama-backed embedder. Same interface as the old PyTorch version."""

    def __init__(self, image_max_dim: int = DEFAULT_MAX_DIM, device: str | None = None):
        self.image_max_dim = image_max_dim
        self._client = httpx.Client(timeout=120.0)

    def _embed_text_ollama(self, text: str, model: str) -> np.ndarray:
        """POST /api/embed with colbert=true -> (n_tokens, 128)."""
        resp = self._client.post(
            f"{OLLAMA_HOST}/api/embed",
            json={"model": model, "input": text or " ", "colbert": True},
        )
        resp.raise_for_status()
        data = resp.json()
        col = data.get("colbert_embeddings")
        if not col:
            raise RuntimeError(f"no colbert_embeddings in response: {data}")
        return np.asarray(col[0], dtype=np.float32)

    def _embed_image_ollama(self, data: bytes, model: str) -> np.ndarray:
        """POST /api/embed with images + colbert=true -> (n_patches, 128)."""
        b64 = base64.b64encode(data).decode()
        resp = self._client.post(
            f"{OLLAMA_HOST}/api/embed",
            json={"model": model, "images": [b64], "colbert": True},
        )
        resp.raise_for_status()
        data_json = resp.json()
        col = data_json.get("colbert_embeddings")
        if not col:
            raise RuntimeError(f"no colbert_embeddings in response: {data_json}")
        return np.asarray(col[0], dtype=np.float32)

    # ---- text (ColBERT) ----
    def embed_text(self, text: str) -> np.ndarray:
        """Document encoding -> (n_tokens, 128)."""
        return self._embed_text_ollama(text, TEXT_MODEL)

    def embed_text_query(self, text: str) -> np.ndarray:
        """Query encoding -> (n_tokens, 128)."""
        return self._embed_text_ollama(text, TEXT_MODEL)

    # ---- images (ColQwen2) ----
    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return "sha256:" + hashlib.sha256(data).hexdigest()

    def resize(self, img: Image.Image) -> Image.Image:
        w, h = img.size
        m = max(w, h)
        if m <= self.image_max_dim:
            return img
        scale = self.image_max_dim / m
        return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    def embed_image_bytes(self, data: bytes) -> tuple[np.ndarray, int, int]:
        """Encode raw image bytes -> (mv (n_patches,128), resized_w, resized_h)."""
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img = self.resize(img)
        w, h = img.size
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        mv = self._embed_image_ollama(buf.getvalue(), IMAGE_MODEL)
        return mv, w, h

    def embed_image_query_text(self, text: str) -> np.ndarray:
        """Encode a TEXT query into the image space (text->image retrieval)."""
        return self._embed_text_ollama(text, IMAGE_MODEL)

    def embed_image_query_bytes(self, data: bytes) -> np.ndarray:
        """Encode an IMAGE query (image->image retrieval)."""
        mv, _, _ = self.embed_image_bytes(data)
        return mv
