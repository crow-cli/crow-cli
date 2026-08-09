# Crow-CLI Architecture: A Comprehensive Understanding

This document is not a runbook. It's a mental model - the "why" behind the code.

## What This Thing IS

Crow-CLI is an **ACP-native coding agent**. It speaks the Agent Client Protocol (ACP) directly - no wrappers, no adapters. You point a client like Zed at it, and it becomes your coding assistant.

The key insight: **the config directory IS the state**. Everything flows from `~/.crow/` (or wherever you point it):
- `config.yaml` - providers, models, MCP servers
- `.env` - API keys (interpolated into config)
- `prompts/` - Jinja2 templates for system prompts
- `logs/` - rotating file logs (NEVER stdout - that's protocol!)
- `crow.db` - SQLite for session/message persistence

```
~/.crow/
├── config.yaml      # The "DNA" of the agent
├── .env             # Secrets
├── prompts/
│   └── system_prompt.jinja2
├── logs/
│   └── crow-cli.log
└── crow.db          # Sessions, messages, prompts
```

## The Core Abstractions

### 1. Config (configure.py)

A dataclass loaded from YAML. The single source of truth for:
- LLM providers (OpenAI-compatible APIs)
- Model definitions (which provider, which model ID)
- MCP server configurations
- Behavior constants (max tokens, tool names, etc.)

**Why it matters**: The config_dir is passed into the Agent at construction time. This means you can have multiple agents with different configs - not a singleton, not a global.

### 2. AcpAgent (main.py)

The single agent class. It:
- **Implements the ACP Agent protocol** - `initialize`, `new_session`, `load_session`, `prompt`, `cancel`
- **Owns the AsyncExitStack** - manages MCP client lifecycles
- **Holds in-memory state** - sessions, MCP clients, cancel events
- **Receives MCP servers from the client** - at runtime, not config time

The agent is NOT a wrapper around something else. It IS the thing.

**Key constraint**: Cannot log to stdout. Stdout is the ACP JSON-RPC channel. One `print()` and you've corrupted the protocol. All logging goes to file via `setup_logger()`.

### 3. Session (session.py)

The persistence layer. One session = one conversation.

```
Session Model (database):
- session_id (PK)
- prompt_id (FK to Prompt)
- prompt_args (JSON)
- system_prompt (rendered text)
- tool_definitions (JSON)
- request_params (JSON)
- model_identifier

Messages (database):
- id (PK)
- session_id (FK)
- data (JSON - the full message dict)
- role (for querying)
```

**The key insight**: One row = one message. No normalization gymnastics. Just serialize the message dict, deserialize it back. The Session Python object loads messages into `self.messages: list[dict]` and the LLM consumes that directly.

### 4. MCP Client (mcp_client.py)

The tool layer. MCP servers provide tools (read, write, terminal, search, etc.).

The ACP protocol lets clients pass MCP server configs at session creation. `create_mcp_client_from_acp()` converts ACP's typed configs to FastMCP's dict format.

**Two sources of MCP servers**:
1. From ACP client (passed in `new_session`/`load_session`)
2. Fallback from config.yaml's `mcpServers`

The client is entered into the Agent's `AsyncExitStack` so it gets cleaned up properly.

### 5. ReAct Loop (react.py)

The thinking layer. The core loop:

```
1. Send messages to LLM (streaming)
2. Yield chunks: thinking, content, tool_call
3. Accumulate tool calls
4. Execute tools (via MCP or ACP client)
5. Add assistant message + tool results to session
6. Repeat until no more tool calls
```

**Cancellation**: The loop checks `cancel_event` at multiple points. On `CancelledError`, partial state is persisted via `state_accumulator` so you don't lose work.

**Compaction**: When `total_tokens > MAX_COMPACT_TOKENS`, the middle of the conversation is summarized and replaced. The session ID is preserved via an atomic swap (old -> archive, compacted -> old_id).

### 6. Tools (tools.py)

The action layer. Two execution paths:

1. **ACP-native tools** - when client supports it:
   - `terminal` → `conn.create_terminal()`, `conn.wait_for_terminal_exit()`
   - `write` → `conn.write_text_file()`
   - `read` → `conn.read_text_file()`

2. **MCP tools** - fallback:
   - `mcp_client.call_tool(name, args)`

Each tool sends ACP `ToolCallStart` and `ToolCallProgress` updates so the client can show live status.

## The Flow of a Prompt

```
User types in Zed
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  ACP Protocol (JSON-RPC over stdin/stdout)              │
│  {"method": "prompt", "params": {...}}                  │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  AcpAgent.prompt()                                      │
│  - Extract text from content blocks                     │
│  - Add user message to session                          │
│  - Create asyncio.Task for _execute_turn()              │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  react_loop()                                           │
│  - Send session.messages to LLM (streaming)             │
│  - Yield thinking/content chunks back to prompt()       │
│  - Accumulate tool calls                                │
│  - Execute tools (ACP or MCP)                           │
│  - Add assistant response + tool results                │
│  - Check for compaction threshold                       │
│  - Repeat until no tool calls                           │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  PromptResponse(stop_reason="end_turn")                 │
│  Sent back via ACP                                      │
└─────────────────────────────────────────────────────────┘
       │
       ▼
Zed displays the response
```

## The Constraints

### 1. Stdout is SACRED

The ACP protocol runs over stdin/stdout as JSON-RPC. Every byte matters.

```python
# ❌ NEVER DO THIS
print("debugging...")
logging.info("here!!!")

# ✅ DO THIS INSTEAD
self._logger.info("debugging...")  # Goes to file
```

This is why debugging is hard. You can't just sprinkle prints. You need a proper external client (like Zed) to see what's actually happening.

### 2. Explicit State, No Magic

No singletons. No globals. No `contextvars` (yet). Everything is passed explicitly:

```python
async def react_loop(
    conn: Client,
    config: Config,
    client_capabilities: ClientCapabilities,
    turn_id: str,
    mcp_clients: dict[str, MCPClient],
    llm: AsyncOpenAI,
    tools: list[dict],
    sessions: dict[str, Session],
    cancel_event: Event,
    session_id: str,
    state_accumulators: dict[str, dict],
    max_turns: int = 50000,
    on_compact: callable = None,
    logger: Logger = None,
):
```

That's 12 parameters. It's verbose but honest. You can trace where everything comes from.

### 3. Resource Lifecycle via AsyncExitStack

MCP clients need to be cleaned up. The Agent owns an `AsyncExitStack`:

```python
mcp_client = await self._exit_stack.enter_async_context(mcp_client)
```

When the agent's `cleanup()` is called, everything gets torn down in reverse order.

## The Pain Points (and why they exist)

### 1. Parameter Explosion

Every function needs `conn`, `config`, `logger`, `session_id`, etc. The "function tax."

**Why**: The alternative is either:
- Singletons/globals (can't have multiple configs)
- OOP with everything on `self` (different headaches)
- Context variables (implicit, hard to understand)

Explicit is chosen over implicit. The handshakes are a feature, not a bug.

### 2. Debugging Without Visibility

When something breaks, you can't see the error because the client hides it.

**Solution**: Build a debug client. A simple JSON-RPC sender that shows raw responses. Like Zed, but for the terminal.

### 3. Compaction Complexity

The compaction logic does an atomic session ID swap:
- old session → archived
- compacted session → takes over old ID

This preserves continuity but requires careful state management. The `Session.update_from()` method is key - it updates the Python object in-place so all references see the new state.

## The Mental Model

Think of it as concentric circles:

```
┌─────────────────────────────────────────────────────────┐
│  ACP Protocol Layer                                     │
│  - JSON-RPC over stdin/stdout                           │
│  - initialize, new_session, prompt, cancel              │
└─────────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────┐
  │  Agent Layer (AcpAgent)                             │
  │  - Protocol implementation                          │
  │  - Resource management (AsyncExitStack)             │
  │  - In-memory state (sessions, clients, events)      │
  └─────────────────────────────────────────────────────┘
    ┌───────────────────────────────────────────────────┐
    │  ReAct Loop Layer (react.py)                     │
    │  - Streaming LLM calls                           │
    │  - Tool execution orchestration                  │
    │  - Cancellation handling                         │
    └───────────────────────────────────────────────────┘
      ┌─────────────────────────────────────────────────┐
      │  Tool Layer (tools.py)                         │
      │  - ACP-native: terminal, read, write           │
      │  - MCP fallback: search, fetch, etc.           │
      └─────────────────────────────────────────────────┘
        ┌───────────────────────────────────────────────┐
        │  Persistence Layer (session.py, db.py)       │
        │  - Session metadata                          │
        │  - Message history (one row = one message)   │
        │  - Prompt templates                          │
        └───────────────────────────────────────────────┘
```

Each layer depends on the layers below it, but not above. The Agent doesn't know about the ReAct loop's internals. The ReAct loop doesn't know about the protocol.

## Why This Architecture?

1. **Single Agent class** - No wrappers, no nesting. The ACP protocol IS the interface.

2. **Config as state root** - Everything flows from config_dir. Multiple configs = multiple agents.

3. **Explicit over implicit** - Verbose signatures, but you always know where things come from.

4. **File logging only** - Stdout is for protocol. Debugging requires external visibility.

5. **One row = one message** - No normalization headaches. Just serialize/deserialize.

6. **ACP when possible, MCP as fallback** - Use the client's native capabilities when available.

This is a scientist's architecture. Not the cleanest OOP, but honest. The seams are visible. The data flows are traceable. It does the job.
