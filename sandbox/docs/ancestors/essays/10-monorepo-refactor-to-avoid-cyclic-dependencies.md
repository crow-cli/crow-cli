# Monorepo Refactor for Clean Package Boundaries

**Date**: February 15, 2026  
**Status**: PLANNED - NOT YET IMPLEMENTED

---

## THE PROBLEM

**Current structure is actually OK but not optimal**:

### The ACP Session is the Source of Truth

From `uv --project . run python -c "import acp; print(acp.schema.SessionInfo.model_json_schema())"`:

```json
{
  "properties": {
    "sessionId": {"type": "string"},  // REQUIRED
    "cwd": {"type": "string"},       // REQUIRED, must be absolute path
    "title": {"anyOf": [{"type": "string"}, {"type": "null"}]},  // optional
    "updatedAt": {"anyOf": [{"type": "string"}, {"type": "null"}]},  // optional
    "_meta": {"anyOf": [{"additionalProperties": true, "type": "object"}, {"type": "null"}]}  // reserved
  },
  "required": ["cwd", "sessionId"]
}
```

**Key insight**: "we want the state of the ACP session to be the state of the agent pretty much"

This means:
- Our database tables should be built ON TOP OF this ACP session schema
- The ACP session IS the source of truth, not just a container
- Session state = agent state = conversation history + working directory + MCP servers

### ACP Update Types - How the Agent Communicates with the Client

The agent sends updates via `session/update` notifications. Each update has a `sessionUpdate` discriminator field:

| sessionUpdate value | Type | Purpose |
|---------------------|------|---------|
| `"plan"` | AgentPlanUpdate | Agent's execution plan with entries |
| `"user_message_chunk"` | UserMessageChunk | User's message |
| `"agent_message_chunk"` | AgentMessageChunk | Agent's response |
| `"tool_call"` | ToolCallStart | Tool call started |
| `"tool_call_update"` | ToolCallUpdate | Tool call progress/status |
| `"usage_update"` | UsageUpdate | Token usage/cost info |
| `"available_commands_update"` | AvailableCommandsUpdate | Available commands |
| `"config_option_update"` | ConfigOptionUpdate | Config options |
| `"current_mode_update"` | CurrentModeUpdate | Current mode |

### Tool Call Content Types - How to Display MCP Outputs

When a tool call returns content, the `type` field tells the client how to display it:

| type | Content Type | Client Display |
|------|--------------|----------------|
| `"content"` | ContentToolCallContent | Text/image/audio content |
| `"diff"` | FileEditToolCallContent | **Show diff UI** (file edits) |
| `"terminal"` | TerminalToolCallContent | **Show terminal UI** |

**This is the "fixtures/configs" you mentioned!** The MCP tools should return content with the appropriate `type` so the ACP client knows how to render them.

**Current structure analysis**:

```
Current Structure (WORKING):
mcp-testing/
├── src/crow/agent/          # Core agent (ACP-native, react loop, etc.)
│   ├── acp_native.py
│   ├── extensions.py
│   └── ...
├── crow-mcp-server/         # MCP tools (file_editor, web_search, fetch)
│   ├── crow_mcp_server/
│   └── pyproject.toml      # ✅ Already has its own pyproject.toml!
├── pyproject.toml           # Has workspace config for crow-mcp-server
└── uv.lock
```

