# Understanding File Editor and Terminal: A Deep Dive

**Date**: February 14, 2026  
**Author**: Crow Team  
**Purpose**: Deep architectural understanding before MCP implementation

---

## Part 1: The File Editor - A String Replacement Powerhouse

### The Core Philosophy

The file_editor is NOT a text editor in the traditional sense. It's a **semantic string manipulation tool** designed specifically for LLM agents. This distinction is crucial.

Traditional text editors (like vim or VSCode) are designed for humans - they have cursors, visual feedback, undo stacks, multiple files, etc. The file_editor has none of these. Instead, it's designed around how LLMs think and work:

1. **String matching, not line numbers** - LLMs see text patterns, not line coordinates
2. **Exact matching requirements** - Forces the agent to be precise and read before editing  
3. **Stateless operations** - Each command is independent (except undo)
4. **Rich error messages** - Guides the agent when operations fail

### The Command Set

The file_editor implements 5 commands:

#### 1. `view` - The Read Operation
```
view(path, view_range=None)
```

**What it does:**
- If path is directory: Lists 2 levels deep, excludes hidden files, shows trailing `/` for directories
- If path is file: Shows numbered lines (cat -n style)  
- If view_range provided: Shows only specified line range
- Special handling for images: Returns base64-encoded data URLs
- Binary files: Rejected with clear error

**Key insight**: The `-n` numbering is crucial - it gives agents coordinates to reason about line positions.

**The encoding dance**: Uses `charset_normalizer` to detect file encoding with 90% confidence threshold. Falls back to UTF-8. Caches encoding by file modification time to avoid re-detection. This ensures read/write consistency.

**Directory viewing**: Uses `find` command with careful exclusions:
- `-maxdepth 2` shows manageable chunk
- Excludes hidden files (`.*/`) patterns
- Counts hidden files and mentions them
- Suggests `ls -la` if user wants to see them

#### 2. `create` - New File Creation  
```
create(path, file_text)
```

**What it does:**
- Validates path doesn't already exist (prevents overwrites)
- Writes file with detected/specified encoding
- Adds initial content to history (for undo)

**Why no overwrite?**: Forces agent to consciously choose `str_replace` for modifications. Prevents accidental data loss from hallucinated paths.

#### 3. `str_replace` - The Heart of the Tool
```
str_replace(path, old_str, new_str)
```

**This is where the magic happens.**

**The matching algorithm:**
1. Uses `re.escape()` to match old_str literally (no regex interpretation)
2. Searches for exact matches in file content
3. If no matches: Strips whitespace and tries again (handles copy-paste noise)
4. If multiple matches: Fails with list of line numbers - forces uniqueness
5. If exactly one match: Performs replacement

**Why strict matching?**
- LLMs often copy-paste slightly wrong snippets
- Extra whitespace, missing indentation
- The strip-and-retry handles common errors
- But multiple matches forces agent to include more context

**Line number tracking**: Uses clever counting:
```python
file_content.count("\n", 0, match.start()) + 1
```
This gives the 1-indexed line number of the match start.

**History management**: Every successful replacement saves the old content to a disk-based cache (FileCache) with LRU eviction. This enables undo.

**Output snippet**: Doesn't return entire file - just a window around the change:
- 4 lines before (`SNIPPET_CONTEXT_WINDOW`)
- N lines after (N = new_str line count + 4)
- With line numbers for verification

**Example flow:**
```
Agent: "Replace 'foo' with 'bar' in file.py"
Editor: Searches for 'foo', finds 3 matches at lines 10, 25, 40
Editor: Fails with "Multiple occurrences in lines [10, 25, 40]. Please ensure it is unique."
Agent: "Replace the 'foo' at line 25 with surrounding context..."
Editor: Matches uniquely, replaces, returns snippet showing lines 21-33
Agent: Verifies the change looks correct
```

#### 4. `insert` - Line Insertion
```
insert(path, insert_line, new_str)
```

**What it does:**
- Reads file up to insert_line
- Writes those lines to temp file
- Writes new_str lines to temp file  
- Writes remaining lines from original
- Atomically moves temp file to original

**Why temp file?** Can't modify file while reading it. The temp file approach is atomic - either complete success or no change.

**insert_line semantics:**
- 0 means insert at beginning (before line 1)
- N means insert after line N
- num_lines means append at end

**Range validation**: Must be [0, num_lines]. Prevents off-by-one errors.

#### 5. `undo_edit` - Reverting Changes
```
undo_edit(path)
```

**What it does:**
- Pops last history entry for this file
- Writes the old content back
- Returns snippet showing reverted content

**History structure:**
- Per-file metadata tracks: `{entries: [counter1, counter2, ...], counter: next_id}`
- Each entry is a separate cache file: `path_hash.counter.json`
- Max 10 entries per file (configurable)
- LRU eviction when cache size exceeds limit

**No history case**: Fails gracefully with "No edit history found for {path}"

### The Validation Layers

**Path validation (`validate_path`):**
1. Must be absolute path (starts with `/`)  
   - Suggests correct path if relative path exists in workspace
