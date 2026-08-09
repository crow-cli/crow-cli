# crow-cli Agen // TEST CURSOR JUMP FIXt-Client Design

## Overview

The crow-cli agent-client is a **dual-role ACP application**:

1. **ACP Server** to upstream clients (Zed, JetBrains, VSCode, etc.)
2. **Agent Orchestrator** that spawns and manages downstream agents via WebSocket

The key innovation: **stdio is reserved for upstream ACP communication**, while **WebSocket handles downstream agent spawning**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    crow-cli (Agent-Client)                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ACP Server (upstream)                                  │   │
│  │  - Listens on stdio (for ACP client)                   │   │
│  │  - Implements: initialize, new_session, prompt, cancel  │   │
│  │  - Session ID → database session_id mapping            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                      ↓                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Agent Orchestrator                                     │   │
│  │  - Spawns child agents: spawn_agent("crow-cli acp")    │   │
│  │  - stdio-to-ws bridge: npx stdio-to-ws → Python impl   │   │
│  │  - WebSocket server for child agent connections        │   │
│  │  - Task delegation and result aggregation              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                      ↓                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Spec Kit Integration (native commands)                 │   │
│  │  - /speckit.constitution, /speckit.specify, etc.       │   │
│  │  - Prompt templates in crow-cli/prompts/               │   │
│  │  - Artifacts stored in .specify/{feature}/             │   │
│  │  - Session persistence via SQLite                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                      ↓                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ReAct Loop + Tool Execution                            │   │
│  │  - Streaming LLM responses (ZAI, OpenAI, etc.)         │   │
│  │  - Parallel tool execution (terminal, read, write, etc.)│   │
│  │  - Session compaction (your custom pattern)            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                      ↓
          ┌───────────────────────────────┐
          │   Child Agent (WebSocket)     │
          │  - crow-cli acp (spawned)    │
          │  - stdio → ws bridge         │
          │  - Independent ReAct loop    │
          │  - Returns results to parent │
          └───────────────────────────────┘
```

---

## stdio-to-WebSocket Bridge (Pure Python)

**Goal:** Spawn a subprocess that speaks stdio (ACP agent) and bridge it to WebSocket so parent can communicate with it.

### Implementation: `crow-cli.stdio_to_ws`

```python
"""
stdio-to-WebSocket bridge for spawning ACP agents.

This replaces `npx stdio-to-ws` with a pure Python implementation.
The subprocess speaks stdio (ACP protocol), we bridge to WebSocket.
"""

import asyncio
import json
import logging
import sys
from typing import List, Optional
from pathlib import Path

import websockets
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


