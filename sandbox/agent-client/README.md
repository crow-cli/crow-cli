# Agent-Client: ACP Bridge Architecture

## What We're Building

An **agent-client** that bridges between:

```
┌─────────────────────────────────────────────────────────┐
│  Upstream Client (Zed, VSCode, etc.)                    │
│  ↔ stdio (ACP protocol)                                 │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  Agent-Client (This Project)                            │
│  • Implements ACP Agent interface (for upstream)        │
│  • Connects to child agents via WebSocket (downstream)  │
│  • Forwards all ACP calls bidirectionally               │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  stdio-to-ws Bridge                                     │
│  ↔ WebSocket (to agent-client)                          │
│  ↔ stdio (to child agent)                               │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  Child Agent (echo_agent.py, crow-cli, etc.)            │
│  ↔ stdio (ACP protocol)                                 │
└─────────────────────────────────────────────────────────┘
```

## Why This Architecture?

### The Problem

ACP uses **stdio** for agent communication. This creates a constraint:
- Upstream clients (Zed, VSCode) expect to spawn an agent and talk via stdio
- Child agents also speak stdio
- **But you can't nest stdio-based agents directly**

### The Solution

Reserve stdio for upstream communication, use WebSocket for downstream:

```
stdio  → upstream (Zed ↔ agent-client)
WebSocket → downstream (agent-client ↔ child agents)
```

## What is an ACP Agent?

