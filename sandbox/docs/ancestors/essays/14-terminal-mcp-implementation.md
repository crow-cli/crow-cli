# Terminal MCP Implementation - Deep Dive Research

**Date**: Session 2026-02-16  
**Status**: RESEARCH COMPLETE - Understanding the OpenHands Terminal for Crow MCP

---

## The Mission

Convert the OpenHands SDK terminal tool from `crow-mcp/src/crow_mcp/terminal/ref/terminal/` into a FastMCP-based tool for the Crow MCP server.

**Key Insight**: This is NOT about ACP terminals (Essay #13). This is about building a **persistent shell MCP tool** that works independently of ACP client capabilities.

---

## Part 1: The Reference Implementation Architecture

### 1.1 Component Overview

The OpenHands terminal implementation has a sophisticated layered architecture:

```
TerminalAction (Pydantic)         ← Input schema
        ↓
TerminalExecutor                   ← Business logic layer
        ↓
TerminalSession                    ← Session controller
        ↓
TerminalInterface (abstract)       ← Backend abstraction
    ├── TmuxTerminal              ← tmux-based (preferred)
    └── SubprocessTerminal         ← PTY-based (fallback)
        ↓
TerminalObservation (Pydantic)    ← Output schema
```

### 1.2 The PS1 Metadata Magic ⭐

**The most brilliant part**: Metadata extraction via PS1 prompt injection.

```bash
###PS1JSON###
{
  "pid": "$!",
  "exit_code": "$?",
  "username": "\u",
  "hostname": "\h",
  "working_dir": "$(pwd)",
  "py_interpreter_path": "$(command -v python || echo '')"
}
###PS1END###
```

**How it works**:
1. Set PS1 to emit JSON after every command
2. Parse output with regex: `###PS1JSON###\n({.*?})\n###PS1END###`
3. Extract metadata: exit code, working directory, Python path
4. Append to tool response for rich context

**Why it's genius**:
- No special APIs needed
- Works with any bash shell
- Self-describing and extensible
- Survives edge cases (concurrent output, partial reads)

### 1.3 Action/Observation Pattern

```python
class TerminalAction(Action):
    command: str          # The bash command to execute
    is_input: bool        # False = new command, True = STDIN to running process
    timeout: float | None # Soft timeout (asks user to continue)
    reset: bool           # Hard reset terminal (loses all state)

class TerminalObservation(Observation):
    command: str | None
    exit_code: int | None  # -1 = still running (soft timeout hit)
    timeout: bool
    metadata: CmdOutputMetadata  # PS1-extracted data
    full_output_save_dir: str | None
```

**Key Parameters**:

- **`is_input`**: Distinguishes between:
  - New command: `is_input=False` → execute fresh command
  - Interactive input: `is_input=True` → send to STDIN of running process
  
- **`timeout`**: Soft timeout with user interaction:
  - If reached → return `exit_code=-1`, ask user
  - User can: continue, interrupt, send input
  
- **`reset`**: Hard reset terminal:
  - Closes current session
  - Starts fresh with original `work_dir` and config
  - Loses environment variables, venv, etc.

### 1.4 Backend Implementations

#### SubprocessTerminal (PTY-based)

**Implementation**: `terminal/ref/terminal/terminal/subprocess_terminal.py`

```python
class SubprocessTerminal(TerminalInterface):
    """PTY-backed terminal with full terminal emulation."""
    
    def initialize(self):
        # Resolve shell path (explicit or auto-detect)
        shell_path = self.shell_path or shutil.which("bash")
        
        # Create pseudoterminal
        master_fd, slave_fd = pty.openpty()
        
        # Spawn bash in PTY
        self.process = subprocess.Popen(
            [shell_path],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            preexec_fn=...,
        )
        
        # Start reader thread
        self.reader_thread = threading.Thread(
            target=self._read_output,
            args=(master_fd,)
        )
        self.reader_thread.start()
```

**Why PTY matters**:
- ✅ Full terminal emulation (colors, cursor control, etc.)
- ✅ Interactive programs work (vim, htop, REPLs)
- ✅ Proper signal handling (Ctrl+C, Ctrl+Z)
- ✅ Environment detection works (`$TERM` set correctly)

#### TmuxTerminal (tmux-based)

**Implementation**: `terminal/ref/terminal/terminal/tmux_terminal.py`

- Uses tmux session for persistence
- Better scrollback history
- Can detach/reattach
- Preferred when tmux available

**For Crow MCP**: Start with SubprocessTerminal only (simpler, fewer dependencies).

### 1.5 Session Controller Logic

**Implementation**: `terminal/ref/terminal/terminal/terminal_session.py`

```python
class TerminalSession:
    """Unified session controller that works with any backend."""
    
    def execute(self, action: TerminalAction) -> TerminalObservation:
        # Handle special keys (C-c, C-z, C-d)
        if self._is_special_key(action.command):
            return self._handle_special_key(action)
        
        # Handle interactive input to running process
        if action.is_input:
            return self._handle_input(action)
        
        # Normal command execution
        return self._execute_command(action)
```

**Key Patterns**:

1. **Polling Loop**:
   ```python
   while True:
       # Check for output
       output = self.terminal.read_screen()
       
       # Check for PS1 metadata (command complete)
       if ps1_matches:
           return self._build_observation(output, metadata)
       
       # Check for soft timeout
       if time.time() - last_change > no_change_timeout:
           return TerminalObservation(
               exit_code=-1,
               text="Command still running. Continue? [Y/n]"
           )
       
       # Sleep and poll again
       time.sleep(POLL_INTERVAL)
   ```

2. **Metadata Extraction**:
   ```python
   # Find PS1 blocks in output
   ps1_matches = CmdOutputMetadata.matches_ps1_metadata(output)
   
   # Use LAST match (handles concurrent output corruption)
   metadata = CmdOutputMetadata.from_ps1_match(ps1_matches[-1])
   
   # Build observation
   return TerminalObservation(
       text=clean_output,
       metadata=metadata,
       exit_code=metadata.exit_code
   )
   ```

3. **Output Truncation**:
   ```python
   # Truncate large outputs, save full version to file
   truncated = maybe_truncate(
       content=output,
       truncate_after=30000,
       save_dir=session_save_dir
   )
   ```

### 1.6 Executor Business Logic

**Implementation**: `terminal/ref/terminal/impl.py`

```python
class TerminalExecutor:
    """High-level executor with secret injection and masking."""
    
    def __call__(self, action: TerminalAction, conversation=None):
        # 1. Validate parameters
        if action.reset and action.is_input:
            raise ValueError("Cannot combine reset with is_input")
        
        # 2. Handle reset
        if action.reset:
            self.reset()
            if not action.command.strip():
                return TerminalObservation(text="Terminal reset")
        
        # 3. Export secrets from conversation (if any)
        if conversation:
            self._export_envs(action, conversation)
        
        # 4. Execute command
        observation = self.session.execute(action)
        
        # 5. Mask secrets in output
        if conversation:
            observation = self._mask_secrets(observation, conversation)
        
        return observation
```

**Secret Management**:
- Extract secrets from conversation's `secret_registry`
- Export as environment variables before command
- Mask secrets in output (replace with `***`)

---

## Part 2: Crow MCP Architecture

### 2.1 Current Structure

```
crow-mcp/
├── pyproject.toml                 # Entry: crow_mcp.server.main:main
├── main.py                        # OLD monolithic (to be removed)
└── src/crow_mcp/
    ├── server/
    │   └── main.py                # FastMCP app + imports tools
    ├── file_editor/
    │   └── main.py                # @mcp.tool decorated
    ├── web_search/
    │   └── main.py                # @mcp.tool decorated
    ├── web_fetch/
    │   └── main.py                # @mcp.tool decorated
    └── terminal/
        ├── main.py                # NEEDS IMPLEMENTATION
        └── ref/                   # OpenHands reference code
```

### 2.2 The Import Pattern

```python
# crow_mcp/server/main.py
from fastmcp import FastMCP

mcp = FastMCP(
    name="crow-mcp",
    instructions="..."
)

def main():
    mcp.run()

# crow_mcp/terminal/main.py
from crow_mcp.server.main import mcp

@mcp.tool
async def terminal(
    command: str,
    is_input: bool = False,
    timeout: float | None = None,
    reset: bool = False
) -> str:
    """Execute bash command in persistent shell session..."""
    # Implementation

# crow_mcp/file_editor/main.py
from crow_mcp.server.main import mcp

@mcp.tool
async def file_editor(command: str, path: str, ...) -> str:
    """File editor for viewing, creating, and editing files..."""
    # Implementation
```

**Key Insight**: Import the shared `mcp` object, then decorate tools. FastMCP handles registration automatically.

### 2.3 Global State Pattern

From file_editor implementation:

```python
# Global editor instance
_editor: FileEditor | None = None

def get_editor() -> FileEditor:
    global _editor
    if _editor is None:
        _editor = FileEditor()
    return _editor

@mcp.tool
async def file_editor(...) -> str:
    editor = get_editor()
    # Use editor
```

**For terminal**:

```python
# Global terminal instance
_terminal: TerminalSession | None = None

def get_terminal(work_dir: str = os.getcwd()) -> TerminalSession:
    global _terminal
    if _terminal is None or _terminal.closed:
        _terminal = create_terminal_session(
            work_dir=work_dir,
            terminal_type="subprocess",  # Start with PTY only
        )
        _terminal.initialize()
    return _terminal
```

---

## Part 3: Implementation Strategy

### 3.1 Phase 1: Minimal Viable Terminal (MVP)

**Goal**: Working persistent shell with basic features.

**What to keep from OpenHands**:
- ✅ SubprocessTerminal (PTY-based backend)
- ✅ PS1 metadata extraction
- ✅ Soft timeout with polling
- ✅ Session persistence

**What to remove/replace**:
- ❌ OpenHands SDK dependencies (`openhands.sdk.*`)
- ❌ Action/Observation classes (use function parameters)
- ❌ Conversation/Executor abstractions
- ❌ Secret management (add later if needed)

**Dependencies**:
```toml
# Already in pyproject.toml
"fastmcp>=2.14.4",
"pydantic>=2.12.5",

# Need to add
# (None - stdlib has everything needed for PTY)
```

### 3.2 File Structure

```
crow_mcp/terminal/
├── __init__.py
├── main.py              # FastMCP @mcp.tool definition
├── session.py           # TerminalSession class (simplified)
├── backend.py           # SubprocessTerminal (PTY backend)
├── metadata.py          # PS1 metadata extraction
├── constants.py         # Timeouts, limits, PS1 template
└── ref/                 # OpenHands reference (keep for reference)
```

### 3.3 Implementation Plan

#### Step 1: Copy Core Logic

```bash
# Copy essential files from ref/
cp ref/terminal/constants.py ../constants.py
cp ref/terminal/metadata.py ../metadata.py
cp ref/terminal/terminal/subprocess_terminal.py ../backend.py
cp ref/terminal/terminal/terminal_session.py ../session.py
```

#### Step 2: Remove SDK Dependencies

Replace in `backend.py`:
```python
# ❌ Remove
from openhands.sdk.logger import get_logger
from openhands.sdk.utils import sanitized_env
from openhands.tools.terminal.constants import ...
from openhands.tools.terminal.metadata import ...

# ✅ Replace with
from logging import getLogger
import os
from .constants import ...
from .metadata import ...

logger = getLogger(__name__)
```

Replace in `session.py`:
```python
# ❌ Remove
from openhands.sdk.utils import maybe_truncate
from openhands.tools.terminal.definition import TerminalAction, TerminalObservation

# ✅ Replace with
# Implement simple truncation or skip for MVP
# No Action/Observation classes - just use dict or tuple
```

#### Step 3: Simplify Session API

```python
# session.py
class TerminalSession:
    def execute(
        self,
        command: str,
        is_input: bool = False,
        timeout: float | None = None,
    ) -> dict:
        """
        Execute command and return result dict:
        {
            "output": str,
            "exit_code": int,
            "working_dir": str,
            "py_interpreter": str | None,
        }
        """
```

#### Step 4: Implement FastMCP Tool

```python
# main.py
import os
from crow_mcp.server.main import mcp
from .session import TerminalSession

_terminal: TerminalSession | None = None

def get_terminal() -> TerminalSession:
    global _terminal
    if _terminal is None or _terminal.closed:
        _terminal = TerminalSession(
            work_dir=os.getcwd(),
            no_change_timeout_seconds=30,
        )
        _terminal.initialize()
    return _terminal

@mcp.tool
async def terminal(
    command: str,
    is_input: bool = False,
    timeout: float | None = None,
    reset: bool = False,
) -> str:
    """Execute a bash command in a persistent shell session.
    
    Commands execute in a persistent shell where environment variables,
    virtual environments, and working directory persist between calls.
    
    Args:
        command: The bash command to execute. Can be:
            - Regular command: "npm install"
            - Empty string "": Check on running process
            - Special keys: "C-c" (Ctrl+C), "C-z" (Ctrl+Z), "C-d" (Ctrl+D)
        is_input: If True, send command as STDIN to running process.
                  If False (default), execute as new command.
        timeout: Max seconds to wait. If omitted, uses soft timeout
                 (pauses after 30s of no output and asks to continue).
        reset: If True, kill terminal and start fresh. Loses all
               environment variables, venv, etc. Cannot use with is_input.
    
    Returns:
        Command output with metadata (exit code, working directory, etc.)
    """
    try:
        term = get_terminal()
        
        if reset:
            term.close()
            term = get_terminal()  # Creates new instance
            if not command.strip():
                return "Terminal reset successfully"
        
        result = term.execute(
            command=command,
            is_input=is_input,
            timeout=timeout,
        )
        
        # Format output
        output = result["output"]
        if result["working_dir"]:
            output += f"\n[Current working directory: {result['working_dir']}]"
        if result["py_interpreter"]:
            output += f"\n[Python interpreter: {result['py_interpreter']}]"
        if result["exit_code"] != -1:
            output += f"\n[Command completed with exit code {result['exit_code']}]"
        else:
            output += "\n[Process still running (soft timeout)]"
        
        return output
        
    except Exception as e:
        return f"Error: {e}"
```

### 3.4 Testing Strategy

```python
# tests/test_terminal.py

def test_persistence_cd():
    """Test working directory persistence"""
    result1 = await terminal("cd /tmp")
    result2 = await terminal("pwd")
    assert "/tmp" in result2

def test_persistence_env():
    """Test environment variable persistence"""
    await terminal("export TEST_VAR=hello")
    result = await terminal("echo $TEST_VAR")
    assert "hello" in result

def test_persistence_venv():
    """Test virtual environment persistence"""
    await terminal("source .venv/bin/activate")
    result = await terminal("which python")
    assert ".venv/bin/python" in result

def test_timeout():
    """Test soft timeout"""
    result = await terminal("sleep 5", timeout=1)
    assert "exit_code=-1" in result or "still running" in result

def test_reset():
    """Test terminal reset"""
    await terminal("export TEST_VAR=hello")
    await terminal("", reset=True)
    result = await terminal("echo $TEST_VAR")
    assert "hello" not in result  # Should be gone after reset
```

---

## Part 4: Critical Implementation Details

### 4.1 Soft Timeout Flow

```
User: terminal("npm install", timeout=120)

1. Start command in PTY
2. Poll for output every 0.5s
3. If NO new output for 30s:
   - Return exit_code=-1
   - Tell user "Process still running"
4. User options:
   a) Send "" → continue waiting
   b) Send "C-c" → interrupt
   c) Send timeout=300 → restart with longer timeout
5. If total time < 120s → continue
6. If total time >= 120s → return current output
```

### 4.2 Interrupt Handling

```python
# In session.py
def execute(self, command: str, ...) -> dict:
    # Check for special keys
    if command == "C-c":
        self.backend.interrupt()
        return {"output": "Process interrupted", "exit_code": 130}
    elif command == "C-z":
        self.backend.send_keys("\x1a", enter=False)
        return {"output": "Process suspended", "exit_code": 147}
    elif command == "C-d":
        self.backend.send_keys("\x04", enter=False)
        return {"output": "EOF sent", "exit_code": 0}
```

### 4.3 Reset Semantics

```python
# In main.py
if reset:
    if is_input:
        return "Error: Cannot use reset=True with is_input=True"
    
    # Save original work_dir
    old_work_dir = _terminal.work_dir if _terminal else os.getcwd()
    
    # Close existing terminal
    if _terminal:
        _terminal.close()
    
    # Create fresh terminal in same directory
    _terminal = TerminalSession(work_dir=old_work_dir)
    _terminal.initialize()
    
    if not command.strip():
        return "Terminal reset successfully. All previous state lost."
```

### 4.4 Working Directory Default

```python
# Use server's cwd, not client's
def get_terminal() -> TerminalSession:
    global _terminal
    if _terminal is None or _terminal.closed:
        work_dir = os.getcwd()  # Server's working directory
        _terminal = TerminalSession(work_dir=work_dir)
        _terminal.initialize()
    return _terminal
```

**Important**: The terminal starts in the MCP server's working directory, which should be the project root when launched via `uv run crow-mcp`.

---

## Part 5: Key Design Decisions

### 5.1 Singleton Terminal

✅ **Decision**: One global terminal instance per server process.

**Rationale**:
- Simple to implement
- Matches file_editor pattern
- Sufficient for single-user MCP usage
- Avoids complex session management

**Trade-off**:
- ❌ Can't have multiple terminals in parallel
- ✅ But that's not needed for MCP tools (sequential tool calls)

### 5.2 PTY-Only Backend

✅ **Decision**: Start with SubprocessTerminal only, no tmux.

**Rationale**:
- Fewer dependencies
- Simpler codebase
- PTY is sufficient for 95% of use cases
- Can add tmux later if needed

**Trade-off**:
- ❌ No tmux features (detach, better scrollback)
- ✅ But simpler and more portable

### 5.3 No Secret Management (MVP)

✅ **Decision**: Skip secret injection/masking for first version.

**Rationale**:
- Adds complexity
- Not needed for basic usage
- Can be added later via session callbacks

**Future Enhancement**:
```python
# Later: Add secret registry parameter
@mcp.tool
async def terminal(
    command: str,
    ...
    secrets: dict[str, str] | None = None,  # Optional
) -> str:
    if secrets:
        # Export secrets before command
        for k, v in secrets.items():
            term.execute(f"export {k}={v}")
```

### 5.4 No Output Truncation (MVP)

✅ **Decision**: Return full output, let client handle truncation.

**Rationale**:
- Simpler implementation
- FastMCP/clients may have their own limits
- Can add later if needed

**Future Enhancement**:
```python
# Later: Add truncation
MAX_OUTPUT = 30000  # 30KB

if len(output) > MAX_OUTPUT:
    # Save full output to temp file
    temp_file = save_output(output)
    truncated = output[:MAX_OUTPUT] + f"\n... (truncated, full output: {temp_file})"
    return truncated
```

### 5.5 Error Handling Approach

✅ **Decision**: Return errors as formatted strings, don't raise exceptions.

**Rationale**:
- Matches file_editor pattern
- Simpler for FastMCP tools
- User-friendly error messages

**Pattern**:
```python
@mcp.tool
async def terminal(...) -> str:
    try:
        # Do work
        return result
    except ValueError as e:
        return f"Error: Invalid parameters - {e}"
    except Exception as e:
        logger.error(f"Terminal error: {e}", exc_info=True)
        return f"Error: {e}"
```

---

## Part 6: What I Learned

### 6.1 Terminal Persistence is Hard

The OpenHands implementation handles many edge cases:
- Concurrent output corruption
- PTY buffer management
- Signal handling (Ctrl+C, Ctrl+Z)
- Process lifecycle (zombie processes)
- Thread safety for reader thread

**Lesson**: Don't reinvent the wheel. Copy and adapt the working implementation.

### 6.2 PS1 Metadata is Inspired

Using PS1 to inject JSON metadata after every command:
- Zero overhead for bash
- Self-describing
- Extensible
- Survives edge cases

**Lesson**: Sometimes the best solution is clever shell scripting, not Python code.

### 6.3 FastMCP Makes Tools Easy

The decorator pattern (`@mcp.tool`) eliminates boilerplate:
- No manual schema definition
- No registration code
- Auto-generated OpenAPI schema
- Type hints drive validation

**Lesson**: Use the framework, don't fight it.

### 6.4 Session Persistence is Critical

From earlier testing in this session:
- ✅ `cd` persists across tool calls
- ✅ `export` persists across tool calls
- ✅ `source venv` persists across tool calls

This is the **most important feature** for users.

**Lesson**: Test persistence early and often.

### 6.5 Singleton Pattern Works for MCP

Global state is usually bad, but for MCP tools it's necessary:
- Tools are stateless functions
- Need to persist terminal across calls
- One terminal per server process is sufficient

**Lesson**: Pragmatism over purity.

---

## Part 7: Implementation Checklist

### Phase 1: Core Implementation

- [ ] Copy `constants.py` from ref/
- [ ] Copy `metadata.py` from ref/  
- [ ] Copy `subprocess_terminal.py` → `backend.py`
  - [ ] Remove SDK dependencies
  - [ ] Replace logger with standard logging
  - [ ] Update imports
- [ ] Copy `terminal_session.py` → `session.py`
  - [ ] Remove Action/Observation classes
  - [ ] Simplify API to use dict returns
  - [ ] Remove maybe_truncate (for now)
- [ ] Create `main.py` with `@mcp.tool` decorator
  - [ ] Implement singleton pattern
  - [ ] Handle reset, timeout, is_input
  - [ ] Format output with metadata
- [ ] Test with `client.py` (already working)
  - [ ] `cd` persistence
  - [ ] `export` persistence  
  - [ ] `source venv` persistence
  - [ ] Timeout behavior
  - [ ] Reset behavior

### Phase 2: Enhancements (Later)

- [ ] Add output truncation
- [ ] Add secret masking
- [ ] Add tmux backend (optional)
- [ ] Add better error messages
- [ ] Add logging for debugging
- [ ] Add unit tests
- [ ] Add integration tests

### Phase 3: Documentation

- [ ] Update README.md
- [ ] Add usage examples
- [ ] Document parameters
- [ ] Document return format
- [ ] Add troubleshooting section

---

## Appendix: File Locations

**Reference Implementation**:
```
crow-mcp/src/crow_mcp/terminal/ref/terminal/
├── README.md                 # Usage docs
├── constants.py              # Timeouts, PS1 template
├── definition.py             # Action/Observation classes
├── impl.py                   # TerminalExecutor
├── metadata.py               # PS1 parsing
└── terminal/
    ├── factory.py            # Auto-detect backend
    ├── interface.py          # Abstract interface
    ├── subprocess_terminal.py # PTY backend
    ├── terminal_session.py   # Session controller
    └── tmux_terminal.py      # tmux backend
```

**Crow MCP Implementation** (target):
```
crow-mcp/src/crow_mcp/terminal/
├── __init__.py
├── main.py                   # FastMCP tool
├── session.py                # Simplified session
├── backend.py                # SubprocessTerminal
├── metadata.py               # PS1 extraction
├── constants.py              # Config
└── ref/                      # Keep for reference
```

---

## References

- **OpenHands Terminal**: `crow-mcp/src/crow_mcp/terminal/ref/terminal/`
- **FastMCP Docs**: https://gofastmcp.com
- **PTY Module**: https://docs.python.org/3/library/pty.html
- **Essay #13**: ACP Terminal Architecture (different topic - client-provided terminals)

---

**Next Steps**:

1. Start implementing by copying core files from ref/
2. Remove SDK dependencies systematically
3. Simplify API to match FastMCP patterns
4. Test persistence with the same tests we ran earlier
5. Iterate based on what breaks

**Estimated Effort**: 4-6 hours for MVP, 2-3 hours for testing/debugging.

---

## Part 8: Implementation Reality Check (2026-02-16 Session)

### 8.1 What Actually Happened

**Implementation**: ✅ Done
- Created all core files (constants, metadata, backend, session, main)
- Fixed circular import issues
- Integrated with FastMCP server
- Tool appears in tool list

**Testing**: ⚠️ **BUFFERING BIT US**
- Ran `manual_test.py` - saw timeouts, thought it was broken
- Ran it again with output redirection - **IT ACTUALLY WORKED**
- The issue: Python's stdout buffering delayed the output
- Tests were PASSING but we couldn't see it!

### 8.2 The Buffering Lesson

```bash
# This looked broken (output held in buffer):
uv run scripts/manual_test.py

# This revealed truth (forced flush on exit):
uv run scripts/manual_test.py > test_results.txt
cat test_results.txt  # Holy shit, it worked!
```

**What we learned**:
1. Terminal output is buffered
2. Exit flushes the buffer
3. Long-running tests need explicit flush or unbuffered output
4. ALWAYS TEST WITH ACTUAL OUTPUT CAPTURE

### 8.3 Current State

**✅ Working**:
- PTY terminal initialization
- Command execution
- Working directory persistence (cd survives across calls)
- Environment variable persistence (export survives)
- Virtual environment activation
- Terminal reset
- FastMCP integration

**⚠️ Issues**:
- PS1 metadata detection maybe not working (30s timeout occurs)
- BUT tests still pass because output is captured before timeout?
- Need better logging to see what's happening

**❓ Unknowns**:
- Is PS1 actually being set in the PTY?
- Is the regex matching but we don't see it?
- Why does it timeout if commands complete successfully?

### 8.4 The PS1 Bug - ROOT CAUSE FOUND

**Problem**: Commands were timing out because PS1 metadata wasn't being detected.

**Root Cause**: Setting `PS1` via environment variable (`env["PS1"] = ...`) **doesn't work for interactive bash shells**. Bash ignores PS1 from environment and uses its internal prompt settings instead.

**The Fix** (in `backend.py`):
```python
# ❌ WRONG - Doesn't work for interactive bash:
env["PS1"] = self.PS1

# ✅ CORRECT - Inject PS1 after bash starts:
# Wait for bash to initialize
time.sleep(0.3)

# Send PS1 command to running bash
ps1_command = f'PS1="{self.PS1}"\n'
os.write(self._pty_master_fd, ps1_command.encode("utf-8"))
time.sleep(0.2)  # Let PS1 take effect

# Clear the buffer (will contain the PS1 command we just sent)
self.clear_screen()
```

**Result**: Commands now complete in **0.5s** instead of timing out!

### 8.5 The Complete Debug Story

**What We Did Wrong**:
1. Said "95% done" when tests were timing out 🤦
2. Thought PS1 env var would work (it doesn't)
3. Didn't have file logging (flying blind)
4. Confused output buffering with broken tests

**What We Did Right**:
1. Actually tested with output capture to file
2. Added comprehensive file logging
3. Debug logged PS1 detection attempts
4. Fixed the root cause systematically

**The Moral**: NEVER claim something works without TESTED EVIDENCE. Buffering made tests look broken when they were actually passing. File logging revealed the truth.

---

## Part 9: Implementation Checklist - UPDATED

### ✅ Phase 1: Core Implementation (COMPLETE)

- [x] Copy `constants.py` from ref/
- [x] Copy `metadata.py` from ref/  
- [x] Copy `subprocess_terminal.py` → `backend.py`
  - [x] Remove SDK dependencies
  - [x] Replace logger with standard logging
  - [x] **FIX: Inject PS1 after bash starts, not via env var**
  - [x] Update imports
- [x] Copy `terminal_session.py` → `session.py`
  - [x] Remove Action/Observation classes
  - [x] Simplify API to use dict returns
  - [x] **ADD: Verbose PS1 debugging logs**
  - [x] Remove maybe_truncate (for now)
- [x] Create `logging_config.py` for file-based logging
- [x] Create `main.py` with `@mcp.tool` decorator
  - [x] Implement singleton pattern
  - [x] Handle reset, timeout, is_input
  - [x] Format output with metadata
- [x] **FIX: Circular import issues (import from .main not .)**
- [x] **TEST: With manual_test.py**
  - [x] `echo` command works
  - [x] `cd` persistence works
  - [x] `export` persistence works
  - [x] `source venv` persistence works
  - [x] Timeout behavior works
  - [x] Reset behavior works
  - [x] **PS1 metadata detected in 0.5s (not 30s!)**

### Phase 2: Polish & Testing (IN PROGRESS)

- [ ] Add pytest unit tests
- [ ] Add integration tests  
- [ ] Add better error messages
- [ ] Add output truncation (optional)
- [ ] Add secret masking (optional)
- [ ] Test with slower commands
- [ ] Test with interactive commands
- [ ] Document PS1 initialization quirk

### Phase 3: Documentation (TODO)

- [ ] Update README.md
- [ ] Add usage examples
- [ ] Document parameters
- [ ] Document return format
- [ ] Add troubleshooting section
- [ ] **Document buffering behavior**
- [ ] **Document PS1 initialization fix**

---

## Part 10: Key Learnings Summary

### Technical Learnings

1. **PS1 Environment Variable Myth**
   - Setting `PS1` in env doesn't work for interactive bash
   - Must inject `PS1="..."` command after bash starts
   - This is a bash quirk, not Python or PTY issue

2. **PTY Output Buffering**
   - Python's stdout is line-buffered by default
   - Long-running tests can appear broken when actually passing
   - Always test with output redirect to file: `cmd > out.txt`
   - Exit flushes buffers, revealing truth

3. **File Logging is Critical for PTY Debugging**
   - Can't use print debugging (output is the test!)
   - File logging reveals what's actually in buffers
   - Verbose logging of regex matching attempts essential

4. **PS1 JSON Metadata Pattern is Brilliant**
   - Self-describing command completion
   - Survives concurrent output, partial reads
   - Provides rich metadata (exit code, working dir, Python path)
   - But requires correct initialization!

### Process Learnings

1. **Never Claim "95% Done" Without Testing**
   - We said this when tests were timing out
   - Classic "pond scum" behavior from AGENTS.md
   - ALWAYS TEST. FOR REAL. WITH OUTPUT CAPTURE.

2. **Simple Tests First**
   - `manual_test.py` saved us
   - `debug_test.py` with short timeout revealed PS1 issue
   - Don't jump to complex pytest before basic manual testing

3. **Logging Infrastructure Pays Off**
   - Spending 30 minutes on `logging_config.py` was worth it
   - Would have spent hours debugging without file logs
   - Log files in `~/.cache/crow-mcp/logs/` made debugging easy

4. **Import Patterns Matter**
   - Circular imports from `from crow_mcp.server import mcp`
   - Fixed by `from crow_mcp.server.main import mcp`
   - Python import system is fragile, be explicit

---

**Final Thought**: The OpenHands terminal is well-architected and battle-tested. Our job is not to reimplement it from scratch, but to **adapt it** for FastMCP and remove SDK dependencies. Preserve the hard parts (PTY handling, PS1 metadata), simplify the abstractions (no Action/Observation classes), and leverage FastMCP's capabilities.

**Real Final Thought**: NEVER claim something works without actually running it. The buffering incident proved that tests can pass even when we think they're failing. Always capture output to a file to see reality.

**True Final Thought**: PS1 environment variable doesn't work for interactive bash. This one thing took 2 hours to debug. File logging saved us. 🎯
