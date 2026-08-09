# Where We Are Now: A Codebase Archaeology

## The Question

Before we build hooks, before we build extensions, we need to know: **what do we actually have?**

This essay is an archaeological dig through the codebase - not just the files, but the *intentions* embedded in them. What did we try to build? What actually works? What's遗留 (left behind)?

---

## The Structure

```
mcp-testing/
├── src/crow/                    # The main package
│   ├── acp_agent.py             # OLD: ACP wrapper (should be deleted)
│   ├── agent/
│   │   ├── acp_native.py        # NEW: Merged ACP-native Agent ✅
│   │   ├── agent.py             # OLD: Standalone Agent (duplication)
│   │   ├── session.py           # Session management ✅
│   │   ├── db.py                # SQLAlchemy models ✅
│   │   ├── llm.py               # LLM configuration ✅
│   │   ├── mcp_client.py        # MCP client setup ✅
│   │   ├── prompt.py            # Template rendering ✅
│   │   ├── config.py            # Configuration ✅
│   │   ├── react.py             # OLD: Legacy react loop
│   │   └── prompts/             # Jinja2 templates
│   └── scripts/
│       ├── example_agent.py     # Usage example
│       └── test_acp_client.py   # Test client
│
├── mcp-servers/
│   ├── file_editor/             # ✅ COMPLETE: Clean FastMCP server
│   ├── terminal/                # ❌ INCOMPLETE: Has impl but no FastMCP server
│   └── web/                     # 🔶 PARTIAL: search.py + fetch.py (not combined)
│
├── kernel_kernel.py             # Jupyter kernel for delegation
├── search.py                    # MCP server for web search (root level - WHY?)
│
├── tests/
│   ├── unit/                    # Unit tests (28+ tests passing)
│   ├── integration/             # Integration tests
│   └── e2e/                     # E2E tests with REAL LLM/DB/MCP
│
└── docs/essays/                 # This memory bank
```

---

## What Actually Works

### 1. ACP-Native Agent (acp_native.py)

The merged `Agent(acp.Agent)` class is the real deal. It实现了:

```python
class Agent(Agent):  # Inherits from acp.Agent
    def __init__(self, db_path: str = "sqlite:///mcp_testing.db"):
        self._db_path = db_path
        self._exit_stack = AsyncExitStack()  # ✅ Proper resource management
        self._sessions: dict[str, Session] = {}  # In-memory cache
        self._mcp_clients: dict[str, Any] = {}   # session_id -> client
        self._tools: dict[str, list[dict]] = {}  # session_id -> tools
        self._llm = configure_llm(debug=False)
    
    # ACP Protocol Methods
    async def initialize(...) -> InitializeResponse: ...
    async def authenticate(...) -> AuthenticateResponse: ...
    async def new_session(...) -> NewSessionResponse: ...
    async def load_session(...) -> LoadSessionResponse: ...
    async def prompt(...) -> PromptResponse: ...
    
    # Business Logic (from old Agent)
    def _send_request(self, session_id): ...
    def _process_chunk(self, ...): ...
    def _process_response(self, ...): ...
    def _process_tool_call_inputs(self, ...): ...
    async def _execute_tool_calls(self, ...): ...
    async def _react_loop(self, session_id, max_turns=50000): ...
    
    async def cleanup(self) -> None:
        await self._exit_stack.aclose()  # ✅ Cleanup guaranteed
```

**41 tests passing** including live E2E with real LLM + DB + MCP.

### 2. Session Management (session.py)

The `Session` class manages conversation state:

```python
class Session:
    def __init__(self, session_id: str, db_path: str):
        self.session_id = session_id
        self.messages = []  # In-memory conversation
        self.conv_index = 0  # Event counter
    
    def add_message(self, role, content, ...): ...
    def add_assistant_response(self, thinking, content, tool_calls, tool_results): ...
    
    @classmethod
    def create(cls, prompt_id, prompt_args, tool_definitions, ...) -> Session: ...
    
    @classmethod
    def load(cls, session_id, db_path) -> Session: ...
```

Key insight: **Session is persisted to DB, but kept in-memory for performance.**

### 3. Persistence Layer (db.py)

SQLAlchemy models:

```python
class Prompt(Base):
    __tablename__ = "prompts"
    id = Column(Text, primary_key=True)
    template = Column(Text)  # Jinja2 template

class Session(Base):
    __tablename__ = "sessions"
    session_id = Column(Text, primary_key=True)
    prompt_id = Column(Text, ForeignKey("prompts.id"))
    system_prompt = Column(Text)  # Rendered prompt (cached)
    tool_definitions = Column(JSON)
    request_params = Column(JSON)
    model_identifier = Column(Text)

class Event(Base):
    __tablename__ = "events"
    session_id = Column(Text, ForeignKey("sessions.session_id"))
    conv_index = Column(Integer)
    role = Column(Text)  # user, assistant, tool
    content = Column(Text)
    reasoning_content = Column(Text)
    tool_call_id = Column(Text)
    tool_call_name = Column(Text)
    tool_arguments = Column(JSON)
```

