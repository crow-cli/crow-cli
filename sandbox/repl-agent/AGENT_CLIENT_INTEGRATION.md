# Agent Server Integration Plan

## Overview

A single ACP agent server that manages multiple child agents behind it, unifying their session/update streams into one coherent interface for upstream clients (Zed, Toad, any ACP-compatible editor).

---

## Problem Statement

| Constraint | Detail |
|------------|--------|
| Upstream expects | One ACP agent (single stdio endpoint) |
| We want | Multiple child agents running simultaneously |
| Each child agent | Has its own session, its own update stream, its own ReAct loop |
| The gap | No way to unify multiple agent streams into one upstream-facing agent |

**The question:** How do you present multiple agents as one?

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Upstream Client                           │
│              (Zed, Toad, VSCode, etc.)                       │
└─────────────────────────────────────────────────────────────┘
                           │ stdio (ACP)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent Server                              │
│                                                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  ACP Agent Interface (to upstream)                 │     │
│  │  • initialize()                                    │     │
│  │  • new_session() → spawns child agent              │     │
│  │  • prompt() → routes to child agent                │     │
│  │  • cancel() → forwards to child agent              │     │
│  └────────────────────────────────────────────────────┘     │
│                           │                                  │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Session Router                                    │     │
│  │  • upstream_session_id → (child_client, child_id) │     │
│  │  • update callback: child session_id → upstream    │     │
│  └────────────────────────────────────────────────────┘     │
│                           │                                  │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Agent Pool (manages child agents as Client)       │     │
│  │  • ReplClient instances (or similar)               │     │
│  │  • spawn_agent_process() per child                 │     │
│  │  • each child has its own session/update stream    │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
        ↕          ↕          ↕
   ┌────────┐ ┌────────┐ ┌────────┐
   │ Agent 1│ │ Agent 2│ │ Agent 3│
   │ crow-  │ │ crow-  │ │ other  │
   │ cli    │ │ cli    │ │ agent  │
   └────────┘ └────────┘ └────────┘
