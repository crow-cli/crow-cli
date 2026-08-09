# ACP Tool Enhancements Plan

## Goal

Make `crow-acp` tools return proper ACP-typed content:
1. **Terminal** → Use ACP client terminal (live streaming in client UI)
2. **File Editor** → Return diffs + file locations (rich diff rendering in client)

## Reference Implementation

`refs/kimi-cli/src/kimi_cli/acp/tools.py` shows the pattern:
- Replace MCP tools with ACP-aware wrappers when client supports it
- Use `acp.schema.TerminalToolCallContent` for live terminals
- Use `acp.schema.FileEditToolCallContent` for diffs
- Use `ToolCallLocation` for file tracking

---

## Part 1: Terminal Tool → ACP Client Terminal

### Current State
- `crow-mcp/terminal/main.py` runs a backend PTY session
- Returns text output to LLM
- Client just sees text, no live streaming

### Target State
- Use `acp_conn.create_terminal()` to create client-side terminal
- Stream output live in client UI
- Return result summary to LLM

### Implementation

```python
# crow_acp/tools/terminal.py

import asyncio
from contextlib import suppress
from typing import Any

import acp
from acp.schema import ToolCallProgress, TerminalToolCallContent

from contextvars import ContextVar

# Context var for current tool call ID (like kimi-cli)
_current_tool_call_id: ContextVar[str | None] = ContextVar("tool_call_id", default=None)

def get_current_tool_call_id() -> str | None:
    return _current_tool_call_id.get()


class AcpTerminalTool:
    """Replaces MCP terminal tool when client supports ACP terminals."""
    
    def __init__(self, acp_conn: acp.Client, session_id: str):
        self._conn = acp_conn
        self._session_id = session_id
    
    async def __call__(
        self,
        command: str,
        is_input: bool = False,
        timeout: float | None = None,
        reset: bool = False,
    ) -> str:
        """Execute command in ACP client terminal."""
        
        if not command:
            return "Error: Command cannot be empty"
        
        if reset:
            return "Error: Reset not supported with ACP terminals"
        
        timeout_seconds = timeout or 30.0
        terminal: acp.TerminalHandle | None = None
        exit_status = None
        timed_out = False
        
        try:
            # Create terminal via ACP
            terminal = await self._conn.create_terminal(
                command=command,
                session_id=self._session_id,
                output_byte_limit=50000,  # Match kimi-cli
            )
            
            # Get current tool call ID from context
            tool_call_id = get_current_tool_call_id()
            
            # Send terminal content to client for live display
            if tool_call_id:
                await self._conn.session_update(
                    session_id=self._session_id,
                    update=ToolCallProgress(
                        session_update="tool_call_update",
                        tool_call_id=tool_call_id,
                        status="in_progress",
                        content=[
                            TerminalToolCallContent(
                                type="terminal",
                                terminal_id=terminal.id,
                            )
                        ],
                    ),
                )
            
            # Wait for completion
            try:
                async with asyncio.timeout(timeout_seconds):
                    exit_status = await terminal.wait_for_exit()
            except TimeoutError:
                timed_out = True
                await terminal.kill()
            
            # Get final output
            output_response = await terminal.current_output()
            output = output_response.output
            
            exit_code = exit_status.exit_code if exit_status else None
            exit_signal = exit_status.signal if exit_status else None
            
            truncated_note = (
                " Output was truncated by the client output limit."
                if output_response.truncated else ""
            )
            
            # Build result message for LLM
            if timed_out:
                return f"Command killed by timeout ({timeout_seconds}s){truncated_note}\nOutput:\n{output}"
            if exit_signal:
                return f"Command terminated by signal: {exit_signal}{truncated_note}\nOutput:\n{output}"
            if exit_code not in (None, 0):
                return f"Command failed with exit code: {exit_code}{truncated_note}\nOutput:\n{output}"
            
            return f"Command executed successfully{truncated_note}\nOutput:\n{output}"
            
        finally:
            if terminal:
                with suppress(Exception):
                    await terminal.release()
```

### Integration in agent.py

