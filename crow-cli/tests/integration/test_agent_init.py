"""Integration test: spawn the crow-cli agent over ACP stdio and verify the
``initialize`` handshake.

This is a real check that the agent process starts and speaks ACP — the same
handshake the IDE and ``crow-cli run`` perform. It spawns the agent exactly the
way ``CrowClient.spawn_agent`` does in dev mode (``python -m crow_cli.agent.main``),
so there is no hardcoded machine path.

Lives under tests/integration/ — runs on every pytest invocation.
"""

import json
import select
import subprocess
import sys

import pytest


def _initialize_request() -> bytes:
    msg = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {"readTextFile": True, "writeTextFile": True},
                "terminal": True,
            },
            "clientInfo": {"name": "pytest", "title": "pytest", "version": "0.0.0"},
        },
    }
    return (json.dumps(msg) + "\n").encode()


def test_agent_initialize_handshake():
    """The agent starts and answers ``initialize`` with its capabilities."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "crow_cli.agent.main"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        proc.stdin.write(_initialize_request())
        proc.stdin.flush()

        # Wait (bounded) for the response line rather than blocking forever —
        # the agent is a long-running stdio server and won't exit on its own.
        ready, _, _ = select.select([proc.stdout], [], [], 30)
        assert ready, "agent produced no output within 30s"

        line = proc.stdout.readline()
        assert line.strip(), "agent returned an empty initialize response"

        response = json.loads(line)
        assert response.get("id") == 0, f"unexpected response id: {response}"
        result = response.get("result", {})
        assert result.get("protocolVersion") == 1, f"bad protocolVersion: {result}"
        assert "agentCapabilities" in result, f"no agentCapabilities in: {result}"
        assert result["agentInfo"]["name"] == "crow-cli", f"bad agentInfo: {result}"
    finally:
        proc.kill()
        proc.wait(timeout=10)
