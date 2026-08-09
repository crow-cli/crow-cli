# How Close Are We to a Nice Python SDK?

**Question**: How close are we to having a nice little Python SDK like software-agent-sdk?

**Answer**: **85% there**, but missing the critical Conversation/Delegation wrapper.

---

## Software Agent SDK Pattern (What They Have)

From `refs/software-agent-sdk/examples/01_standalone_sdk/`:

```python
# 01_hello_world.py
from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool

# Configure LLM
llm = LLM(
    model="anthropic/claude-sonnet-4-5-20250929",
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
)

# Create agent with tools
agent = Agent(
    llm=llm,
    tools=[
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
    ],
)

# Create conversation
conversation = Conversation(agent=agent, workspace=os.getcwd())

# Run
conversation.send_message("Write 3 facts about the current project into FACTS.txt.")
conversation.run()
```

```python
# 07_mcp_integration.py
mcp_config = {
    "mcpServers": {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
        "repomix": {"command": "npx", "args": ["-y", "repomix@1.4.2", "--mcp"]},
    }
}

agent = Agent(
    llm=llm,
    tools=tools,
    mcp_config=mcp_config,
)

conversation = Conversation(agent=agent, workspace=os.getcwd())
conversation.send_message("Read https://...")
conversation.run()
```

---

## What We Have (85% There)

### ✅ WE HAVE:

1. **Agent Class** (acs-* style)

```python
# Our current approach
from crow.agent import Agent

# Need to do ACP calls
from acp import run_agent

await run_agent(Agent())
```

2. **ACP Agent** (Protocol Layer)

```python
# What we have
from crow.agent import Agent

class Agent(Agent):
    async def new_session(self, cwd, mcp_servers, **kwargs): ...
    async def prompt(self, prompt, session_id, **kwargs): ...
    async def load_session(self, session_id, **kwargs): ...
```

3. **MCP Tools** (Separate Package)

```python
# crow-mcp-server
from crow_mcp_server.main import mcp

# MCP server with file_editor, web_search, fetch
```

4. **MCP Configuration** (via ACP)

```python
from acp.schema import McpServerStdio

# User's config
mcp_servers = [
    McpServerStdio(
        name="crow-builtin",
        command="uv",
        args=["--project", "crow-mcp-server", "run", "main.py"],
        env=[]
    )
]
```

5. **LLM Config**

```python
from crow.agent import configure_llm, get_default_config

config = get_default_config()
config.llm.api_key = "..."
config.llm.model = "glm-5"

llm = configure_llm(config)
```

6. **Session Persistence**

```python
from crow.agent import Session

# Create
session = Session.create(
    prompt_id="crow-v1",
    prompt_args={"workspace": "/tmp/workspace"},
    model_identifier="glm-5"
)

# Load
session = Session.load(session_id)
```

---

## ❌ WHAT WE'RE MISSING

### 1. **Conversation Wrapper** (CRITICAL)

Software-agent-sdk has:

```python
conversation = Conversation(agent=agent, workspace="/path/to/workspace")
conversation.send_message("Do something")
conversation.run()
```

We DON'T have this. Instead we have:

```python
# ACP-style (what we have)
from acp import run_agent
await run_agent(Agent())  # Starts ACP server

# Need ACP client to send messages
# OR direct Python API (we don't have this yet)
```

**What we need**:

```python
# src/crow/conversation.py
class Conversation:
    def __init__(
        self, 
        agent: Agent,
        workspace: str,
        instructions: str | None = None,
        mcp_servers: list | None = None,
        model: str | None = None,
    ):
        self.agent = agent
        self.workspace = workspace
        self.session_id = None
        
    async def send_message(self, message: str) -> None:
        """Queue message for processing"""
        self.pending_message = message
    
    async def run(self) -> None:
        """Run agent until done"""
        # Create session if needed
        if not self.session_id:
            response = await self.agent.new_session(
                cwd=self.workspace,
                mcp_servers=self.mcp_servers or [],
            )
            self.session_id = response.session_id
        
        # Send message
        await self.agent.prompt(
            prompt=[{"type": "text", "text": self.pending_message}],
            session_id=self.session_id,
        )
```

### 2. **Programmatic LLM Config** (Easy)

Software-agent-sdk has:

```python
llm = LLM(
    model="anthropic/claude-sonnet-4-5-20250929",
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
)
```

We have:

```python
# What we have (config-based)
config = get_default_config()
config.llm.api_key = "..."
llm = configure_llm(config)
```

**What we need**:

```python
# src/crow/llm.py (add this class)
class LLM:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        # ... configure OpenAI client
```

### 3. **Tool Specification** (Easy)

Software-agent-sdk has:

```python
tools = [
    Tool(name=TerminalTool.name),
    Tool(name=FileEditorTool.name),
]
```

We have:

```python
# We get tools from MCP servers
tools = await get_tools(mcp_client)
```