**Current state analysis**:
- ✅ crow-mcp-server has its own pyproject.toml (already a separate package)
- ✅ Root pyproject.toml has uv.workspace configured
- ✅ crow-mcp-server is in workspace members
- ❌ src/crow/agent is NOT in workspace (it's just a regular package)

**Problems with current structure**:

1. **src/crow/agent is not a workspace member** - Can't be installed independently
2. **No clear package boundaries** - Everything under src/crow/ is one big package
3. **Hard to extend** - Can't easily add new packages like crow-persistence, crow-skills
4. **Future-proofing** - When we add more packages, where do they go?

**What we actually want**:

```
Target Structure (CLEAR BOUNDARIES):
mcp-testing/
├── crow-agent/              # Programmatic SDK for long-running workflows
│   ├── crow/
│   └── pyproject.toml       # Can be installed independently: pip install crow-agent
├── crow-compact/            # Post-response token threshold checker
│   ├── crow_compact/
│   └── pyproject.toml       # Can be installed independently: pip install crow-compact
├── crow-core/               # ACP native react agent
│   ├── crow/
│   └── pyproject.toml       # Can be installed independently: pip install crow-core
├── crow-mcp-server/         # Built-in MCP tools
│   ├── crow_mcp_server/
│   └── pyproject.toml       # Already exists ✅
├── crow-persistence/        # Session persistence hook
│   ├── crow_persistence/
│   └── pyproject.toml       # New package
├── crow-skills/             # Context injection via skills
│   ├── crow_skills/
│   └── pyproject.toml       # New package
├── pyproject.toml           # Workspace configuration (uv workspace members)
└── uv.lock                  # Shared dependency lock
```

---

## THE SOLUTION

**Monorepo structure** with packages at root level (like `refs/software-agent-sdk`):

```
Target Structure (CLEAR BOUNDARIES):
mcp-testing/
├── crow-agent/              # Programmatic SDK for long-running workflows
│   └── pyproject.toml       # Can be installed independently: pip install crow-agent
├── crow-compact/            # Post-response token threshold checker
│   └── pyproject.toml       # Can be installed independently: pip install crow-compact
├── crow-core/               # ACP native react agent
│   └── pyproject.toml       # Can be installed independently: pip install crow-core
├── crow-mcp-server/         # Built-in MCP tools
│   └── pyproject.toml       # Can be installed independently: pip install crow-mcp-server
├── crow-persistence/        # Session persistence hook
│   └── pyproject.toml       # Can be installed independently: pip install crow-persistence
├── crow-skills/             # Context injection via skills
│   └── pyproject.toml       # Can be installed independently: pip install crow-skills
├── pyproject.toml           # Workspace configuration (uv workspace members)
└── uv.lock                  # Shared dependency lock
```

**Key Changes**:
1. **Each package has its own pyproject.toml** - independently installable (like crow-mcp-server already does)
2. **Workspace configuration** - uv manages intra-repo dependencies (already partially set up)
3. **Clear boundaries** - Each package has a single responsibility
4. **src/crow/agent moved to crow-core/** - Make it a proper workspace member

---

## THE EXTENSION PATTERN

**Flask-inspired**: Extensions receive direct references to agent:

```python
# crow-agent/extension.py
class Extension:
    def __init__(self, agent=None):
        self.agent = agent
        if agent is not None:
            self.init_app(agent)
    
    def init_app(self, agent):
        # Register hooks
        agent.hooks.register_hook("pre_request", self.pre_request)
        # Store reference
        agent.extensions['my_extension'] = self
    
    async def pre_request(self, ctx: ExtensionContext):
        # Access agent directly - it's all just Python!
        agent = ctx.agent
        # ... do anything the agent can do ...
```

**No context variables needed. No complex abstractions. Just Python code.**

---

## ACP/MCP INTEROP

**Problem**: ACP clients need to know how to display MCP tool outputs:

```
MCP Tool Output → ACP Display
─────────────────────────────
file_editor diff → Show diff UI
terminal output → Show terminal UI
web_search results → Show search results UI
```

**Solution**: **Fixtures/configs** to tell ACP client how to render:

```python
# crow-mcp-server/file_editor.py
@tool(
    name="file_editor",
    description="View, create, and edit files",
    fixtures={
        "display": "diff",  # Show diff UI for file changes
        "language": "text",  # Text content type
    }
)
async def file_editor(path: str, content: str, old_content: Optional[str] = None):
    """Edit a file with diff support"""
    # ... implementation ...
```

**ACP Client receives**:
```json
{
  "type": "tool_call",
  "id": "tool_123",
  "name": "file_editor",
  "arguments": {...},
  "fixtures": {
    "display": "diff",
    "language": "text"
  }
}
```

**ACP Client renders**:
- If `fixtures.display == "diff"` → Show side-by-side diff UI
- If `fixtures.display == "terminal"` → Show terminal UI
- If `fixtures.display == "content"` → Show plain content

---

## PRIORITY: USE ACP TERMINAL OVER MCP TERMINAL

**Smart interop**: When ACP client has native terminal, use it instead of MCP:

```python
# crow-core/agent.py
class Agent:
    def __init__(self, mcp_servers: List[MCPConfig], use_acp_terminal: bool = True):
        self.mcp_servers = mcp_servers
        self.use_acp_terminal = use_acp_terminal  # NEW!
    
    async def call_tool(self, tool_name: str, args: dict):
        # Priority: ACP terminal > MCP terminal
        if tool_name == "terminal" and self.use_acp_terminal:
            # Use ACP native terminal
            return await self.acp_client.create_terminal(...)
        else:
            # Use MCP tool
            return await self.mcp_client.call_tool(tool_name, args)
```

**Configuration**:
```yaml
# config.yaml
agent:
  use_acp_terminal: true  # Use ACP terminal if available
  use_acp_file_editor: false  # Use MCP file_editor (more powerful)
```

---

## IMPLEMENTATION PLAN

### Phase 1: Package Structure ✅ (Documentation)
- [ ] Create root-level package directories
- [ ] Set up workspace pyproject.toml
- [ ] Configure uv workspace members
- [ ] Document package responsibilities

### Phase 2: Extension System ✅ (Already Done)
- [x] ExtensionContext with direct agent reference
- [x] HookRegistry for registering hooks
- [x] Flask-inspired init_app pattern

### Phase 3: Package Migration
- [ ] Move crow-mcp-server to crow-mcp-server/
- [ ] Move persistence logic to crow-persistence/
- [ ] Move skills logic to crow-skills/
- [ ] Move compaction logic to crow-compact/
- [ ] Keep core agent in crow-core/

### Phase 4: ACP/MCP Interop
- [ ] Define fixture/config system
- [ ] Add fixtures to MCP tools
- [ ] Implement ACP terminal priority
- [ ] Test with real ACP clients

### Phase 5: Testing & Documentation
- [ ] Test each package independently
- [ ] Test package integration
- [ ] Update documentation
- [ ] Write examples

---

## WHY THIS ISN'T AS BIG AS IT SEEMS

**Current state is already 80% there**:
- ✅ Core agent architecture complete (ACP-native)
- ✅ Extension system designed (direct references)
- ✅ MCP integration working
- ✅ Session management working

**What's left is mostly refactoring**:
- Move files to new directories
- Update imports
- Add workspace configuration
- Define fixtures for ACP interop

**No new features needed** - just better organization!

---

## SUCCESS CRITERIA

**Before (Broken)**:
- ❌ Cyclic dependencies between packages
- ❌ Extensions can't import from other packages
- ❌ Hard to test packages independently
- ❌ Confusing import structure

**After (Fixed)**:
- ✅ No cyclic dependencies
- ✅ Extensions can use any package
- ✅ Each package independently testable
- ✅ Clear package boundaries
- ✅ ACP/MCP interop via fixtures
- ✅ Priority system for ACP vs MCP tools

---

## CONCLUSION

This refactor is about **removing artificial barriers** between packages. We're not changing the architecture - we're just organizing it better to match how we actually want to use it.

**The vision**: Extensions are just Python code. If you can write it, you can extend Crow. No proprietary APIs, no context variables, no magic - just direct Python code calling direct Python code.

**The monorepo** makes this possible by removing cyclic dependencies and giving each package its own identity while keeping them all in one place.

---

**Next Step**: Implement the package structure and migrate code gradually. No rush - we can do this iteratively while keeping the current system working.
