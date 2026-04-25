"""
Agent-Client: ACP bridge between upstream client and downstream agent.

Architecture:
    Upstream (Zed) ↔ stdio ↔ AgentClient ↔ WebSocket ↔ Bridge ↔ Child Agent (stdio)

The agent-client:
1. Implements ACP Agent interface (for upstream)
2. Spawns child agent + bridge on initialization
3. Connects to bridge via WebSocket
4. Forwards all ACP calls bidirectionally
"""

import asyncio
import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

import websockets
from acp import (
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
)
from acp.interfaces import Client
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AudioContentBlock,
    AvailableCommandsUpdate,
    ClientCapabilities,
    ConfigOptionUpdate,
    CurrentModeUpdate,
    EmbeddedResourceContentBlock,
    FileSystemCapability,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    ResourceContentBlock,
    SessionInfoUpdate,
    SseMcpServer,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    UsageUpdate,
    UserMessageChunk,
)

# Log to file, NOT stdio (stdio is for ACP protocol!)
log_file = Path(__file__).parent / "agent_client.log"
logging.basicConfig(
    filename=str(log_file),
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class AgentClient(Agent):
    """
    ACP agent that forwards to child agent via WebSocket.

    Flow:
        Zed → AgentClient (stdio) → WebSocket → Bridge → Child Agent
    """

    def __init__(self):
        """Initialize the agent-client."""
        self._conn: Client | None = None  # Upstream connection (Zed)
        self._upstream_capabilities: ClientCapabilities | None = None  # What upstream supports
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._ws_port: int = 8765
        self._request_id: int = 0
        self._pending_requests: dict[int, asyncio.Future] = {}
        self._bridge_process: asyncio.subprocess.Process | None = None
        self._update_task: asyncio.Task | None = None
        self._downstream_tasks: set[asyncio.Task] = set()  # Track background request tasks
        self._cleanup_done: bool = False

        # Track terminal tool calls so we can report correct status to upstream
        # terminal_id -> {session_id, command, exit_code, signal}
        self._terminal_tool_calls: dict[str, dict] = {}
        # Map tool_call_ids from child agent to our terminal_ids
        # tool_call_id -> terminal_id (set when terminal/create is called)
        self._tool_call_to_terminal: dict[str, str] = {}
        # Track the most recent terminal tool_call_ids in FIFO order.
        # When the child sends a tool_call notification, we enqueue it.
        # When terminal/create fires, we dequeue the oldest pending ID.
        # This handles parallel terminal creation without race conditions.
        self._pending_terminal_tool_calls: deque[str] = deque()

        logger.info("AgentClient initialized")

    def on_connect(self, conn: Client) -> None:
        """Called when upstream client (Zed) connects."""
        self._conn = conn
        logger.info("Upstream client connected")

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        try:
            logger.info("AgentClient.initialize() called")
            logger.info(f"  protocol_version: {protocol_version}")
            logger.info(f"  client_capabilities: {client_capabilities}")
            logger.info(f"  client_info: {client_info}")

            # Store upstream capabilities so we know what we can forward
            self._upstream_capabilities = client_capabilities

            # Determine what capabilities we can advertise downstream
            # (only what the upstream client actually supports)
            upstream_terminal = bool(
                client_capabilities and getattr(client_capabilities, "terminal", False)
            )
            upstream_fs = (
                getattr(client_capabilities, "fs", None)
                if client_capabilities
                else None
            )
            upstream_read = bool(
                upstream_fs and getattr(upstream_fs, "read_text_file", False)
            )
            upstream_write = bool(
                upstream_fs and getattr(upstream_fs, "write_text_file", False)
            )

            logger.info(
                f"Upstream capabilities: terminal={upstream_terminal}, "
                f"read_text_file={upstream_read}, write_text_file={upstream_write}"
            )

            # Build ClientCapabilities to advertise downstream
            downstream_caps = ClientCapabilities(
                terminal=upstream_terminal,
                fs=FileSystemCapability(
                    read_text_file=upstream_read,
                    write_text_file=upstream_write,
                ),
            )

            # Spawn child agent + bridge
            await self._spawn_child()

            # Connect to bridge via WebSocket
            await self._connect_to_bridge()

            # Forward initialize to child agent with proper client capabilities
            logger.info("Forwarding initialize to child agent...")
            logger.info(f"  downstream_capabilities: {downstream_caps}")
            response = await self._send_request(
                "initialize",
                {
                    "protocolVersion": protocol_version,
                    "clientCapabilities": downstream_caps,
                    "clientInfo": client_info,
                },
            )

            logger.info(f"Child agent initialized: {response}")

            # Extract protocol version from response
            child_protocol_version = response.get("result", {}).get(
                "protocolVersion", protocol_version
            )

            logger.info(
                f"Returning InitializeResponse with protocol_version={child_protocol_version}"
            )
            return InitializeResponse(protocol_version=child_protocol_version)

        except Exception as e:
            logger.error(f"Error in initialize: {e}", exc_info=True)
            raise

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        **kwargs: Any,
    ) -> NewSessionResponse:
        logger.info(f"AgentClient.new_session(cwd={cwd})")

        # Forward to child agent
        response = await self._send_request(
            "session/new",
            {
                "cwd": cwd,
                "mcpServers": mcp_servers,
            },
        )

        logger.info(f"Child session created: {response}")

        # Extract session ID from response
        session_id = response.get("result", {}).get("sessionId")
        if not session_id:
            raise RuntimeError("Child agent did not return sessionId")

        return NewSessionResponse(session_id=session_id)

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        try:
            logger.info(f"AgentClient.prompt(session_id={session_id})")
            logger.info(f"  prompt: {prompt}")

            # Forward to child agent
            logger.info("Forwarding prompt to child agent...")
            response = await self._send_request(
                "session/prompt",
                {
                    "sessionId": session_id,
                    "prompt": prompt,
                },
            )

            # The child agent may have responded with end_turn while tool calls
            # are still executing via client methods (terminal/fs). Wait for all
            # in-flight downstream requests to complete before returning to Zed,
            # so Zed sees end_turn only after all tool calls have finished.
            if self._downstream_tasks:
                logger.info(
                    f"Waiting for {len(self._downstream_tasks)} downstream tasks to complete..."
                )
                await asyncio.gather(*self._downstream_tasks, return_exceptions=True)
                self._downstream_tasks.clear()
                logger.info("All downstream tasks completed")

            logger.info(f"Child prompt complete: {response}")

            # Extract stop reason from response
            stop_reason = response.get("result", {}).get("stopReason", "end_turn")

            logger.info(f"Returning PromptResponse with stop_reason={stop_reason}")
            return PromptResponse(stop_reason=stop_reason)

        except Exception as e:
            logger.error(f"Error in prompt: {e}", exc_info=True)
            raise

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Handle cancellation request from upstream."""
        logger.info(f"AgentClient.cancel(session_id={session_id})")

        # Forward cancellation to child agent
        try:
            await self._send_notification(
                "session/cancel",
                {
                    "sessionId": session_id,
                },
            )
            logger.info("Cancellation forwarded to child agent")
        except Exception as e:
            logger.error(f"Error forwarding cancellation: {e}")

    async def _spawn_child(self):
        """Spawn child agent with stdio-to-ws bridge."""
        logger.info("Spawning child agent...")

        here = Path(__file__).parent
        stdio_to_ws = here / "stdio_to_ws.py"

        # Downstream agent: crow-cli via uvx
        child_cmd = ["uvx", "crow-cli", "acp"]

        logger.info(f"  bridge: {stdio_to_ws}")
        logger.info(f"  child cmd: {' '.join(child_cmd)}")

        # Spawn bridge (which spawns child agent via stdio)
        self._bridge_process = await asyncio.create_subprocess_exec(
            "uv",
            "--project",
            str(here),
            "run",
            str(stdio_to_ws),
            "--port",
            str(self._ws_port),
            *child_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(here),
        )

        logger.info(f"Bridge spawned (PID: {self._bridge_process.pid})")

    async def _connect_to_bridge(self):
        """Connect to the WebSocket server with retries."""
        logger.info(f"Connecting to WebSocket on port {self._ws_port}...")

        max_retries = 10
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                self._ws = await websockets.connect(f"ws://localhost:{self._ws_port}")

                # Start task to handle incoming updates
                self._update_task = asyncio.create_task(self._handle_updates())

                logger.info("WebSocket connected")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(
                        f"Connection attempt {attempt + 1} failed, retrying..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    logger.error(f"Failed to connect after {max_retries} attempts: {e}")
                    raise RuntimeError(f"Failed to connect to bridge: {e}")

    async def _handle_updates(self):
        """Handle incoming WebSocket messages (all messages from child agent)."""
        try:
            async for message in self._ws:
                data = json.loads(message)

                # Check if this is a JSON-RPC message with an ID
                if "id" in data:
                    request_id = data["id"]

                    # Check if this is a response to OUR request
                    if request_id in self._pending_requests:
                        future = self._pending_requests.pop(request_id)
                        future.set_result(data)

                    # Otherwise, this is a request FROM the child agent that we need to execute.
                    # Spawn as a background task so _handle_updates can keep reading
                    # WebSocket messages while waiting for the upstream client to respond.
                    elif "method" in data:
                        task = asyncio.create_task(
                            self._handle_downstream_request(data)
                        )
                        self._downstream_tasks.add(task)
                        task.add_done_callback(self._downstream_tasks.discard)

                # Check if this is a notification from child agent (no "id" field)
                elif "method" in data:
                    method = data["method"]
                    params = data.get("params", {})

                    # Forward session/update notifications to upstream
                    if method == "session/update":
                        logger.debug(f"Forwarding session/update to upstream: {params}")
                        session_id = params.get("sessionId")
                        update_data = params.get("update", {})
                        
                        session_update_type = update_data.get("sessionUpdate")
                        
                        # Track terminal tool calls when they start
                        if session_update_type == "tool_call" and update_data.get("kind") == "execute":
                            tool_call_id = update_data.get("toolCallId", "")
                            self._pending_terminal_tool_calls.append(tool_call_id)
                            logger.debug(f"Enqueued pending terminal tool_call: {tool_call_id}")
                        
                        # Intercept tool_call_update for terminal tool calls and correct status
                        update = self._intercept_tool_call_update(update_data)
                        
                        await self._conn.session_update(
                            session_id=session_id,
                            update=update,
                        )
                        logger.debug(
                            f"Forwarded session/update: {update_data.get('sessionUpdate')}"
                        )

                    # Forward other notifications via ext_notification
                    else:
                        logger.debug(f"Forwarding notification to upstream: {method}")
                        await self._conn.ext_notification(method, params)

                else:
                    logger.warning(f"Unknown message type: {data}")

        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"WebSocket connection closed: {e}")
            # Fail all pending requests so callers don't hang forever
            for req_id, future in self._pending_requests.items():
                if not future.done():
                    future.set_exception(RuntimeError(f"WebSocket closed: {e}"))
            self._pending_requests.clear()
            # Cancel any in-flight downstream request tasks
            for task in self._downstream_tasks:
                if not task.done():
                    task.cancel()
            self._downstream_tasks.clear()
        except Exception as e:
            logger.error(f"Error handling updates: {e}", exc_info=True)
            # Fail all pending requests
            for req_id, future in self._pending_requests.items():
                if not future.done():
                    future.set_exception(RuntimeError(f"Update handler error: {e}"))
            self._pending_requests.clear()
            # Cancel any in-flight downstream request tasks
            for task in self._downstream_tasks:
                if not task.done():
                    task.cancel()
            self._downstream_tasks.clear()

    async def _handle_downstream_request(self, data: dict):
        """
        Handle a JSON-RPC request from the downstream agent.

        The downstream agent is calling a client method (like create_terminal,
        read_text_file, etc.) and expects a response. We need to execute this
        against the upstream client and send the response back.

        Args:
            data: JSON-RPC request dict with id, method, params
        """
        request_id = data["id"]
        method = data["method"]
        params = data.get("params", {})

        logger.info(f"Downstream request: {method} (id={request_id})")

        try:
            # Execute the method against the upstream client
            result = await self._execute_client_method(method, params)

            # Send successful response back to downstream
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
            await self._ws.send(json.dumps(response))
            logger.info(f"Sent response to downstream (id={request_id})")

        except Exception as e:
            logger.error(f"Error executing {method}: {e}", exc_info=True)

            # Send error response back to downstream
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32000,
                    "message": str(e),
                },
            }
            await self._ws.send(json.dumps(response))

    async def _execute_client_method(self, method: str, params: dict) -> dict:
        """
        Execute a client method against the upstream client.

        Args:
            method: JSON-RPC method name (e.g., "terminal/create", "fs/read_text_file")
            params: Method parameters

        Returns:
            Result dict from the upstream client
        """
        # Map JSON-RPC method names to upstream client methods
        if method == "terminal/create":
            response = await self._conn.create_terminal(
                command=params.get("command"),
                session_id=params.get("sessionId"),
                args=params.get("args"),
                cwd=params.get("cwd"),
                env=params.get("env"),
                output_byte_limit=params.get("outputByteLimit"),
            )
            terminal_id = response.terminal_id
            session_id = params.get("sessionId")
            
            # Pop the oldest pending tool_call_id (FIFO) to associate with this terminal
            if self._pending_terminal_tool_calls:
                tool_call_id = self._pending_terminal_tool_calls.popleft()
                self._tool_call_to_terminal[tool_call_id] = terminal_id
                logger.info(f"Mapped tool_call {tool_call_id} → terminal {terminal_id}")
            
            # Store terminal info so we can report correct status later
            self._terminal_tool_calls[terminal_id] = {
                "session_id": session_id,
                "command": params.get("command", ""),
                "exit_code": None,
                "signal": None,
            }
            
            return {"terminalId": terminal_id}

        elif method == "terminal/output":
            response = await self._conn.terminal_output(
                session_id=params.get("sessionId"),
                terminal_id=params.get("terminalId"),
            )
            terminal_id = params.get("terminalId")
            
            # Track exit status for terminal tool call status correction
            if terminal_id in self._terminal_tool_calls and response.exit_status:
                self._terminal_tool_calls[terminal_id]["exit_code"] = response.exit_status.exit_code
                self._terminal_tool_calls[terminal_id]["signal"] = response.exit_status.signal
                logger.info(
                    f"Tracked terminal {terminal_id} exit: code={response.exit_status.exit_code}, signal={response.exit_status.signal}"
                )
            
            result = {
                "output": response.output,
                "truncated": response.truncated,
            }
            if response.exit_status:
                result["exitStatus"] = {
                    "exitCode": response.exit_status.exit_code,
                    "signal": response.exit_status.signal,
                }
            return result

        elif method == "terminal/wait_for_exit":
            # First check if already exited via terminal/output (avoids race condition
            # for quick commands that complete before wait_for_exit is called)
            session_id = params.get("sessionId")
            terminal_id = params.get("terminalId")

            output_response = await self._conn.terminal_output(
                session_id=session_id,
                terminal_id=terminal_id,
            )

            # ACP protocol includes exitStatus in output response if command exited
            if hasattr(output_response, "exit_status") and output_response.exit_status:
                logger.info(
                    f"Terminal already exited (from output): {output_response.exit_status}"
                )
                return {
                    "exitCode": output_response.exit_status.exit_code,
                    "signal": output_response.exit_status.signal,
                }

            # Still running, actually wait for exit
            logger.info("Terminal still running, waiting for exit...")
            response = await self._conn.wait_for_terminal_exit(
                session_id=session_id,
                terminal_id=terminal_id,
            )
            return {
                "exitCode": response.exit_code,
                "signal": response.signal,
            }

        elif method == "terminal/release":
            response = await self._conn.release_terminal(
                session_id=params.get("sessionId"),
                terminal_id=params.get("terminalId"),
            )
            return self._serialize_value(response) if response else {}

        elif method == "terminal/kill":
            response = await self._conn.kill_terminal(
                session_id=params.get("sessionId"),
                terminal_id=params.get("terminalId"),
            )
            return self._serialize_value(response) if response else {}

        elif method == "fs/read_text_file":
            response = await self._conn.read_text_file(
                path=params.get("path"),
                session_id=params.get("sessionId"),
                limit=params.get("limit"),
                line=params.get("line"),
            )
            return {"content": response.content}

        elif method == "fs/write_text_file":
            response = await self._conn.write_text_file(
                content=params.get("content"),
                path=params.get("path"),
                session_id=params.get("sessionId"),
            )
            # WriteTextFileResponse is a Pydantic model — serialize to dict
            return self._serialize_value(response) if response else {}

        elif method == "session/request_permission":
            response = await self._conn.request_permission(
                options=params.get("options"),
                session_id=params.get("sessionId"),
                tool_call=params.get("toolCall"),
            )
            return self._serialize_value(response) if response else {}

        else:
            # Try ext_method for unknown methods
            logger.warning(f"Unknown client method: {method}, trying ext_method")
            return await self._conn.ext_method(method, params)

    async def _send_request(self, method: str, params: dict) -> dict:
        """Send JSON-RPC request to child agent and wait for response."""
        self._request_id += 1
        request_id = self._request_id

        # Serialize params recursively
        serialized_params = self._serialize_value(params)

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": serialized_params,
        }

        # Create future to wait for response
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        # Send request
        await self._ws.send(json.dumps(request))
        logger.info(f"Sent request {request_id}: {method}")

        # Wait for response
        response = await future
        logger.info(f"Received response {request_id}")

        if "error" in response:
            raise RuntimeError(f"Request failed: {response['error']}")

        return response

    def _serialize_value(self, value: Any) -> Any:
        """Recursively serialize a value (Pydantic models → dicts)."""
        if hasattr(value, "model_dump"):
            # Pydantic model
            return value.model_dump(exclude_none=True)
        elif isinstance(value, dict):
            # Dict - recursively serialize values
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            # List/tuple - recursively serialize items
            return [self._serialize_value(item) for item in value]
        else:
            # Primitive value (str, int, float, bool, None)
            return value

    def _intercept_tool_call_update(self, update_data: dict) -> Any:
        """
        Intercept tool_call_update for terminal tool calls and correct status.
        
        The downstream agent may report "failed" because it timed out waiting,
        but the actual exit code might be 0 (success). Since we track the
        real exit status from terminal/output responses, we can correct this.
        
        Returns the deserialized Pydantic model with corrected status.
        """
        session_update_type = update_data.get("sessionUpdate")
        
        # Only intercept tool_call_update for terminal status correction
        if session_update_type == "tool_call_update":
            tool_call_id = update_data.get("toolCallId", "")
            status = update_data.get("status", "")
            
            # Look up terminal_id for this tool_call
            terminal_id = self._tool_call_to_terminal.get(tool_call_id)
            
            if terminal_id and terminal_id in self._terminal_tool_calls:
                terminal_info = self._terminal_tool_calls[terminal_id]
                exit_code = terminal_info.get("exit_code")
                signal = terminal_info.get("signal")
                
                # If we have exit status, determine correct status
                if exit_code is not None:
                    # exit_code 0 + no signal = success, regardless of timeout
                    if exit_code == 0 and not signal:
                        corrected_status = "completed"
                    else:
                        corrected_status = "failed"
                    
                    if status != corrected_status:
                        logger.info(
                            f"Correcting terminal tool call status: "
                            f"tool_call_id={tool_call_id}, terminal_id={terminal_id}, "
                            f"downstream said='{status}', actual exit_code={exit_code}, "
                            f"corrected='{corrected_status}'"
                        )
                        # Create corrected copy with proper status
                        update_data = {**update_data, "status": corrected_status}
                    
                    # Clean up tracking
                    del self._terminal_tool_calls[terminal_id]
                    if tool_call_id in self._tool_call_to_terminal:
                        del self._tool_call_to_terminal[tool_call_id]
        
        return self._deserialize_update(update_data)

    def _deserialize_update(self, update_data: dict) -> Any:
        """
        Deserialize a session update dict into the correct Pydantic model.

        The update_data dict should have a 'sessionUpdate' field that indicates
        the type of update (e.g., "agent_message_chunk", "tool_call", etc.).

        Args:
            update_data: Raw dict from JSON-RPC notification

        Returns:
            Pydantic model instance of the appropriate type
        """
        session_update_type = update_data.get("sessionUpdate")

        if not session_update_type:
            logger.warning(f"Missing sessionUpdate field in update: {update_data}")
            # Return as-is if no type specified
            return update_data

        # Map sessionUpdate type to Pydantic model class
        type_to_model = {
            "agent_message_chunk": AgentMessageChunk,
            "agent_thought_chunk": AgentThoughtChunk,
            "tool_call": ToolCallStart,
            "tool_call_update": ToolCallProgress,
            "plan": AgentPlanUpdate,
            "available_commands_update": AvailableCommandsUpdate,
            "current_mode_update": CurrentModeUpdate,
            "config_option_update": ConfigOptionUpdate,
            "session_info_update": SessionInfoUpdate,
            "usage_update": UsageUpdate,
            "user_message_chunk": UserMessageChunk,
        }

        model_class = type_to_model.get(session_update_type)

        if not model_class:
            logger.warning(f"Unknown sessionUpdate type: {session_update_type}")
            return update_data

        try:
            # Convert snake_case keys to camelCase if needed
            converted_data = self._convert_keys_to_camel(update_data)
            return model_class(**converted_data)
        except Exception as e:
            logger.error(f"Failed to deserialize {session_update_type}: {e}")
            logger.debug(f"Data: {update_data}")
            # Return raw dict as fallback
            return update_data

    def _convert_keys_to_camel(self, data: dict) -> dict:
        """
        Convert snake_case keys to camelCase for Pydantic model compatibility.

        Some ACP models expect camelCase keys (e.g., toolCallId, sessionUpdate).
        """
        if not isinstance(data, dict):
            return data

        result = {}
        for key, value in data.items():
            # Convert snake_case to camelCase
            camel_key = key
            if "_" in key:
                parts = key.split("_")
                camel_key = parts[0] + "".join(part.capitalize() for part in parts[1:])

            # Recursively convert nested dicts
            if isinstance(value, dict):
                value = self._convert_keys_to_camel(value)
            elif isinstance(value, list):
                value = [
                    self._convert_keys_to_camel(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]

            result[camel_key] = value

        return result

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send JSON-RPC notification to child agent (no response expected)."""
        # Serialize params recursively
        serialized_params = self._serialize_value(params)

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": serialized_params,
        }

        await self._ws.send(json.dumps(notification))
        logger.info(f"Sent notification: {method}")

    async def cleanup(self):
        """Clean up child processes and resources."""
        if self._cleanup_done:
            return

        self._cleanup_done = True
        logger.info("Cleaning up child processes...")

        # Cancel update task
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass

        # Cancel pending downstream request tasks
        for task in self._downstream_tasks:
            if not task.done():
                task.cancel()
        if self._downstream_tasks:
            await asyncio.gather(*self._downstream_tasks, return_exceptions=True)
        self._downstream_tasks.clear()

        # Close WebSocket
        if self._ws and not self._ws.closed:
            await self._ws.close()
            logger.info("WebSocket closed")

        # Kill bridge process (which will also kill child agent)
        if self._bridge_process and self._bridge_process.returncode is None:
            logger.info(f"Terminating bridge process (PID: {self._bridge_process.pid})")
            try:
                self._bridge_process.terminate()
                # Wait briefly for graceful shutdown
                try:
                    await asyncio.wait_for(self._bridge_process.wait(), timeout=2.0)
                    logger.info("Bridge process terminated gracefully")
                except asyncio.TimeoutError:
                    logger.warning("Bridge process didn't terminate, killing...")
                    self._bridge_process.kill()
                    await self._bridge_process.wait()
                    logger.info("Bridge process killed")
            except ProcessLookupError:
                logger.info("Bridge process already terminated")

        logger.info("Cleanup complete")


async def main() -> None:
    """Run the agent-client."""
    logger.info("Starting AgentClient")
    agent = AgentClient()

    try:
        await run_agent(agent)
    finally:
        # Always clean up child processes on exit
        await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
