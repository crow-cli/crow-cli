"""Resident embedders: ColBERT (text) + ColQwen2/ColPali (images).

Both models live in GPU memory at once (~5.3GB / 8GB). The transformers
caching-allocator warmup is disabled because it double-allocates the model
size at load time and OOMs an 8GB card even though steady-state fits.

First run downloads models from HF Hub (~9GB). All subsequent loads are
fully offline — no network requests.
"""

import hashlib
import io
import os
from pathlib import Path

TEXT_MODEL = "lightonai/GTE-ModernColBERT-v1"
IMAGE_MODEL = "vidore/colqwen2-v1.0"

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def _models_cached() -> bool:
    """Check if both models have snapshots in the HF cache."""
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    for repo in ("models--lightonai--GTE-ModernColBERT-v1", "models--vidore--colqwen2-v1.0"):
        snapshots = hub / repo / "snapshots"
        if not snapshots.exists() or not any(snapshots.iterdir()):
            return False
    return True


def _ensure_config_symlink():
    """The adapter repo (colqwen2-v1.0) has no config.json — the processor's
    AutoTokenizer needs it. Symlink from the base model for offline use."""
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    adapter_snaps = hub / "models--vidore--colqwen2-v1.0" / "snapshots"
    base_snaps = hub / "models--vidore--colqwen2-base" / "snapshots"
    if not adapter_snaps.exists() or not base_snaps.exists():
        return
    adapter_snap = next(adapter_snaps.iterdir(), None)
    base_snap = next(base_snaps.iterdir(), None)
    if adapter_snap and base_snap and (base_snap / "config.json").exists():
        link = adapter_snap / "config.json"
        if not link.exists():
            link.symlink_to(base_snap / "config.json")


# Decide offline vs online BEFORE any huggingface imports resolve the hub.
if _models_cached():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    _ensure_config_symlink()
else:
    print("crow-memory: downloading embedding models (~9GB, first run only)...")

import numpy as np
import torch
import transformers.modeling_utils
from PIL import Image

# Disable load-time allocator warmup (pre-allocates a 2nd buffer == model size).
transformers.modeling_utils.caching_allocator_warmup = lambda *a, **k: None
DEFAULT_MAX_DIM = 1024  # resize cap: bounds patch count -> bounds embed time + storage
EMBED_DIM = 128         # both models project to 128-dim per token/patch


class Embedders:
    """Holds both embedders resident and exposes text/image embedding."""

    def __init__(self, image_max_dim: int = DEFAULT_MAX_DIM, device: str | None = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.image_max_dim = image_max_dim

        from pylate import models

        self.text = models.ColBERT(model_name_or_path=TEXT_MODEL)

        from colpali_engine.models import ColQwen2, ColQwen2Processor

        self.image = ColQwen2.from_pretrained(
            IMAGE_MODEL, torch_dtype=torch.bfloat16, device_map=self.device
        ).eval()
        self.image_proc = ColQwen2Processor.from_pretrained(IMAGE_MODEL)
        _ensure_config_symlink()

    # ---- text (ColBERT) ----
    def embed_text(self, text: str) -> np.ndarray:
        """Document encoding -> (n_tokens, 128)."""
        e = self.text.encode([text or " "], is_query=False)[0]
        return np.asarray(e, dtype=np.float32)

    def embed_text_query(self, text: str) -> np.ndarray:
        """Query encoding -> (n_tokens, 128)."""
        e = self.text.encode([text or " "], is_query=True)[0]
        return np.asarray(e, dtype=np.float32)

    # ---- images (ColQwen2 / ColPali) ----
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
        with torch.no_grad():
            batch = self.image_proc.process_images([img]).to(self.image.device)
            e = self.image(**batch)
        if self.device == "cuda":
            torch.cuda.synchronize()
        return e[0].float().cpu().numpy().astype("float32"), w, h

    def embed_image_query_text(self, text: str) -> np.ndarray:
        """Encode a TEXT query into the image space (text->image retrieval)."""
        with torch.no_grad():
            batch = self.image_proc.process_queries([text or " "]).to(self.image.device)
            e = self.image(**batch)
        if self.device == "cuda":
            torch.cuda.synchronize()
        return e[0].float().cpu().numpy().astype("float32")

    def embed_image_query_bytes(self, data: bytes) -> np.ndarray:
        """Encode an IMAGE query (image->image retrieval)."""
        mv, _, _ = self.embed_image_bytes(data)
        return mv


if __name__ == "__main__":
    print(f"Loading {TEXT_MODEL} + {IMAGE_MODEL}...")
    e = Embedders()
    print(f"Done. Models cached on {e.device}. All future loads are offline.")
