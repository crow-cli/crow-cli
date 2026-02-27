"""Shared fixtures for Crow Agent tests."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from crow_cli.agent.configure import Config
from crow_cli.agent.db import Base, create_database


@pytest.fixture
def temp_db_uri(tmp_path):
    """Create a temporary SQLite database."""
    db_path = tmp_path / "test.db"
    db_uri = f"sqlite:///{db_path}"
    create_database(db_uri)
    return db_uri


@pytest.fixture
def test_config_dir(tmp_path):
    """Create a temporary config directory with test config."""
    config_dir = tmp_path / ".crow"
    config_dir.mkdir(parents=True)

    # Create .env file
    env_file = config_dir / ".env"
    env_file.write_text("TEST_VAR=test_value\nAPI_KEY=test_api_key\n")

    # Create config.yaml
    config_file = config_dir / "config.yaml"
    config_data = {
        "providers": {
            "test-provider": {
                "api_key": "${API_KEY}",
                "base_url": "https://test.example.com/v1",
            }
        },
        "models": {
            "test-model": {"provider": "test-provider", "model": "test-model-id"}
        },
        "db_uri": f"sqlite:///{tmp_path}/test.db",
    }
    config_file.write_text(yaml.dump(config_data))

    return config_dir


@pytest.fixture
def test_config(test_config_dir):
    """Load test configuration."""
    return Config.load(test_config_dir)


@pytest.fixture
def sample_prompt_template():
    """Sample system prompt template."""
    return """You are {{name}}.
Workspace: {{workspace}}
Directory: {{display_tree}}
"""


@pytest.fixture
def sample_tool_definition():
    """Sample tool definition for testing."""
    return {
        "name": "test_tool",
        "description": "A test tool",
        "inputSchema": {
            "type": "object",
            "properties": {"param1": {"type": "string"}},
            "required": ["param1"],
        },
    }


@pytest.fixture
def sample_messages():
    """Sample conversation messages."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help?"},
    ]


@pytest.fixture
def test_file_content(tmp_path):
    """Create a test file and return its path and content."""
    file_path = tmp_path / "test.txt"
    content = "Hello, World!\nThis is a test file."
    file_path.write_text(content)
    return {"path": str(file_path), "content": content}


@pytest.fixture
def sample_workspace(tmp_path):
    """Create a sample workspace directory structure."""
    # Create some files
    (tmp_path / "file1.txt").write_text("File 1 content")
    (tmp_path / "file2.py").write_text("print('hello')")

    # Create subdirectory
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "file3.txt").write_text("File 3 content")

    return str(tmp_path)
