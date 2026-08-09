# ACP-Centered MCP Configuration Implementation Summary

## What Was Done

Successfully replaced the hardcoded static file configuration for MCP servers with a proper ACP-centered approach that uses the `mcp_servers` parameter from the ACP protocol.

## Changes Made

### 1. New Module: `src/crow/agent/mcp_config.py`
Created a conversion utility that transforms ACP protocol MCP server configurations into FastMCP client format.

**Key Function:**
```python
def acp_to_fastmcp_config(
    mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio]
) -> dict[str, Any]:
    """
    Convert ACP mcp_servers to FastMCP configuration dict.
    
    ACP uses List[EnvVariable] and List[HttpHeader].
    FastMCP uses dict[str, str] for both.
    """
```

### 2. Updated: `src/crow/agent/mcp_client.py`
Enhanced `create_mcp_client_from_acp()` to:
- Accept a list of ACP MCP servers (instead of single server)
- Use the conversion function to create FastMCP config
- Fall back to builtin crow-mcp-server if no servers provided
- Support multi-server configuration

### 3. Updated: `src/crow/acp_agent.py`
Modified `new_session()` and `load_session()` to:
- Use `create_mcp_client_from_acp()` with the `mcp_servers` parameter
- Remove hardcoded `setup_mcp_client("src/crow/mcp/search.py")`
- Log which MCP servers are being used

### 4. Tests

#### Unit Tests: `tests/unit/test_mcp_config.py` (17 tests)
- Tests for all three server types (Stdio, HTTP, SSE)
- Conversion from ACP List[EnvVariable] to dict
- Conversion from ACP List[HttpHeader] to dict
- Mixed server configurations
- Edge cases and constraint validation

#### E2E Tests: `tests/e2e/test_acp_mcp_config.py` (4 tests)
- Real MCP server communication (no mocks)
- In-memory builtin server usage
- Stdio server configuration (user's actual use case)
- Tool discovery and calling
- OpenAI format conversion

## User's Use Case - Now Supported!

The user can now configure crow-mcp-server (or any MCP server) via ACP protocol:

```python
from acp.schema import McpServerStdio, EnvVariable

# Configure the builtin tools as a separate MCP server with its own venv
crow_server = McpServerStdio(
    name="crow-builtin",
    command="uv",
    args=[
        "--project",
        "/home/thomas/src/projects/mcp-testing/crow-mcp-server",
        "run",
        "/home/thomas/src/projects/mcp-testing/crow-mcp-server/crow_mcp_server/main.py",
    ],
    env=[EnvVariable(name="DEBUG", value="false")]
)

# Pass to ACP client when creating session
response = await agent.new_session(
    cwd="/path/to/workspace",
    mcp_servers=[crow_server]
)
```

## Benefits

1. **Protocol Compliance**: Properly uses ACP `mcp_servers` parameter
2. **Flexibility**: Clients can configure any MCP server they want
3. **Separation**: crow-mcp-server can have its own venv and dependencies
4. **Testability**: Easy to test with mock servers or in-memory servers
5. **Scalability**: Multiple MCP servers from different sources
6. **No sys.path**: All packages properly importable via pyproject.toml

## Test Results

```
tests/unit/test_mcp_config.py ............................. [100%] 17 passed
tests/e2e/test_acp_mcp_config.py ......................... [100%] 4 passed
```

All new tests passing, demonstrating:
- ACP to FastMCP conversion works
- Builtin server loads correctly
- Stdio server configuration works (actual subprocess)
- Tool discovery and calling works
- Multi-server support works

## Architecture

```
┌─────────────────────────────────────────┐
│         ACP Protocol Layer              │
│                                         │
│  new_session(mcp_servers=[...])         │
└──────────────┬──────────────────────────┘
               │
               │ List[McpServerStdio | HttpMcpServer | SseMcpServer]
               │
               ▼
┌─────────────────────────────────────────┐
│     Conversion Layer (acp_to_fastmcp)   │
│                                         │
│  ACP List[EnvVariable] → dict[str,str]  │
│  ACP List[HttpHeader] → dict[str,str]   │
└──────────────┬──────────────────────────┘
               │
               │ {"mcpServers": {...}}
               │
               ▼
┌─────────────────────────────────────────┐
│         FastMCP Client Layer            │
│                                         │
│  Client(config)                         │
│  - Multi-server support                 │
│  - Tool namespacing                     │
└──────────────┬──────────────────────────┘
               │
               │ Connected MCP servers
               │
               ▼
┌─────────────────────────────────────────┐
│          Tool Discovery Layer           │
│                                         │
│  get_tools() → OpenAI format            │
└─────────────────────────────────────────┘
```

## Next Steps

The infrastructure is now in place for:
1. Running multiple MCP servers simultaneously
2. Hot-swappable MCP server configurations
3. Per-session MCP server configurations
4. Custom MCP server implementations by users

## Files Modified

- ✅ `src/crow/agent/mcp_config.py` (new)
- ✅ `src/crow/agent/mcp_client.py` (updated)
- ✅ `src/crow/acp_agent.py` (updated)
- ✅ `tests/unit/test_mcp_config.py` (new)
- ✅ `tests/e2e/test_acp_mcp_config.py` (new)
- ✅ `docs/essays/15Feb2026-acp-mcp-configuration.md` (new)
- ✅ `pyproject.toml` (fixed package configuration)
