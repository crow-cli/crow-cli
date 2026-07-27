"""Latency benchmark: ColPali multivector IMAGE embeddings + LanceDB on REAL crow images.

Mirrors bench_latency.py but for the IMAGE table. Answers:
  - is image embedding fast enough to do synchronously, or does it need to be async?
  - does ColPali work in this stack (colpali-engine + LanceDB multivector)?
  - what's text->image and image->image query latency?
  - how heavy are the multivectors (storage cost per image)?
"""

import statistics
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import lancedb
import torch
from PIL import Image

# Disable transformers' load-time caching-allocator warmup: it pre-allocates a
# buffer the size of the model ON TOP of the model itself, so peak ≈ 2× weights
# and OOMs an 8GB card during from_pretrained even though steady-state fits fine.
import transformers.modeling_utils
transformers.modeling_utils.caching_allocator_warmup = lambda *a, **k: None

# ColQwen2 = ColPali variant (same late-interaction multivector retrieval),
# Qwen2-VL-2B backbone (~4GB) fits an 8GB card; ColPali-v1.3 (PaliGemma-3B) OOMs.
# Bonus: keeps arbitrary aspect ratios instead of PaliGemma's forced square crop.
MODEL = "vidore/colqwen2-v1.0"
IMG_DIR = Path("./test_images")
LANCEDB_PATH = "./bench_colpali_lancedb"
TABLE = "crow_images"
N_QUERIES = 6


def ms(s: float) -> str:
    return f"{s*1000:,.1f} ms"


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"torch device: {device}\n")

    paths = sorted([p for p in IMG_DIR.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")])
    images = [Image.open(p).convert("RGB") for p in paths]
    print(f"[corpus] {len(images)} real crow images loaded")
    print(f"         sizes: {sorted({f'{i.size[0]}x{i.size[1]}' for i in images})[:6]} ...\n")

    # ---- model load ----
    from colpali_engine.models import ColQwen2, ColQwen2Processor
    t0 = time.perf_counter()
    model = ColQwen2.from_pretrained(MODEL, torch_dtype=torch.bfloat16, device_map=device).eval()
    processor = ColQwen2Processor.from_pretrained(MODEL)
    t_model = time.perf_counter() - t0
    print(f"[model load] {ms(t_model)}\n")

    # ---- IMAGE embed throughput (the sync-vs-async question) ----
    per_image = []
    all_embs = []
    t_batch0 = time.perf_counter()
    with torch.no_grad():
        for img in images:
            t0 = time.perf_counter()
            batch = processor.process_images([img]).to(model.device)
            emb = model(**batch)  # (1, n_patches, dim)
            torch.cuda.synchronize() if device == "cuda" else None
            per_image.append(time.perf_counter() - t0)
            all_embs.append(emb[0].float().cpu().numpy())
    t_batch = time.perf_counter() - t_batch0

    n_patches = all_embs[0].shape[0]
    dim = all_embs[0].shape[1]
    bytes_per_image = n_patches * dim * 4  # fp32
    print(f"[IMAGE embed] {len(images)} images in {ms(t_batch)}")
    print(f"              => p50 {ms(pct(per_image,.5))}/image   p95 {ms(pct(per_image,.95))}/image")
    print(f"              => {len(images)/t_batch:.2f} images/sec")
    print(f"              multivector: {n_patches} patches x {dim} dim = {bytes_per_image//1024} KB/image (fp32)\n")

    # ---- store in LanceDB (multivector schema) ----
    schema = pa.schema([
        pa.field("img_id", pa.string()),
        pa.field("path", pa.string()),
        pa.field("mv", pa.list_(pa.list_(pa.float32(), dim))),
    ])
    rows = [{"img_id": p.stem, "path": str(p), "mv": e.tolist()}
            for p, e in zip(paths, all_embs)]
    db = lancedb.connect(LANCEDB_PATH)
    tbl = db.create_table(TABLE, data=rows, schema=schema, mode="overwrite")
    print(f"[store] table '{TABLE}' with {len(rows)} rows")

    t0 = time.perf_counter()
    tbl.create_index(vector_column_name="mv", metric="cosine")
    t_index = time.perf_counter() - t0
    print(f"[index build] {ms(t_index)}\n")

    # ---- TEXT -> IMAGE query latency ----
    text_queries = [
        "a screenshot of code or a terminal",
        "a diagram or chart",
        "a photograph of a person",
        "a castle drawing",
        "a meme",
        "a stability diagram",
    ][:N_QUERIES]
    enc_t, search_t = [], []
    print("[TEXT->IMAGE]  query-encode | lance-search | total")
    for q in text_queries:
        with torch.no_grad():
            t0 = time.perf_counter()
            qb = processor.process_queries([q]).to(model.device)
            qe = model(**qb)
            torch.cuda.synchronize() if device == "cuda" else None
            te = time.perf_counter() - t0
        qemb = qe[0].float().cpu().numpy()
        t1 = time.perf_counter()
        res = tbl.search(qemb).limit(3).to_pandas()
        ts = time.perf_counter() - t1
        enc_t.append(te); search_t.append(ts)
        top = res.iloc[0]["path"] if len(res) else "?"
        print(f"  {ms(te):>11} | {ms(ts):>11} | {ms(te+ts):>9}  <- {q[:34]:34} top={Path(top).name}")

    print(f"\n[TEXT->IMAGE summary] encode p50 {ms(pct(enc_t,.5))} | search p50 {ms(pct(search_t,.5))} | total p50 {ms(pct([a+b for a,b in zip(enc_t,search_t)],.5))}")

    # ---- IMAGE -> IMAGE query latency ----
    with torch.no_grad():
        qb = processor.process_images([images[0]]).to(model.device)
        qe = model(**qb)
    qemb = qe[0].float().cpu().numpy()
    t1 = time.perf_counter()
    res = tbl.search(qemb).limit(3).to_pandas()
    ts = time.perf_counter() - t1
    print(f"\n[IMAGE->IMAGE] search latency {ms(ts)}  (query={paths[0].name}; top hits: {[Path(r).name for r in res['path']]})")


if __name__ == "__main__":
    main()
