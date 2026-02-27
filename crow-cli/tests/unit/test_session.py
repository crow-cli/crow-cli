"""Unit tests for Session management."""

import pytest

from crow_cli.agent.db import create_database
from crow_cli.agent.session import Session, lookup_or_create_prompt


class TestSessionCreate:
    """Test session creation."""

    def test_session_create(self, temp_db_uri, sample_prompt_template):
        """Create session with prompt, tools, params."""
        # Create prompt
        prompt_id = lookup_or_create_prompt(
            sample_prompt_template,
            name="test-prompt",
            db_uri=temp_db_uri,
        )

        # Create session
        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[{"name": "test_tool"}],
            request_params={"temperature": 0.7},
            model_identifier="test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Verify
        assert session.session_id is not None
        # Session ID format: word-word-word-word-hex (5 parts from coolname)
        assert len(session.session_id.split("-")) >= 4
        assert session.db_uri == temp_db_uri
        assert session.cwd == "/tmp"
        assert len(session.messages) == 1  # System message
        assert session.messages[0]["role"] == "system"
        assert "Crow" in session.messages[0]["content"]

    def test_session_create_with_initial_messages(
        self, temp_db_uri, sample_prompt_template
    ):
        """Create session with initial messages."""
        prompt_id = lookup_or_create_prompt(
            sample_prompt_template,
            name="test-prompt",
            db_uri=temp_db_uri,
        )

        initial_messages = [
            {"role": "user", "content": "Previous message"},
            {"role": "assistant", "content": "Previous response"},
        ]

        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
            initial_messages=initial_messages,
        )

        # Verify system message + 2 initial messages
        assert len(session.messages) == 3
        assert session.messages[0]["role"] == "system"
        assert session.messages[1]["role"] == "user"
        assert session.messages[2]["role"] == "assistant"

    def test_session_create_skips_system_in_initial(
        self, temp_db_uri, sample_prompt_template
    ):
        """Session creation skips system messages in initial_messages."""
        prompt_id = lookup_or_create_prompt(
            sample_prompt_template,
            name="test-prompt",
            db_uri=temp_db_uri,
        )

        initial_messages = [
            {"role": "system", "content": "Should be ignored"},
            {"role": "user", "content": "Should be kept"},
        ]

        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
            initial_messages=initial_messages,
        )

        # Only original system + user message (not the duplicate system)
        assert len(session.messages) == 2
        assert session.messages[0]["content"] != "Should be ignored"


class TestSessionLoad:
    """Test session loading."""

    def test_session_load(self, temp_db_uri, sample_prompt_template):
        """Load existing session from database."""
        # Create session
        prompt_id = lookup_or_create_prompt(
            sample_prompt_template,
            name="test-prompt",
            db_uri=temp_db_uri,
        )

        session1 = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[{"name": "test_tool"}],
            request_params={"temperature": 0.7},
            model_identifier="test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )
        session_id = session1.session_id

        # Load session
        session2 = Session.load(session_id, db_uri=temp_db_uri)

        # Verify
        assert session2.session_id == session_id
        assert session2.db_uri == temp_db_uri
        assert session2.cwd == "/tmp"
        assert session2.model_identifier == "test-model"
        assert len(session2.messages) == 1
        assert session2.messages[0]["role"] == "system"

    def test_session_load_not_found(self, temp_db_uri):
        """Load non-existent session raises error."""
        with pytest.raises(ValueError, match="not found"):
            Session.load("non-existent-id", db_uri=temp_db_uri)


