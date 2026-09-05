"""Result objects for crow_cli.tools — the Python channel of the three-fold split.

A tool call inside an execute cell produces three outputs, and only one of
them is the return value:

1. Python — what the calling code gets back: these result objects. Truthy
   on success, compact repr for the REPL's Out[n], real attributes for
   reuse in later cells. Failures RAISE (ToolError subclasses); "Error: ..."
   strings are an MCP wire convention, not a Python one.
2. ACP — what the client sees: ``acp_payload()`` returns a JSON-native
   semantic dict (diff, image ref, text). The server-side drain renders it
   into acp types (ToolCallStart/Progress content); this package never
   imports acp.
3. LLM — what the model sees: execute's text output (stdout + Out[n]
   reprs) plus, for vision results, ``llm_images()`` ImageStore refs
   hydrated into image_url blocks prepended to the response. Images are
   first-class citizens: tools DECLARE them, no autodetection from blobs.
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


@dataclass(repr=False)
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

    def __repr__(self) -> str:
        return f"EditResult({self.path}, +{self.added}/-{self.removed})"


class EditError(ToolError):
    pass


#: The repr blob doubles as the LLM-channel marker: execute's text output
#: carries ``![image](crow-image://<key>)`` and the server-side drain
#: hydrates the key into a real image_url block prepended to the response.
#: ~60 chars — cheap in text, machine-extractable, renders in markdown.
VISION_BLOB = "![image](crow-image://{key})"


@dataclass(repr=False)
class VisionResult(ToolResult):
    """One captured image. Bytes live in the ImageStore under ``key``
    (content-addressed ``<sha256hex><ext>``, same scheme as message
    images) — the result object, the register entry, and the DB row all
    hold refs, never bytes."""

    key: str
    mime: str
    width: int
    height: int
    source: str  # original file path, or "webcam:<device_index>"

    result_kind = "image"

    def acp_payload(self) -> dict:
        # Rendered server-side into acp.schema.ImageContentBlock
        # ({"type": "image", "data": <b64>, "mimeType": ...}) — bytes
        # hydrated from the ImageStore by key.
        return {"content": "image", "key": self.key, "mime": self.mime}

    def llm_images(self) -> list[dict]:
        return [{"key": self.key, "mime": self.mime}]

    def __repr__(self) -> str:
        blob = VISION_BLOB.format(key=self.key)
        return f"VisionResult({blob}, {self.mime}, {self.width}x{self.height}, {self.source})"


class VisionError(ToolError):
    pass