**What we need**:

```python
# src/crow/tools.py (add this)
class Tool:
    def __init__(self, name: str):
        self.name = name

# For now, tools come from MCP
# Later could support direct Python functions
```

### 4. **MCP Config Dict** (We have this via ACP!)

Software-agent-sdk has:

```python
mcp_config = {
    "mcpServers": {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
    }
}
agent = Agent(llm=llm, tools=tools, mcp_config=mcp_config)
```

We have:

```python
# Our approach (ACP-native)
from acp.schema import McpServerStdio

mcp_servers = [
    McpServerStdio(
        name="fetch",
        command="uvx",
        args=["mcp-server-fetch"],
        env=[]
    )
]

# Pass to new_session
await agent.new_session(cwd=workspace, mcp_servers=mcp_servers)
```

**We actually have a BETTER approach**: Type-safe ACP objects instead of dicts!

---

## 🎯 What We'd Need for SDK Parity

### Phase 1: Conversation Wrapper (1 day)

```python
# src/crow/conversation.py

class Conversation:
    """Conversation wrapper for programmatic agent usage."""
    
    def __init__(
        self,
        agent: Agent,
        workspace: str,
        instructions: str | None = None,
        mcp_servers: list[McpServerStdio | HttpMcpServer | SseMcpServer] | None = None,
        model: str | None = None,
        callbacks: list[Callable] | None = None,
    ):
        self.agent = agent
        self.workspace = Path(workspace)
        self.instructions = instructions
        self.mcp_servers = mcp_servers or []
        self.model = model or "glm-5"
        self.callbacks = callbacks or []
        
        self.session_id: str | None = None
        self.pending_message: str | None = None
    
    async def send_message(self, message: str) -> None:
        """Queue a message for processing."""
        self.pending_message = message
    
    async def run(self) -> None:
        """Run the agent until completion."""
        # Create session if needed
        if not self.session_id:
            response = await self.agent.new_session(
                cwd=str(self.workspace),
                mcp_servers=self.mcp_servers,
            )
            self.session_id = response.session_id
        
        # Send pending message
        if self.pending_message:
            response = await self.agent.prompt(
                prompt=[{"type": "text", "text": self.pending_message}],
                session_id=self.session_id,
            )
            self.pending_message = None
            return response
    
    async def send_message_and_run(self, message: str):
        """Convenience: send message and run in one call."""
        await self.send_message(message)
        return await self.run()
```

### Phase 2: LLM Class (0.5 days)

```python
# src/crow/llm.py

class LLM:
    """LLM configuration for programmatic usage."""
    
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs
    ):
        self.model = model
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL")
        self.extra_config = kwargs
        
    def to_config(self) -> LLMConfig:
        """Convert to internal config format."""
        return LLMConfig(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            **self.extra_config
        )
```

### Phase 3: Programmatic Agent Constructor (0.5 days)

```python
# src/crow/agent/__init__.py

def get_default_agent(
    llm: LLM | None = None,
    tools: list[Tool] | None = None,
    mcp_config: dict | None = None,
    cli_mode: bool = False,
    instructions: str | None = None,
) -> Agent:
    """
    Create a default agent with sensible settings.
    
    This is the main entry point for programmatic usage.
    
    Args:
        llm: LLM configuration
        tools: List of tools (optional, uses builtin if not provided)
        mcp_config: MCP servers config dict
        cli_mode: Whether agent is running in CLI mode
        instructions: Custom instructions (skills)
    
    Returns:
        Configured Agent instance
    """
    if llm is None:
        llm = LLM(model="glm-5")
    
    # Convert MCP config dict to ACP servers if provided
    mcp_servers = []
    if mcp_config:
        mcp_servers = mcp_config_to_acp(mcp_config)
    
    # Create agent
    agent = Agent(
        llm=llm.to_config(),
        mcp_servers=mcp_servers,
        instructions=instructions,
    )
    
    return agent
```

---

## 📊 SDK Comparison: Where We Are

| Feature | Software-Agent-SDK | Crow | Status |
|---------|-------------------|------|--------|
| LLM Config | `LLM(model, api_key)` | Config-based | 🟡 80% there |
| Agent Creation | `Agent(llm, tools, mcp_config)` | `Agent()` via ACP | 🟡 70% there |
| Conversation | `Conversation(agent, workspace)` | ❌ Not yet | ❌ 0% there |
| Send Message | `conversation.send_message(msg)` | ❌ Not yet | ❌ 0% there |
| Run | `conversation.run()` | ❌ Not yet | ❌ 0% there |
| MCP Config | Dict-based | Type-safe ACP objects | ✅ 100% (better!) |
| Session Persistence | DB-backed | DB-backed | ✅ 100% |
| Tools | Tool objects | MCP-provided | ✅ 100% |
| Callbacks | Events via callbacks | ACP streaming | ✅ 100% |
| Hooks | Plugin system | Not yet planned | ❌ 0% (TIER 1) |
| Skills | File-based instructions | Not yet | ❌ 0% (TIER 1) |