**This is the "wide" schema**: Every row is a turn, no joins needed.

### 4. MCP Tools

**file_editor** - Complete FastMCP server:
- Commands: view, create, str_replace, insert, undo_edit
- Clean implementation, no openhands SDK dependencies
- Rich error messages for LLM guidance
- History for undo
- Encoding detection

**terminal** - Has implementation from openhands, but:
- `main.py` just prints "Hello from terminal!" 
- Depends on `openhands.sdk.*` - coupled to their SDK
- Needs to be rebuilt as FastMCP server like file_editor

**web**:
- `search.py` - SearXNG search (FastMCP)
- `fetch.py` - URL fetching with robots.txt (raw MCP, needs FastMCP conversion)
- Not combined into single server

### 5. Test Suite

```
tests/
├── unit/
│   ├── test_mcp_lifecycle.py      # AsyncExitStack pattern ✅
│   ├── test_prompt_persistence.py  # Prompt management ✅
│   ├── test_file_editor.py         # Partial file editor tests
│   ├── test_compaction_feature.py  # ❌ FAILING: Rail-guard for future
│   └── test_merged_agent.py        # ❌ SOME FAILING: Rail-guard for cleanup
│
├── integration/
│   └── test_session_lifecycle.py   # Session + DB integration
│
└── e2e/
    ├── test_agent_e2e.py           # Agent with real MCP + DB
    ├── test_file_editor_mcp.py     # File editor MCP E2E
    └── test_live_llm_e2e.py        # Real LLM + DB + MCP (comprehensive)
```

**41 tests passing**. The failing tests are intentional TDD rail-guards.

---

## What's Confusing / Needs Cleanup

### 1. Three Agent Classes!

```
src/crow/acp_agent.py          # CrowACPAgent - wrapper (DEPRECATED)
src/crow/agent/agent.py        # Agent - standalone (DUPLICATION)
src/crow/agent/acp_native.py   # Agent - merged (THE GOOD ONE)
```

The merged agent exists, but the old ones weren't deleted. **This needs cleanup.**

### 2. Two React Loops

```
src/crow/agent/react.py        # OLD: Standalone functions
src/crow/agent/acp_native.py   # NEW: _react_loop method on agent
```

The legacy `react.py` still exists. It imports from `database` (old module) directly.

### 3. MCP Server Locations

```
mcp-testing/search.py          # Why at root?
mcp-testing/mcp-servers/web/search.py  # Duplicate?
```

### 4. File Editor Not Connected

The file_editor MCP server is complete, but the agent uses `search.py` hardcoded:

```python
# acp_native.py line 136
mcp_client = setup_mcp_client("src/crow/mcp/search.py")
```

**The agent doesn't use the tools we built!**

### 5. kernel_kernel.py

A Jupyter kernel wrapper exists but isn't integrated. It was intended for:
- IPython cell execution
- Persistent Python state
- Shell commands via subprocess

Now we see it differently: **delegation mechanism for subagents.**

---

## The Gap Between Intent and Reality

### What We Said We Built

From IMPLEMENTATION_PLAN.md:
> ✅ COMPLETE - Single Agent(acp.Agent) class, 41 tests passing

### What We Actually Have

- ✅ Merged agent class exists and works
- ❌ Old agent classes still exist (confusion)
- ❌ Agent hardcoded to use search.py, not file_editor
- ❌ Terminal MCP not implemented as FastMCP server
- ❌ No hooks framework yet
- ❌ No skills implementation
- ❌ No compaction implementation
- ❌ No delegation mechanism wired up

### The Tests Tell The Truth

```
41 tests passing = Core agent works
8 compaction tests failing = Compaction not implemented
6 merged_agent tests failing = Cleanup not done
```

**The failing tests are our roadmap.**

---

## The Delegation Question

`kernel_kernel.py` is fascinating. It's a Jupyter kernel wrapper that:

1. Spins up a Python kernel with any venv
2. Executes code with persistent state
3. Returns structured output (stdout, stderr, result, error)

**Original intent**: Replacement for bash?

**New understanding**: This is how delegation works!

```python
# Future vision
from crow import Agent, PythonEnv

# Create subagent with specific environment
subagent = Agent(
    instructions="You are a test writer",
    python_env=PythonEnv("path/to/venv"),  # Uses kernel_kernel
    mcp_servers=["./mcp-servers/file_editor"],
)

# Delegate task
result = await subagent.prompt("Write tests for auth.py")
```

The kernel maintains persistent state across executions. Perfect for subagent isolation.

---

## The Configuration Gap

Current config (llm.py, config.py):

```python
# Environment variables
ZAI_API_KEY = os.getenv("ZAI_API_KEY")
ZAI_BASE_URL = os.getenv("ZAI_BASE_URL")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "glm-5")
DATABASE_PATH = os.getenv("DATABASE_PATH", "sqlite:///mcp_testing.db")
DEFAULT_MCP_PATH = os.getenv("DEFAULT_MCP_PATH", "src/crow/mcp/search.py")
```