```python
# In AcpAgent.__init__
self._client_capabilities: ClientCapabilities | None = None

# In initialize()
self._client_capabilities = client_capabilities

# In _execute_tool_calls() - intercept terminal calls
async def _execute_tool_calls(self, session_id: str, tool_call_inputs: list[dict]) -> list[dict]:
    mcp_client = self._mcp_clients[session_id]
    tool_results = []
    
    # Check if client supports terminals
    use_acp_terminal = (
        self._client_capabilities and 
        getattr(self._client_capabilities, 'terminal', False)
    )
    
    for tool_call in tool_call_inputs:
        tool_name = tool_call["function"]["name"]
        tool_args = maximal_deserialize(tool_call["function"]["arguments"])
        
        # Intercept terminal tool if ACP terminals available
        if tool_name == "terminal" and use_acp_terminal:
            result = await self._execute_acp_terminal(
                session_id, tool_call["id"], tool_args
            )
        else:
            result = await mcp_client.call_tool(tool_name, tool_args)
            result = result.content[0].text
        
        tool_results.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": result,
        })
    
    return tool_results
```

---

## Part 2: File Editor → Diffs + Locations

### Current State
- `crow-mcp/file_editor/main.py` returns text snippets
- Client sees text, no diff highlighting
- No file location tracking

### Target State
- Return `FileEditToolCallContent` with `type: "diff"`
- Include `ToolCallLocation` for file tracking
- Client renders beautiful diffs

### ACP Schema Types

```python
# From ACP spec
class FileEditToolCallContent:
    type: Literal["diff"]
    path: str           # Absolute file path
    oldText: str | None # Original content (null for new files)
    newText: str        # New content

class ToolCallLocation:
    path: str           # Absolute file path
    line: int | None    # Optional line number
```

### Implementation

```python
# crow_acp/tools/file_editor.py

from dataclasses import dataclass
from typing import Literal

@dataclass
class EditResult:
    """Structured result from file editor operations."""
    message: str                    # Human-readable message for LLM
    path: str | None = None         # File path if applicable
    old_content: str | None = None  # Original content (for diffs)
    new_content: str | None = None  # New content (for diffs)
    line: int | None = None         # Line number for location
    kind: Literal["read", "edit", "create", "delete"] | None = None


def parse_file_editor_result(result_text: str) -> EditResult:
    """
    Parse text result from MCP file_editor tool into structured data.
    
    Example outputs:
    - "The file /path/to/file.py has been edited.\\n/path/to/file.py snippet:\\n..."
    - "File created successfully at: /path/to/file.py\\n"
    - "/path/to/file.py:\\n     1\\timport os\\n..."
    """
    # Parse the result to extract path, detect if edit vs read vs create
    # This is a bit hacky but works with current file_editor output format
    
    lines = result_text.strip().split('\n')
    
    if "has been edited" in result_text:
        # str_replace or insert - extract path from first line
        path_match = result_text.split(" has been edited")[0].replace("The file ", "")
        return EditResult(
            message=result_text,
            path=path_match,
            kind="edit",
        )
    
    if "File created successfully at:" in result_text:
        path = result_text.split("File created successfully at:")[1].strip()
        return EditResult(
            message=result_text,
            path=path,
            kind="create",
        )
    
    if ":" in (lines[0] or ""):
        # View command - path is first line before colon
        path = lines[0].rstrip(':')
        return EditResult(
            message=result_text,
            path=path,
            kind="read",
        )
    
    return EditResult(message=result_text)
```

### Enhanced Integration

```python
# In _execute_tool_calls() - intercept file_editor calls

from acp.schema import (
    ToolCallProgress,
    FileEditToolCallContent,
    ToolCallLocation,
)

async def _execute_tool_calls(self, session_id: str, tool_call_inputs: list[dict]) -> list[dict]:
    # ... existing setup ...
    
    for tool_call in tool_call_inputs:
        tool_name = tool_call["function"]["name"]
        tool_args = maximal_deserialize(tool_call["function"]["arguments"])
        tool_call_id = tool_call["id"]
        
        # Execute via MCP
        result = await mcp_client.call_tool(tool_name, tool_args)
        result_text = result.content[0].text
        
        # Enhance file_editor results with ACP types
        if tool_name == "file_editor":
            edit_result = parse_file_editor_result(result_text)
            
            # Send tool call update with location + diff content
            content = []
            locations = []
            
            if edit_result.path:
                locations.append(ToolCallLocation(
                    path=edit_result.path,
                    line=edit_result.line,
                ))
                
                # For edits, include diff content
                if edit_result.kind == "edit" and edit_result.old_content:
                    content.append(FileEditToolCallContent(
                        type="diff",
                        path=edit_result.path,
                        old_text=edit_result.old_content,
                        new_text=edit_result.new_content or "",
                    ))
            
            # Send update if we have structured content
            if content or locations:
                await self._conn.session_update(
                    session_id=session_id,
                    update=ToolCallProgress(
                        session_update="tool_call_update",
                        tool_call_id=tool_call_id,
                        status="completed",
                        content=content if content else None,
                        locations=locations if locations else None,
                    ),
                )
        
        tool_results.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result_text,
        })
    
    return tool_results
```