class StdioToWsBridge:
    """Bridge between WebSocket connections and subprocess stdio.
    
    This allows spawning ACP agents (which use stdio) and communicating
    with them over WebSocket.
    
    Usage:
        bridge = StdioToWsBridge(["uv", "run", "crow-cli", "acp"])
        await bridge.run(port=8765)
    """
    
    def __init__(
        self,
        command: List[str],
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
    ):
        """Initialize the bridge.
        
        Args:
            command: Command to spawn (e.g., ["uv", "run", "crow-cli", "acp"])
            cwd: Working directory for subprocess
            env: Environment variables for subprocess
        """
        self.command = command
        self.cwd = cwd
        self.env = env or {}
        self._process: Optional[asyncio.subprocess.Process] = None
        self._ws_server = None
        
    async def run(self, port: int = 8765, host: str = "localhost") -> None:
        """Start the WebSocket server and bridge.
        
        Args:
            port: WebSocket port to listen on
            host: WebSocket host to bind to
        """
        logger.info(f"Starting stdio-to-ws bridge on ws://{host}:{port}")
        logger.info(f"Spawning subprocess: {' '.join(self.command)}")
        
        # Spawn the subprocess
        self._process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env,
        )
        
        logger.info(f"Subprocess spawned with PID {self._process.pid}")
        
        # Start WebSocket server
        self._ws_server = await websockets.serve(
            self._handle_connection,
            host,
            port,
        )
        
        logger.info(f"WebSocket server running on ws://{host}:{port}")
        
        # Keep running until interrupted
        try:
            await asyncio.Future()  # Run forever
        except asyncio.CancelledError:
            logger.info("Bridge shutdown requested")
        finally:
            await self._cleanup()
    
    async def _handle_connection(
        self,
        websocket: WebSocketServerProtocol,
        path: str,
    ) -> None:
        """Handle a WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            path: WebSocket path (unused)
        """
        logger.info(f"WebSocket connection established")
        
        # Create tasks for bidirectional forwarding
        ws_to_stdio = asyncio.create_task(
            self._forward_ws_to_stdio(websocket)
        )
        stdio_to_ws = asyncio.create_task(
            self._forward_stdio_to_ws(websocket)
        )
        
        try:
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [ws_to_stdio, stdio_to_ws],
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
            logger.error(f"Connection error: {e}")
        finally:
            logger.info("WebSocket connection closed")
    
    async def _forward_ws_to_stdio(self, websocket: WebSocketServerProtocol) -> None:
        """Forward WebSocket messages to subprocess stdin.
        
        Args:
            websocket: WebSocket connection
        """
        try:
            async for message in websocket:
                logger.debug(f"WS -> stdio: {message[:200]}...")
                
                # Send to subprocess stdin
                if self._process and self._process.stdin:
                    # Ensure message ends with newline
                    if isinstance(message, str):
                        if not message.endswith("\n"):
                            message += "\n"
                        self._process.stdin.write(message.encode("utf-8"))
                    else:
                        if not message.endswith(b"\n"):
                            message += b"\n"
                        self._process.stdin.write(message)
                    
                    await self._process.stdin.drain()
        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error forwarding WS to stdio: {e}")
    
    async def _forward_stdio_to_ws(self, websocket: WebSocketServerProtocol) -> None:
        """Forward subprocess stdout to WebSocket.
        
        Handles large messages and buffering.
        
        Args:
            websocket: WebSocket connection
        """
        if not self._process or not self._process.stdout:
            return
        
        buffer = b""
        chunk_size = 64 * 1024  # 64KB chunks
        
        try:
            while True:
                # Read a chunk
                chunk = await self._process.stdout.read(chunk_size)
                if not chunk:
                    # EOF
                    if buffer:
                        text = buffer.decode("utf-8").rstrip("\n")
                        if text:
                            await websocket.send(text)
                    break
                
                buffer += chunk
                
                # Process complete lines
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    text = line.decode("utf-8")
                    if text:
                        logger.debug(f"stdio -> WS: {text[:200]}...")
                        await websocket.send(text)
        except Exception as e:
            logger.error(f"Error forwarding stdio to WS: {e}")
        finally:
            # Send any remaining buffer
            if buffer:
                try:
                    text = buffer.decode("utf-8").rstrip("\n")
                    if text:
                        await websocket.send(text)
                except:
                    pass
    
    async def _cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up bridge resources")
        
        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()
        
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass  # Already terminated
        
        logger.info("Bridge cleanup complete")