```

---

## Design

### The Agent Server

A hybrid that plays two roles:

| Role | To | Implements |
|------|----|----|
| **Agent** | Upstream | `initialize`, `new_session`, `prompt`, `cancel` |
| **Client** | Downstream | `session_update` callback, `request_permission`, `terminal/*`, `fs/*` |

```python
class AgentServer(Agent):
    """Single ACP agent that manages multiple child agents."""
    
    def __init__(self):
        self._upstream_conn: Client | None = None
        self._upstream_capabilities: ClientCapabilities | None = None
        self._session_map: dict[str, ChildSession] = {}
        self._agent_pool: AgentPool = AgentPool()
    
    def on_connect(self, conn: Client) -> None:
        self._upstream_conn = conn
    
    async def initialize(self, protocol_version, client_capabilities, client_info, **kwargs):
        self._upstream_capabilities = client_capabilities
        return InitializeResponse(protocol_version=protocol_version)
    
    async def new_session(self, cwd, mcp_servers, **kwargs):
        # Pick an available child agent from the pool
        child = await self._agent_pool.acquire(
            cwd=cwd,
            capabilities=self._upstream_capabilities,
        )
        
        # Create session on the child agent
        child_session = await child.conn.new_session(cwd=cwd, mcp_servers=mcp_servers)
        
        # Track the mapping
        session_id = child_session.session_id
        self._session_map[session_id] = ChildSession(
            client=child,
            session_id=session_id,
        )
        
        return NewSessionResponse(session_id=session_id)
    
    async def prompt(self, prompt, session_id, **kwargs):
        child = self._session_map[session_id].client
        response = await child.conn.prompt(session_id=session_id, prompt=prompt)
        return PromptResponse(stop_reason=response.stop_reason)
    
    async def cancel(self, session_id, **kwargs):
        child = self._session_map[session_id].client
        await child.conn.cancel(session_id=session_id)
```

### The Session Router

The core abstraction. Every upstream session maps to exactly one child agent:

```
upstream_session_id ──→ (child_client, child_session_id)
```

**Update forwarding:** When a child agent calls `session_update`, the callback receives the child's session_id. The router doesn't need to translate — session IDs pass through unchanged because the Agent Server creates the upstream session by delegating to the child, so they're the same ID.

**Client method forwarding:** When a child agent calls `terminal/create`, `fs/read_text_file`, etc., the Agent Server (acting as Client to the child) receives the call and forwards it to the upstream client. This is the same pattern as the existing `agent_client.py` — just without the WebSocket bridge.

### The Agent Pool

Manages the lifecycle of child agents:

```python
class AgentPool:
    """Manages a pool of child agents."""
    
    def __init__(self, agent_command="uvx crow-cli acp"):
        self._agent_command = agent_command
        self._active: list[ChildAgent] = []
        self._available: list[ChildAgent] = []
    
    async def acquire(self, cwd, capabilities) -> ChildAgent:
        if self._available:
            return self._available.pop()
        
        # Spawn a new child agent
        child = ChildAgent(
            command=self._agent_command,
            cwd=cwd,
            capabilities=capabilities,
            update_callback=self._forward_update,
        )
        await child.start()
        self._active.append(child)
        return child
    
    def release(self, child: ChildAgent):
        self._available.append(child)
```

### The Child Agent Wrapper

Each child agent is a ReplClient-like object:

```python
class ChildAgent:
    """Wraps a child agent spawned via spawn_agent_process."""
    
    def __init__(self, command, cwd, capabilities, update_callback):
        self._command = command
        self._cwd = cwd
        self._capabilities = capabilities
        self._update_callback = update_callback
        self._conn: Connection | None = None
        self._process = None
    
    async def start(self):
        """Spawn the child agent and initialize."""
        client = ChildClient(update_callback=self._update_callback)
        self._spawn_cm = spawn_agent_process(client, *self._command)
        self._conn, self._process = await self._spawn_cm.__aenter__()
        
        await self._conn.initialize(
            protocol_version=1,
            client_capabilities=self._capabilities,
            client_info=Implementation(
                name="agent-server",
                title="Agent Server",
                version="0.1.0",
            ),
        )
    
    async def stop(self):
        await self._spawn_cm.__aexit__(None, None, None)
```

### The Child Client

Acts as the ACP client for each child agent, forwarding updates upstream:

```python
class ChildClient(Client):
    """Client implementation for a child agent. Forwards updates to the parent."""
    
    def __init__(self, update_callback):
        self._update_callback = update_callback
    
    async def session_update(self, session_id, update, **kwargs):
        # Forward directly to upstream — session IDs are the same
        await self._update_callback(session_id, update)
    
    async def request_permission(self, options, session_id, tool_call, **kwargs):
        # Forward to upstream
        ...
    
    async def read_text_file(self, path, session_id, **kwargs):
        # Forward to upstream
        ...
    
    async def write_text_file(self, content, path, session_id, **kwargs):
        # Forward to upstream
        ...
```

---

## Routing Strategy

### Per-Session Routing (default)

Each upstream session maps to one child agent. Conversation stays coherent.

| Property | Value |
|----------|-------|
| Coherence | ✅ Full conversation context per agent |
| Parallelism | ✅ Multiple sessions → multiple agents |
| Complexity | ✅ Simple — one-to-one mapping |
| Use case | Standard coding sessions |

### Future: Spec-Driven Routing

Once the basic per-session model works, add routing logic:

| Scenario | Routing |
|----------|---------|
| User opens a spec file | Route to a "spec agent" that reads the spec and delegates |
| User asks for architecture review | Route to a "review agent" with different system prompt |
| User wants to explore multiple approaches | Spawn multiple agents, collect responses |

This is where the Agent Server becomes more than a passthrough — it becomes an orchestrator.

---

## Relationship to Existing Code

| File | Role | Fate |
|------|------|------|
| `sandbox/agent-client/agent_client.py` | WebSocket-bridged agent proxy | Reference for client method forwarding pattern |
| `sandbox/agent-client/stdio_to_ws.py` | stdio ↔ WebSocket bridge | Not needed — we're doing direct Python, no WebSocket |
| `sandbox/repl-agent/client.py` | ReplClient — programmatic ACP client | Template for ChildClient |
| `sandbox/repl-agent/main.py` | Spawns a single AcpAgent | Template for ChildAgent lifecycle |
| `crow-cli/src/crow_cli/agent/react.py` | The ReAct loop | Runs inside each child agent (crow-cli) |

The key difference from `agent_client.py`: no WebSocket, no subprocess bridge. The Agent Server spawns child agents directly via `spawn_agent_process` (the same mechanism ReplClient uses). The bridge is in-process, not over WebSocket.

---

## Implementation Phases

### Phase 1: Single Child Agent

Verify the Agent Server can manage one child agent end-to-end:

1. Agent Server spawns one child agent on `initialize`
2. `new_session` creates session on child
3. `prompt` forwards to child, returns child's response
4. `session_update` from child forwards to upstream
5. Client method calls (terminal, fs) forward child → upstream

### Phase 2: Agent Pool

Manage multiple child agents:

1. Pool spawns agents on demand
2. Session router maps upstream sessions to child agents
3. Cleanup on session end or agent exit

### Phase 3: Routing Logic

Add intelligence to session assignment:

1. Configurable routing strategy (round-robin, affinity, etc.)
2. Different agent configurations (different system prompts, different models)
3. Spec-driven routing (future)

---

## What This Enables

- **One endpoint, multiple agents** — upstream sees a single ACP agent
- **Parallel sessions** — each session gets its own child agent with full context
- **Agent heterogeneity** — different children can run different models, different system prompts
- **Orchestration foundation** — the routing layer is where spec-kit integration, task decomposition, and multi-agent collaboration happen
- **Zero protocol changes** — upstream talks standard ACP, child agents talk standard ACP. The server just bridges them.