2. `create` requires path doesn't exist
3. All other commands require path exists
4. Only `view` works on directories

**File validation (`validate_file`):**
1. Size check: Max 10MB (configurable)
   - Prevents memory issues with huge files
2. Binary check: Uses `binaryornot` library
   - Images bypass this (checked earlier)  
   - Other binaries rejected with helpful error

### The Encoding Manager

**Why encoding matters:**
Different files use different encodings (UTF-8, Latin-1, etc). If you read with wrong encoding, you get mojibake. If you write with different encoding than you read, you corrupt the file.

**The EncodingManager:**
- Detects encoding using `charset_normalizer` 
- Caches by `(path, mtime)` - if file changes, re-detect
- Confidence threshold: 90% (falls back to UTF-8 if unsure)  
- ASCII → UTF-8 conversion (ASCII is subset, UTF-8 is more flexible)

**The `@with_encoding` decorator:**
```python
@with_encoding
def read_file(self, path, encoding="utf-8"):
    # encoding is auto-injected by decorator
    ...
```

- Wraps any file operation method
- Auto-detects and injects encoding parameter
- For new files: uses default UTF-8
- For existing files: uses detected/cached encoding
- Ensures read/write consistency

### Output Formatting

**`_make_output` method:**
```
_make_output(content, description, start_line=1)
```

**What it does:**
1. Truncates if exceeds MAX_RESPONSE_LEN_CHAR (16000 chars)
   - Adds helpful notice with grep hint
2. Adds line numbers: `     1\tcontent`
3. Returns formatted string: `Here's the result of running cat -n on {description}:`

**Truncation notices:**
- Text files: Suggests using `grep -n` to find specific content
- Directories: Suggests using `ls -la` for large directories  
- Binary: Suggests using Python libraries

### The Shell Utilities

The editor uses shell commands for some operations:

**`run_shell_cmd`**:
- Executes shell command safely
- Captures stdout, stderr
- Truncates large outputs with notices
- Used for directory listings (`find`)

**Why shell?** Some operations (like directory tree listing) are more reliable with battle-tested Unix tools than pure Python.

### Error Handling Philosophy

**Custom exception hierarchy:**
```
ToolError (base)
├── EditorToolParameterMissingError
├── EditorToolParameterInvalidError  
└── FileValidationError
```

**Every error message:**
1. Explains what went wrong
2. Suggests how to fix it
3. Includes relevant context (line numbers, values)

**Example:**
```
Invalid `view_range` parameter: [5, 3]. Its second element `3` should be 
greater than or equal to the first element `5`.
```

This guides the agent to self-correct.

---

## Summary: Design Principles

The file_editor embodies these principles:

1. **LLM-First Design** - Commands match how LLMs think about text
2. **Fail Safely** - Rich errors guide agents to correct commands
3. **Stateless by Default** - Only history breaks this, for good reason
4. **Exact Matching** - Forces precision, prevents hallucinated edits
5. **Encoding Aware** - Handles real-world files with different encodings
6. **Resource Bound** - File size limits, output truncation, history eviction
7. **Atomic Operations** - Temp files ensure consistency
8. **Helpful Context** - Snippets and line numbers aid verification

The tool is essentially a **semantic patch utility** for LLMs - apply precise transformations to files with verification at every step.

---

## Part 2: FastMCP - The Protocol Layer

### What is MCP?

**MCP (Model Context Protocol)** is a protocol for connecting AI models to tools and resources. It's like REST for AI - a standardized way for models to:

1. **Discover tools** (via schema)
2. **Call tools** (via JSON-RPC messages)  
3. **Receive results** (structured responses)

MCP abstracts tool calling into a protocol. You don't write code to call tools - you speak MCP. The protocol handles discovery, invocation, error handling, transports.

**Transport layer**: MCP can run over:
- `stdio` - subprocess communication (parent/child)
- `sse` - Server-Sent Events over HTTP
- `streamable-http` - HTTP with streaming

### What is FastMCP?

**FastMCP** is to MCP what FastAPI is to REST - a decorator-based framework that makes MCP servers trivial to write.

**The philosophy**: Don't write MCP handlers. Write Python functions. Let FastMCP handle the protocol.

### How FastMCP Works

#### 1. **Server Creation**
```python
from fastmcp import FastMCP

mcp = FastMCP(name="MyTools")
```

This creates an MCP server instance. That's it. No boilerplate.

#### 2. **Tool Registration via Decorator**
```python
@mcp.tool
async def my_tool(name: str, count: int = 5) -> str:
    """This docstring becomes the tool description.
    
    Args:
        name: This becomes the parameter description
        count: Optional with default
    """
    return f"Hello {name} " * count
```

**What happens automatically:**
- Function name → tool name (`my_tool`)
- Type hints → JSON schema (`name`: string, `count`: integer)
- Default values → optional parameters
- Docstring → tool description (parsed for parameter docs)
- Return type → output schema

