# `crow-acp`

`crow-acp` is an [Agent Client Protocol (ACP)](https://agentclientprotocol.com/) native agent implementation that serves as the core execution engine for the Crow agent framework.

## Installation

```bash
# Ensure you're in the correct project directory
cd /home/thomas/src/nid

# Install dependencies using uv
uv sync --project /home/thomas/src/nid/crow-acp

# Or install from the workspace root
uv sync
```

## Quick Start

### Run as CLI Agent

```bash
# Activate the virtual environment (if not using --project)
source /home/thomas/src/nid/crow-acp/.venv/bin/activate

# Run the agent
crow-acp
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

### Environment Variables

Create a `.env` file in your project root or set these environment variables:

```bash
# LLM Configuration
ZAI_API_KEY=your-api-key-here
ZAI_BASE_URL=https://api.zai.ai

# Database path (optional, defaults to ~/.crow/crow.db)
DATABASE_PATH=sqlite:~/.crow/crow.db
```

### MCP Server Configuration

MCP servers are configured in `~/.crow/mcp.json`. The default configuration includes the built-in Crow MCP tools:

```json
{
  "mcpServers": {
    "crow-mcp": {
      "command": "uv",
      "args": [
        "--project",
        "/home/thomas/src/nid/crow-mcp",
        "run",
        "python",
        "-m",
        "crow_mcp.server",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

## Features

### 1. ACP Protocol Native
- Implements all ACP agent endpoints (`initialize`, `new_session`, `load_session`, `prompt`, `cancel`)
- Full streaming support for token-by-token responses
- Session persistence to SQLite database

### 2. Multi-Session Support
- Handles multiple concurrent sessions with proper isolation
- Sessions persist across agent restarts
- Load existing sessions by ID

### 3. MCP Tool Integration
- Automatically discovers tools from connected MCP servers
- Supports both MCP and ACP-native tool execution
- Tool execution with progress updates

### 4. Streaming ReAct Loop
- Real-time streaming of thinking tokens (for reasoning models)
- Content token streaming
- Tool call progress updates (pending → in_progress → completed/failed)

### 5. Cancellation Support
- Immediate task cancellation via async events
- Persists partial state on cancellation
- Safe resource cleanup on cancel

### 6. ACP Terminal Support
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

`crow-acp` is designed to work with any ACP-compatible client:

```bash
# Example with ACP client that supports terminal and filesystem capabilities
# The agent will automatically use ACP-native features when available
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
crow-acp/
├── agent.py          # AcpAgent class - ACP protocol + ReAct loop
├── session.py        # Session management + persistence
├── db.py             # SQLAlchemy database models
├── config.py         # Configuration (LLM, MCP, database)
├── llm.py            # LLM client configuration
├── mcp_client.py     # MCP client creation + tool extraction
├── context.py        # Context providers (directory tree, file fetching)
├── prompts/          # Jinja2 system prompt templates
│   ├── system_prompt.jinja2
│   ├── self_documentation.jinja2
│   ├── skill_knowledge_info.jinja2
│   └── system_message_suffix.jinja2
└── pyproject.toml    # Project dependencies and entry point
```

## Development

### Running Tests

```bash
# From the project root
uv run --project /home/thomas/src/nid pytest crow-acp/tests/
```

### Building

```bash
# Build the package
uv build --project /home/thomas/src/nid/crow-acp

# Install locally
pip install --force-reinstall ./crow-acp/dist/*.whl
```

## Integration with Other Crow Packages

`crow-acp` works as the core agent implementation alongside other Crow packages:

| Package | Purpose | Relationship to crow-acp |
|---------|---------|------------------------|
| `crow-mcp` | MCP tools (file, terminal, search) | Provides tools that crow-acp executes |
| `crow-agent` | SDK for programmatic agent control | Wraps crow-acp for easier use |
| `crow-core` | ACP-native agent with extensions | Future: extension system on top |
| `crow-persistence` | Post-request DB hooks | Future: session persistence hooks |
| `crow-skills` | Pre-request context injectors | Future: filesystem context hooks |

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
