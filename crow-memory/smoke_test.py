"""Smoke test: the core crow-memory flow on a real image.

Proves: inline base64 -> extracted to images table (sha256 + ColPali embed),
message stored image-free with image_ref, hydrate restores it, and both
text->text and text->image search return hits.
"""

import base64
import shutil
import tempfile
from pathlib import Path

from crow_memory.embed import Embedders
from crow_memory.store import MemoryStore

TEST_IMG = Path("/home/thomas/src/crow-team/crow-cli/sandbox/lancedb-testing/test_images/img_003.png")


def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    assert cond, label


def main():
    tmp = tempfile.mkdtemp(prefix="crowmem_")
    print(f"store path: {tmp}\n")
    print("loading both embedders (ColBERT + ColQwen2)...")
    emb = Embedders(image_max_dim=1024)
    store = MemoryStore(tmp, emb)

    # ---- build a message with an inline base64 image (OpenAI format) ----
    raw = TEST_IMG.read_bytes()
    b64 = base64.b64encode(raw).decode()
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "here is a screenshot of the terminal output"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }

    print("\n[1] add_message with inline base64 image")
    rec = store.add_message("smoke-agent-1", msg)
    image_ids = rec["image_ids"]
    check("one image extracted", len(image_ids) == 1)
    check("image_id is content-addressed sha256", image_ids[0].startswith("sha256:") and len(image_ids[0]) == 71)

    expected_id = Embedders.hash_bytes(raw)
    check("image_id == sha256(raw bytes)", image_ids[0] == expected_id)

    # ---- message stored image-free ----
    print("\n[2] message stored image-free with image_ref")
    msgs = store.load_messages("smoke-agent-1")
    check("one message stored", len(msgs) == 1)
    stored = msgs[0]
    blocks = stored["content"]
    has_ref = any(b.get("type") == "image_ref" for b in blocks)
    has_inline = any(b.get("type") == "image_url" for b in blocks)
    check("inline base64 removed", not has_inline)
    check("image_ref present", has_ref)
    check("no base64 blob in stored message", "base64," not in str(stored))

    # ---- dedupe: same image again -> same id, still one image row ----
    print("\n[3] dedupe (same image twice)")
    rec2 = store.add_message("smoke-agent-1", msg)
    check("same content -> same image_id", rec2["image_ids"][0] == expected_id)
    img_rows = store.images.to_pandas()
    check("only ONE image row (deduped)", len(img_rows) == 1)

    # ---- image stored with raw bytes + embedding ----
    print("\n[4] images table has raw bytes + ColPali embedding")
    img = store.get_image(expected_id)
    check("image bytes round-trip exactly", img["data"] == raw)
    check("mime preserved", img["mime"] == "image/png")
    mv_rows = store.images.to_pandas()
    n_patches = len(mv_rows.iloc[0]["mv"])
    check(f"ColPali multivector present ({n_patches} patches x 128)", n_patches > 0 and len(mv_rows.iloc[0]["mv"][0]) == 128)

    # ---- hydrate restores inline image for the LLM ----
    print("\n[5] hydrate restores inline base64")
    hydrated = store.hydrate(stored)
    hblocks = hydrated["content"]
    url = next((b["image_url"]["url"] for b in hblocks if b.get("type") == "image_url"), "")
    check("hydrate produced data URL", url.startswith("data:image/png;base64,"))
    check("hydrated bytes match original", base64.b64decode(url.split(",", 1)[1]) == raw)

    # ---- text -> text search ----
    print("\n[6] text->text search (ColBERT MaxSim)")
    hits = store.search_messages("screenshot of the terminal", limit=3)
    check("text search returns the message", len(hits) >= 1 and hits[0]["agent_id"] == "smoke-agent-1")

    # ---- text -> image search ----
    print("\n[7] text->image search (ColQwen2)")
    ihits = store.search_images(query="a screenshot of code or a terminal", limit=3)
    check("image search returns the image", len(ihits) >= 1 and ihits[0]["image_id"] == expected_id)

    print("\nALL CHECKS PASSED ✔")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