async def main():
    """Run the stdio-to-ws bridge."""
    import argparse
    
    parser = argparse.ArgumentParser(description="stdio-to-WebSocket bridge")
    parser.add_argument(
        "command",
        nargs="+",
        help="Command to spawn (e.g., 'uv run crow-cli acp')"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="WebSocket port (default: 8765)"
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="WebSocket host (default: localhost)"
    )
    parser.add_argument(
        "--cwd",
        help="Working directory for subprocess"
    )
    parser.add_argument(
        "--log",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Log level"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Run the bridge
    bridge = StdioToWsBridge(
        command=args.command,
        cwd=args.cwd,
    )
    
    await bridge.run(port=args.port, host=args.host)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Usage Examples

### Spawn a Child Agent

```python
# In crow-cli agent orchestrator
import asyncio
from crow_cli.agent.stdio_to_ws import StdioToWsBridge

async def spawn_child_agent() -> str:
    """Spawn a child agent and return its WebSocket URL."""
    # Start the bridge on a random port
    bridge = StdioToWsBridge(
        command=["uv", "run", "crow-cli", "acp"],
        cwd="/path/to/workspace",
    )
    
    # Run bridge in background (e.g., port 8766)
    bridge_task = asyncio.create_task(bridge.run(port=8766))
    
    # Wait a moment for bridge to start
    await asyncio.sleep(1)
    
    # Return WebSocket URL for parent to connect to
    return "ws://localhost:8766"
```

### Connect to Child Agent

```python
# In parent agent orchestrator
import asyncio
import json
import websockets

async def communicate_with_child(ws_url: str, task: str):
    """Send task to child agent and collect results."""
    async with websockets.connect(ws_url) as ws:
        # Send initialization
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "1"}
        }))
        
        # Wait for response
        response = await ws.recv()
        print(f"Child initialized: {response}")
        
        # Send task
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "prompt",
            "params": {
                "session_id": "child-session-123",
                "prompt": [{"type": "text", "text": task}]
            }
        }))
        
        # Stream results
        async for message in ws:
            data = json.loads(message)
            print(f"Child result: {data}")
```

---

## CLI Integration

### crow-cli acp (Main Agent-Client)

```bash
# Run as ACP server to upstream client
crow-cli acp

# This starts:
# 1. ACP server on stdio (for Zed/JetBrains/etc.)
# 2. WebSocket server for child agents
# 3. Agent orchestrator for task delegation
```

### crow-cli acp-bridge (Standalone Bridge)

```bash
# Run standalone stdio-to-ws bridge
crow-cli acp-bridge uv run crow-cli acp --port 8766

# This spawns: uv run crow-cli acp
# And bridges stdio to ws://localhost:8766
```

---

## Session Management

### Session Flow

```
1. Upstream client connects via ACP (stdio)
   ↓
2. crow-cli creates session in database
   session_id = "abc123"
   ↓
3. crow-cli spawns child agent
   - stdio-to-ws bridge on port 8766
   - child_session_id = "def456"
   ↓
4. Parent connects to child via WebSocket
   - Sends task delegation
   - Collects results
   ↓
5. Results aggregated and returned to upstream
   via ACP session_updates
   ↓
6. Compaction when session grows large
   - Compress old events
   - Create new session
   - Route updates as session_updates
   - Client sees continuous session
```

### Database Schema

```sql
-- Sessions table (existing)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,           -- session_id from ACP client
    agent_type TEXT,               -- "crow-cli", "crow-child", etc.
    parent_session_id TEXT,        -- Link to parent if child
    agent_session_id TEXT,         -- Agent's internal session ID
    config TEXT,                   -- JSON config
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Events table (existing)
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    session_id TEXT,               -- Links to sessions.id
    turn_number INTEGER,
    role TEXT,                     -- "user", "assistant", "tool"
    content TEXT,                  -- JSON message content
    tool_calls TEXT,               -- JSON tool calls
    tool_results TEXT,             -- JSON tool results
    usage TEXT,                    -- JSON token usage
    created_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Compaction tracking (new)
CREATE TABLE compaction_history (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    old_event_range TEXT,          -- "1-100"
    new_event_range TEXT,          -- "1-10"
    compressed_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

---

## Spec Kit Integration

### Native Command Routing

crow-cli recognizes `/speckit.*` commands and routes them to appropriate prompt templates:

```python
# In crow-cli/agent/main.py
async def prompt(self, prompt, session_id, **kwargs):
    # Parse prompt for commands
    text = extract_text(prompt)
    
    if text.startswith("/speckit."):
        return await self.handle_speckit_command(text, session_id)
    
    # Normal ReAct loop
    return await self.react_loop(text, session_id)
```

### Prompt Templates

```
crow-cli/prompts/
  system_prompt.jinja2
  speckit_constitution.jinja2   # ← New
  speckit_specify.jinja2        # ← New
  speckit_plan.jinja2           # ← New
  speckit_tasks.jinja2          # ← New
  speckit_implement.jinja2      # ← New
```

### Artifact Storage

```
.project/
  .specify/
    memory/
      constitution.md
    specs/
      001-photo-albums/
        spec.md
        plan.md
        tasks.md
        research.md
        data-model.md
```

All artifacts are **session-persistent** and tied to the ACP session ID.

---

## Key Design Decisions

### 1. **No Node.js Dependencies**
- stdio-to-ws bridge is pure Python
- Uses `websockets` library (already a dependency via fastmcp)
- No `npx` or Node runtime required

### 2. **Session ID Flow**
- Upstream ACP session ID → database → child agent sessions
- Enables session tracking across hierarchy
- Compaction maintains session continuity

### 3. **WebSocket for Child Agents**
- stdio reserved for upstream ACP communication
- WebSocket handles downstream agent spawning
- Bidirectional streaming support

### 4. **Hand-Crafted Architecture**
- Minimal dependencies (ACP SDK, fastmcp, websockets)
- No auto-generation
- Full control over abstractions

---

## Next Steps

1. **Implement stdio-to-ws bridge** (code above)
2. **Add command routing** for `/speckit.*` commands
3. **Create prompt templates** from Spec Kit
4. **Design session compaction** pattern
5. **Test hierarchical agent spawning**

---

## Comparison: Your Vision vs Current crow-cli

| Aspect | Current crow-cli | Agent-Client Vision |
|--------|------------------|---------------------|
| **Role** | ACP agent only | ACP server + agent orchestrator |
| **Communication** | stdio (ACP) | stdio (upstream) + WebSocket (downstream) |
| **Session Management** | Single session | Hierarchical sessions with parent-child links |
| **Spec Kit** | External CLI | Native commands in crow-cli |
| **Agent Spawning** | None | Spawn child agents via stdio-to-ws bridge |
| **Compaction** | Database swap | Session migration with continuous updates |

This is **your artisanal, frameworkless vision** - owning every layer from ACP protocol to agent orchestration to spec-driven workflows. 🚀