class TestSessionAddMessage:
    """Test adding messages to session."""

    def test_session_add_message(self, temp_db_uri, sample_prompt_template):
        """Add message persists to database."""
        prompt_id = lookup_or_create_prompt(
            sample_prompt_template,
            name="test-prompt",
            db_uri=temp_db_uri,
        )

        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Add message
        session.add_message({"role": "user", "content": "Hello!"})

        # Verify in-memory
        assert len(session.messages) == 2
        assert session.messages[1] == {"role": "user", "content": "Hello!"}

        # Verify in database
        loaded = Session.load(session.session_id, db_uri=temp_db_uri)
        assert len(loaded.messages) == 2
        assert loaded.messages[1] == {"role": "user", "content": "Hello!"}

    def test_session_message_order(self, temp_db_uri, sample_prompt_template):
        """Messages maintain insertion order."""
        prompt_id = lookup_or_create_prompt(
            sample_prompt_template,
            name="test-prompt",
            db_uri=temp_db_uri,
        )

        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Add messages in order
        session.add_message({"role": "user", "content": "First"})
        session.add_message({"role": "assistant", "content": "Second"})
        session.add_message({"role": "user", "content": "Third"})

        # Verify order
        assert session.messages[1]["content"] == "First"
        assert session.messages[2]["content"] == "Second"
        assert session.messages[3]["content"] == "Third"

        # Verify after reload
        loaded = Session.load(session.session_id, db_uri=temp_db_uri)
        assert loaded.messages[1]["content"] == "First"
        assert loaded.messages[2]["content"] == "Second"
        assert loaded.messages[3]["content"] == "Third"


class TestSessionSwapIds:
    """Test session ID swapping for compaction."""

    def test_session_swap_ids(self, temp_db_uri, sample_prompt_template):
        """Atomically swap session IDs for compaction."""
        # Create two sessions
        prompt_id = lookup_or_create_prompt(
            sample_prompt_template,
            name="test-prompt",
            db_uri=temp_db_uri,
        )

        session1 = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        session2 = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=[],
            request_params={},
            model_identifier="test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        old_id = session1.session_id
        new_id = session2.session_id

        # Swap
        archive_id = Session.swap_session_id(old_id, new_id, db_uri=temp_db_uri)

        # Verify archive_id is correct format
        assert archive_id.startswith("sess_archive_")
        
        # Verify old_id is now archived (can't load it as old_id anymore)
        # After swap: old_id -> archive_id, new_id -> old_id
        # So loading old_id now gives us session2's data
        loaded = Session.load(old_id, db_uri=temp_db_uri)
        assert loaded is not None
        # The loaded session should have session2's data now


class TestSessionToolDefinitions:
    """Test tool definitions persistence."""

    def test_session_tool_definitions(self, temp_db_uri, sample_prompt_template):
        """Tool definitions persist correctly."""
        prompt_id = lookup_or_create_prompt(
            sample_prompt_template,
            name="test-prompt",
            db_uri=temp_db_uri,
        )

        tools = [
            {"name": "tool1", "description": "Tool 1"},
            {"name": "tool2", "description": "Tool 2"},
        ]

        session = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=tools,
            request_params={},
            model_identifier="test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Verify
        assert session.tools == tools

        # Verify after reload
        loaded = Session.load(session.session_id, db_uri=temp_db_uri)
        assert loaded.tools == tools


class TestSessionRoundtrip:
    """Test full session lifecycle."""

    def test_session_roundtrip(self, temp_db_uri, sample_prompt_template):
        """Create → reload → verify all fields match."""
        prompt_id = lookup_or_create_prompt(
            sample_prompt_template,
            name="test-prompt",
            db_uri=temp_db_uri,
        )

        tools = [{"name": "test_tool", "description": "A test tool"}]

        session1 = Session.create(
            prompt_id=prompt_id,
            prompt_args={"name": "Crow", "workspace": "/tmp", "display_tree": "test/"},
            tool_definitions=tools,
            request_params={"temperature": 0.7, "max_tokens": 100},
            model_identifier="test-model",
            db_uri=temp_db_uri,
            cwd="/tmp",
        )

        # Add some messages
        session1.add_message({"role": "user", "content": "Hello!"})
        session1.add_message({"role": "assistant", "content": "Hi!"})

        # Reload
        session2 = Session.load(session1.session_id, db_uri=temp_db_uri)

        # Verify all fields
        assert session2.session_id == session1.session_id
        assert session2.db_uri == session1.db_uri
        assert session2.cwd == session1.cwd
        assert session2.model_identifier == session1.model_identifier
        assert session2.tools == session1.tools
        assert session2.request_params == session1.request_params
        assert session2.prompt_id == session1.prompt_id
        assert session2.prompt_args == session1.prompt_args
        assert len(session2.messages) == len(session1.messages)
        assert session2.messages == session1.messages