From the [ACP spec](https://agentclientprotocol.com/protocol/overview):

> Agents are programs that use generative AI to autonomously modify code. They typically run as subprocesses of the Client.

### Agent Responsibilities

**Required Methods:**
- `initialize` - Negotiate protocol version and capabilities
- `session/new` - Create a new conversation session
- `session/prompt` - Process user prompts, execute tools, return results

**Optional Methods:**
- `authenticate` - Handle authentication if required
- `session/load` - Resume existing sessions (if `loadSession` capability)
- `session/set_mode` - Switch between modes (deprecated)
- `session/set_config_option` - Update session configuration

**Notifications:**
- `session/update` - Send streaming updates to client (tool calls, messages, etc.)

### What Agents DON'T Do

Agents do **NOT** implement:
- File system operations (`fs/read_text_file`, `fs/write_text_file`) - these are **client** methods
- Terminal operations (`terminal/create`, `terminal/output`) - these are **client** methods
- Permission requests (`session/request_permission`) - this is a **client** method

Agents **call** these methods on the client, they don't implement them.

## What is an ACP Client?

From the spec:

> Clients provide the interface between users and agents. They are typically code editors (IDEs, text editors) but can also be other UIs for interacting with agents. Clients manage the environment, handle user interactions, and control access to resources.

### Client Responsibilities

**Required Methods:**
- `session/request_permission` - Ask user for permission to run tools

**Optional Methods (capabilities):**
- `fs/read_text_file` - Read files on behalf of agent (if `fs.readTextFile` capability)
- `fs/write_text_file` - Write files on behalf of agent (if `fs.writeTextFile` capability)
- `terminal/create` - Create terminal sessions (if `terminal` capability)
- `terminal/output`, `terminal/kill`, etc. - Terminal control

**Notifications:**
- Receive `session/update` from agents

## The Agent-Client Pattern

Our **agent-client** is a **hybrid**:

1. **To upstream (Zed):** Acts as an **Agent**
   - Implements `initialize`, `session/new`, `session/prompt`, etc.
   - Sends `session/update` notifications
   
2. **To downstream (child agents):** Acts as a **Client**
   - Calls agent methods (`initialize`, `session/new`, `session/prompt`)
   - Receives `session/update` notifications
   - Optionally provides client capabilities (fs, terminal)

3. **Core Function:** **Forwarding**
   - Forward agent method calls upstream → downstream
   - Forward session updates downstream → upstream
   - **No business logic** (initially)
   - **No ReAct loop** (child agent handles that)

## Status: ✅ WORKING!

The agent-client is fully functional and tested:

```bash
cd /home/thomas/src/backup/crow-spec/nid/sandbox/agent-client
uv --project . run test_agent_client.py
```

**Test results:**
```
✓ Initialized
✓ Session created: ac17e365a7ed4b899d845c718f939823
  UPDATE: session_update='agent_message_chunk'
✓ Response: stop_reason='end_turn'
✓ All tests passed!
```

## What We've Built So Far

### ✅ echo_agent.py

Simple ACP agent that echoes messages. Used for testing.

```python
class EchoAgent(Agent):
    async def prompt(self, prompt, session_id):
        for block in prompt:
            text = block.get("text", "")
            await self._conn.session_update(
                session_id,
                update_agent_message(text_block(text))
            )
        return PromptResponse(stop_reason="end_turn")
```

### ✅ stdio_to_ws.py

Bridge between stdio (ACP agent) and WebSocket.

```
WebSocket client ↔ stdio_to_ws.py ↔ ACP agent (stdio)
```

**Key features:**
- Spawns ACP agent subprocess
- Bridges WebSocket ↔ stdio bidirectionally
- Logs to file (not stdio!)
- Handles line-based JSON-RPC messages

### ✅ test_simple.py

Proves the bridge works end-to-end.

```
test_simple.py → WebSocket → stdio_to_ws.py → echo_agent.py
```

**Test results:**
```
✓ initialize → protocolVersion: 1
✓ session/new → sessionId: "..."
  Notification: session/update
✓ session/prompt → stopReason: "end_turn"
✓ All tests passed!
```

### ✅ agent_client.py

The actual agent-client that bridges ACP clients (like Zed) to child agents.

```
Zed → agent_client.py → WebSocket → stdio_to_ws.py → echo_agent.py
```

**Key features:**
- Implements ACP Agent interface for upstream clients
- Spawns bridge + child agent on initialization
- Forwards all ACP calls (initialize, session/new, session/prompt)
- Forwards session/update notifications bidirectionally
- Handles Pydantic model serialization
- Logs to file (not stdio!)

### ✅ test_agent_client.py

End-to-end test of the full stack.

```bash
uv --project . run test_agent_client.py
```

**Proves:**
- Agent-client accepts ACP connections via stdio
- Bridge spawns child agent successfully
- WebSocket connection established
- All ACP calls forwarded correctly
- Session updates flow upstream

## Future Enhancements

Now that the basic bridge works, we can add:

1. **Session management** - Track parent/child session relationships
2. **Multiple child agents** - Spawn different agents for different tasks
3. **Orchestration logic** - Spec Kit integration, task routing
4. **Telemetry** - Log all traffic for debugging/analytics
5. **Compaction coordination** - Handle context compaction across sessions

## Testing

### Test 1: Bridge + Echo Agent
```bash
uv --project . run test_simple.py
```

### Test 2: Agent-Client (once implemented)
```bash
# Terminal 1: Run agent-client
uv --project . run agent_client.py

# Terminal 2: Test with Zed or mock client
# (Zed will spawn agent_client.py as subprocess)
```

## References

- [ACP Protocol Overview](https://agentclientprotocol.com/protocol/overview)
- [ACP Schema Reference](https://agentclientprotocol.com/protocol/schema)
- [Session Setup](https://agentclientprotocol.com/protocol/session-setup)
- [Prompt Turn Lifecycle](https://agentclientprotocol.com/protocol/prompt-turn)

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    Upstream Client                        │
│                  (Zed, VSCode, etc.)                      │
└──────────────────────────────────────────────────────────┘
                        │ stdio (ACP)
                        ↓
┌──────────────────────────────────────────────────────────┐
│                    Agent-Client                           │
│                                                          │
│  ┌────────────────────────────────────────────────┐     │
│  │  ACP Agent Interface (upstream)                │     │
│  │  • initialize()                                │     │
│  │  • new_session()                               │     │
│  │  • prompt()                                    │     │
│  │  • cancel()                                    │     │
│  └────────────────────────────────────────────────┘     │
│                      ↓ forwarding                        │
│  ┌────────────────────────────────────────────────┐     │
│  │  WebSocket Client (downstream)                 │     │
│  │  • connect()                                   │     │
│  │  • send_request()                              │     │
│  │  • recv_updates() → forward upstream           │     │
│  └────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────┘
                        │ WebSocket
                        ↓
┌──────────────────────────────────────────────────────────┐
│                stdio-to-ws Bridge                         │
│  ↔ WebSocket (to agent-client)                           │
│  ↔ stdio (to child agent)                                │
└──────────────────────────────────────────────────────────┘
                        │ stdio (ACP)
                        ↓
┌──────────────────────────────────────────────────────────┐
│                    Child Agent                            │
│           (echo_agent.py, crow-cli, etc.)                │
│                                                          │
│  • Real ReAct loop                                       │
│  • Tool execution                                        │
│  • LLM integration                                       │
│  • Session persistence                                   │
└──────────────────────────────────────────────────────────┘
```

## Summary

The agent-client is a **protocol bridge** that:

1. **Speaks ACP Agent protocol** to upstream clients (Zed)
2. **Speaks ACP Agent protocol** to downstream agents (via WebSocket bridge)
3. **Forwards all calls** bidirectionally
4. **Adds value later** with orchestration, telemetry, session management

The key insight: **stdio is reserved for upstream, WebSocket handles downstream**.

This allows us to nest ACP agents without stdio conflicts, enabling powerful orchestration patterns while maintaining protocol compatibility.
