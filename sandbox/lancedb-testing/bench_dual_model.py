"""Can BOTH embedders live in GPU memory at once? (the crow-memory service question)

The service embeds text on every message (ColBERT) AND images on upload (ColQwen2).
Both must be resident. Do they fit in 8GB? Warmup disabled.
"""

import subprocess
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

import transformers.modeling_utils
transformers.modeling_utils.caching_allocator_warmup = lambda *a, **k: None

TEXT_MODEL = "lightonai/GTE-ModernColBERT-v1"
IMG_MODEL = "vidore/colqwen2-v1.0"
IMG = next(Path("./test_images").glob("*.png"))


def vram(label):
    alloc = torch.cuda.memory_allocated() / 1e9
    reserved = torch.cuda.memory_reserved() / 1e9
    smi = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True).stdout.strip()
    print(f"  [{label:28}] torch-alloc {alloc:5.2f} GB | torch-reserved {reserved:5.2f} GB | nvidia-smi used {smi} MiB")
    return alloc


def main():
    print(f"GPU: {torch.cuda.get_device_name(0)}  ({torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB total)\n")
    vram("baseline")

    # ---- text model (ColBERT via pylate) ----
    from pylate import models
    t0 = time.perf_counter()
    text_model = models.ColBERT(model_name_or_path=TEXT_MODEL)
    text_model.encode(["warmup"], is_query=True)  # force onto GPU
    torch.cuda.synchronize()
    print(f"\n[TEXT ColBERT] loaded in {time.perf_counter()-t0:.1f}s")
    a_text = vram("after text model")

    # ---- image model (ColQwen2) ----
    from colpali_engine.models import ColQwen2, ColQwen2Processor
    t0 = time.perf_counter()
    img_model = ColQwen2.from_pretrained(IMG_MODEL, torch_dtype=torch.bfloat16, device_map="cuda").eval()
    img_proc = ColQwen2Processor.from_pretrained(IMG_MODEL)
    torch.cuda.synchronize()
    print(f"\n[IMAGE ColQwen2] loaded in {time.perf_counter()-t0:.1f}s")
    a_both = vram("after BOTH models")

    # ---- prove both work concurrently ----
    print("\n[concurrency check]")
    t0 = time.perf_counter()
    te = text_model.encode(["how does compaction keep the cache warm"], is_query=True)
    torch.cuda.synchronize()
    print(f"  text embed OK  shape={np.asarray(te[0]).shape}  ({(time.perf_counter()-t0)*1000:.0f} ms)")

    t0 = time.perf_counter()
    with torch.no_grad():
        b = img_proc.process_images([Image.open(IMG).convert("RGB")]).to(img_model.device)
        ie = img_model(**b)
    torch.cuda.synchronize()
    print(f"  image embed OK shape={tuple(ie[0].shape)}  ({(time.perf_counter()-t0)*1000:.0f} ms)")

    vram("after both embeds (peak)")

    total = torch.cuda.get_device_properties(0).total_memory / 1e9
    headroom = total - (torch.cuda.memory_reserved() / 1e9)
    print(f"\n[VERDICT] both models resident: torch-reserved {torch.cuda.memory_reserved()/1e9:.2f} GB / {total:.1f} GB  ->  {headroom:.2f} GB headroom")
    print(f"          delta from text-only to both: +{(a_both-a_text):.2f} GB for the image model")


if __name__ == "__main__":
    main()
