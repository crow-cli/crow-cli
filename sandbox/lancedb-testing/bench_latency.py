"""Latency benchmark: pylate ColBERT multivector + LanceDB on REAL crow.db data.

Answers the question: is pylate (torch ColBERT) fast enough, or do we need
rust / llama.cpp / Candle embeddings?

We time the phases that map to crow's actual access patterns:
  - model load          (one-time, service startup)
  - encode throughput   (ASYNC path — runs on compaction, not user-facing)
  - index build         (one-time per table rebuild)
  - query latency       (REAL-TIME path — this is `query_memory`, user-facing)
      split into: query-encode  vs  lance-search
"""

import json
import sqlite3
import statistics
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import lancedb
from pylate import models

DB_PATH = Path.home() / ".crow" / "crow.db"
LANCEDB_PATH = "./bench_lancedb"
TABLE = "bench_messages"
SAMPLE_SIZE = 200          # docs to embed into the search table
N_QUERIES = 12             # queries to time for the real-time path
MODEL = "lightonai/GTE-ModernColBERT-v1"


def extract_text(data_json: str) -> str:
    data = json.loads(data_json)
    parts = []
    content = data.get("content")
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "image":
                    parts.append("[image]")
    reasoning = data.get("reasoning_content")
    if reasoning:
        parts.append(reasoning)
    tool_calls = data.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            fn = tc.get("function", {})
            parts.append(f"{fn.get('name','')}: {fn.get('arguments','')}")
    text = "\n".join(p for p in parts if p and p.strip())
    return text or ""


def load_corpus(limit: int) -> list[dict]:
    """Pull real messages across ALL agents, extract text, keep searchable ones."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, agent_id, role, data FROM messages ORDER BY id"
    ).fetchall()
    conn.close()
    corpus = []
    for r in rows:
        text = extract_text(r["data"])
        if len(text) > 40:  # searchable
            corpus.append({"msg_id": r["id"], "agent_id": r["agent_id"],
                           "role": r["role"], "text": text})
        if len(corpus) >= limit:
            break
    return corpus


def ms(seconds: float) -> str:
    return f"{seconds*1000:,.1f} ms"


def main():
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"torch device: {device}\n")

    # ---- load corpus from real sqlite data ----
    t0 = time.perf_counter()
    corpus = load_corpus(SAMPLE_SIZE)
    t_load = time.perf_counter() - t0
    chars = [len(c["text"]) for c in corpus]
    print(f"[corpus] {len(corpus)} searchable messages from crow.db in {ms(t_load)}")
    print(f"         text length: median {int(statistics.median(chars))} chars, "
          f"max {max(chars)} chars\n")

    # ---- model load (service startup cost) ----
    t0 = time.perf_counter()
    model = models.ColBERT(model_name_or_path=MODEL)
    t_model = time.perf_counter() - t0
    dim = model.encode(["hello"], is_query=True)[0].shape[1]
    print(f"[model load] {ms(t_model)}  (dim={dim})\n")

    # ---- ENCODE throughput (ASYNC path — compaction) ----
    texts = [c["text"][:2000] for c in corpus]
    t0 = time.perf_counter()
    doc_embs = model.encode(texts, is_query=False, batch_size=32)
    t_encode = time.perf_counter() - t0
    per_doc = t_encode / len(texts)
    print(f"[ENCODE async] {len(texts)} docs in {ms(t_encode)}")
    print(f"               => {per_doc*1000:.1f} ms/doc  |  {len(texts)/t_encode:.1f} docs/sec\n")

    # ---- build table + index ----
    schema = pa.schema([
        pa.field("msg_id", pa.int64()),
        pa.field("agent_id", pa.string()),
        pa.field("role", pa.string()),
        pa.field("text", pa.string()),
        pa.field("mv", pa.list_(pa.list_(pa.float32(), dim))),
    ])
    rows = []
    for c, emb in zip(corpus, doc_embs):
        rows.append({"msg_id": c["msg_id"], "agent_id": c["agent_id"],
                     "role": c["role"], "text": c["text"][:2000],
                     "mv": np.asarray(emb, dtype=np.float32).tolist()})
    db = lancedb.connect(LANCEDB_PATH)
    tbl = db.create_table(TABLE, data=rows, schema=schema, mode="overwrite")

    t0 = time.perf_counter()
    tbl.create_index(vector_column_name="mv", metric="cosine")
    t_index = time.perf_counter() - t0
    print(f"[index build] {ms(t_index)}\n")

    # ---- QUERY latency (REAL-TIME path — query_memory) ----
    queries = [
        "how does compaction keep the prompt cache warm",
        "what is the agent_idx lineage for a session",
        "how do we fix the task_write tool",
        "why did the nag not fire",
        "images stored as base64 in sqlite",
        "multivector ColBERT MaxSim search",
        "orchestration state machine delegated tasks",
        "build_display_tree skips home directory",
        "skills progressive disclosure catalog",
        "prefix preserving summary call",
        "terminal backend posix pty fcntl",
        "lancedb separate tables for images and text",
    ][:N_QUERIES]

    encode_times, search_times, total_times = [], [], []
    print("[QUERY real-time]  query-encode | lance-search | total")
    for q in queries:
        t0 = time.perf_counter()
        q_emb = np.asarray(model.encode([q], is_query=True)[0], dtype=np.float32)
        t_enc = time.perf_counter() - t0

        t1 = time.perf_counter()
        res = tbl.search(q_emb).limit(5).to_pandas()
        t_search = time.perf_counter() - t1

        encode_times.append(t_enc)
        search_times.append(t_search)
        total_times.append(t_enc + t_search)
        print(f"  {ms(t_enc):>12} | {ms(t_search):>12} | {ms(t_enc+t_search):>10}   <- {q[:40]}")

    def pct(xs, p):
        xs = sorted(xs)
        return xs[min(len(xs)-1, int(p*len(xs)))]

    print(f"\n[QUERY summary] n={len(queries)}")
    print(f"  query-encode : p50 {ms(pct(encode_times,.5))}  p95 {ms(pct(encode_times,.95))}")
    print(f"  lance-search : p50 {ms(pct(search_times,.5))}  p95 {ms(pct(search_times,.95))}")
    print(f"  TOTAL        : p50 {ms(pct(total_times,.5))}  p95 {ms(pct(total_times,.95))}")

    # ---- sample result quality (sanity) ----
    print("\n[quality sanity] query: 'images stored as base64 in sqlite'")
    q_emb = np.asarray(model.encode(["images stored as base64 in sqlite"], is_query=True)[0], dtype=np.float32)
    res = tbl.search(q_emb).limit(3).to_pandas()
    for _, row in res.iterrows():
        print(f"  [{row['role']}] {row['text'][:110].replace(chr(10),' ')}...")


if __name__ == "__main__":
    main()