**What's missing:**
- No way to pass API keys programmatically
- No way to configure multiple MCP servers
- No way to add skills
- No way to attach hooks
- No programmatic agent creation like software-agent-sdk

The ACP protocol receives `mcp_servers` in `new_session()` but we ignore it!

```python
async def new_session(
    self,
    cwd: str,
    mcp_servers: list[...],  # ← ACP client gives us MCP servers
    **kwargs,
) -> NewSessionResponse:
    # TODO: Use mcp_servers from ACP client  ← WE IGNORE IT
    mcp_client = setup_mcp_client("src/crow/mcp/search.py")  # Hardcoded!
```

---

## The Hook Opportunity

Looking at software-agent-sdk, their hook system:

```python
# From their tests
class HookConfig:
    pre_tool_use: list[HookDefinition]
    post_tool_use: list[HookDefinition]
    # ...

# hooks.json
{
    "hooks": {
        "pre_tool_use": [
            {"hooks": [{"command": "my-hook"}]}
        ]
    }
}
```

They use JSON config files. We can do better with Python:

```python
# Our vision
from crow import Agent, Hook, HookContext

class MySkill(Hook):
    """A pre-request hook that injects context."""
    
    async def __call__(self, ctx: HookContext) -> HookContext:
        if "database" in ctx.request.lower():
            schema = load_schema()
            ctx.session.add_message("user", f"DB Schema: {schema}")
        return ctx

agent = Agent(
    hooks={
        "pre_request": [MySkill()],
    }
)
```

---

## What We Need To Do

### Phase 1: Cleanup (Immediate)

1. **Delete old agent files**
   - Remove `src/crow/acp_agent.py`
   - Remove `src/crow/agent/agent.py`
   - Remove `src/crow/agent/react.py`
   
2. **Update imports**
   - Point everything to `crow.agent.acp_native.Agent`
   
3. **Connect file_editor**
   - Remove hardcoded `search.py` path
   - Use MCP servers from ACP client when provided
   - Fall back to builtin MCP when not provided

### Phase 2: Builtin MCP Server

1. **Combine into one package:**
   - terminal (build as FastMCP)
   - file_editor (already done)
   - web_search (exists)
   - fetch (convert to FastMCP)

2. **Create `mcp-servers/builtin/`:**
   - Own `pyproject.toml`
   - Own `.venv` (managed by uv workspace)
   - Single entry point

### Phase 3: Hook Framework

1. **Design Hook Protocol:**
   ```python
   class Hook(Protocol):
       async def __call__(self, ctx: HookContext) -> Optional[HookContext]: ...
   ```

2. **Hook points in react loop:**
   - `pre_request` - Before LLM call (skills)
   - `post_response` - After LLM response (tool checking)
   - `post_tool` - After tool execution (caching)
   - `post_react` - After loop ends (ralph loops)
   - `mid_react` - Check for compaction

3. **Plugin discovery via entry points:**
   ```toml
   [project.entry-points."crow.hooks"]
   my_skill = "my_package.hooks:MySkill"
   ```

### Phase 4: Programmatic Agent

```python
# Target API
from crow import Agent, Conversation

agent = Agent(
    instructions="You are a helpful assistant",
    mcp_servers=["./mcp-servers/builtin"],
    hooks=[MySkill(), CompactionHook()],
    db_path="sqlite:///my_agent.db",
)

# ACP mode
await run_agent(agent)

# Script mode
conv = Conversation(agent=agent, workspace="/workspace")
response = await conv.send_message("Hello!")
print(response)

# Delegation mode
subagent = Agent(instructions="You are a specialist")
result = await subagent.prompt(research_task)
```

---

## Summary

### What Works
- Merged ACP agent (41 tests passing)
- Session persistence (DB + in-memory cache)
- file_editor MCP server (complete, clean)
- Live E2E tests with real LLM/DB/MCP

### What's Broken
- Old agent files still exist (confusion)
- Agent hardcoded to search.py (not using builtin tools)
- Terminal MCP not a FastMCP server
- No hooks framework
- No skills/compaction
- No programmatic agent creation
- ACP client's MCP servers ignored

### What's Next
1. **Cleanup** - Remove confusion, update imports
2. **Connect** - Wire up builtin MCP, respect ACP client
3. **Build** - Hook framework + builtin MCP server
4. **Extend** - Skills, compaction, delegation

---

## The Deeper Pattern

We're building **ACP-native**, not "our own framework":

- ACP IS the agent framework
- MCP IS the tool calling framework  
- FastMCP IS the MCP implementation
- Our code just connects them with a react loop

Hooks are the only extension mechanism we need to invent, because ACP doesn't specify react loop hooks. Everything else is protocol compliance.

**The agent is 90% protocol, 10% react loop.**

---

*Essay编号: 03*
*Topic: Codebase archaeology - where we are and what's next*
*Dialectic: "It works" → Tests reveal gaps → "Here's what actually works"*
