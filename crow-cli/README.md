# `crow-cli`

`crow-cli` is an [Agent Client Protocol (ACP)](https://agentclientprotocol.com/) native agent implementation that serves as the core execution engine for the Crow agent framework.

## Installation

```bash
# Ensure you're in the correct project directory
git clone https://github.com/crow-cli/crow-cli.git
uv venv
# Install dependencies using uv
uv --project /path/to/crow/crow-cli sync
```


Or run directly
```
uvx crow-cli --help
```

if you like having it available globally, you can install it using pip
```
uv tool install crow-cli --python 3.14
```


```
```


## Quick Start

```
uvx crow-cli init
```


### Run Programmatically

```python
import asyncio
from crow_acp.agent import AcpAgent, agent_run

async def main():
    await agent_run()

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration


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
- Immediate task cancellation via async events
- Persists partial state on cancellation
- Safe resource cleanup on cancel

### 5. ACP Terminal Support
When the ACP client supports terminals (`clientCapabilities.terminal: true`):
- Uses ACP-native terminals instead of MCP terminal calls
- Better terminal display in the client
- Live output streaming
- Proper terminal lifecycle management

## Built-in Tools

The agent automatically discovers and registers tools from connected MCP servers:

- `crow-mcp_terminal` - Execute shell commands in the workspace
- `crow-mcp_write` - Write content to files
- `crow-mcp_read` - Read files with line numbers
- `crow-mcp_edit` - Fuzzy string replacement in files
- `crow-mcp_web_search` - Search the web using a search engine
- `crow-mcp_web_fetch` - Fetch URL content as markdown

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
- **Event** - Conversation turns (messages, tool calls, results)

## Usage with ACP Clients

`crow-cli` is designed to work with any ACP-compatible client:

```json
// In Zed
{
  "agent_servers": {
      "crow-cli": {
        "type": "custom",
        "command": "uvx",
        "args": ["crow-cli", "acp"],
      },
...
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
│   │   ├── main.py           # Agent entry point
│   │   ├── mcp_client.py     # MCP client creation + tool extraction
│   │   ├── prompt.py         # Prompt building
│   │   ├── react.py          # ReAct loop implementation
│   │   ├── session.py        # Session management + persistence
│   │   ├── skills.py         # Skills handling
│   │   ├── tools.py          # Tool definitions
│   │   └── prompts/          # Jinja2 system prompt templates
│   │       ├── system_prompt.jinja2
│   │       ├── self_documentation.jinja2
│   │       ├── skill_knowledge_info.jinja2
│   │       └── system_message_suffix.jinja2
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── init_cmd.py       # `crow init` command
│   │   └── main.py           # CLI entry point
│   └── client/
│       ├── __init__.py
│       └── main.py           # Programmatic client
├── config/
│   ├── compose.yaml          # Docker compose for services
│   ├── config.yaml           # Default configuration
│   ├── .env.example          # Environment variables template
│   ├── searxng/
│   │   └── settings.yml      # SearXNG search config
│   └── prompts/              # Override prompts (user customization)
│       ├── system_prompt.jinja2
│       ├── self_documentation.jinja2
│       ├── skill_knowledge_info.jinja2
│       └── system_message_suffix.jinja2
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
uv run --project /home/thomas/src/nid pytest crow-cli/tests/
```

### Building

```bash
# Build the package
uv build --project /home/thomas/src/nid/crow-cli

# Install locally
pip install --force-reinstall ./crow-cli/dist/*.whl
```
### ReAct Loop Logic

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           REACT LOOP (Turn N)                           │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                    ┌───────────────────────────────┐
                    │   cancel_event.is_set()?      │
                    └───────────────────────────────┘
                          │                  │
                         YES                 NO
                          │                  │
                          ▼                  ▼
                    ┌──────────┐    ┌────────────────────────┐
                    │  RETURN  │    │  send_request(LLM)     │
                    └──────────┘    └────────────────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────────┐
                              │  process_response() stream   │
                              │  ┌────────────────────────┐  │
                              │  │ Yield: thinking/token  │  │
                              │  │ Yield: content/token   │  │
                              │  │ Yield: tool_args/token │  │
                              │  └────────────────────────┘  │
                              │           │                  │
                              │           ▼                  │
                              │    Collect in              │
                              │    state_accumulator       │
                              └──────────────────────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────────┐
                              │  Cancelled during stream?    │
                              └──────────────────────────────┘
                          ┌────────┴────────┐
                         YES                NO
                          │                  │
                          ▼                  ▼
                    ┌──────────────┐  ┌────────────────────────┐
                    │ Add partial  │  │ Yield: final           │
                    │ response     │  │ (thinking, content,    │
                    │ + results    │  │  tool_call_inputs)     │
                    │ Raise        │  └────────────────────────┘
                    │ CancelledErr │                │
                    └──────────────┘                ▼
                          │                  ┌────────────────────────┐
                          │                  │ Log pre-tool usage     │
                          ▼                  └────────────────────────┘
                    ┌──────────┐                         │
                    │  RETURN  │                 ┌────────────────────────┐
                    └──────────┘                 │ tokens > threshold?    │
                          │                      └────────────────────────┘
┌──────────────────────────────┐                           │              │
│  Turn Loop: for turn in      │                          YES             NO
│    range(max_turns):         │                           │              │
└──────────────────────────────┘                           ▼              ▼
                          │                      ┌──────────────┐  ┌──────────┐
                          ▼                      │  COMPACT     │  │  SKIP  │
              ┌──────────────────────────┐      │  session()   │  │ COMPACT│
              │  process_response DONE   │      └──────────────┘  └──────────┘
              │  Extract: thinking       │           │                │
              │         content          │           └────────┬───────┘
              │         tool_call_inputs │                    │
              │         usage            │                    ▼
              └──────────────────────────┘         ┌────────────────────────┐
                          │                         │  Has tools to call?  │
                          ▼                         └────────────────────────┘
              ┌──────────────────────────┐                           │
              │  Cancelled after stream? │                      ┌────┴────┐
              └──────────────────────────┘                     YES      NO
                          │                                       │          │
                         YES                                      ▼          ▼
                          │                              ┌──────────────┐  ┌──────────────┐
                          ▼                              │  EXECUTE     │  │  NO TOOLS    │
                    ┌──────────────┐                     │  TOOLS       │  │  (final msg) │
                    │ Add partial  │                     └──────────────┘  └──────────────┘
                    │ response     │                            │              │
                    │ + tool       │                            │              │
                    │ results      │                            ▼              ▼
                    │ RETURN       │                    ┌──────────────┐  ┌──────────────┐
                    └──────────────┘                    │ Add tools    │  │ Add assistant│
                                                        │ to results   │  │ response     │
                                                        └──────────────┘  └──────────────┘
                                                        │              │              │
                                                        ▼              ▼              ▼
                              ┌──────────────────────────────────────────────────┐
                              │  Cancelled after tool execution?               │
                              └──────────────────────────────────────────────────┘
                                          │
                                 ┌────────┴────────┐
                                YES                NO
                                 │                  │
                                 ▼                  ▼
                        ┌──────────────┐  ┌────────────────────────┐
                        │ Add partial  │  │ Add assistant response │
                        │ response +   │  │ + tool results         │
                        │ tool results │  └────────────────────────┘
                        │ RETURN       │              │
                        └──────────────┘              │
                                                    │
                                                    ▼
                                        ┌────────────────────────┐
                                        │  Turn N complete       │
                                        │  ───────────────────── │
                                        │  Loop back to turn N+1 │
                                        │  (or max_turns reached)│
                                        └────────────────────────┘
```

## Troubleshooting

### Connection Issues

If the agent can't connect to MCP servers:

1. Verify MCP server config in `~/.crow/mcp.json`
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

## License

Apache-2.0
