"""Constructors for ACP v1 wire types.

Upstream deleted ``acp.helpers`` in python-sdk ``713cbc1`` ("remove schema helper
API"): the position is that applications should build the pydantic models
directly. These are the ten constructors crow actually uses, vendored verbatim
so the v1 surface keeps working while ``acp.experimental.v2`` is developed
against the same install.

v2 renames most of these types (``ToolCallStart``/``ToolCallProgress`` collapse
into one upsert ``SessionToolCallUpdate``, chunks gain a required ``messageId``),
so nothing here is reusable on the v2 path -- it exists to keep v1 alive.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ContentToolCallContent,
    FileEditToolCallContent,
    ImageContentBlock,
    TerminalToolCallContent,
    TextContentBlock,
    ToolCallLocation,
    ToolCallProgress,
    ToolCallStart,
    ToolCallStatus,
    ToolKind,
)

__all__ = [
    "image_block",
    "start_edit_tool_call",
    "start_read_tool_call",
    "start_tool_call",
    "text_block",
    "tool_content",
    "tool_diff_content",
    "tool_terminal_ref",
    "update_agent_message",
    "update_agent_thought",
    "update_tool_call",
]

ContentBlock = TextContentBlock | ImageContentBlock
ToolCallContentVariant = ContentToolCallContent | FileEditToolCallContent | TerminalToolCallContent


def text_block(text: str) -> TextContentBlock:
    return TextContentBlock(type="text", text=text)


def image_block(data: str, mime_type: str, *, uri: str | None = None) -> ImageContentBlock:
    return ImageContentBlock(type="image", data=data, mime_type=mime_type, uri=uri)


def tool_content(block: ContentBlock) -> ContentToolCallContent:
    return ContentToolCallContent(type="content", content=block)


def tool_diff_content(path: str, new_text: str, old_text: str | None = None) -> FileEditToolCallContent:
    return FileEditToolCallContent(type="diff", path=path, new_text=new_text, old_text=old_text)


def tool_terminal_ref(terminal_id: str) -> TerminalToolCallContent:
    return TerminalToolCallContent(type="terminal", terminal_id=terminal_id)


def update_agent_message(content: ContentBlock) -> AgentMessageChunk:
    return AgentMessageChunk(session_update="agent_message_chunk", content=content)


def update_agent_thought(content: ContentBlock) -> AgentThoughtChunk:
    return AgentThoughtChunk(session_update="agent_thought_chunk", content=content)


def start_tool_call(
    tool_call_id: str,
    title: str,
    *,
    kind: ToolKind | None = None,
    status: ToolCallStatus | None = None,
    content: Sequence[ToolCallContentVariant] | None = None,
    locations: Sequence[ToolCallLocation] | None = None,
    raw_input: Any | None = None,
    raw_output: Any | None = None,
) -> ToolCallStart:
    return ToolCallStart(
        session_update="tool_call",
        tool_call_id=tool_call_id,
        title=title,
        kind=kind,
        status=status,
        content=list(content) if content is not None else None,
        locations=list(locations) if locations is not None else None,
        raw_input=raw_input,
        raw_output=raw_output,
    )


def start_read_tool_call(
    tool_call_id: str,
    title: str,
    path: str,
    *,
    extra_options: Sequence[ToolCallContentVariant] | None = None,
) -> ToolCallStart:
    return start_tool_call(
        tool_call_id,
        title,
        kind="read",
        status="pending",
        content=list(extra_options) if extra_options is not None else None,
        locations=[ToolCallLocation(path=path)],
        raw_input={"path": path},
    )


def start_edit_tool_call(
    tool_call_id: str,
    title: str,
    path: str,
    content: Any,
    *,
    extra_options: Sequence[ToolCallContentVariant] | None = None,
) -> ToolCallStart:
    return start_tool_call(
        tool_call_id,
        title,
        kind="edit",
        status="pending",
        content=list(extra_options) if extra_options is not None else None,
        locations=[ToolCallLocation(path=path)],
        raw_input={"path": path, "content": content},
    )


def update_tool_call(
    tool_call_id: str,
    *,
    title: str | None = None,
    kind: ToolKind | None = None,
    status: ToolCallStatus | None = None,
    content: Sequence[ToolCallContentVariant] | None = None,
    locations: Sequence[ToolCallLocation] | None = None,
    raw_input: Any | None = None,
    raw_output: Any | None = None,
) -> ToolCallProgress:
    return ToolCallProgress(
        session_update="tool_call_update",
        tool_call_id=tool_call_id,
        title=title,
        kind=kind,
        status=status,
        content=list(content) if content is not None else None,
        locations=list(locations) if locations is not None else None,
        raw_input=raw_input,
        raw_output=raw_output,
    )
