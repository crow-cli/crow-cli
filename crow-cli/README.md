# `crow-cli`

`crow-cli` is an [Agent Client Protocol (ACP)](https://agentclientprotocol.com/) native agent implementation that serves as the core execution engine for the Crow agent framework.

## System Requirements

| Platform | Requirements |
|----------|-------------|
| **Linux** | glibc 2.35+ (Ubuntu 22.04+, Debian 12+, or equivalent) |
| **macOS** | macOS 13+ (Ventura) - Intel & Apple Silicon |
| **Windows** | Windows 10+ (64-bit) |

**Note:** Linux binaries are built on Ubuntu 22.04 for maximum compatibility. If you're on an older distribution (Ubuntu 20.04, Debian 11, etc.), you'll need to build from source.

## Installation

```bash
# Ensure you're in the correct project directory
git clone https://github.com/crow-cli/crow-cli.git
uv venv
# Install dependencies using uv
uv --project /path/to/crow/crow-cli sync
```

Or run directly:
```bash
uvx crow-cli --help
```

If you like having it available globally, you can install it using pip:
```bash
uv tool install crow-cli --python 3.14
```

## Quick Start

```bash
uvx crow-cli init
```

### Run Programmatically

```python
import asyncio
from crow_cli.agent.main import agent_run

async def main():
    await agent_run()

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

Configuration lives in `~/.crow/config.yaml`. See the configuration section below for details.

## Features

### 1. ACP Protocol Native
- Implements all ACP agent endpoints (`initialize`, `new_session`, `load_session`, `prompt`, `cancel`)
- Full streaming support for token-by-token responses
- Session persistence to SQLite database

### 2. MCP Tool Integration
- Automatically discovers tools from connected MCP servers
- Supports both MCP and ACP-native tool execution
- Tool execution with progress updates

### 3. Streaming ReAct Loop
- Real-time streaming of thinking tokens (for reasoning models)
- Content token streaming
- Tool call progress updates (pending → in_progress → completed/failed)

### 4. Cancellation Support
- **Task-based cancellation**: Uses `asyncio.Task.cancel()` to immediately interrupt the LLM stream
- **State accumulator**: Preserves partial thinking/content on cancellation
- **Safe history**: Never persists tool calls on cancellation (avoids breaking conversation history)
- **Clean propagation**: `CancelledError` propagates through the entire async stack

### 5. ACP Terminal Support
When the ACP client supports terminals (`clientCapabilities.terminal: true`):
- Uses ACP-native terminals instead of MCP terminal calls
- Better terminal display in the client
- Live output streaming
- Proper terminal lifecycle management

### 6. JSON Repair for Tool Calls
- Automatically validates and repairs malformed JSON in tool call arguments
- Critical for models like `qwen3.5-plus` that may produce incomplete JSON during streaming
- Falls back to empty object `{}` if repair fails
- Prevents poisoned conversation history from breaking future API calls

## Built-in Tools

The agent automatically discovers and registers tools from connected MCP servers:

- `crow-mcp_terminal` - Execute shell commands in the workspace
- `crow-mcp_write` - Write content to files
- `crow-mcp_read` - Read files with line numbers
- `crow-mcp_edit` - Fuzzy string replacement in files
- `crow-mcp_web_search` - Search the web using a search engine
- `crow-mcp_web_fetch` - Fetch URL content as markdown

## Architecture

### High-Level Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           CROW-CLI ARCHITECTURE                           │
└──────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   client/       │  ───→   │   agent/        │  ───→   │   agent/        │
│   main.py       │         │   main.py       │         │   react.py      │
│                 │         │                 │         │                 │
│ CrowClient      │         │ AcpAgent        │         │ react_loop()    │
│ .prompt()       │         │ .prompt()       │         │                 │
│                 │         │                 │         │ 6 methods:      │
│                 │         │ ┌─────────────┐ │         │ • send_request  │
│                 │         │ │_prompt_tasks│ │         │ • process_chunk │
│                 │         │ │_cancel_events││         │ • process_tool..│
│                 │         │ │_state_accum..││         │ • process_resp..│
│                 │         │ └─────────────┘ │         │ • execute_tools │
│                 │         │                 │         │ • react_loop    │
└─────────────────┘         └─────────────────┘         └─────────────────┘
       │                           │                           │
       │  ACP Protocol             │  asyncio.Task             │
       │  (session_update)         │  cancellation             │
       │                           │                           │
       ▼                           ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         STREAMING FLOW                                   │
│                                                                          │
│  LLM Stream → process_chunk() → yield chunks → session_update() → UI    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### The ReAct Loop - 6 Methods

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        REACT_LOOP() - THE ORCHESTRATOR                   │
│                                                                          │
│  for turn in range(max_turns):                                          │
│      ┌─────────────────────────────────────────────────────────────┐    │
│      │  1. send_request()                                          │    │
│      │     - POST to LLM API                                       │    │
│      │     - Retry logic (exponential backoff)                     │    │
│      │     - Returns: async stream generator                       │    │
│      └─────────────────────────────────────────────────────────────┘    │
│                          │                                               │
│                          ▼                                               │
│      ┌─────────────────────────────────────────────────────────────┐    │
│      │  2. process_response()                                      │    │
│      │     - Iterates over stream                                  │    │
│      │     - Calls process_chunk() for each chunk                  │    │
│      │     - Yields: (msg_type, token)                             │    │
│      │                                                             │    │
│      │     ┌───────────────────────────────────────────────────┐   │    │
│      │     │  2a. process_chunk()                              │   │    │
│      │     │     - Parse delta from chunk                      │   │    │
│      │     │     - Accumulate: thinking, content, tool_calls   │   │    │
│      │     │     - Return: new_token for yielding              │   │    │
│      │     └───────────────────────────────────────────────────┘   │    │
│      │                                                             │    │
│      │     ┌───────────────────────────────────────────────────┐   │    │
│      │     │  2b. process_tool_call_inputs()                   │   │    │
│      │     │     - Called at end of stream                     │   │    │
│      │     │     - Validate JSON arguments                     │   │    │
│      │     │     - Repair malformed JSON (qwen3.5-plus fix)    │   │    │
│      │     │     - Return: list[tool_call dicts]               │   │    │
│      │     └───────────────────────────────────────────────────┘   │    │
│      └─────────────────────────────────────────────────────────────┘    │
│                          │                                               │
│                          ▼                                               │
│      ┌─────────────────────────────────────────────────────────────┐    │
│      │  3. execute_tool_calls()                                    │    │
│      │     - Route to: ACP terminal / MCP tools                    │    │
│      │     - Execute: read, write, edit, terminal, custom          │    │
│      │     - Return: list[tool_results]                            │    │
│      └─────────────────────────────────────────────────────────────┘    │
│                          │                                               │
│                          ▼                                               │
│      ┌─────────────────────────────────────────────────────────────┐    │
│      │  4. session.add_assistant_response()                        │    │
│      │     - Persist: thinking + content + tool_calls              │    │
│      │                                                             │    │
│      │  5. session.add_tool_response()                             │    │
│      │     - Persist: tool_results                                 │    │
│      └─────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Repeat until: no tool_calls → yield final_history → return             │
└──────────────────────────────────────────────────────────────────────────┘
```

### Method Responsibilities

| Method | Purpose |
|--------|---------|
| `send_request()` | HTTP to LLM with retry logic (exponential backoff) |
| `process_chunk()` | Parse single streaming delta from LLM |
| `process_tool_call_inputs()` | Validate/repair tool call JSON arguments |
| `process_response()` | Orchestrate full stream, yield chunks |
| `execute_tool_calls()` | Route & execute tools via MCP/ACP |
| `react_loop()` | Main loop, ties it all together |

## Cancellation System

### Evolution: Old vs New

**OLD APPROACH** ❌ - Scattered cancel event checks:
```python
async def react_loop(..., cancel_event: asyncio.Event):
    for turn in range(max_turns):
        response = await send_request(...)
        async for chunk in response:
            if cancel_event.is_set():  # Check here
                break
            yield chunk
        
        # Check again after tool execution
        if cancel_event.is_set():  # Check here too
            break
```

**Problems:**
- Checks scattered everywhere (easy to miss one)
- Doesn't actually interrupt the LLM stream
- Race conditions between checks

**NEW APPROACH** ✅ - Task-based cancellation:
```python
# In agent/main.py - AcpAgent.prompt()
async def _execute_turn():
    async for chunk in react_loop(...):
        await self._conn.session_update(...)

task = asyncio.create_task(_execute_turn())
self._prompt_tasks[session_id] = task

try:
    return await task
except asyncio.CancelledError:
    return PromptResponse(stop_reason="cancelled")

# In agent/main.py - AcpAgent.cancel()
async def cancel(session_id: str):
    task = self._prompt_tasks.get(session_id)
    if task and not task.done():
        task.cancel()  # Forcefully interrupts LLM stream!
```

**Benefits:**
- Single cancellation point (`task.cancel()`)
- Actually interrupts the LLM stream (asyncio magic)
- No scattered checks to miss
- Clean exception propagation
- State accumulator preserves partial progress

### Cancellation Sequence

```
User          Client           AcpAgent           react_loop          LLM
  │              │                  │                   │               │
  │  [Ctrl+C]    │                  │                   │               │
  │─────────────>│                  │                   │               │
  │              │                  │                   │               │
  │              │  cancel()        │                   │               │
  │              │─────────────────>│                   │               │
  │              │                  │                   │               │
  │              │                  │  task.cancel()    │               │
  │              │                  │──────────────────>│               │
  │              │                  │                   │               │
  │              │                  │                   │  CancelledError
  │              │                  │                   │<──────────────
  │              │                  │                   │               │
  │              │                  │                   │  # Don't persist
  │              │                  │                   │  # tool calls!
  │              │                  │                   │  session.add_..
  │              │                  │                   │  (empty tools)
  │              │                  │                   │               │
  │              │                  │  CancelledError   │               │
  │              │                  │<──────────────────│               │
  │              │                  │                   │               │
  │              │  PromptResponse  │                   │               │
  │              │  (cancelled)     │                   │               │
  │              │<─────────────────│                   │               │
  │              │                  │                   │               │
  │  "Cancelled" │                  │                   │               │
  │<─────────────│                  │                   │               │
```

### Key Cancellation Insights

1. **`asyncio.Task.cancel()`** is like yanking the power cord - it sends `CancelledError` through the entire async stack at the exact point where it's blocked waiting for I/O.

2. **State accumulator** preserves partial `thinking`/`content` so we can persist something even when cancelled mid-stream.

3. **NEVER persist tool calls on cancellation** - Tools weren't executed, so no tool responses exist in history. Next API call would fail with: *"An assistant message with tool_calls must be followed by tool messages responding to each tool_call_id"*

4. **`CancelledError` propagates up** through the entire async call stack, interrupting at every level.

## State Accumulator Pattern

Purpose: Preserve partial progress when cancellation hits mid-stream.

```python
# In AcpAgent.__init__()
self._state_accumulators: dict[str, dict] = {}
# session_id → {"thinking": [], "content": [], "tool_calls": {}}

# In AcpAgent.prompt()
self._state_accumulators[session_id] = {
    "thinking": [],
    "content": [],
    "tool_calls": {},
}

# In process_response()
state_accumulator.update({
    "thinking": thinking,
    "content": content,
    "tool_calls": tool_calls,
})

async for chunk in response:
    thinking, content, tool_calls, new_token = process_chunk(...)
    state_accumulator["thinking"] = thinking  # Update
    state_accumulator["content"] = content    # Update
    state_accumulator["tool_calls"] = tool_calls  # Update

# In react_loop() cancellation handler
except asyncio.CancelledError:
    # state_accumulator has partial progress!
    session.add_assistant_response(
        state_accumulator["thinking"],  # What we got
        state_accumulator["content"],   # What we got
        [],  # NEVER tool calls!
    )
```

## Tool Calling Stream Flow

```
LLM Response Stream:
┌─────────────────────────────────────────────────────────────────────────┐
│  Chunk 1: {"delta": {"content": "Let me"}}                             │
│  Chunk 2: {"delta": {"content": " check that"}}                        │
│  Chunk 3: {"delta": {"tool_calls": [{"index": 0,                       │
│               "function": {"name": "read"}}]}}                         │
│  Chunk 4: {"delta": {"tool_calls": [{"index": 0,                       │
│               "function": {"arguments": "{\"path\":"}}]}}              │
│  Chunk 5: {"delta": {"tool_calls": [{"index": 0,                       │
│               "function": {"arguments": " \"/tmp/test.txt\"}"}}]}}     │
│  Chunk 6: {"delta": {}, "usage": {...}}  ← END                         │
└─────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
process_chunk() accumulates:
┌─────────────────────────────────────────────────────────────────────────┐
│  content = ["Let me", " check that"]                                    │
│  tool_calls = {                                                         │
│      0: {                                                               │
│          "id": "call_abc123",                                           │
│          "function_name": "read",                                       │
│          "arguments": ["{\"path\":", " \"/tmp/test.txt\"}"]            │
│      }                                                                  │
│  }                                                                      │
└─────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
process_tool_call_inputs() validates/repairs:
┌─────────────────────────────────────────────────────────────────────────┐
│  arguments_str = "".join(tool_calls[0]["arguments"])                    │
│              = "{\"path\": \"/tmp/test.txt\"}"                          │
│                                                                         │
│  try:                                                                   │
│      json.loads(arguments_str)  # VALID!                                │
│  except:                                                                │
│      # Repair logic for qwen3.5-plus                                    │
│      # (add missing braces, fallback to {})                             │
│                                                                         │
│  tool_call_inputs = [{                                                  │
│      "id": "call_abc123",                                               │
│      "type": "function",                                                │
│      "function": {                                                      │
│          "name": "read",                                                │
│          "arguments": "{\"path\": \"/tmp/test.txt\"}"                  │
│      }                                                                  │
│  }]                                                                     │
└─────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
execute_tool_calls() routes and executes:
┌─────────────────────────────────────────────────────────────────────────┐
│  if tool_name == "read" and use_acp_read:                               │
│      result = execute_acp_read(...)                                     │
│  elif tool_name == "edit":                                              │
│      result = execute_acp_edit(...)                                     │
│  else:                                                                  │
│      result = execute_acp_tool(...)  # MCP fallback                     │
│                                                                         │
│  tool_results = [{                                                      │
│      "role": "tool",                                                    │
│      "tool_call_id": "call_abc123",                                     │
│      "content": "file contents here..."                                 │
│  }]                                                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

## Session Management

### Creating a New Session

```python
# When connecting via ACP, a new session is created automatically
# with the working directory and MCP servers provided by the client
```

### Loading an Existing Session

```python
# Sessions persist to the database and can be loaded by ID
# The load_session endpoint handles this automatically
```

### Session Data Storage

Sessions are stored in SQLite with three main tables:

- **Prompt** - System prompt templates (Jinja2)
- **Session** - Session metadata (config, tools, model, cwd)
- **Message** - Conversation messages (one row = one message, JSON-serialized)

## Usage with ACP Clients

`crow-cli` is designed to work with any ACP-compatible client:

```json
// In Zed
{
  "agent_servers": {
    "crow-cli": {
      "type": "custom",
      "command": "uvx",
      "args": ["crow-cli", "acp"]
    }
  }
}
```

### ACP Client Capabilities

The agent automatically detects and uses client capabilities:

| Capability | When Enabled | Behavior |
|------------|--------------|----------|
| `terminal` | Client supports ACP terminals | Uses ACP-native terminals |
| `fs.write_text_file` | Client supports file writing | Uses ACP file write |
| `fs.read_text_file` | Client supports file reading | Uses ACP file read |

## Project Structure

```
crow-cli/
├── src/crow_cli/
│   ├── __init__.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── compact.py        # Conversation compaction
│   │   ├── configure.py      # Agent configuration
│   │   ├── context.py        # Context providers (directory tree, file fetching)
│   │   ├── db.py             # SQLAlchemy database models
│   │   ├── llm.py            # LLM client configuration
│   │   ├── logger.py         # Logging utilities
│   │   ├── main.py           # Agent entry point (AcpAgent class)
│   │   ├── mcp_client.py     # MCP client creation + tool extraction
│   │   ├── prompt.py         # Prompt building
│   │   ├── react.py          # ReAct loop implementation (6 methods)
│   │   ├── session.py        # Session management + persistence
│   │   ├── tools.py          # Tool execution functions
│   │   └── prompts/          # Jinja2 system prompt templates
│   │       └── system_prompt.jinja2
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── init_cmd.py       # `crow init` command
│   │   └── main.py           # CLI entry point
│   └── client/
│       ├── __init__.py
│       └── main.py           # Programmatic client (CrowClient)
├── config/
│   ├── compose.yaml          # Docker compose for services
│   ├── config.yaml           # Default configuration
│   ├── .env.example          # Environment variables template
│   ├── searxng/
│   │   └── settings.yml      # SearXNG search config
│   └── prompts/              # Override prompts (user customization)
│       └── system_prompt.jinja2
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_agent_init.py
│   └── unit/
│       └── test_session.py
├── examples/
│   ├── mc_escher_loop.py
│   └── quick_test.py
├── pyproject.toml
├── README.md
├── TODO.md
└── run_tests.sh
```

## Development

### Running Tests

```bash
# From the project root
uv run --project /path/to/crow-cli pytest crow-cli/tests/
```

### Building

```bash
# Build the package
uv build --project /path/to/crow-cli

# Install locally
pip install --force-reinstall ./crow-cli/dist/*.whl
```

## Troubleshooting

### Connection Issues

If the agent can't connect to MCP servers:

1. Verify MCP server config in `~/.crow/config.yaml`
2. Check that the MCP server path is correct
3. Ensure the server is executable

### Session Loading Failures

If sessions fail to load:

1. Check database exists: `ls ~/.crow/crow.db`
2. Verify database permissions: `chmod 644 ~/.crow/crow.db`
3. Check session ID exists in database

### Terminal Not Working

If ACP terminals aren't working:

1. Check client capabilities: `clientCapabilities.terminal` should be `true`
2. Verify MCP terminal fallback is configured
3. Check terminal command is valid in the workspace directory

### Tool Call JSON Errors

If you see errors about malformed tool call arguments:

1. This is handled automatically by `process_tool_call_inputs()`
2. The function attempts to repair common JSON issues (missing braces/brackets)
3. Falls back to empty object `{}` if repair fails
4. Check logs for "Malformed tool arguments" warnings

## License

MIT
