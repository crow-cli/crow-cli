"""Quick test of Session with db_v2."""

import asyncio
import tempfile
from pathlib import Path

from crow_cli.agent.db import Base, create_database
from crow_cli.agent.session import Session, get_coolname, lookup_or_create_prompt
from sqlalchemy import create_engine


def test_session():
    # Create temp db
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = f"sqlite:///{f.name}"
    f.close()

    create_database(db_path)
    print(f"Created db: {db_path}")

    # Create a prompt
    prompt_id = lookup_or_create_prompt(
        template="You are {{name}}. Workspace: {{workspace}}",
        name="test-prompt",
        db_path=db_path,
    )
    print(f"Created prompt: {prompt_id}")

    # Create a session
    session = Session.create(
        prompt_id=prompt_id,
        prompt_args={"name": "Crow", "workspace": "/tmp"},
        tool_definitions=[{"name": "test_tool"}],
        request_params={"temperature": 0.7},
        model_identifier="test-model",
        db_path=db_path,
        cwd="/tmp",
    )
    print(f"Created session: {session.session_id}")
    print(f"  - Messages: {len(session.messages)}")
    print(f"  - First message: {session.messages[0]}")

    # Add some messages
    session.add_message({"role": "user", "content": "Hello!"})
    session.add_message({"role": "assistant", "content": "Hi there!"})
    session.add_message({"role": "user", "content": "How are you?"})
    session.add_message({"role": "assistant", "content": "I'm doing well, thanks!"})
    print(f"\nAdded 4 messages. Total: {len(session.messages)}")

    # Load session from db
    loaded = Session.load(session.session_id, db_path)
    print(f"\nLoaded session: {loaded.session_id}")
    print(f"  - Messages: {len(loaded.messages)}")

    # Verify
    assert len(loaded.messages) == 5, f"Expected 5 messages, got {len(loaded.messages)}"
    assert loaded.messages[0]["role"] == "system"
    assert loaded.messages[1]["content"] == "Hello!"
    assert loaded.messages[4]["content"] == "I'm doing well, thanks!"

    print("\n✓ All assertions passed!")

    # Test coolnames
    print(f"\nCool session IDs:")
    for _ in range(3):
        print(f"  - {get_coolname()}")

    # Cleanup
    Path(f.name).unlink(missing_ok=True)
    print(f"\nCleaned up temp db")


if __name__ == "__main__":
    test_session()
