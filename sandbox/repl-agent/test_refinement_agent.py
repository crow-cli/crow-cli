"""Integration tests for IterativeRefinementAgent via stdio pipe.

Usage:
    uv --project . run pytest test_refinement_agent.py -v
"""

import asyncio
import json
from pathlib import Path

import pytest

AGENT_CMD = [
    "uv",
    "--project",
    str(Path(__file__).parent),
    "run",
    str(Path(__file__).parent / "iterative_refinement_agent.py"),
]


async def _run_with_input(messages: list[dict], timeout: float = 60) -> list[dict]:
    """Spawn agent, feed JSON-RPC messages, collect all responses."""
    proc = await asyncio.create_subprocess_exec(
        *AGENT_CMD,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Feed all messages
    for msg in messages:
        proc.stdin.write((json.dumps(msg) + "\n").encode())

    # Read responses
    results: list[dict] = []
    buf = b""
    try:
        while True:
            chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=timeout)
            if not chunk:
                break
            buf += chunk
            for line in buf.split(b"\n"):
                if line.strip():
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            buf = b""
    except asyncio.TimeoutError:
        pass
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    return results


def _init_message() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": 1,
            "clientCapabilities": {
                "terminal": True,
                "fs": {"read_text_file": True, "write_text_file": True},
            },
            "clientInfo": {"name": "test", "version": "0.1.0"},
        },
    }


def _new_session(cwd: str = "/tmp") -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "session/new",
        "params": {"cwd": cwd, "mcpServers": []},
    }


def _prompt(session_id: str, text: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "session/prompt",
        "params": {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": text}],
        },
    }


class TestRefinementAgentInit:
    """Basic initialization tests."""

    async def test_initialize_returns_protocol_version(self):
        results = await _run_with_input([_init_message()], timeout=10)
        init_resp = next((r for r in results if r.get("id") == 1), None)
        assert init_resp is not None
        assert init_resp["result"]["protocolVersion"] == 1

    async def test_new_session_returns_session_id(self):
        results = await _run_with_input([_init_message(), _new_session()], timeout=15)
        session_resp = next((r for r in results if r.get("id") == 2), None)
        assert session_resp is not None
        assert "sessionId" in session_resp["result"]

    async def test_available_commands_forwarded_with_upstream_session(self):
        results = await _run_with_input([_init_message(), _new_session()], timeout=15)
        session_resp = next((r for r in results if r.get("id") == 2), None)
        assert session_resp is not None
        upstream_sid = session_resp["result"]["sessionId"]

        # All session/update notifications should use the upstream session ID
        updates = [r for r in results if r.get("method") == "session/update"]
        for upd in updates:
            assert upd["params"]["sessionId"] == upstream_sid, (
                f"session/update uses wrong session_id: {upd['params']['sessionId']} "
                f"expected {upstream_sid}"
            )


class TestRefinementAgentPrompt:
    """End-to-end prompt execution tests."""

    async def test_prompt_returns_end_turn(self):
        results = await _run_with_input(
            [_init_message(), _new_session()],
            timeout=15,
        )
        session_resp = next((r for r in results if r.get("id") == 2), None)
        session_id = session_resp["result"]["sessionId"]

        # Now send the prompt (separate call to get fresh output)
        proc = await asyncio.create_subprocess_exec(
            *AGENT_CMD,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        for msg in [_init_message(), _new_session()]:
            proc.stdin.write((json.dumps(msg) + "\n").encode())

        # Wait for session response
        buf = b""
        while True:
            chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=30)
            buf += chunk
            for line in buf.split(b"\n"):
                if line.strip():
                    obj = json.loads(line)
                    if obj.get("id") == 2 and "result" in obj:
                        session_id = obj["result"]["sessionId"]
                        break
            buf = b""

        # Send prompt
        proc.stdin.write(
            (json.dumps(_prompt(session_id, "write hello world")) + "\n").encode()
        )

        # Collect all outputs
        results2: list[dict] = []
        end_turn_seen = False
        buf = b""
        while not end_turn_seen:
            chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=120)
            buf += chunk
            for line in buf.split(b"\n"):
                if line.strip():
                    try:
                        obj = json.loads(line)
                        results2.append(obj)
                        if obj.get("id") == 3:
                            if "result" in obj:
                                assert obj["result"]["stopReason"] == "end_turn"
                                end_turn_seen = True
                            elif "error" in obj:
                                pytest.fail(f"Prompt failed: {obj['error']}")
                    except json.JSONDecodeError:
                        pass
            buf = b""

        proc.terminate()
        await proc.wait()

        # Verify all session/updates use the same upstream session ID
        updates = [r for r in results2 if r.get("method") == "session/update"]
        assert len(updates) > 0, "No session updates received"
        for upd in updates:
            assert upd["params"]["sessionId"] == session_id


class TestRefinementAgentCancel:
    """Cancellation tests."""

    async def test_cancel_idempotent(self):
        """Canceling when no prompt is running should not crash."""
        proc = await asyncio.create_subprocess_exec(
            *AGENT_CMD,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        for msg in [_init_message(), _new_session()]:
            proc.stdin.write((json.dumps(msg) + "\n").encode())

        # Wait for session
        buf = b""
        while True:
            chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=15)
            buf += chunk
            for line in buf.split(b"\n"):
                if line.strip():
                    obj = json.loads(line)
                    if obj.get("id") == 2 and "result" in obj:
                        session_id = obj["result"]["sessionId"]
                        break
            buf = b""

        # Send cancel
        cancel_msg = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "session/cancel",
            "params": {"sessionId": session_id},
        }
        proc.stdin.write((json.dumps(cancel_msg) + "\n").encode())

        await asyncio.sleep(1)
        proc.terminate()
        await proc.wait()
