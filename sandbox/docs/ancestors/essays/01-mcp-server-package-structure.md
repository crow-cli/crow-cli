# Structuring MCP Servers as Standalone Packages

**Date**: February 19, 2026
**Author**: Crow Team
**Purpose**: Understanding how to structure MCP servers with their own pyproject.toml for isolation and testability

---

## The Problem

Currently, our `file_editor` MCP server lives inside the main `mcp-servers/file_editor/` directory but relies on the root `pyproject.toml` for dependencies. This creates issues:

1. **Coupling**: MCP servers depend on the main project's dependencies
2. **Testing**: Can't test the MCP server in isolation
3. **Deployment**: Can't ship the MCP server as a standalone package
4. **Dependency bloat**: The main project pulls in all MCP server dependencies

## The Solution: uv Workspaces

From the [uv workspaces documentation](https://docs.astral.sh/uv/concepts/projects/workspaces/):

> A workspace is "a collection of one or more packages, called workspace members, that are managed together."
> 
> In a workspace, each package defines its own `pyproject.toml`, but the workspace shares a single lockfile, ensuring that the workspace operates with a consistent set of dependencies.

This is exactly what we need: each MCP server is its own package with its own dependencies, but the whole project shares one lockfile.

## Workspace Structure

```
mcp-testing/
├── pyproject.toml          # Root project (crow) + workspace definition
├── uv.lock                 # Shared lockfile for all packages
├── src/crow/                # Main agent code
│
├── mcp-servers/
│   ├── file_editor/
│   │   ├── pyproject.toml  # file_editor as standalone package
│   │   └── src/
│   │       └── file_editor/
│   │           ├── __init__.py
│   │           └── server.py
│   │
│   └── terminal/
│       ├── pyproject.toml  # terminal as standalone package
│       └── src/
│           └── terminal/
│               ├── __init__.py
│               └── server.py
```

## Key Concepts

### 1. Workspace Root Configuration

The root `pyproject.toml` defines the workspace:

```toml
[project]
name = "crow"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [...]

[tool.uv.workspace]
members = ["mcp-servers/*"]
```

The `members` key uses glob patterns to find packages. Every directory matching the glob must contain a `pyproject.toml`.

### 2. MCP Server Package Configuration

Each MCP server is a proper Python package:

```toml
# mcp-servers/file_editor/pyproject.toml
[project]
name = "mcp-file-editor"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=2.14.4",
    "charset-normalizer>=3.4.4",
    "binaryornot>=0.4.4",
    "cachetools>=7.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/file_editor"]
```

### 3. Running MCP Servers

With uv workspaces, we can run commands in specific packages:

```bash
# Run the file_editor MCP server
uv run --package mcp-file-editor python -m file_editor.server

# Or from within the package directory
cd mcp-servers/file_editor && uv run python -m file_editor.server

# Test the package
uv run --package mcp-file-editor pytest tests/
```

### 4. Dependency Management

If the main project needs to use an MCP server as a library:

```toml
# Root pyproject.toml
[project]
dependencies = [
    "mcp-file-editor",  # Reference workspace member
]

[tool.uv.sources]
mcp-file-editor = { workspace = true }
```

The `workspace = true` tells uv to use the local package, not PyPI.

## Alternative: FastMCP Configuration

FastMCP 2.12+ introduced `fastmcp.json` for declarative configuration:

```json
{
  "$schema": "https://gofastmcp.com/public/schemas/fastmcp.json/v1.json",
  "source": {
    "path": "server.py",
    "entrypoint": "mcp"
  },
  "environment": {
    "type": "uv",
    "python": ">=3.12",
    "dependencies": ["charset-normalizer", "binaryornot", "cachetools"]
  },
  "deployment": {
    "transport": "stdio"
  }
}
```

With this, running the server is:

```bash
fastmcp run fastmcp.json
```

FastMCP creates an isolated environment with the specified dependencies. This is simpler for development but doesn't integrate with uv workspaces for testing.

## Our Approach: Hybrid

We'll use **uv workspaces** for the project structure because:

1. **Single source of truth**: One `uv.lock` for everything
2. **Test integration**: `uv run --package mcp-file-editor pytest` works naturally
3. **IDE support**: Standard Python project structure
4. **CI/CD**: Same commands work everywhere

Each package will also include a `fastmcp.json` for easy deployment:

```bash
# Development: uv workspace
uv run --package mcp-file-editor python -m file_editor.server

# Deployment: FastMCP
fastmcp run mcp-servers/file_editor/fastmcp.json
```

## TDD for Package Structure

How do we "test" package structure? We test the behavior:

```python
# tests/e2e/test_file_editor_mcp.py

async def test_file_editor_mcp_server_startup():
    """The MCP server should start and respond to tools/list."""
    # Start the real MCP server as a subprocess
    server = subprocess.Popen(
        ["uv", "run", "--package", "mcp-file-editor", "python", "-m", "file_editor.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    
    # Connect with real MCP client
    async with MCPClient(stdin=server.stdout, stdout=server.stdin) as client:
        tools = await client.list_tools()
        
        assert "file_editor" in [t.name for t in tools]
    
    server.terminate()
```

This E2E test validates:
1. The package has correct dependencies installed
2. The server starts without errors
3. The MCP protocol works end-to-end

## Implementation Plan

1. **Create `mcp-servers/file_editor/pyproject.toml`** with minimal dependencies
2. **Reorganize source code** to `mcp-servers/file_editor/src/file_editor/`
3. **Update root `pyproject.toml`** to define workspace
4. **Write E2E test** that runs the MCP server via `uv run --package`
5. **Validate** that `uv sync` still works at root level
6. **Repeat** for terminal MCP server

## Key Insight: Don't Overcomplicate

The essay on 14Feb2026 said it best:

> **No openhands SDK needed.** Just:
> - FastMCP (protocol framework)
> - Standard library (file operations)
> - Our understanding of file_editor semantics

The same applies to package structure. We don't need complex build systems. Just:
- A minimal `pyproject.toml` per MCP server
- uv workspace to tie them together
- FastMCP for the protocol layer

That's it. Simple, standard, testable.

---

## Next Steps

1. Write E2E test for file_editor MCP server (real subprocess, real MCP client)
2. Create pyproject.toml for file_editor package
3. Reorganize source layout
4. Verify tests pass with new structure
5. Apply same pattern to terminal MCP server

---

**Reference Links**:
- [uv Workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)
- [uv Running Commands](https://docs.astral.sh/uv/concepts/projects/run/)
- [FastMCP Configuration](https://gofastmcp.com/deployment/server-configuration)
- [PEP 723 - Inline Script Metadata](https://peps.python.org/pep-0723/) (for single-file scripts)
