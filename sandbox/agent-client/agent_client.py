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
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._ws_port: int = 8765
        self._request_id: int = 0
        self._pending_requests: dict[int, asyncio.Future] = {}
        self._bridge_process: asyncio.subprocess.Process | None = None
        self._update_task: asyncio.Task | None = None
        self._cleanup_done: bool = False

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

            # Spawn child agent + bridge
            await self._spawn_child()

            # Connect to bridge via WebSocket
            await self._connect_to_bridge()

            # Forward initialize to child agent
            logger.info("Forwarding initialize to child agent...")
            response = await self._send_request(
                "initialize",
                {
                    "protocolVersion": protocol_version,
                    "clientCapabilities": client_capabilities or {},
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
        echo_agent = here / "echo_agent.py"

        logger.info(f"  bridge: {stdio_to_ws}")
        logger.info(f"  child: {echo_agent}")

        # Spawn bridge (which spawns child agent)
        self._bridge_process = await asyncio.create_subprocess_exec(
            "uv",
            "--project",
            str(here),
            "run",
            str(stdio_to_ws),
            "--port",
            str(self._ws_port),
            "/home/thomas/src/backup/nid-backup/crow-cli/dist/crow-cli",
            "acp",
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
                    
                    # Otherwise, this is a request FROM the child agent that we need to execute
                    elif "method" in data:
                        await self._handle_downstream_request(data)

                # Check if this is a notification from child agent (no "id" field)
                elif "method" in data:
                    method = data["method"]
                    params = data.get("params", {})
                    
                    # Forward session/update notifications to upstream
                    if method == "session/update":
                        logger.debug(f"Forwarding session/update to upstream: {params}")
                        session_id = params.get("sessionId")
                        update_data = params.get("update", {})
                        
                        # Deserialize the update into the correct Pydantic model
                        update = self._deserialize_update(update_data)
                        
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

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error handling updates: {e}", exc_info=True)

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
            method: Method name (e.g., "create_terminal", "read_text_file")
            params: Method parameters
            
        Returns:
            Result dict from the upstream client
        """
        # Map method names to client methods
        if method == "create_terminal":
            response = await self._conn.create_terminal(
                command=params.get("command"),
                session_id=params.get("sessionId"),
                args=params.get("args"),
                cwd=params.get("cwd"),
                env=params.get("env"),
                output_byte_limit=params.get("outputByteLimit"),
            )
            return {"terminalId": response.terminal_id}
            
        elif method == "terminal_output":
            response = await self._conn.terminal_output(
                session_id=params.get("sessionId"),
                terminal_id=params.get("terminalId"),
            )
            return {
                "output": response.output,
                "truncated": response.truncated,
            }
            
        elif method == "wait_for_terminal_exit":
            response = await self._conn.wait_for_terminal_exit(
                session_id=params.get("sessionId"),
                terminal_id=params.get("terminalId"),
            )
            return {
                "exitCode": response.exit_code,
                "signal": response.signal,
            }
            
        elif method == "release_terminal":
            response = await self._conn.release_terminal(
                session_id=params.get("sessionId"),
                terminal_id=params.get("terminalId"),
            )
            return response or {}
            
        elif method == "kill_terminal":
            response = await self._conn.kill_terminal(
                session_id=params.get("sessionId"),
                terminal_id=params.get("terminalId"),
            )
            return response or {}
            
        elif method == "read_text_file":
            response = await self._conn.read_text_file(
                path=params.get("path"),
                session_id=params.get("sessionId"),
                limit=params.get("limit"),
                line=params.get("line"),
            )
            return {"content": response.content}
            
        elif method == "write_text_file":
            response = await self._conn.write_text_file(
                content=params.get("content"),
                path=params.get("path"),
                session_id=params.get("sessionId"),
            )
            return response or {}
            
        elif method == "request_permission":
            response = await self._conn.request_permission(
                options=params.get("options"),
                session_id=params.get("sessionId"),
                tool_call=params.get("toolCall"),
            )
            return response or {}
            
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