---

## Part 3: Tool Call ID Context

To send tool call updates, we need the ACP tool call ID in context.

### Pattern from kimi-cli

```python
# Context var for turn ID
_current_turn_id: ContextVar[str | None] = ContextVar("turn_id", default=None)

# In prompt()
turn_id = str(uuid.uuid4())
token = _current_turn_id.set(turn_id)

# Build ACP tool call ID as "{turn_id}/{llm_tool_call_id}"
def get_acp_tool_call_id(llm_tool_call_id: str) -> str:
    turn_id = _current_turn_id.get()
    return f"{turn_id}/{llm_tool_call_id}"
```

### For crow-acp

```python
# crow_acp/context.py

from contextvars import ContextVar
import uuid

_current_turn_id: ContextVar[str | None] = ContextVar("turn_id", default=None)

def set_turn_id(turn_id: str | None = None) -> str:
    """Set turn ID for this prompt turn. Returns the ID."""
    turn_id = turn_id or str(uuid.uuid4())
    _current_turn_id.set(turn_id)
    return turn_id

def get_turn_id() -> str | None:
    return _current_turn_id.get()

def get_acp_tool_call_id(llm_tool_call_id: str) -> str:
    """Build ACP tool call ID from turn ID + LLM tool call ID."""
    turn_id = _current_turn_id.get()
    if turn_id is None:
        return llm_tool_call_id  # Fallback
    return f"{turn_id}/{llm_tool_call_id}"
```

---

## Implementation Order

### Phase 1: Infrastructure
1. Add context vars for turn ID tracking
2. Store `client_capabilities` in agent
3. Track tool call IDs during execution

### Phase 2: Terminal (High Impact)
1. Create `AcpTerminalTool` class
2. Intercept `terminal` tool calls in `_execute_tool_calls`
3. Send `TerminalToolCallContent` updates
4. Test with Zed/Kimi client

### Phase 3: File Editor (Medium Impact)
1. Create `parse_file_editor_result()` helper
2. Track old/new content for str_replace operations
3. Send `FileEditToolCallContent` + `ToolCallLocation`
4. Test diff rendering in client

### Phase 4: Enhancements
1. Add `kind` field to tool call start (`read`, `edit`, `execute`, etc.)
2. Add `title` field with dynamic extraction (like kimi-cli)
3. Add permission requests for dangerous operations

---

## Testing

### Manual Testing with Zed
1. Run crow-acp agent
2. Connect from Zed with ACP support
3. Execute terminal command → see live output in client
4. Edit file → see diff highlighting in client
5. View file → see file location in client

### Verify Capabilities
```python
# In initialize(), log capabilities
logger.info(f"Client capabilities: {client_capabilities}")
# Should see: terminal=True, ... when client supports it
```

---

## Files to Create/Modify

### New Files
- `crow_acp/tools/__init__.py`
- `crow_acp/tools/terminal.py` - ACP terminal wrapper
- `crow_acp/tools/file_editor.py` - Diff parsing + formatting
- `crow_acp/context.py` - Context vars for turn/tool tracking

### Modified Files
- `crow_acp/agent.py` - Tool interception logic
- `crow-mcp/file_editor/main.py` - Optionally return structured data

---

## Questions/Open Items

1. **MCP file_editor enhancement**: Should we modify the MCP tool to return structured JSON instead of text? Would make parsing cleaner.

2. **Old content tracking**: For diffs, we need `oldText`. Options:
   - Read file before edit (requires extra MCP call)
   - Modify file_editor to return old content in result
   - Use history manager that already tracks this

3. **Terminal fallback**: If client doesn't support terminals, fall back to current backend terminal implementation.

4. **Permission requests**: Should we add `session/request_permission` for dangerous commands? (kimi-cli does this)
