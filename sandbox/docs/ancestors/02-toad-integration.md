# Toad Integration Guide

## Overview

Toad is a Terminal User Interface (TUI) for coding agents that supports the Agent Client Protocol (ACP). Crow can be made compatible with Toad by implementing ACP, allowing users who prefer TUI interfaces to use Crow without any custom integration work.

## What is Toad?

Toad provides:
- **AI App Store**: Discover and run agents directly from the UI
- **Full Shell Integration**: Unlike other TUIs, Toad integrates a working shell with full color output, interactive commands, and tab completion
- **Prompt Editor**: Markdown prompt editor with syntax highlighting and mouse support
- **File Picker**: Fuzzy file picker (`@` key) to add files to prompts
- **Beautiful Diffs**: Side-by-side or unified diffs with syntax highlighting
- **Session Resume**: Resume previous sessions with `ctrl+r`
- **ACP Support**: Any agent implementing ACP works with Toad

## Why ACP Integration Matters

Without ACP:
- Users who prefer TUIs can't use Crow
- Each TUI would need custom integration for Crow
- Maintenance burden increases with each client

With ACP:
- Crow works with any ACP-compatible client (Toad, VSCode extensions, JetBrains, custom clients)
- Zero integration work per client
- Users can choose their preferred interface
- Focus development effort on agent capabilities, not UI

## ACP Specification

The Agent Client Protocol (ACP) standardizes communication between code editors/IDEs and coding agents. It's:
- **REST-based** (or JSON-RPC over stdio for local agents)
- **Streaming-first**: Supports streaming responses essential for local models
- **Modal-agnostic**: Works with any data format (text, images, etc.)
- **Offline-capable**: Agents can embed metadata for discovery even when inactive

## Crow ACP Implementation

### Minimum ACP Requirements

To be ACP-compatible, Crow needs to implement:

1. **Agent List Endpoint**: List available agents and their capabilities
2. **Create Session Endpoint**: Start a new conversation/session
3. **Send Message Endpoint**: Send user message, get streaming response
4. **Cancel Endpoint**: Cancel in-progress generation
5. **Session Resume Endpoint**: Restore previous session from ID

### Architecture: ACP as a Layer Around Core Agent

```
┌─────────────────┐
│   Toad TUI      │ (or any ACP client)
└────────┬────────┘
         │ ACP (JSON-RPC/REST)
         ▼
┌─────────────────┐
│  Crow ACP Layer │ ← Converts ACP requests to internal agent operations
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Core Agent     │ ← ReAct loop, MCP tools, persistence, etc.
│  (no ACP deps)  │
└─────────────────┘
```

### Minimal ACP Server (Proof of Concept)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json

class AgentInfo(BaseModel):
    name: str
    id: str
    description: str
    capabilities: list[str]

class Message(BaseModel):
    role: str
    content: str

class CreateSessionRequest(BaseModel):
    session_id: str | None = None
    initial_message: Message | None = None

app = FastAPI(title="Crow ACP Server")

# In-memory session storage (in production: replace with SQLite-backed persistence)
sessions: dict[str, list[Message]] = {}

@app.get("/agents")
async def list_agents() -> list[AgentInfo]:
    """List available agents and their capabilities"""
    return [
        AgentInfo(
            name="Crow",
            id="crow-ai",
            description="Lightweight, extensible AI coding agent with MCP support",
            capabilities=[
                "code_editing",
                "search",
                "shell_execution",
                "file_operations",
                "python_repl"
            ]
        )
    ]

@app.post("/sessions")
async def create_session(request: CreateSessionRequest) -> dict:
    """Create a new session or resume existing one"""
    session_id = request.session_id or f"session_{asyncio.get_event_loop().time()}"
    
    if session_id not in sessions:
        sessions[session_id] = []
    
    if request.initial_message:
        sessions[session_id].append(request.initial_message)
    
    return {
        "session_id": session_id,
        "status": "active"
    }

@app.post("/sessions/{session_id}/messages", response_class=StreamingResponse)
async def send_message(session_id: str, message: Message):
    """Send a message and stream the agent's response"""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    
    session = sessions[session_id]
    session.append(message)
    
    # Convert to internal format and process through core agent
    messages = [{"role": msg.role, "content": msg.content} for msg in session]
    
    async def response_generator():
        """Stream response from core agent"""
        # This calls your existing process_turn function
        # Need to adapt it to yield chunks as SSE or chunked HTTP
        async for chunk in process_turn_with_streaming(messages):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
    
    return StreamingResponse(response_generator(), media_type="text/event-stream")

