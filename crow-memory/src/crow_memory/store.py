"""LanceDB store: dual tables (messages + images) with multivector embeddings.

Replaces crow-cli's SQLAlchemy db.py. Full schema parity (prompts, agents,
messages) PLUS the images table that gets base64 blobs out of message records.
"""

import base64
import json
import re
from datetime import datetime, timezone

import lancedb
import pyarrow as pa

from .embed import EMBED_DIM, Embedders

# ---- LanceDB schemas -------------------------------------------------------

_mv = pa.list_(pa.list_(pa.float32(), EMBED_DIM))

PROMPTS_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("name", pa.string()),
    pa.field("template", pa.string()),
    pa.field("created_at", pa.string()),
])

AGENTS_SCHEMA = pa.schema([
    pa.field("agent_id", pa.string()),
    pa.field("session_id", pa.string()),
    pa.field("agent_idx", pa.int64()),
    pa.field("cwd", pa.string()),
    pa.field("prompt_id", pa.string()),
    pa.field("prompt_args", pa.string()),       # JSON
    pa.field("system_prompt", pa.string()),
    pa.field("tool_definitions", pa.string()),  # JSON
    pa.field("request_params", pa.string()),    # JSON
    pa.field("model_identifier", pa.string()),
    pa.field("status", pa.string()),
    pa.field("created_at", pa.string()),
])

MESSAGES_SCHEMA = pa.schema([
    pa.field("id", pa.int64()),
    pa.field("agent_id", pa.string()),
    pa.field("created_at", pa.string()),
    pa.field("data", pa.string()),              # JSON message dict (images extracted)
    pa.field("role", pa.string()),
    pa.field("prompt_tokens", pa.int64()),
    pa.field("completion_tokens", pa.int64()),
    pa.field("total_tokens", pa.int64()),
    pa.field("mv", _mv),                        # ColBERT text embedding
])

IMAGES_SCHEMA = pa.schema([
    pa.field("image_id", pa.string()),          # sha256 of decoded bytes (content-addressed)
    pa.field("mime", pa.string()),
    pa.field("data", pa.large_binary()),        # raw decoded bytes (NOT base64)
    pa.field("w", pa.int64()),
    pa.field("h", pa.int64()),
    pa.field("created_at", pa.string()),
    pa.field("mv", _mv),                        # ColQwen2/ColPali patch embedding
])

