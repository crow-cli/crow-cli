import numpy as np
import pyarrow as pa
import lancedb
from pylate import models

# 1) Load a late-interaction model via PyLate
# PyLate docs show ColBERT() + encode(..., is_query=...) :contentReference[oaicite:2]{index=2}
model = models.ColBERT(model_name_or_path="lightonai/GTE-ModernColBERT-v1")

# You can discover dim from one embedding (avoid guessing)
dim = model.encode(["hello"], is_query=True)[0].shape[1]

# 2) Create a LanceDB table with a multivector column
db = lancedb.connect("./pylate_lancedb")
schema = pa.schema([
    pa.field("doc_id", pa.string()),
    pa.field("text", pa.string()),
    # multivector: list<list<float32, dim>> :contentReference[oaicite:3]{index=3}
    pa.field("mv", pa.list_(pa.list_(pa.float32(), dim))),
])

import random

base_docs = [
    {"doc_id": "1", "text": "The train to Tokyo leaves at 5pm."},
    {"doc_id": "2", "text": "That Pho restaurant in Hanoi is highly rated."},
    {"doc_id": "3", "text": "This is a noodle bar in Osaka, Japan."},
]

# Generate synthetic docs — enough for PQ training (needs 256+ rows).
# Mix of project-relevant content and varied topics for retrieval testing.
templates = [
    "The {subject} uses {tool} to manage {obj} in the {layer} layer.",
    "When {subject} calls {tool}, the {layer} clears {obj} and generates new IDs.",
    "In the {layer}, {subject} delegates {obj} to a subagent via {tool}.",
    "The {layer} state machine nags {subject} when {obj} is incomplete.",
    "After {tool} replaces the full list, {subject} must adopt orphaned {obj}.",
    "Persistent memory for {subject} stores {obj} in a vector database.",
    "The {layer} loop exits when {tool} returns None for all {obj}.",
    "Fire-and-forget {tool} prompts {subject} without waiting for {obj} completion.",
    "Knowledge graph nodes connect {subject} to related {obj} in the {layer}.",
    "The agent uses {tool} to search memories and retrieve relevant {obj}.",
]
subjects = ["agent", "orchestrator", "worker", "crow-cli", "sidex", "user", "subagent"]
tools = ["task_write", "_send", "_task/send", "query_memory", "task_read", "web_search", "send_prompt"]
objs = ["tasks", "sessions", "embeddings", "memories", "prompts", "callbacks", "tool calls"]
layers = ["orchestration", "ACP", "MCP", "frontend", "backend", "retrieval", "Tauri"]

random.seed(42)
docs = list(base_docs)
for i in range(4, 304):
    tpl = random.choice(templates)
    text = tpl.format(
        subject=random.choice(subjects),
        tool=random.choice(tools),
        obj=random.choice(objs),
        layer=random.choice(layers),
    )
    docs.append({"doc_id": str(i), "text": text})

# 3) Encode documents with PyLate (token vectors per doc)
doc_texts = [d["text"] for d in docs]
doc_embs = model.encode(doc_texts, is_query=False)  # list/array of (T, dim) per doc :contentReference[oaicite:4]{index=4}

rows = []
for d, emb in zip(docs, doc_embs):
    emb = np.asarray(emb, dtype=np.float32)
    rows.append({**d, "mv": emb.tolist()})

tbl = db.create_table("docs", data=rows, schema=schema, mode="overwrite")

# 4) Build an index + query using a query matrix.
# Multivector brute-force scales with rows × vectors-per-row, so build the index
# at much smaller dataset sizes than you would for single-vector search — and
# always before exposing the table to remote traffic.
tbl.create_index(vector_column_name="mv", metric="cosine")

query = "Tell me about ramen in Japan"
q_emb = np.asarray(model.encode([query], is_query=True)[0], dtype=np.float32)  # (Tq, dim) :contentReference[oaicite:5]{index=5}

out = tbl.search(q_emb).limit(5).to_pandas()  # multivector search accepts a matrix :contentReference[oaicite:6]{index=6}
print(out[["doc_id", "text"]])