@app.delete("/sessions/{session_id}/generation")
async def cancel_generation(session_id: str):
    """Cancel in-progress generation"""
    # Implement cancellation - need to track active generations per session
    # This requires hooking into the core agent's cancellation mechanism
    return {"status": "cancelled"}

@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> list[Message]:
    """Get session history for resumption"""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    
    return sessions[session_id]
```

### Adding ACP to Crow CLI

Keep the CLI minimal:

```python
# crow/cli.py
import click
import subprocess
import sys

@click.group()
def cli():
    """Crow AI - Lightweight, extensible coding agent"""
    pass

@cli.command()
@click.option('--session-id', '-s', help='Resume existing session')
@click.option('--message', '-m', help='Send message and close')
def start(session_id: str | None, message: str | None):
    """
    Start Crow ACP server.
    
    For interactive use, connect via ACP client (Toad, VSCode extension, etc.)
    """
    if message:
        # Non-interactive mode: send message and print response
        send_message_and_print(session_id, message)
    else:
        # Start ACP server
        click.echo("Starting Crow ACP server...")
        click.echo("Connect via: toad connect crow")
        # Start uvicorn/FastAPI server
        subprocess.run([sys.executable, "-m", "uvicorn", "crow.acp:app", "--host", "0.0.0.0", "--port", "8000"])

@cli.command()
@click.argument('session_id')
@click.argument('message')
def send(session_id: str, message: str):
    """Send message to existing session (non-interactive)"""
    send_message_and_print(session_id, message)

def send_message_and_print(session_id: str | None, message: str):
    """Send message via HTTP and print response"""
    import requests
    
    create_resp = requests.post(
        "http://localhost:8000/sessions",
        json={"session_id": session_id, "initial_message": {"role": "user", "content": message}}
    )
    session_id = create_resp.json()["session_id"]
    
    # Stream response
    with requests.post(
        f"http://localhost:8000/sessions/{session_id}/messages",
        json={"role": "user", "content": message},
        stream=True
    ) as resp:
        for line in resp.iter_lines():
            if line:
                data = json.loads(line[6:])  # Remove "data: " prefix
                print(data.get('content', ''), end='', flush=True)
        print()
```

### Submission to Toad Registry

Once ACP is implemented, Crow can be added to the Toad registry:

```yaml
# Metadata that would be registered
name: Crow
id: crow-ai
version: 0.1.0
description: Lightweight, extensible AI coding agent with MCP support
author: your-name
license: MIT
homepage: https://github.com/your-repo/crow

# ACP connection info
acp_servers:
  - type: http
    url: http://localhost:8000
    # or for stdio:
    # type: stdio
    # command: crow acp-stdio

capabilities:
  - code_editing
  - search
  - shell_execution
  - file_operations
  - python_repl
```

## Minimal CLI Philosophy

The Crow CLI should focus on:
- Starting the ACP server
- Connecting to existing sessions
- Simple non-interactive message sending

Interactive features (editing, history, etc.) should be handled by ACP clients like Toad.

## Testing ACP Integration

```python
import httpx
import asyncio

async def test_acp():
    """Test Crow ACP implementation"""
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        # List agents
        agents = (await client.get(f"{base_url}/agents")).json()
        assert "crow" in [a['id'] for a in agents]
        
        # Create session
        session_resp = await client.post(
            f"{base_url}/sessions",
            json={
                "initial_message": {
                    "role": "user",
                    "content": "Hello Crow!"
                }
            }
        )
        session_id = session_resp.json()["session_id"]
        
        # Stream response
        async with client.stream(
            "POST",
            f"{base_url}/sessions/{session_id}/messages",
            json={"role": "user", "content": "What's 2+2?"}
        ) as response:
            async for chunk in response.aiter_bytes():
                print(chunk.decode(), end='')
        print()
```

## Benefits

- **Zero UI maintenance**: Focus on agent logic
- **Multiple interfaces**: Users choose TUI, GUI, or CLI
- **Community compatibility**: Join ACP ecosystem
- **Future-proof**: New clients automatically work

## References

- Toad: https://github.com/batrachianai/toad
- ACP Spec: https://agentclientprotocol.com/
- ACP GitHub: https://github.com/agentclientprotocol/agent-client-protocol
