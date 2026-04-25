import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional, Union

import lancedb
import pydantic
from lancedb.pydantic import LanceModel


# Define the sub-structures for the polymorphic content
class TextBlock(pydantic.BaseModel):
    type: str = "text"
    text: str


class ImageURLBlock(pydantic.BaseModel):
    type: str = "image_url"
    image_url: Dict[str, str]


class ToolCall(pydantic.BaseModel):
    id: str
    type: str = "function"
    function: Dict[str, Any]


class Message(LanceModel):
    """
    Strictly typed schema for a conversation message.
    Handles the polymorphic 'content' field and optional reasoning/tool fields.
    """

    session_id: str
    role: str
    # In LanceDB/Arrow, complex Unions are often best handled as JSON strings
    # to ensure bit-for-bit fidelity during the testing phase.
    content: str
    reasoning_content: Optional[str] = None
    tool_calls: Optional[str] = None  # JSON string of List[ToolCall]
    tool_call_id: Optional[str] = None
    timestamp: float


class LanceSession:
    def __init__(self, db_uri: str, session_id: str):
        self.db_uri = db_uri
        self.session_id = session_id
        self.db = lancedb.connect(db_uri)
        self.table_name = f"session_{session_id.replace('-', '_')}"
        self.table = None

    async def initialize(self):
        """Create the table if it doesn't exist."""
        if self.table_name in self.db.table_names():
            self.table = self.db.open_table(self.table_name)
        else:
            self.table = self.db.create_table(self.table_name, schema=Message)

    def add_message(self, msg: Dict[str, Any]):
        """
        Persist a message dict.
        Note: We serialize complex fields to JSON strings to ensure
        we are testing the fidelity of the content itself.
        """
        content_to_store = msg.get("content")
        if not isinstance(content_to_store, str):
            content_to_store = json.dumps(content_to_store)

        tool_calls = msg.get("tool_calls")
        tc_to_store = json.dumps(tool_calls) if tool_calls else None

        record = {
            "session_id": self.session_id,
            "role": msg.get("role", "unknown"),
            "content": content_to_store,
            "reasoning_content": msg.get("reasoning_content"),
            "tool_calls": tc_to_store,
            "tool_call_id": msg.get("tool_call_id"),
            "timestamp": time.time(),
        }
        self.table.add([record])

    def get_messages(self) -> List[Dict[str, Any]]:
        """Retrieve all messages and deserialize complex fields."""
        results = self.table.to_pandas()
        messages = []
        for _, row in results.iterrows():
            msg = {
                "role": row["role"],
                "content": row["content"],
                "reasoning_content": row["reasoning_content"],
                "tool_call_id": row["tool_call_id"],
                "timestamp": row["timestamp"],
            }

            # Reconstruct content if it was a JSON string (list of blocks)
            try:
                # If it starts with [ or {, it was a serialized list/dict
                if isinstance(row["content"], str) and (
                    row["content"].startswith("[") or row["content"].startswith("{")
                ):
                    msg["content"] = json.loads(row["content"])
            except Exception:
                pass

            if row["tool_calls"]:
                try:
                    msg["tool_calls"] = json.loads(row["tool_calls"])
                except Exception:
                    msg["tool_calls"] = None
            else:
                msg["tool_calls"] = None

            messages.append(msg)
        return messages

    async def close(self):
        self.db.close()