_DATA_URL = re.compile(r"^data:(?P<mime>[\w/+.-]+);base64,(?P<b64>.+)$", re.DOTALL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    """Owns the LanceDB connection, the four tables, and the embedders."""

    def __init__(self, path: str, embedders: Embedders):
        self.db = lancedb.connect(path)
        self.emb = embedders
        self.prompts = self._table("prompts", PROMPTS_SCHEMA)
        self.agents = self._table("agents", AGENTS_SCHEMA)
        self.messages = self._table("messages", MESSAGES_SCHEMA)
        self.images = self._table("images", IMAGES_SCHEMA)

    def _table(self, name: str, schema: pa.Schema):
        try:
            return self.db.open_table(name)
        except Exception:
            return self.db.create_table(name, schema=schema)

    # ---- images ------------------------------------------------------------

    def _store_image(self, data: bytes, mime: str) -> str:
        """Content-addressed dedupe: hash, embed if new, store raw bytes. Returns image_id."""
        image_id = Embedders.hash_bytes(data)
        existing = self.images.search().where(f"image_id = '{image_id}'").limit(1).to_pandas()
        if len(existing) == 0:
            mv, w, h = self.emb.embed_image_bytes(data)
            self.images.add([{
                "image_id": image_id, "mime": mime, "data": data,
                "w": w, "h": h, "created_at": _now(), "mv": mv.tolist(),
            }])
        return image_id

    def get_image(self, image_id: str) -> dict | None:
        rows = self.images.search().where(f"image_id = '{image_id}'").limit(1).to_pandas()
        if len(rows) == 0:
            return None
        r = rows.iloc[0]
        return {"image_id": r["image_id"], "mime": r["mime"], "data": bytes(r["data"]),
                "w": int(r["w"]), "h": int(r["h"])}

    def extract_images(self, message: dict) -> tuple[dict, list[str]]:
        """Pull inline images out of a message; replace with image_ref blocks.

        Handles ACP ({type:image,data,mimeType}) and OpenAI
        ({type:image_url,image_url:{url:data:...}}) formats. Returns
        (cleaned_message, [image_id, ...]).
        """
        content = message.get("content")
        if not isinstance(content, list):
            return message, []

        cleaned = []
        image_ids = []
        for block in content:
            if not isinstance(block, dict):
                cleaned.append(block)
                continue
            btype = block.get("type")
            data = mime = None
            if btype == "image" and block.get("data"):
                data, mime = base64.b64decode(block["data"]), block.get("mimeType", "image/png")
            elif btype == "image_url":
                m = _DATA_URL.match(block.get("image_url", {}).get("url", ""))
                if m:
                    data, mime = base64.b64decode(m.group("b64")), m.group("mime")
            elif btype == "image_ref":
                cleaned.append(block)  # already extracted
                image_ids.append(block.get("image_id"))
                continue

            if data is not None:
                image_id = self._store_image(data, mime)
                img = self.get_image(image_id)
                image_ids.append(image_id)
                cleaned.append({"type": "image_ref", "image_id": image_id, "mime": mime,
                                "w": img["w"] if img else 0, "h": img["h"] if img else 0})
            else:
                cleaned.append(block)

        out = dict(message)
        out["content"] = cleaned
        return out, image_ids

    def hydrate(self, message: dict) -> dict:
        """Swap image_ref blocks back to inline base64 data URLs (for the LLM)."""
        content = message.get("content")
        if not isinstance(content, list):
            return message
        out_blocks = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image_ref":
                img = self.get_image(block["image_id"])
                if img:
                    b64 = base64.b64encode(img["data"]).decode()
                    out_blocks.append({"type": "image_url",
                                       "image_url": {"url": f"data:{img['mime']};base64,{b64}"}})
                    continue
            out_blocks.append(block)
        out = dict(message)
        out["content"] = out_blocks
        return out

    # ---- messages ----------------------------------------------------------

    @staticmethod
    def _text_for_embedding(message: dict) -> str:
        parts = []
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                elif b.get("type") in ("image", "image_url", "image_ref"):
                    parts.append("[image]")
        if message.get("reasoning_content"):
            parts.append(message["reasoning_content"])
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function", {})
            parts.append(f"{fn.get('name','')}: {fn.get('arguments','')}")
        text = "\n".join(p for p in parts if p and p.strip())
        return text or f"[{message.get('role','message')}]"

    def _next_message_id(self) -> int:
        df = self.messages.search().limit(1).to_pandas()
        # LanceDB has no MAX aggregate over brute force cheaply; track via count is unsafe.
        # Use max id by scanning the id column.
        try:
            ids = self.messages.to_pandas()["id"]
            return int(ids.max()) + 1 if len(ids) else 1
        except Exception:
            return 1

    def add_message(self, agent_id: str, message: dict, usage: dict | None = None) -> dict:
        """Extract images, embed text, store one message row. Returns stored record."""
        cleaned, image_ids = self.extract_images(message)
        text = self._text_for_embedding(cleaned)
        mv = self.emb.embed_text(text)
        rec = {
            "id": self._next_message_id(),
            "agent_id": agent_id,
            "created_at": _now(),
            "data": json.dumps(cleaned),
            "role": cleaned.get("role", "unknown"),
            "prompt_tokens": (usage or {}).get("prompt_tokens") or 0,
            "completion_tokens": (usage or {}).get("completion_tokens") or 0,
            "total_tokens": (usage or {}).get("total_tokens") or 0,
            "mv": mv.tolist(),
        }
        self.messages.add([rec])
        rec["image_ids"] = image_ids
        return rec

    def load_messages(self, agent_id: str, hydrate_images: bool = False) -> list[dict]:
        df = self.messages.search().where(f"agent_id = '{agent_id}'").limit(1_000_000).to_pandas()
        df = df.sort_values("id")
        msgs = [json.loads(d) for d in df["data"]]
        if hydrate_images:
            msgs = [self.hydrate(m) for m in msgs]
        return msgs

    # ---- agents ------------------------------------------------------------

    def add_agent(self, agent: dict) -> dict:
        rec = {
            "agent_id": agent["agent_id"],
            "session_id": agent["session_id"],
            "agent_idx": agent.get("agent_idx", 1),
            "cwd": agent.get("cwd", "/tmp"),
            "prompt_id": agent.get("prompt_id") or "",
            "prompt_args": json.dumps(agent.get("prompt_args") or {}),
            "system_prompt": agent.get("system_prompt", ""),
            "tool_definitions": json.dumps(agent.get("tool_definitions") or []),
            "request_params": json.dumps(agent.get("request_params") or {}),
            "model_identifier": agent.get("model_identifier", ""),
            "status": agent.get("status", "active"),
            "created_at": _now(),
        }
        self.agents.add([rec])
        return {
            "agent_id": rec["agent_id"], "session_id": rec["session_id"],
            "agent_idx": rec["agent_idx"], "cwd": rec["cwd"],
            "prompt_id": rec["prompt_id"], "prompt_args": json.loads(rec["prompt_args"]),
            "system_prompt": rec["system_prompt"],
            "tool_definitions": json.loads(rec["tool_definitions"]),
            "request_params": json.loads(rec["request_params"]),
            "model_identifier": rec["model_identifier"], "status": rec["status"],
        }

    def get_agent(self, agent_id: str) -> dict | None:
        df = self.agents.search().where(f"agent_id = '{agent_id}'").limit(1).to_pandas()
        if len(df) == 0:
            return None
        r = df.iloc[0]
        return {
            "agent_id": r["agent_id"], "session_id": r["session_id"],
            "agent_idx": int(r["agent_idx"]), "cwd": r["cwd"],
            "prompt_id": r["prompt_id"], "prompt_args": json.loads(r["prompt_args"]),
            "system_prompt": r["system_prompt"],
            "tool_definitions": json.loads(r["tool_definitions"]),
            "request_params": json.loads(r["request_params"]),
            "model_identifier": r["model_identifier"], "status": r["status"],
        }

    def get_max_agent_idx(self, session_id: str) -> int:
        df = self.agents.search().where(f"session_id = '{session_id}'").limit(1_000_000).to_pandas()
        if len(df) == 0:
            return -1
        return int(df["agent_idx"].max())

    # ---- prompts -----------------------------------------------------------

    def upsert_prompt(self, prompt_id: str, name: str, template: str) -> dict:
        existing = self.prompts.search().where(f"id = '{prompt_id}'").limit(1).to_pandas()
        if len(existing) > 0:
            return {"id": prompt_id, "name": name, "template": template, "created": False}
        rec = {"id": prompt_id, "name": name, "template": template, "created_at": _now()}
        self.prompts.add([rec])
        return {"id": prompt_id, "name": name, "template": template, "created": True}

    def get_prompt(self, prompt_id: str) -> dict | None:
        df = self.prompts.search().where(f"id = '{prompt_id}'").limit(1).to_pandas()
        if len(df) == 0:
            return None
        r = df.iloc[0]
        return {"id": r["id"], "name": r["name"], "template": r["template"]}

    # ---- search (unified MaxSim) ------------------------------------------

    def _where(self, filters: dict) -> str | None:
        clauses = []
        for key in ("agent_id", "role", "session_id"):
            if filters.get(key):
                clauses.append(f"{key} = '{filters[key]}'")
        if filters.get("after"):
            clauses.append(f"created_at >= '{filters['after']}'")
        if filters.get("before"):
            clauses.append(f"created_at <= '{filters['before']}'")
        return " AND ".join(clauses) if clauses else None

    def search_messages(self, query: str, filters: dict | None = None,
                        limit: int = 10) -> list[dict]:
        """Text -> text search over the messages table (ColBERT MaxSim)."""
        qmv = self.emb.embed_text_query(query)
        q = self.messages.search(qmv).limit(limit)
        where = self._where(filters or {})
        if where:
            q = q.where(where)
        df = q.to_pandas()
        out = []
        for _, r in df.iterrows():
            out.append({"agent_id": r["agent_id"], "role": r["role"],
                        "created_at": r["created_at"], "data": json.loads(r["data"]),
                        "score": float(r.get("_distance", 0.0))})
        return out

    def search_images(self, query: str | None = None, query_image: bytes | None = None,
                      limit: int = 10) -> list[dict]:
        """Text -> image (ColQwen2 text query) or image -> image search."""
        if query_image is not None:
            qmv = self.emb.embed_image_query_bytes(query_image)
        else:
            qmv = self.emb.embed_image_query_text(query or "")
        df = self.images.search(qmv).limit(limit).to_pandas()
        return [{"image_id": r["image_id"], "mime": r["mime"], "w": int(r["w"]),
                 "h": int(r["h"]), "score": float(r.get("_distance", 0.0))}
                for _, r in df.iterrows()]
