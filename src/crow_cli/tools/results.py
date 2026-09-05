"""Result objects for crow_cli.tools — the Python channel of the three-fold split.

A tool call inside an execute cell produces three outputs, and only one of
them is the return value:

1. Python — what the calling code gets back: these result objects. Truthy
   on success, real attributes for reuse in later cells (EditResult.diff,
   VisionResult.image as a PIL Image). Failures RAISE (ToolError
   subclasses); "Error: ..." strings are an MCP wire convention, not a
   Python one. No designed reprs: execute returns what the cell PRINTED,
   so display strings are not a channel — print() is.
2. ACP — what the client sees: ``acp_payload()`` returns a JSON-native
   semantic dict (diff, image ref, text). The server-side drain renders it
   into acp types (ToolCallStart/Progress content); this package never
   imports acp.
3. LLM — what the model sees: execute's output — stdout + stderr, or the
   traceback on failure — UNMODIFIED. The one exception, and the only
   reason this channel exists: when vision tools ran, hydrated image_url
   blocks are PREPENDED to that output, or vision models could never see
   images. The signal is ``llm_images()`` ImageStore refs riding the DB
   row — non-empty means prepend (has_vision, in effect). No text
   markers, no repr tricks, no blob autodetection.
"""

from __future__ import annotations

from dataclasses import dataclass


class ToolError(Exception):
    """Base for tool failures — raised, never returned as strings."""


class ToolResult:
    """Base for the Python channel. Subclasses declare their ACP/LLM split."""

    result_kind: str = "text"

    def acp_payload(self) -> dict | None:
        return None

    def llm_images(self) -> list[dict]:
        """ImageStore refs ``[{"key": ..., "mime": ...}]``, hydrated at drain."""
        return []

    def __bool__(self) -> bool:
        return True


@dataclass
class EditResult(ToolResult):
    path: str
    old_text: str
    new_text: str
    diff: str = ""

    result_kind = "diff"

    def acp_payload(self) -> dict:
        # Mirrors agent/tools.py execute_acp_edit: whole-file old/new text,
        # rendered as tool_diff_content at emission time.
        return {
            "content": "diff",
            "path": self.path,
            "old_text": self.old_text,
            "new_text": self.new_text,
        }

    @property
    def added(self) -> int:
        return sum(
            1
            for ln in self.diff.splitlines()
            if ln.startswith("+") and not ln.startswith("+++")
        )

    @property
    def removed(self) -> int:
        return sum(
            1
            for ln in self.diff.splitlines()
            if ln.startswith("-") and not ln.startswith("---")
        )


class EditError(ToolError):
    pass


@dataclass
class VisionResult(ToolResult):
    """One captured image. Bytes live in the ImageStore under ``key``
    (content-addressed ``<sha256hex><ext>``, same scheme as message
    images) — the result object, the register entry, and the DB row all
    hold refs, never bytes.

    Code gets a real image: ``.image`` loads the bytes from the store as a
    PIL Image (save/resize/compose/pass along). The LLM side needs no
    marker anywhere: ``llm_images()`` refs ride the row, and the
    server-side drain prepends hydrated image_url blocks to execute's
    output when any are present (has_vision, in effect).
    """

    key: str
    mime: str
    width: int
    height: int
    source: str  # original file path, or "webcam:<device_index>"

    result_kind = "image"

    def acp_payload(self) -> dict:
        # Rendered server-side into an acp image content block — bytes
        # hydrated from the ImageStore by key at emission time.
        return {"content": "image", "key": self.key, "mime": self.mime}

    def llm_images(self) -> list[dict]:
        return [{"key": self.key, "mime": self.mime}]

    @property
    def image(self):
        """The bytes as a PIL Image, loaded from the ImageStore."""
        import io

        from PIL import Image

        from .register import image_store

        store = image_store()
        raw = store.get(self.key) if store is not None else None
        if raw is None:
            raise VisionError(f"image blob missing from store: {self.key}")
        return Image.open(io.BytesIO(raw))


class VisionError(ToolError):
    pass
