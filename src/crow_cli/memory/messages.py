"""Message-dict transforms: image extraction/hydration, searchable text.

Images never live in the database: inline base64 blocks are extracted at
write time into an :class:`~crow_cli.memory.image_store.ImageStore` keyed
by ``<sha256hex><ext>`` (content-addressed, so dupes dedupe for free) and
the stored message carries an ``image_ref`` block with the key. The
in-memory conversation keeps the original data URL so the LLM always sees
base64; on load, ``hydrate`` swaps refs back to data URLs.
"""

import base64
import hashlib

from .image_store import ImageStore

_MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


def _block_bytes(block: dict) -> tuple[bytes, str] | None:
    """Decode an inline image block (OpenAI image_url or ACP image) to bytes."""
    btype = block.get("type")
    if btype == "image_url":
        url = (block.get("image_url") or {}).get("url", "")
        mime, _, b64 = url.partition(";base64,")
        if mime.startswith("data:") and b64:
            try:
                return base64.b64decode(b64), mime[5:]
            except ValueError:
                return None
    if btype == "image":
        b64 = block.get("data", "")
        if b64:
            try:
                return base64.b64decode(b64), block.get("mimeType", "image/png")
            except ValueError:
                return None
    return None


def extract_images(message: dict, store: ImageStore) -> dict:
    """Replace inline image blocks with image_ref blocks keyed by
    ``<sha256hex><ext>`` in the store. Non-image blocks pass through."""
    content = message.get("content")
    if not isinstance(content, list):
        return message
    cleaned = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") == "image_ref":
            cleaned.append(block)
            continue
        decoded = _block_bytes(block)
        if decoded is None:
            cleaned.append(block)
            continue
        raw, mime = decoded
        key = f"{hashlib.sha256(raw).hexdigest()}{_MIME_EXT.get(mime, '.png')}"
        store.put(key, raw)
        cleaned.append({"type": "image_ref", "path": key, "mime": mime})
    out = dict(message)
    out["content"] = cleaned
    return out


def hydrate_message(message: dict, store: ImageStore) -> dict:
    """Swap image_ref blocks back to base64 data URLs (for the LLM).
    Missing blobs pass through untouched."""
    content = message.get("content")
    if not isinstance(content, list):
        return message
    out_blocks = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "image_ref":
            data = store.get(block.get("path", ""))
            if data is not None:
                b64 = base64.b64encode(data).decode()
                out_blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{block.get('mime', 'image/png')};base64,{b64}"},
                    }
                )
                continue
        out_blocks.append(block)
    out = dict(message)
    out["content"] = out_blocks
    return out


def message_text(data: dict) -> str:
    """Searchable text of a message: content (str or text blocks) + reasoning."""
    parts = []
    content = data.get("content")
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        parts.extend(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if data.get("reasoning_content"):
        parts.append(data["reasoning_content"])
    return "\n".join(p for p in parts if p)
