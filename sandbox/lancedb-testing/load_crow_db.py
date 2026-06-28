"""Load crow.db messages into LanceDB with ColBERT multivector embeddings.

Reads all messages for a given agent from ~/.crow/crow.db (SQLite),
extracts text content, encodes with PyLate ColBERT, and stores in LanceDB.
"""

import json
import sqlite3
import numpy as np
import pyarrow as pa
import lancedb
from pathlib import Path
from pylate import models

DB_PATH = Path.home() / ".crow" / "crow.db"
LANCEDB_PATH = "./pylate_lancedb"
TABLE_NAME = "crow_messages"
AGENT_ID = "tunneling-slick-lorikeet-of-wizardry-1"


def extract_text(data_json: str) -> str:
    """Extract the most meaningful text from a message's JSON data field."""
    data = json.loads(data_json)
    role = data.get("role", "")
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

    # Include reasoning content for assistant messages — it's often the
    # most information-dense part.
    reasoning = data.get("reasoning_content")
    if reasoning:
        parts.append(f"[reasoning] {reasoning}")

    # Include tool call names for assistant messages.
    tool_calls = data.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", "")
            parts.append(f"[tool_call] {name}: {args}")

    text = "\n".join(p for p in parts if p.strip())
    return text or f"[empty {role} message]"


def load_messages(agent_id: str) -> list[dict]:
    """Load all messages for an agent from crow.db."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, agent_id, created_at, data, role, "
        "prompt_tokens, completion_tokens, total_tokens "
        "FROM messages WHERE agent_id = ? ORDER BY id",
        (agent_id,),
    ).fetchall()
    conn.close()

    messages = []
    for row in rows:
        text = extract_text(row["data"])
        messages.append({
            "msg_id": row["id"],
            "agent_id": row["agent_id"],
            "created_at": row["created_at"],
            "role": row["role"],
            "text": text,
            "prompt_tokens": row["prompt_tokens"] or 0,
            "completion_tokens": row["completion_tokens"] or 0,
            "total_tokens": row["total_tokens"] or 0,
            "char_count": len(text),
        })
    return messages


def main():
    print(f"Loading messages for {AGENT_ID} from {DB_PATH}...")
    messages = load_messages(AGENT_ID)
    print(f"  {len(messages)} messages loaded")
    print(f"  Roles: { {m['role']: sum(1 for x in messages if x['role'] == m['role']) for m in messages} }")

    # Filter out messages that are too short to be meaningful for retrieval
    searchable = [m for m in messages if m["char_count"] > 20]
    print(f"  {len(searchable)} messages with >20 chars (searchable)")

    # Load ColBERT model
    print("Loading ColBERT model...")
    model = models.ColBERT(model_name_or_path="lightonai/GTE-ModernColBERT-v1")
    dim = model.encode(["hello"], is_query=True)[0].shape[1]
    print(f"  Embedding dim: {dim}")

    # Encode all searchable messages
    texts = [m["text"] for m in searchable]
    print(f"Encoding {len(texts)} messages...")
    doc_embs = model.encode(texts, is_query=False, batch_size=32)
    print(f"  Encoded {len(doc_embs)} documents")

    # Build LanceDB rows
    schema = pa.schema([
        pa.field("msg_id", pa.int64()),
        pa.field("agent_id", pa.string()),
        pa.field("created_at", pa.string()),
        pa.field("role", pa.string()),
        pa.field("text", pa.string()),
        pa.field("total_tokens", pa.int64()),
        pa.field("char_count", pa.int64()),
        pa.field("mv", pa.list_(pa.list_(pa.float32(), dim))),
    ])

    rows = []
    for msg, emb in zip(searchable, doc_embs):
        emb = np.asarray(emb, dtype=np.float32)
        rows.append({
            "msg_id": msg["msg_id"],
            "agent_id": msg["agent_id"],
            "created_at": str(msg["created_at"]),
            "role": msg["role"],
            "text": msg["text"][:2000],  # truncate for storage
            "total_tokens": msg["total_tokens"],
            "char_count": msg["char_count"],
            "mv": emb.tolist(),
        })

    # Create table
    db = lancedb.connect(LANCEDB_PATH)
    tbl = db.create_table(TABLE_NAME, data=rows, schema=schema, mode="overwrite")
    print(f"Created table '{TABLE_NAME}' with {len(rows)} rows")

    # Build index
    print("Building PQ index...")
    tbl.create_index(vector_column_name="mv", metric="cosine")
    print("  Index built")

    # Test queries
    queries = [
        "how do we fix the task_write tool?",
        "what is the orchestration state machine?",
        "why did the nag not fire?",
        "how does full-list-replace work?",
    ]

    print("\n--- Retrieval Test ---")
    for q in queries:
        q_emb = np.asarray(model.encode([q], is_query=True)[0], dtype=np.float32)
        results = tbl.search(q_emb).limit(3).to_pandas()
        print(f"\nQuery: {q}")
        for _, row in results.iterrows():
            print(f"  [{row['role']}] msg_id={row['msg_id']} | {row['text'][:120]}...")


if __name__ == "__main__":
    main()
