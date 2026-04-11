"""
ACP Bridge - WebSocket to subprocess stdio bridge.

This module provides a bridge between WebSocket connections and subprocess
stdin/stdout, enabling communication with ACP-compatible agents.

All messages are persisted to SQLite for session replay and training data extraction.
"""

import asyncio
import json
import logging
from typing import List, Optional

import websockets

from db import SessionStore, get_store

logger = logging.getLogger(__name__)


def _extract_message_type(content: str) -> Optional[str]:
    """Extract message type from JSON-RPC message."""
    try:
        data = json.loads(content)
        # JSON-RPC method for requests/notifications
        if "method" in data:
            return data["method"]
        # JSON-RPC result/error for responses
        if "result" in data:
            return "result"
        if "error" in data:
            return "error"
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _extract_agent_session_id(content: str) -> Optional[str]:
    """Extract agent session ID from new session response."""
    try:
        data = json.loads(content)
        # session/new response
        if "result" in data and isinstance(data["result"], dict):
            if "sessionId" in data["result"]:
                return data["result"]["sessionId"]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


class ACPBridge:
    """Bridge WebSocket connections to subprocess stdio."""

    def __init__(self, command: List[str], cwd: Optional[str] = None):
        """Initialize the bridge with a command to run.

        Args:
            command: Command and arguments to spawn as subprocess.
            cwd: Working directory for the subprocess.
        """
        self.command = command
        self.cwd = cwd
        self._process = None

    async def handle(self, websocket) -> None:
        """Handle a WebSocket connection by bridging to subprocess.

        Args:
            websocket: Starlette WebSocket connection.
        """
        await websocket.accept()
        print(f"ACPBridge: Spawning subprocess: {self.command}", flush=True)
        logger.info(f"ACPBridge: Spawning subprocess: {self.command}")

        # Spawn the subprocess
        self._process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
        )
        print(f"ACPBridge: Subprocess spawned with PID {self._process.pid}", flush=True)

        # Create tasks for reading from stdout/stderr and websocket
        stdout_task = asyncio.create_task(self._forward_stdout(websocket))
        stderr_task = asyncio.create_task(self._log_stderr())
        ws_task = asyncio.create_task(self._forward_websocket(websocket))

        try:
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [stdout_task, ws_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            if self._process:
                try:
                    self._process.terminate()
                except ProcessLookupError:
                    pass

    async def _log_stderr(self) -> None:
        """Log subprocess stderr."""
        print("ACPBridge: Starting stderr logging", flush=True)
        while True:
            line = await self._process.stderr.readline()
            if not line:
                print("ACPBridge: stderr EOF", flush=True)
                break
            text = line.decode("utf-8").rstrip("\n")
            if text:
                print(f"ACPBridge stderr: {text}", flush=True)

    async def _forward_stdout(self, websocket) -> None:
        """Forward subprocess stdout to WebSocket.

        Handles large JSON messages that exceed the default 64KB readline limit
        by buffering chunks until a complete line is found.

        Args:
            websocket: Starlette WebSocket connection.
        """
        print("ACPBridge: Starting stdout forwarding", flush=True)
        buffer = b""
        chunk_size = 64 * 1024  # 64KB chunks for responsiveness

        while True:
            # Read a chunk of data
            chunk = await self._process.stdout.read(chunk_size)
            if not chunk:
                # EOF - send any remaining buffered data
                if buffer:
                    text = buffer.decode("utf-8").rstrip("\n")
                    if text:
                        print(f"ACPBridge: stdout -> ws (final): {text}", flush=True)
                        await websocket.send_text(text)
                print("ACPBridge: stdout EOF", flush=True)
                break

            buffer += chunk

            # Process complete lines from the buffer
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                text = line.decode("utf-8")
                if text:
                    print(
                        f"ACPBridge: stdout -> ws: {text} — ({len(text)} bytes)",
                        flush=True,
                    )
                    await websocket.send_text(text)

    async def _forward_websocket(self, websocket) -> None:
        """Forward WebSocket messages to subprocess stdin.

        Args:
            websocket: Starlette WebSocket connection.
        """
        print("ACPBridge: Starting websocket forwarding", flush=True)
        try:
            while True:
                message = await websocket.receive()
                print(
                    f"ACPBridge: received ws message type: {message.get('type')}",
                    flush=True,
                )
                if message["type"] == "websocket.disconnect":
                    print("ACPBridge: websocket disconnected", flush=True)
                    break

                # Handle both text and binary messages
                if "text" in message:
                    data = message["text"].encode("utf-8")
                elif "bytes" in message:
                    data = message["bytes"]
                else:
                    print(f"ACPBridge: unknown message type: {message}", flush=True)
                    continue

                print(
                    f"ACPBridge: ws -> stdin: {data if data else b'(empty)'}",
                    flush=True,
                )
                if not data.endswith(b"\n"):
                    data += b"\n"
                self._process.stdin.write(data)
                await self._process.stdin.drain()
        except Exception as e:
            print(f"ACPBridge: websocket forwarding error: {e}", flush=True)


class ACPWebSocketProxy:
    """Proxy WebSocket connections to another WebSocket server.

    All messages are logged to SQLite for session persistence.
    """

    def __init__(self, target_url: str, agent_type: str = "unknown"):
        """Initialize the proxy with a target WebSocket URL.

        Args:
            target_url: WebSocket URL to connect to (e.g., ws://localhost:3000).
            agent_type: Type of agent (e.g., 'karla', 'claude').
        """
        self.target_url = target_url
        self.agent_type = agent_type
        self._target_ws = None
        self._store: Optional[SessionStore] = None
        self._session_id: Optional[str] = None
        self._agent_session_id: Optional[str] = None

    async def handle(self, websocket) -> None:
        """Handle a WebSocket connection by proxying to target.

        Args:
            websocket: Starlette WebSocket connection.
        """
        await websocket.accept()

        # Initialize session storage
        self._store = get_store()
        self._session_id = self._store.create_session(
            agent_type=self.agent_type,
            title=f"Session with {self.agent_type}",
        )
        logger.info(f"Created session {self._session_id} for agent {self.agent_type}")

        try:
            async with websockets.connect(self.target_url) as target_ws:
                self._target_ws = target_ws

                # Create tasks for bidirectional forwarding
                client_to_target = asyncio.create_task(
                    self._forward_client_to_target(websocket, target_ws)
                )
                target_to_client = asyncio.create_task(
                    self._forward_target_to_client(websocket, target_ws)
                )

                # Wait for either task to complete
                done, pending = await asyncio.wait(
                    [client_to_target, target_to_client],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
        except Exception as e:
            # Log error
            if self._store and self._session_id:
                self._store.add_message(
                    self._session_id,
                    direction="error",
                    content=str(e),
                    message_type="connection_error",
                )
            # Send error to client if connection fails
            try:
                await websocket.send_text(
                    f'{{"error": "Failed to connect to agent: {e}"}}'
                )
            except:
                pass

    async def _forward_client_to_target(self, client_ws, target_ws) -> None:
        """Forward messages from client to target WebSocket."""
        try:
            async for message in client_ws.iter_text():
                # Log outbound message
                if self._store and self._session_id:
                    msg_type = _extract_message_type(message)
                    self._store.add_message(
                        self._session_id,
                        direction="outbound",
                        content=message,
                        message_type=msg_type,
                    )
                await target_ws.send(message)
        except (KeyError, RuntimeError):
            # Client disconnected
            pass

    async def _forward_target_to_client(self, client_ws, target_ws) -> None:
        """Forward messages from target to client WebSocket."""
        async for message in target_ws:
            # Log inbound message
            if self._store and self._session_id:
                msg_type = _extract_message_type(message)
                self._store.add_message(
                    self._session_id,
                    direction="inbound",
                    content=message,
                    message_type=msg_type,
                )

                # Check for agent session ID in response
                if not self._agent_session_id:
                    agent_sid = _extract_agent_session_id(message)
                    if agent_sid:
                        self._agent_session_id = agent_sid
                        self._store.update_session(
                            self._session_id,
                            agent_session_id=agent_sid,
                        )
                        logger.info(f"Captured agent session ID: {agent_sid}")

            await client_ws.send_text(message)
