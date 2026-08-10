"""Contract tests for the crow_memory_types bindings as the SDK consumes them.

No server needed: the bindings ARE the crow-memory server's serde impls
compiled to a native module, so round-tripping here is the wire contract.
"""

from __future__ import annotations

import base64
import json

import pytest

import crow_memory_types as wire
from crow_memory_sdk import (
    DEFAULT_MEMORY_PORT,
    ImageRecord,
    MessageRecord,
    SessionInfo,
)

MSG = {
    "id": 17,
    "agent_id": "sess-1-3",
    "created_at": "2026-08-10T00:00:00Z",
    "data": {"role": "user", "content": "hi"},
    "role": "user",
}


def test_port_const() -> None:
    assert DEFAULT_MEMORY_PORT == 27697
    assert wire.DEFAULT_MEMORY_PORT == DEFAULT_MEMORY_PORT


def test_schema_json_covers_wire_types() -> None:
    schema = json.loads(wire.SCHEMA_JSON)
    for name in ("MessageRecord", "SessionInfo", "AddImageRequest"):
        assert name in schema["$defs"]


def test_message_round_trip() -> None:
    rec = MessageRecord.from_dict(MSG)
    assert rec.id == 17
    assert rec.data == {"role": "user", "content": "hi"}
    assert rec.session_id == "sess-1"
    assert rec.agent_idx == 3
    assert rec.to_dict() == MSG  # score=None is skipped on serialize
    assert json.loads(rec.to_json()) == MSG


def test_message_validation_error() -> None:
    bad = dict(MSG)
    del bad["agent_id"]
    with pytest.raises(ValueError):
        MessageRecord.from_dict(bad)


def test_message_score_optional() -> None:
    rec = MessageRecord.from_json(json.dumps({**MSG, "score": 0.42}))
    assert rec.score == pytest.approx(0.42)
    assert "score" not in MessageRecord.from_dict(MSG).to_dict()


def test_message_agent_id_without_idx() -> None:
    rec = MessageRecord.from_dict({**MSG, "agent_id": "weird"})
    assert rec.session_id == "weird"
    assert rec.agent_idx is None


def test_image_data_decodes() -> None:
    payload = b"\x89PNG-fake-bytes"
    b64 = base64.b64encode(payload).decode()
    rec = ImageRecord.from_dict(
        {
            "image_id": "sha256:x",
            "mime": "image/png",
            "data": b64,
            "w": 1,
            "h": 1,
            "created_at": "2026-08-10T00:00:00Z",
        }
    )
    assert rec.data == payload
    assert rec.data is rec.data  # cached
    assert rec.mime == "image/png"
    assert rec.to_dict()["data"] == b64  # wire stays base64


def test_session_last_message_wraps() -> None:
    s = SessionInfo.from_dict(
        {
            "session_id": "s",
            "last_activity": "t",
            "message_count": 1,
            "agent_count": 1,
            "last_role": "user",
            "cwd": "/x",
            "model_identifier": "m",
            "agent_idxs": [0],
            "last_message": MSG,
        }
    )
    assert s.message_count == 1
    assert s.agent_idxs == [0]
    lm = s.last_message
    assert isinstance(lm, MessageRecord)
    assert lm.session_id == "sess-1"


def test_session_defaults_for_old_servers() -> None:
    s = SessionInfo.from_dict(
        {
            "session_id": "s",
            "last_activity": "t",
            "message_count": 0,
            "agent_count": 1,
            "last_role": "user",
            "cwd": "/x",
            "model_identifier": "m",
        }
    )
    assert s.last_message is None
    assert s.agent_idxs == []


def test_agent_record_wire_class() -> None:
    rec = wire.AgentRecord.from_dict(
        {
            "agent_id": "sess-1-0",
            "session_id": "sess-1",
            "agent_idx": 0,
            "cwd": "/x",
            "prompt_id": "p",
            "prompt_args": {},
            "system_prompt": "you are crow",
            "tool_definitions": [],
            "request_params": {},
            "model_identifier": "m",
            "status": "active",
            "created_at": "t",
        }
    )
    assert rec.agent_idx == 0
    assert rec.system_prompt == "you are crow"
    assert rec.to_dict()["status"] == "active"