**The MCP client sees:**
```json
{
  "name": "my_tool",
  "description": "This docstring becomes the tool description...",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "This becomes..."},
      "count": {"type": "integer", "default": 5, ...}
    },
    "required": ["name"]
  }
}
```

FastMCP generates this schema from your function signature. No manual schema writing.

#### 3. **Server Execution**
```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

This starts the MCP server listening on stdin/stdout. The protocol:
1. Client sends JSON-RPC request on stdin
2. FastMCP parses, routes to tool function
3. Tool function executes
4. Result sent back on stdout as JSON-RPC response

**You never see the protocol.** You write functions, FastMCP handles everything else.

### Why FastMCP is Great

#### 1. **Zero Boilerplate**
Traditional MCP server (without FastMCP):
```python
# 50+ lines of protocol handling
class MyServer:
    def handle_request(self, request):
        if request["method"] == "tools/list":
            return self.list_tools()
        elif request["method"] == "tools/call":
            return self.call_tool(request["params"])
        ...
    
    def list_tools(self):
        return {
            "tools": [{
                "name": "my_tool",
                "inputSchema": {...}  # Manual schema!
            }]
        }
    
    def call_tool(self, params):
        # Manual argument parsing
        name = params["arguments"]["name"]
        ...
```

FastMCP version:
```python
@mcp.tool
async def my_tool(name: str) -> str:
    return f"Hello {name}"
```

That's it. FastMCP generates the schema, handles routing, parsing, error handling.

#### 2. **Type Safety**
Type hints aren't just documentation - they're **schema definition**:
- `str` → `{"type": "string"}`
- `int` → `{"type": "integer"}`  
- `list[str]` → `{"type": "array", "items": {"type": "string"}}`
- `Literal["a", "b"]` → `{"enum": ["a", "b"]}`
- Pydantic models → full object schemas

The type system becomes the schema system. Writing typed Python = writing MCP schemas.

#### 3. **Async-Native**
```python
@mcp.tool
async def web_fetch(url: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    return response.text
```

FastMCP handles async automatically. Tools can be sync or async - FastMCP does the right thing.

#### 4. **Rich Metadata**
```python
@mcp.tool(
    name="custom_name",
    description="Override description",
    tags=["utility", "web"],
    annotations={"readOnlyHint": True}
)
def my_tool(...):
    ...
```

You can override anything, but defaults are sensible.

#### 5. **Transport Agnostic**
```python
# stdio (for subprocess-based integration)
mcp.run(transport="stdio")

# SSE (for web-based integration)  
mcp.run(transport="sse")

# HTTP (for REST-like integration)
mcp.run(transport="http")
```

Same tools, different transports. MCP abstracts the communication layer.

### The MCP Philosophy

MCP treats tool calling as a **protocol problem**, not a library problem:

**Old way (library-based):**
```python
# Agent code imports tools directly
from my_tools import tool1, tool2
agent.register(tool1, tool2)
```

**MCP way (protocol-based):**
```python
# Agent talks to tools via protocol
client = MCPClient("path/to/tool_server.py")
tools = await client.list_tools()  # Protocol discovery
result = await client.call_tool("tool1", {...})  # Protocol invocation
```

**Benefits:**
1. **Language agnostic** - Python agent can call tools written in any language
2. **Process isolation** - Tools crash without crashing agent
3. **Dynamic loading** - Add tools without restarting agent
4. **Schema-first** - Discovery is built into the protocol
5. **Pluggable transports** - Same tools work over stdio, HTTP, SSE

### How This Applies to file_editor

To implement file_editor as an MCP server:

1. **FastMCP server** wraps file_editor functionality
2. **One tool per command** (or one tool with command parameter)
3. **Type hints define schema** - Python signatures become MCP schemas
4. **stdio transport** - Agent launches server as subprocess
5. **Protocol communication** - Agent calls via MCP, not direct imports

**No openhands SDK needed.** Just:
- FastMCP (protocol framework)
- Standard library (file operations)
- Our understanding of file_editor semantics

### Implementation Strategy

**Don't copy openhands code.** Instead:

1. **Extract semantics** (done in Part 1)
2. **Implement fresh** using:
   - Python standard library (`pathlib`, `re`, `tempfile`)
   - Minimal dependencies (`charset_normalizer` for encoding)
   - FastMCP decorators for protocol layer
3. **Keep what matters**:
   - Exact string matching
   - Encoding detection/preservation
   - History for undo
   - Rich error messages
4. **Drop what doesn't**:
   - openhands SDK types (Action/Observation)
   - Security analyzers/threat evaluation
   - Conversation state integration
   - SDK-specific infrastructure

**Result**: Clean, focused MCP server that does one thing well - file editing for LLMs via MCP protocol.

---

**Status**: Part 1 & 2 complete - Architecture and protocol understood  
**Implementation**: ✅ DONE - `mcp-servers/file_editor/server.py` (needs TDD tests)
**Tests**: Started in `tests/unit/test_file_editor.py`
**Next**: Complete TDD tests, then terminal MCP server
