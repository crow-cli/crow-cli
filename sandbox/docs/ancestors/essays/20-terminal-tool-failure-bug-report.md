# Terminal Tool Failure: A Bug Report from the Inside

## Session Context

**Agent uptime:** ~24 hours (estimate, no `date` command available)

**Last known working terminal command:**
```
find /home/thomas/src/projects/mcp-testing -name "streaming_react.py" -o -name "*streaming*react*"
```
Result: Successfully returned file paths.

**Also worked:**
```
ls
```
(with `reset=true`) - Successfully listed directory contents.

## The Failure

**Command attempted:**
```
git log --oneline -20
```

**Error received:**
```
Error: name 'CMD_OUTPUT_PS1_BEGIN' is not defined
```

## Error Analysis

The error message `CMD_OUTPUT_PS1_BEGIN is not defined` is NOT a shell error. It's a **Python NameError** from inside the terminal tool implementation.

### What this suggests:

1. **Internal tool bug:** `CMD_OUTPUT_PS1_BEGIN` appears to be a constant used by the `crow-mcp-terminal` tool for parsing terminal output (likely marking the beginning of PS1 prompt output).

2. **State corruption:** The tool may have accumulated some corrupted state over the ~24 hour session. Python NameError at runtime suggests something that should have been defined at module load time wasn't.

3. **Not command-specific:** The error occurs regardless of command:
   - `git log --oneline -20` - fails
   - `echo "test"` - fails
   - Various shell wrappers (`/bin/bash -c '...'`) - fail

4. **Reset doesn't fix it:** Using `reset=true` parameter doesn't resolve the issue.

## Commands That Failed

| Command | Error |
|---------|-------|
| `git log --oneline -20` | `Error: name 'CMD_OUTPUT_PS1_BEGIN' is not defined` |
| `echo "test"` | Same error |
| `/bin/bash -c 'git log --oneline -20'` | Same error |
| `bash -c "cd /home/thomas/src/projects/mcp-testing && git log --oneline -20"` | Same error |
| `git -C /home/thomas/src/projects/mcp-testing log --oneline -20` | Same error |

## Commands That Still Worked

| Tool | Status |
|------|--------|
| `crow-mcp_file_editor` | ✅ Working |
| `crow-mcp_web_search` | ✅ Working |
| `crow-mcp_web_fetch` | ✅ Working |
| `crow-mcp_terminal` | ❌ Broken |

## Hypothesis: Long-Running Session State

After ~24 hours of continuous operation, the terminal tool may have accumulated corrupted state. Possible causes:

1. **Memory corruption:** Some internal buffer or parser state got into an invalid state.

2. **Reference leak:** An object that defines `CMD_OUTPUT_PS1_BEGIN` was garbage collected or never properly initialized in a long-running async context.

3. **Async event loop issue:** The terminal tool may use async I/O that degraded over time.

4. **Import issue:** Late evaluation of some lazy import that failed silently earlier.

## Not Related to: maximally deserialize JSON hack

User noted they have a hack in the agent for maximal JSON deserialization:

```python
# agent.py - not the cause
def maximal_deserialize(data):
    """Recursively drills into dictionaries and lists..."""
```

This is unrelated to the terminal tool failure. The error occurs at the tool invocation level, not in agent code.

## Contrast with Other Agents

User reports another agent session has a working terminal. This confirms:

1. The bug is session-specific, not system-wide
2. Fresh sessions don't have this problem
3. It's likely related to long-running state

## Recommendation: Session Metadata

User suggests adding to system prompt:

1. **Timestamp** - When session started
2. **Directory tree** - `tree -L5 -I node_modules -I __pycache__ -I dist -I *.egg_info`
3. **Current date** - Via terminal `date` command (if terminal works)

This would give the agent temporal and spatial awareness, and help diagnose issues like "how long have I been running?"

## Workaround

When terminal fails:
1. Use `crow-mcp_file_editor` for file operations
2. Ask user to run terminal commands manually and paste output
3. Request session restart if terminal is critical

## The Irony

I am writing this bug report **using the tool that still works** (file_editor) about the tool that doesn't (terminal). This essay will outlive my broken terminal session.

## What We Missed

Because terminal was broken, I could not:
- See `git log` to understand recent commits
- Run `date` to know what time it is
- Check process state or system info
- Run any shell commands

## Moral

Long-running agent sessions need:
1. Better state management in tools
2. Session metadata in context
3. Graceful degradation when tools fail
4. Self-diagnostic capabilities

---

*"The terminal is dead. Long live the file editor."*

**Next session: Add session start timestamp and directory tree to context.**


# FIXED!

Turns out agent did a reset and the terminal works fine. Need to note that in system prompt for future agents. Or in the description of the terminal tool for reset.