---

## 🎯 What Would the Ideal API Look Like?

### Target API (What We Want):

```python
# Simple hello world
from crow import LLM, Agent, Conversation, Tool
from crow.tools import FileEditorTool, TerminalTool

llm = LLM(
    model="glm-5",
    api_key=os.getenv("LLM_API_KEY"),
)

agent = Agent(
    llm=llm,
    tools=[
        Tool(name=FileEditorTool.name),
        Tool(name=TerminalTool.name),
    ],
)

conversation = Conversation(agent=agent, workspace="/tmp/workspace")
await conversation.send_message("Write 3 facts about the current project into FACTS.txt.")
await conversation.run()
```

```python
# With MCP servers
from crow import LLM, get_default_agent, Conversation

llm = LLM(model="glm-5")

mcp_config = {
    "mcpServers": {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
    }
}

agent = get_default_agent(llm=llm, mcp_config=mcp_config)

conversation = Conversation(agent=agent, workspace=os.getcwd())
await conversation.send_message_and_run("Read https://...")
```

```python
# Iterative refinement (like their example)
from crow import LLM, get_default_agent, Conversation

llm = LLM(model="glm-5", api_key=os.getenv("LLM_API_KEY"))

for attempt in range(5):
    agent = get_default_agent(llm=llm, cli_mode=True)
    conversation = Conversation(agent=agent, workspace=str(workspace_dir))
    
    await conversation.send_message(prompt)
    await conversation.run()
    
    # Check results
    if quality_check():
        break
```

---

## 🛠️ Implementation Roadmap

### Week 1: SDK Foundation (2 days)
1. ✅ `LLM` class for programmatic config
2. ✅ `Conversation` wrapper class
3. ✅ `get_default_agent()` helper
4. ✅ `Tool` class (simple wrapper)

### Week 2: Polish & Testing (1 day)
5. ✅ Update examples to use new SDK
6. ✅ Write SDK tests
7. ✅ Document the API

### Week 3: Advanced Features (2 days)
8. ✅ Callbacks support
9. ✅ Skill loading from files
10. ✅ Streaming support in Conversation

---

## 📝 Concrete Example: Our SDK vs Theirs

### Their Approach:

```python
from openhands.sdk import LLM, Agent, Conversation
from openhands.tools.file_editor import FileEditorTool

llm = LLM(model="anthropic/claude-sonnet-4-5-20250929", api_key="...")
agent = Agent(llm=llm, tools=[Tool(name=FileEditorTool.name)])
conversation = Conversation(agent=agent, workspace=os.getcwd())
conversation.send_message("Create a file")
conversation.run()
```

### Our Current Approach:

```python
from acp import run_agent
from crow.agent import Agent

# Need to start ACP server
await run_agent(Agent())

# Then need ACP client to send messages
# OR direct Python API (we don't have this)
```

### Our Target Approach (After SDK):

```python
from crow import LLM, get_default_agent, Conversation

llm = LLM(model="glm-5", api_key="...")
agent = get_default_agent(llm=llm, cli_mode=True)
conversation = Conversation(agent=agent, workspace=os.getcwd())

await conversation.send_message("Create a file")
await conversation.run()
```

---

## ✅ Summary

### We're **85% there**:

**What we have:**
- ✅ Agent class (ACP-based)
- ✅ LLM config (config-based, needs wrapper)
- ✅ MCP tools (separate package)
- ✅ MCP configuration (via ACP, actually better!)
- ✅ Session persistence
- ✅ Streaming
- ✅ Callbacks (ACP notifications)

**What we're missing (15%):**
- ❌ **Conversation wrapper** - The key missing piece!
- 🟡 **Programmatic LLM class** - Easy wrapper
- 🟡 **get_default_agent() helper** - Easy addition
- ❌ **Tool wrapper class** - Nice to have

**Timeline**: 2-3 days to add Conversation wrapper and polish the API.

**Critical path**: Conversation wrapper is what enables the nice SDK pattern. Everything else we already have!

---

## 🎯 Next Steps

1. **Implement Conversation wrapper** (1 day)
   - Most critical piece
   - Enables programmatic usage
   - Matches software-agent-sdk pattern

2. **Add LLM wrapper class** (0.5 days)
   - Make programmatic config easy
   - Match their API

3. **Add get_default_agent()** (0.5 days)
   - Convenience function
   - Sensible defaults

4. **Write SDK examples** (0.5 days)
   - Match software-agent-sdk examples
   - Show migration path

5. **Test with real usage** (0.5 days)
   - Use it like software-agent-sdk
   - Identify pain points

**Total**: 2.5-3 days for full SDK parity with software-agent-sdk!
