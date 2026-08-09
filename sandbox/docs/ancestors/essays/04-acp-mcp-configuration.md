# ACP-Centered MCP Server Configuration

**Date**: 15 Feb 2026
**Context**: Moving from hardcoded MCP server setup to proper ACP protocol compliance
**Status**: Understanding Phase

## The Problem

Currently, `src/crow/acp_agent.py` ignores the `mcp_servers` parameter from ACP and hardcodes:

```python
# Line 117 in new_session
mcp_client = setup_mcp_client("src/crow/mcp/search.py")
```

This violates the ACP protocol, which specifies that clients provide MCP server configurations via the `mcp_servers` parameter in `new_session` and `load_session` calls.

## ACP Protocol Specification

The ACP protocol defines three MCP server types (from `refs/python-sdk/src/acp/schema.py`):

### McpServerStdio
```python
class McpServerStdio(BaseModel):
    command: str              # Path to executable (e.g., "python", "uv")
    args: List[str]           # Command-line arguments
    env: List[EnvVariable]    # Environment variables
    name: str                 # Human-readable identifier
```

### McpServerHttp
```python
class McpServerHttp(BaseModel):
    url: str                  # HTTP endpoint
    headers: List[HttpHeader] # HTTP headers
    name: str                 # Human-readable identifier
```

### SseMcpServer
```python
class SseMcpServer(BaseModel):
    url: str                  # SSE endpoint
    headers: List[HttpHeader] # HTTP headers
    name: str                 # Human-readable identifier
```

Where:
- `EnvVariable = {name: str, value: str}`
- `HttpHeader = {name: str, value: str}`

## FastMCP Client Configuration

FastMCP supports a configuration-based client that can handle multiple servers. The format (from fastmcp.wiki):

```python
config = {
    "mcpServers": {
        "server_name": {
            # stdio server
            "transport": "stdio",
            "command": "python",
            "args": ["./server.py"],
            "env": {"DEBUG": "true"},
            
            # OR http server
            "transport": "http",
            "url": "https://...",
            "headers": {"Authorization": "Bearer ..."},
            
            # OR sse server
            "transport": "sse", 
            "url": "https://...",
            "headers": {...}
        }
    }
}

client = Client(config)
```

**Key differences from ACP:**
1. Headers/env are `dict[str, str]` not `List[{name, value}]`
2. Requires explicit `"transport"` field
3. Tools are prefixed with server name (e.g., `"weather_get_forecast"`)

## The Use Case

The user wants to run `crow-mcp-server` as a separate package with its own venv:

```python
from acp.schema import McpServerStdio

crow_server = McpServerStdio(
    name="crow-builtin",
    command="uv",
    args=[
        "--project",
        "/home/thomas/src/projects/mcp-testing/crow-mcp-server",
        "run",
        "/home/thomas/src/projects/mcp-testing/crow-mcp-server/crow_mcp_server/main.py",
    ],
    env=[]
)
```

This should be passed to `new_session()` and converted to a FastMCP Client.

## Implementation Approach

### 1. Conversion Function

Create `src/crow/agent/mcp_config.py`:

```python
from acp.schema import HttpMcpServer, SseMcpServer, McpServerStdio

def acp_to_fastmcp_config(
    servers: list[HttpMcpServer | SseMcpServer | McpServerStdio]
) -> dict:
    """
    Convert ACP mcp_servers to FastMCP configuration dict.
    
    ACP uses List[EnvVariable] and List[HttpHeader].
    FastMCP uses dict[str, str].
    """
    config = {"mcpServers": {}}
    
    for server in servers:
        if isinstance(server, McpServerStdio):
            config["mcpServers"][server.name] = {
                "transport": "stdio",
                "command": server.command,
                "args": server.args,
                "env": {e.name: e.value for e in server.env}
            }
        elif isinstance(server, HttpMcpServer):
            config["mcpServers"][server.name] = {
                "transport": "http",
                "url": server.url,
                "headers": {h.name: h.value for h in server.headers}
            }
        elif isinstance(server, SseMcpServer):
            config["mcpServers"][server.name] = {
                "transport": "sse",
                "url": server.url,
                "headers": {h.name: h.value for h in server.headers}
            }
    
    return config
```

### 2. Update MCP Client Creation

In `src/crow/agent/mcp_client.py`:

```python
async def create_mcp_client_from_acp(
    mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio]
) -> MCPClient:
    """
    Create FastMCP client from ACP MCP server configurations.
    
    If no servers provided, use builtin crow-mcp-server.
    """
    if not mcp_servers:
        # Default to builtin server (in-memory for performance)
        from crow_mcp_server.main import mcp as builtin_mcp
        return MCPClient(builtin_mcp)
    
    # Convert ACP format to FastMCP config
    config = acp_to_fastmcp_config(mcp_servers)
    return MCPClient(config)
```

### 3. Update ACP Agent

In `src/crow/acp_agent.py`:

```python
async def new_session(
    self,
    cwd: str,
    mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
    **kwargs: Any,
) -> NewSessionResponse:
    logger.info("Creating new session in cwd: %s", cwd)
    logger.info("MCP servers: %s", [s.name for s in mcp_servers])
    
    # Create MCP client from ACP-provided configuration
    mcp_client = await create_mcp_client_from_acp(mcp_servers)
    
    # ... rest of session creation
```

## Testing Strategy

### Unit Tests (tests/unit/test_mcp_config.py)
- Test conversion function handles all three server types
- Test empty list returns fallback
- Test List[EnvVariable] -> dict conversion
- Test List[HttpHeader] -> dict conversion

### Integration Tests  
- Test with in-memory FastMCP server
- Test tool discovery works
- Test tool calling works with prefixed names

### E2E Test (tests/e2e/test_acp_mcp_config.py)
- Create a simple test MCP server
- Configure it via ACP McpServerStdio
- Run full agent loop with the server
- Verify tools are discovered and callable

## Benefits

1. **Protocol Compliance**: Properly uses ACP mcp_servers parameter
2. **Flexibility**: Clients can configure any MCP server they want
3. **Separation**: crow-mcp-server can have its own venv and dependencies
4. **Testability**: Easy to test with mock servers or in-memory servers
5. **Scalability**: Multiple MCP servers from different sources

## Next Steps

1. Write conversion function
2. Write unit tests
3. Update acp_agent.py to use mcp_servers
4. Write E2E test demonstrating the full workflow
5. Update documentation
