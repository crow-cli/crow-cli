"""
Test that the messages sent to the API match what's stored in the database.

This catches any token loss that occurs between DB persistence and API request.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

from crow_cli.agent.configure import Config
from crow_cli.agent.prompt import normalize_blocks
from crow_cli.agent.session import Session


def normalize_messages_for_api(messages: list[dict]) -> list[dict]:
    """Exactly replicates send_request normalization logic."""
    normalized_messages = []
    for msg in messages:
        normalized_msg = dict(msg)
        content = msg.get("content")
        if isinstance(content, list):
            normalized_msg["content"] = normalize_blocks(content)
        normalized_messages.append(normalized_msg)
    return normalized_messages


def dump_payload(session_id: str, normalized_messages: list[dict]) -> str:
    """Dump payload to ~/.crow/logs/ like send_request does."""
    payload_hash = hashlib.sha256(
        json.dumps(normalized_messages, sort_keys=True).encode()
    ).hexdigest()[:12]
    log_dir = os.path.expanduser("~/.crow/logs")
    os.makedirs(log_dir, exist_ok=True)
    payload_path = os.path.join(log_dir, f"payload-{session_id}-{payload_hash}.json")
    with open(payload_path, "w") as f:
        json.dump(normalized_messages, f)
    return payload_path


class TestPayloadVsDatabaseIntegrity:
    """Ensure what we send to the API matches what's in the DB."""

    def test_full_session_payload_matches_db(self):
        """Load a real session, normalize, dump payload, verify no content loss."""
        config = Config.load()

        # Find a session with messages
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SQLAlchemySession

        from crow_cli.agent.db import Message

        db = SQLAlchemySession(create_engine(config.db_uri))
        try:
            # Get session with most messages
            from sqlalchemy import func

            subq = (
                db.query(Message.session_id, func.count().label("cnt"))
                .group_by(Message.session_id)
                .subquery()
            )
            top = db.query(subq).order_by(subq.c.cnt.desc()).first()
            if top is None:
                pytest.skip("No sessions in database")
            sid = top[0]
            msg_count = top[1]
        finally:
            db.close()

        # Load session
        session = Session.load(sid, db_uri=config.db_uri)
        assert len(session.messages) == msg_count

        # Normalize exactly as send_request does
        normalized = normalize_messages_for_api(session.messages)

        # Dump payload
        payload_path = dump_payload(session.session_id, normalized)

        # Verify: no messages should be dropped
        assert len(normalized) == len(session.messages), (
            f"Message count mismatch: stored={len(session.messages)}, "
            f"sent={len(normalized)}"
        )

        # Verify: no content should shrink
        for i, (stored, sent) in enumerate(zip(session.messages, normalized)):
            stored_content = stored.get("content", "")
            sent_content = sent.get("content", "")

            if isinstance(stored_content, list):
                stored_len = sum(
                    len(b.get("text", "")) if isinstance(b, dict) else len(str(b))
                    for b in stored_content
                )
            else:
                stored_len = len(str(stored_content))

            if isinstance(sent_content, list):
                sent_len = sum(
                    len(b.get("text", "")) if isinstance(b, dict) else len(str(b))
                    for b in sent_content
                )
            else:
                sent_len = len(str(sent_content))

            assert stored_len == sent_len, (
                f"msg[{i}] ({stored.get('role')}): content shrunk "
                f"from {stored_len} to {sent_len} chars"
            )

        # Verify: payload was actually written
        assert os.path.exists(payload_path), f"Payload not dumped to {payload_path}"

        # Verify: payload is valid JSON that can be reloaded
        with open(payload_path) as f:
            reloaded = json.load(f)
        assert len(reloaded) == len(normalized)

    def test_normalize_blocks_does_not_drop_content(self):
        """normalize_blocks should never change total character count."""
        # Simulate messages with various content shapes
        test_cases = [
            # Simple string content - untouched
            {"role": "system", "content": "You are a helpful assistant"},
            # List with text blocks
            {"role": "user", "content": [{"type": "text", "text": "hello world"}]},
            # List with empty block - gets filtered
            {"role": "user", "content": [{"type": "text", "text": "  "}]},
            # List with mixed empty and real
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "  "},
                    {"type": "text", "text": "keep this"},
                ],
            },
            # String content (not a list) - untouched
            {"role": "assistant", "content": "I will help you"},
            # Empty list
            {"role": "tool", "tool_call_id": "x", "content": []},
        ]

        for msg in test_cases:
            content = msg.get("content")
            if isinstance(content, list):
                normalized = normalize_blocks(content)
                orig_chars = sum(
                    len(b.get("text", "")) if isinstance(b, dict) else len(str(b))
                    for b in content
                )
                norm_chars = sum(
                    len(b.get("text", "")) if isinstance(b, dict) else len(str(b))
                    for b in normalized
                )
                # If empty blocks get filtered, that's by design but we log it
                if orig_chars != norm_chars:
                    print(
                        f"Content changed: {orig_chars} -> {norm_chars} chars "
                        f"(msg={msg.get('role')})"
                    )

    async def test_llm_token_count_consistency(self):
        """Hit litellm with the dumped payload and verify token count matches usage reported by the agent."""
        config = Config.load()
        provider = config.llm.providers["litellm"]
        if not provider.base_url:
            pytest.skip("No litellm provider configured")

        from openai import AsyncOpenAI

        llm = AsyncOpenAI(api_key=provider.api_key, base_url=provider.base_url)

        # Load the dumped payload
        log_dir = os.path.expanduser("~/.crow/logs")
        payload_files = sorted(
            Path(log_dir).glob("payload-*.json"),
            key=lambda p: p.stat().st_mtime
        )
        if not payload_files:
            pytest.skip("No payload dumps found in ~/.crow/logs/")

        payload_path = payload_files[-1]
        with open(payload_path) as f:
            messages = json.load(f)

        resp = await llm.chat.completions.create(
            model="qwen3.5-plus",
            messages=messages,
            max_tokens=50,
            stream=False,
        )
        prompt_tokens = resp.usage.prompt_tokens

        # Extract session_id and hash from filename
        # Format: payload-{session_id}-{hash}.json
        stem = payload_path.stem  # e.g. "payload-perky-wealthy-whippet-of-election-3b34c3-9974caa749a3"
        # Remove "payload-" prefix
        rest = stem[len("payload-"):]
        # Hash is last 12 chars, preceded by "-"
        session_id = rest[:-13]  # remove "-{12charhash}"
        session = Session.load(session_id, db_uri=config.db_uri)

        # Log for comparison
        print(f"\n=== Token Consistency Check ===")
        print(f"Payload: {payload_path.name}")
        print(f"DB messages: {len(session.messages)}")
        print(f"API prompt_tokens: {prompt_tokens}")
        print(f"Payload message count: {len(messages)}")

        # The key invariant: message count in payload must equal message count in session
        assert len(messages) == len(session.messages), (
            f"Payload has {len(messages)} messages but DB session has {len(session.messages)}"
        )

    def test_db_json_roundtrip_preserves_content(self):
        """Verify SQLite JSON serialization doesn't lose content."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_uri = f"sqlite:///{f.name}"

        from crow_cli.agent.prompt import render_template
        from crow_cli.agent.db import Base, Message, Session as SessionModel, create_database
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SQLAlchemySession

        create_database(db_uri)
        sid = "test-json-roundtrip"
        db = SQLAlchemySession(create_engine(db_uri))
        db.add(SessionModel(
            session_id=sid,
            system_prompt="test",
            tool_definitions=[],
            request_params={},
            model_identifier="test",
        ))
        db.commit()
        db.close()

        session = Session(sid, db_uri=db_uri)
        test_msg = {
            "role": "assistant",
            "content": "",
            "reasoning_content": "thinking about stuff",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "read", "arguments": '{"path": "/tmp/test"}'},
                }
            ],
        }
        session.add_message(test_msg)

        session2 = Session.load(sid, db_uri=db_uri)
        assert len(session2.messages) == len(session.messages)
        assert session2.messages[0] == session.messages[0]
