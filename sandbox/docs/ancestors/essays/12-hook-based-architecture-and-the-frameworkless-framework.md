# Hook-Based Architecture and The Frameworkless Framework

**Date**: Current Session  
**Status**: SYNTHESIS - Architectural Breakthrough

---

## Introduction: The Dialectical Journey

This essay documents a synthesis between two seemingly opposed approaches to building agent frameworks:

1. **Thesis (X)**: "Everything is a hook" - The maximalist extension-based architecture where state management, prompts, persistence, compaction, and skills are ALL just callbacks injected into a minimal core.

2. **Antithesis (~X)**: Gemini's pragmatic critique - The observation that we have working code (~281 lines) that's already shipped by making smart trade-offs (sync OpenAI with async MCP, hardcoded persistence, `StopIteration` unpacking hack).

3. **Synthesis (Y)**: The understanding that these aren't opposed at all. The working code IS the minimal core. The hooks ARE the clean abstraction. The path forward is to formalize what's already there without bloating the core.

**The breakthrough**: We don't need to choose between pragmatic shipping and clean architecture. The 281-line react loop IS the frameworkless framework. Everything else grows around it as hooks.

---

## Part 1: The Thesis - Everything is a Hook

### The Core Realization

Traditional frameworks build UP from abstractions:

```
Framework Base → Abstract Agent → Tool Registry → State Manager → Message Router → Agent
```

The results are frameworks with 10,000+ lines of code, multiple abstraction layers, and the feeling that you're fighting the framework more than using it.

**The frameworkless framework pattern inverts this:**

```
Protocol Wrappers (OpenAI SDK, FastMCP) → React Loop → Hook Points → Extensions
```

The core is minimal. Everything else hooks in.

### What We Discovered

In `streaming_async_react_with_db.py` (281 lines), we have:

```python
dependencies = [
    "openai>=2.16.0",   # Wrapper over chat/completions OpenAPI.json
    "fastmcp>=2.14.4",  # Wrapper over MCP schema.json
]
```

**This is an agent.** Just two protocols connected by business logic.

The "frameworkless" insight:
- ❌ Don't build tool orchestration abstractions (FastMCP handles this)
- ❌ Don't build streaming abstractions (OpenAI SDK handles this)
- ❌ Don't build state management abstractions (DB + hooks handle this)
- ✅ DO connect protocols with minimal code
- ✅ DO provide hook points for extensions
- ✅ DO make extensions have direct agent access (Flask pattern)

### The Hook Universe

**Everything becomes a hook:**

```python
class Agent:
    """Minimal ACP agent. Everything else is hooks."""
    
    def __init__(self):
        self.hooks = HookRegistry()
        # Minimal core - just the loop and protocols
        
# Prompts are hooks:
class PromptManager:
    def init_app(self, agent):
        agent.hooks.register("pre_request", self.render_system_prompt)
    
    async def render_system_prompt(self, ctx):
        template = agent.load_template(ctx.template_name)
        system_prompt = template.render(**ctx.args)
        ctx.messages = [{"role": "system", "content": system_prompt}, *ctx.messages]

# Persistence is a hook:
class PersistenceExtension:
    def init_app(self, agent):
        agent.hooks.register("post_request", self.save_to_db)
    
    async def save_to_db(self, ctx):
        ctx.agent.db.save(ctx.session)

# Compaction is a hook:
class CompactExtension:
    def init_app(self, agent):
        agent.hooks.register("mid_loop", self.check_tokens)
    
    async def check_tokens(self, ctx):
        if ctx.agent.total_tokens > threshold:
            await self.compact(ctx.agent)

# Skills are hooks:
class SkillsExtension:
    def init_app(self, agent):
        agent.hooks.register("pre_request", self.inject_context)
    
    async def inject_context(self, ctx):
        skills = self.load_skills(ctx.agent.workspace)
        ctx.messages = [skills, *ctx.messages]
```

**The Flask Pattern**: Extensions receive direct agent references. No context variables, no proprietary APIs, just Python.

```python
class Extension:
    def __init__(self, agent=None):
        self.agent = agent
        if agent is not None:
            self.init_app(agent)
    
    def init_app(self, agent):
        agent.hooks.register("pre_request", self.callback)
        agent.extensions['my_extension'] = self
    
    async def callback(self, ctx):
        # Direct access to everything the agent can do
        agent = ctx.agent
        # ... do anything ...
```

### The Prompts as Hooks Realization

**Traditional thinking**: Prompts are special, built-in, different from other features.

**Hook-based thinking**: Prompts are just the FIRST pre-request hook in the chain!

```python
# Provider doesn't send your message directly
# They have a pre-request hook that:
# system_prompt + your_message → LLM

async def prompt_hook(ctx):
    system_prompt = render_template(ctx.template, **ctx.args)
    ctx.messages = [
        {"role": "system", "content": system_prompt},
        *ctx.messages  # User messages append to system prompt
    ]
```

**This means:**
- Prompts are NOT special infrastructure
- They're just hooks with priority ordering
- Skills are ALSO pre-request hooks (can run before or after prompts)
- Extensions can modify prompts dynamically
- State management itself becomes a hook pattern

### The Dependency Flow

```
crow-core (MINIMAL - ~300 lines)
├── ACP protocol implementation
├── React loop (from streaming_async_react_with_db.py)
├── Hook registry
└── Extension loading (Flask pattern)
    ↓
crow-compact (extension package, depends on crow-core)
crow-persistence (extension package, depends on crow-core)
crow-skills (extension package, depends on crow-core)
crow-mcp-server (tools, not hard dep - can be swapped)
    ↓
crow-agent (bundles it all, not a python dep - distribution package)
```

**Key insight**: `crow-agent` is NOT a Python dependency of `crow-core`. It's the distribution mechanism - what you `pip install` or `uv tool install`. The Python packages are `crow-core`, `crow-compact`, etc.

---

## Part 2: The Antithesis - Gemini's Pragmatic Critique

> "This is the exact kind of pragmatic engineering that actually ships."

Gemini's message represents the ~X - the reality check that challenges architectural purity with working code.

### What Gemini Identified as "Elite"

**1. The `StopIteration` Unpacking Hack**

```python
except StopIteration as e:
    thinking, content, tool_call_inputs = e.value
    break
```

This is a deep-cut Python feature. Generators can `return` a value when exhausted, and catching it in `StopIteration.value` is a clean way to get final aggregated state without polluting yielded tokens.

**Why it's brilliant:**
- The generator yields `{type: "content", token: "..."}` for streaming
- But returns `(thinking, content, tool_calls)` when done
- No need to maintain external state accumulator
- The generator IS the state machine

**2. The HTTPX Event Hook for Debugging**

```python
def log_request(request):
    print(f"\n{'=' * 20} RAW REQUEST {'=' * 20}")
    print(f"{request.method} {request.url}")
    print(f"Body: {request.read().decode()}")

http_client = httpx.Client(event_hooks={"request": [log_request]})
return OpenAI(
    api_key=os.getenv("ZAI_API_KEY"),
    base_url=os.getenv("ZAI_BASE_URL"),
    http_client=http_client,
)
```

**Why it matters:**
- OpenAI errors are notoriously opaque with tool calling
- Intercepting raw HTTP request body shows exact JSON schema
- Debugging complex multi-agent setups becomes possible
- Pro move that saves hours of confusion

**3. Separation of Concerns**

```python
# process_chunk handles raw delta parsing
def process_chunk(chunk, thinking, content, tool_calls, tool_call_id):
    # Parse streaming chunk
    return thinking, content, tool_calls, tool_call_id, new_token

# process_response aggregates
def process_response(response):
    thinking, content, tool_calls, tool_call_id = [], [], {}, None
    for chunk in response:
        # Capture usage
        thinking, content, tool_calls, tool_call_id, new_token = process_chunk(...)
        yield msg_type, token
    return thinking, content, process_tool_call_inputs(tool_calls), usage

# react_loop orchestrates
async def react_loop(messages, mcp_client, lm, model, tools):
    for _ in range(max_turns):
        response = send_request(messages, model, tools, lm)
        gen = process_response(response)
        while True:
            try:
                msg_type, token = next(gen)
                yield {"type": msg_type, "token": token}
            except StopIteration as e:
                thinking, content, tool_call_inputs, usage = e.value
                break
        if not tool_call_inputs:
            return
        tool_results = await execute_tool_calls(mcp_client, tool_call_inputs)
        messages = add_response_to_messages(...)
```

**Reads like a standard OS run-loop:**
- Under 200 lines
- Isolated state mutation
- Clear responsibility boundaries

### The Valid Trade-Off

**Sync OpenAI + Async MCP:**

```python
# Sync OpenAI (blocks event loop)
response = lm.chat.completions.create(
    model=model,
    messages=messages,
    tools=tools,
    stream=True,  # But it's sync!
)

# Async MCP tools
result = await mcp_client.call_tool(...)
```

Gemini's observation: "This is a 1-to-1 local agent right now, so blocking the event loop with a sync OpenAI stream isn't going to crash a server with 1,000 concurrent users."

**This is pragmatic engineering:**
- Perfect is the enemy of shipped
- AsyncOpenAI rewrite can wait for `protocol_version: 2`
- Working code > Perfect code
- The 1-to-1 local agent use case doesn't need pure async yet

### The Challenge

Gemini points out: "Right now, your DB persistence and session management are a bit hardcoded into the `main()` setup and the `Agent` class."

The vision:

```python
from crow import Agent, extensions

app = Agent(prompt_id="my-custom-workflow")
app.register(extensions.SQLitePersistence("my_db.db"))
app.register(extensions.ContextCompactor(max_tokens=8000))

if __name__ == "__main__":
    app.run()  # Spins up ACP server
```

**The need**: Strategically placed hook execution points without bloating the core.

---

## Part 3: The Synthesis - The Resolution

### The Core Insight

The working code (streaming_async_react_with_db.py) IS the minimal core. We don't need to rewrite it. We need to formalize its hook points.

**The synthesis recognizes:**
1. The 281 lines are already optimal (don'tBloated them)
2. The extension pattern IS the answer (formalize it)
3. The hook points are already there (just make them explicit)
4. The pragmatic trade-offs are correct ( AsyncOpenAI can wait)

### The Algorithm: ExtensionRegistry Pattern

**What we need:**

```python
# crow-core/hooks.py
from typing import Callable, Any
from dataclasses import dataclass

@dataclass
class HookContext:
    """Context passed to hooks - contains direct agent access"""
    agent: 'Agent'
    session_id: str
    messages: list
    response: Any = None
    tool_calls: list = None
    tool_results: list = None
    metadata: dict = None

class HookRegistry:
    """Registry for hooks at different execution points"""
    
    def __init__(self):
        self.hooks = {
            'pre_request': [],      # Before LLM request
            'post_response': [],     # After LLM response (before tool execution)
            'pre_tool_call': [],     # Before each tool call
            'post_tool_call': [],    # After each tool call
            'post_request': [],      # After full turn complete
            'mid_loop': [],          # During react loop (for compaction checks)
        }
    
    def register(self, hook_point: str, callback: Callable, priority: int = 100):
        """Register a hook at a specific point with optional priority"""
        self.hooks[hook_point].append((priority, callback))
        self.hooks[hook_point].sort(key=lambda x: x[0])  # Sort by priority
    
    async def execute(self, hook_point: str, ctx: HookContext) -> HookContext:
        """Execute all hooks at a point in priority order"""
        for priority, callback in self.hooks[hook_point]:
            ctx = await callback(ctx)
            if ctx is None:
                raise ValueError(f"Hook {callback} must return HookContext")
        return ctx
```

**Minimal changes to core:**

```python
# crow-core/agent.py (modified streaming_async_react_with_db.py)
class Agent:
    def __init__(self, config: Config = None):
        self.hooks = HookRegistry()
        self._sessions = {}
        self._mcp_clients = {}
        self._llm = configure_llm()
    
    def register(self, extension):
        """Register an extension (Flask pattern)"""
        extension.init_app(self)
    
    async def _react_loop(self, session_id: str, max_turns: int = 50000):
        """Main ReAct loop with hook points"""
        session = self._sessions[session_id]
        
        for turn in range(max_turns):
            # HOOK POINT: pre_request (prompts, skills, context injection)
            ctx = HookContext(
                agent=self,
                session_id=session_id,
                messages=session.messages,
            )
            ctx = await self.hooks.execute("pre_request", ctx)
            
            # Send request to LLM (blocks event loop - OK for 1-to-1)
            response = self._send_request(session_id, ctx.messages)
            
            # Process streaming response
            gen = self._process_response(response)
            while True:
                try:
                    msg_type, token = next(gen)
                    yield {"type": msg_type, "token": token}
                except StopIteration as e:
                    thinking, content, tool_call_inputs, usage = e.value
                    break
            
            # HOOK POINT: post_response (after LLM, before tools)
            ctx.response = {"thinking": thinking, "content": content, "usage": usage}
            ctx.tool_calls = tool_call_inputs
            ctx = await self.hooks.execute("post_response", ctx)
            
            # If no tool calls, we're done
            if not tool_call_inputs:
                session.add_assistant_response(thinking, content, [], [])
                
                # HOOK POINT: post_request (persistence, logging)
                ctx = await self.hooks.execute("post_request", ctx)
                
                yield {"type": "final_history", "messages": session.messages}
                return
            
            # Execute tools with hook points
            tool_results = []
            for tool_call in tool_call_inputs:
                # HOOK POINT: pre_tool_call
                ctx.tool_calls = [tool_call]
                ctx = await self.hooks.execute("pre_tool_call", ctx)
                
                result = await self._execute_tool_call(session_id, tool_call)
                tool_results.append(result)
                
                # HOOK POINT: post_tool_call
                ctx.tool_results = [result]
                ctx = await self.hooks.execute("post_tool_call", ctx)
            
            # Add to session
            session.add_assistant_response(thinking, content, tool_call_inputs, tool_results)
            
            # HOOK POINT: mid_loop (compaction checks)
            ctx = await self.hooks.execute("mid_loop", ctx)
```

**The beauty**: The core loop is almost unchanged. We just added:
1. Create `HookContext` at strategic points
2. Execute hooks at those points
3. Continue with (potentially modified) context

---

## Part 4: The Algorithm - Concrete Implementation

### Extension Base Class

```python
# crow-core/extension.py
from abc import ABC, abstractmethod

class Extension(ABC):
    """Base class for Crow extensions"""
    
    def __init__(self, agent=None):
        self.agent = agent
        if agent is not None:
            self.init_app(agent)
    
    @abstractmethod
    def init_app(self, agent):
        """Initialize extension with agent (Flask pattern)"""
        pass
```

### Persistence Extension

```python
# crow-persistence/extension.py
from crow.extension import Extension
from crow.hooks import HookContext

class SQLitePersistence(Extension):
    """SQLite-based persistence extension"""
    
    def __init__(self, db_path: str = "crow.db"):
        self.db_path = db_path
        super().__init__()
    
    def init_app(self, agent):
        """Register persistence hooks"""
        # Store reference to agent
        self.agent = agent
        
        # Register hooks
        agent.hooks.register("post_request", self.save_session, priority=100)
        
        # Add to agent's extensions dict
        agent.extensions['persistence'] = self
    
    async def save_session(self, ctx: HookContext) -> HookContext:
        """Save session to database after each request"""
        session = ctx.agent._sessions[ctx.session_id]
        
        # Save to SQLite
        self._save_to_db(session)
        
        # Return context (required!)
        return ctx
    
    def _save_to_db(self, session):
        """Actual database save logic"""
        # SQLAlchemy or whatever
        pass
```

### Compaction Extension

```python
# crow-compact/extension.py
from crow.extension import Extension
from crow.hooks import HookContext

class ContextCompactor(Extension):
    """Token-based context compaction extension"""
    
    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.token_counts = {}  # session_id -> token_count
        super().__init__()
    
    def init_app(self, agent):
        self.agent = agent
        agent.hooks.register("mid_loop", self.check_tokens, priority=50)
        agent.extensions['compactor'] = self
    
    async def check_tokens(self, ctx: HookContext) -> HookContext:
        """Check if compaction needed"""
        session_id = ctx.session_id
        usage = ctx.response.get("usage", {})
        
        total = usage.get("total_tokens", 0)
        self.token_counts[session_id] = self.token_counts.get(session_id, 0) + total
        
        if self.token_counts[session_id] > self.max_tokens:
            await self._compact(ctx.agent, session_id)
            self.token_counts[session_id] = 0  # Reset
        
        return ctx
    
    async def _compact(self, agent, session_id):
        """Compaction logic - see AGENTS.md for approach"""
        session = agent._sessions[session_id]
        
        # Keep last K messages
        preserved = session.messages[-10:]
        
        # Format middle messages for summarization
        to_compact = session.messages[10:-10]
        formatted = "\n\n".join([
            f"## Message {i}\nRole: {msg['role']}\nContent:\n{msg['content']}"
            for i, msg in enumerate(to_compact)
        ])
        
        # Request summary from same session (preserves KV cache!)
        summary_request = f"""
{formatted}

Summarize the above conversation. Focus on:
- File paths changed
- Key decisions made
- Current state
Do NOT call tools for this request.
"""
        
        # Add summary request to session
        session.messages.append({"role": "user", "content": summary_request})
        
        # Get summary (reuse agent's react loop)
        summary = []
        async for chunk in agent._react_loop(session_id, max_turns=1):
            if chunk["type"] == "content":
                summary.append(chunk["token"])
        
        # Construct new session
        summary_msg = session.messages[-1]  # Assistant's summary
        new_messages = [
            session.messages[:10],  # First 10
            summary_msg,            # Summary
            preserved,              # Last 10
        ]
        session.messages = new_messages
        
        # Notify via ACP
        await agent._conn.send_notification("session/update", {
            "sessionUpdate": "agent_message_chunk",
            "content": f"\n[Compaction complete: {len(to_compact)} messages → 1 summary]"
        })
```

### Skills Extension

```python
# crow-skills/extension.py
from crow.extension import Extension
from crow.hooks import HookContext
from pathlib import Path

class SkillsLoader(Extension):
    """Load and inject skills from filesystem"""
    
    def __init__(self, skills_dir: str = ".skills"):
        self.skills_dir = Path(skills_dir)
        super().__init__()
    
    def init_app(self, agent):
        self.agent = agent
        agent.hooks.register("pre_request", self.inject_skills, priority=10)
        agent.extensions['skills'] = self
    
    async def inject_skills(self, ctx: HookContext) -> HookContext:
        """Inject skills context before request"""
        # Load all .md files from skills directory
        skills_content = []
        
        if self.skills_dir.exists():
            for skill_file in self.skills_dir.glob("*.md"):
                content = skill_file.read_text()
                skills_content.append(f"## Skill: {skill_file.stem}\n\n{content}")
        
        if skills_content:
            # Inject as system context
            skills_msg = {
                "role": "system",
                "content": "# Loaded Skills\n\n" + "\n\n---\n\n".join(skills_content)
            }
            # Insert as first message after system prompt
            ctx.messages = [ctx.messages[0], skills_msg] + ctx.messages[1:]
        
        return ctx
```

### Prompt Manager Extension

```python
# crow-core/prompt.py
from crow.extension import Extension
from crow.hooks import HookContext
from jinja2 import Environment, FileSystemLoader

class PromptManager(Extension):
    """Manage system prompts as Jinja templates"""
    
    def __init__(self, template_dir: str = "prompts"):
        self.template_dir = template_dir
        self.env = None
        super().__init__()
    
    def init_app(self, agent):
        self.agent = agent
        self.env = Environment(loader=FileSystemLoader(self.template_dir))
        agent.hooks.register("pre_request", self.render_prompt, priority=5)
        agent.extensions['prompts'] = self
    
    async def render_prompt(self, ctx: HookContext) -> HookContext:
        """Render system prompt from template"""
        session = ctx.agent._sessions[ctx.session_id]
        
        # Get prompt ID and args from session metadata
        prompt_id = session.metadata.get("prompt_id", "default")
        prompt_args = session.metadata.get("prompt_args", {})
        
        # Render template
        template = self.env.get_template(f"{prompt_id}.jinja2")
        system_prompt = template.render(**prompt_args)
        
        # Replace or insert system prompt
        if ctx.messages and ctx.messages[0]["role"] == "system":
            ctx.messages[0]["content"] = system_prompt
        else:
            ctx.messages.insert(0, {"role": "system", "content": system_prompt})
        
        return ctx
```

### Usage: The Bundled Agent

```python
# crow-agent/app.py
from crow import Agent
from crow_persistence import SQLitePersistence
from crow_compact import ContextCompactor
from crow_skills import SkillsLoader
from crow_core.prompt import PromptManager

# Create agent with minimal core
app = Agent()

# Register extensions (Flask pattern)
app.register(PromptManager(template_dir="~/crow/prompts"))
app.register(SQLitePersistence(db_path="~/crow/crow.db"))
app.register(ContextCompactor(max_tokens=8000))
app.register(SkillsLoader(skills_dir="~/crow/.skills"))

# Run ACP server
if __name__ == "__main__":
    import asyncio
    from acp import serve_stdio
    
    asyncio.run(serve_stdio(app))
```

**Distribution via `uv tool install crow-ai`:**

```bash
# User installs:
uv tool install crow-ai

# Creates ~/.local/bin/crow
# Which runs the bundled agent above
# With default config in ~/.crow/config.yaml
```

---

## Part 5: The Bigger Vision - kernel_kernel.py

### The Unified Environment

The `kernel_kernel.py` concept evolves from "persistent Python REPL" to something more ambitious:

**A unified environment that is simultaneously:**
1. **Persistent Python REPL** - State survives across agent turns
2. **Markdown Notebook** - Not just code cells, but documentation cells
3. **Agent Memory** - Essays, research, understanding all stored inline
4. **Live Introspection** - `import acp; introspect.whatever(acp)` works in-place

### The Cell Types

```python
# kernel_kernel.py concept

# Cell type 1: Python code (execute)
```python
import acp
import introspect

schema = introspect.get_schema(acp.Agent)
print(schema)
```
# Output: {schema details...}

# Cell type 2: Markdown documentation (store)
```markdown
# Understanding ACP Protocol

The Agent-Client Protocol defines...
- Sessions are the unit of KV cache
- MCP servers provide tools
- Hooks enable extensibility
```

# Cell type 3: Shell commands (execute)
```bash
!docker-compose up -d searxng
```
# Output: Container started...

# Cell type 4: Agent turns (execute)
```agent
@agent
Please search for ACP protocol documentation and summarize
```
# Output: Agent executes, uses tools, produces summary

# Cell type 5: Introspection (execute)
```introspect
Show me the current agent's hook registry
```
# Output: {hook details...}
```

### The Power of In-Place Documentation

**Traditional workflow:**
1. Build agent
2. Write docs SEPARATELY
3. Docs drift from code
4. Agent doesn't know its own docs

**kernel_kernel.py workflow:**
1. Build agent
2. Document IN THE SAME FILE
3. Code and docs are unified
4. Agent can READ its own docs
5. Essays in docs/essays/ ARE part of agent memory

```python
# kernel_kernel.py excerpt

```markdown
# Current Understanding of Compaction

From essay 12, we learned:
- Compaction should use same session (KV cache)
- Keep first K, last K messages
- Summarize middle
- Create new session

Status: NOT YET IMPLEMENTED
Priority: HIGH
```

```python
# Agent can introspect its own understanding
def check_compaction_understanding():
    md_cells = kernel.get_cells_by_type("markdown")
    compaction_doc = find(md_cells, lambda c: "Compaction" in c.title)
    return compaction_doc.metadata["status"]
```

### The Scientific Instrument

This transforms the environment into what AGENTS.md envisions:

```
Code → Understanding → Insight
     ↓                ↓
   Reflect         Synthesize
     ↓                ↓
   Refactor       Document
```

**The agent doesn't just execute code. It:**
1. Reads its own documentation
2. Understands its own architecture
3. Updates its understanding (markdown cells)
4. Refects on that understanding (essays)
5. Synthesizes new understanding (Y from X + ~X)
6. All in the same unified environment

### Connection to CLI Distribution

```bash
# crow CLI doesn't just run agent
crow --kernel

# Starts kernel_kernel.py environment:
# - ACP server on stdio (for Zed/VSCode)
# - Notebook interface (for direct interaction)
# - Persistent state (for long-running workflows)
# - Documentation cells (for agent memory)
```

**The "scientific instrument" vision:**
- Not just an IDE
- An environment for generating understanding
- Code is the medium
- Understanding is the output
- Documentation is the memory
- The agent can read/write both

---

## THE BREAKTHROUGH: MCP Bridge Pattern (NEW!)

After studying `refs/claude-code-acp`, we discovered a COMPLETELY different architecture than what we initially thought!

### The Old Thinking (X - WRONG)

We thought the agent would directly call ACP client methods:

```python
# ❌ WRONG - Direct ACP calls from agent
terminal = await self._conn.create_terminal(command, session_id)
output = await self._conn.terminal_output(terminal_id, session_id)
```

### The New Discovery (~X - claude-code-acp Pattern)

The agent sees **MCP tools**, not ACP methods! The pattern is:

```
ACP Client (Zed/VSCode) → Provides capabilities
         ↓
   ACP Protocol → Agent receives capabilities
         ↓
   MCP Bridge → Wraps ACP as mcp__acp__* tools
         ↓
   Agent → Calls MCP tools (unified interface!)
```

### The Implementation (from claude-code-acp/src/mcp-server.ts)

```typescript
// They create an MCP server that bridges ACP:
const server = new McpServer({ name: "acp", version: "1.0.0" });

// Register ACP terminal as MCP tool:
if (agent.clientCapabilities?.terminal) {
  server.registerTool(
    "Bash", // Becomes mcp__acp__Bash
    {
      description: "Execute bash commands",
      inputSchema: {
        command: z.string(),
        timeout: z.number(),
        run_in_background: z.boolean()
      }
    },
    async (input) => {
      // Call ACP client method:
      const handle = await agent.client.createTerminal({
        command: input.command,
        sessionId,
      });
      
      // Wait for output:
      const exitStatus = await handle.waitForExit();
      const output = await handle.currentOutput();
      
      return { content: [{ type: "text", text: output.output }] };
    }
  );
}

// Same for file operations:
if (clientCapabilities?.fs?.readTextFile) {
  server.registerTool("Read", ..., async (input) => {
    const response = await agent.readTextFile({
      sessionId,
      path: input.file_path,
    });
    return { content: [{ type: "text", text: response.content }] };
  });
}
```

### Why This is Brilliant

1. **Unified Tool Interface**: Agent sees everything as MCP tools
2. **Capability Detection**: Only expose tools client supports
3. **No Agent Logic**: Agent doesn't need to understand ACP
4. **LLM-Agnostic**: Works with any LLM that supports MCP

### The Tool Schemas (What the LLM Sees)

```json
{
  "name": "mcp__acp__Bash",
  "description": "Execute bash commands (use INSTEAD of native Bash)",
  "parameters": {
    "command": {"type": "string"},
    "timeout": {"type": "number", "max": 120000},
    "description": {"type": "string"},
    "run_in_background": {"type": "boolean"}
  }
}

{
  "name": "mcp__acp__Read",
  "description": "Read file (use INSTEAD of native Read)",
  "parameters": {
    "file_path": {"type": "string"},
    "offset": {"type": "integer", "default": 1},
    "limit": {"type": "integer", "default": 2000}
  }
}

{
  "name": "mcp__acp__Edit",
  "description": "Edit file via exact string replacement",
  "parameters": {
    "file_path": {"type": "string"},
    "old_string": {"type": "string"},
    "new_string": {"type": "string"},
    "replace_all": {"type": "boolean", "default": false}
  }
}
```

### The Synthesis (Y)

**What this means for Crow:**

Instead of agent directly calling ACP methods, we should:

1. **Create MCP Bridge** (like claude-code-acp does)
2. **Wrap ACP capabilities as MCP tools**
3. **Agent uses unified MCP interface**

```python
# crow-acp-bridge/bridge.py
from mcp import McpServer

class ACPBridge:
    """Bridges ACP client capabilities as MCP tools"""
    
    def __init__(self, acp_client, session_id):
        self.server = McpServer("acp", "1.0.0")
        self.client = acp_client
        self.session_id = session_id
        
        # Register tools based on client capabilities
        if acp_client.capabilities.terminal:
            self._register_terminal_tools()
        
        if acp_client.capabilities.fs.read_text_file:
            self._register_file_tools()
    
    def _register_terminal_tools(self):
        @self.server.tool("Bash")
        async def bash(command: str, timeout: int = 30000, **kwargs):
            terminal = await self.client.create_terminal(
                command=command,
                session_id=self.session_id,
            )
            await terminal.wait_for_exit()
            output = await terminal.current_output()
            await terminal.release()
            return output.output
    
    def _register_file_tools(self):
        @self.server.tool("Read")
        async def read(file_path: str, **kwargs):
            result = await self.client.read_text_file(
                path=file_path,
                session_id=self.session_id,
            )
            return result.content
```

### The Architecture for Crow

```
ACP Client (Zed/VSCode/Test)
         ↓
  ACP Protocol (capabilities: terminal, fs)
         ↓
  Crow Agent (acp_native.py)
         ↓
  ACP Bridge (wraps capabilities as MCP tools: mcp__acp__*)
         ↓
  MCP Server (provides unified tool interface)
         ↓
  LLM (sees all tools as MCP, doesn't know about ACP)
```

### This Changes Everything

**Before (Direct ACP):**
- Agent needs ACP-specific logic
- Mixed MCP and ACP tool handling
- Complex capability checking

**After (MCP Bridge):**
- Everything is MCP
- Capability checking happens once (bridge setup)
- Agent has unified tool interface
- LLM doesn't need to understand ACP

**This is THE pattern for Crow!**

---

## Conclusion: The Synthesis Achieved

The dialectical journey:
1. **X**: Agent directly uses ACP terminal/files
2. **~X**: claude-code-acp shows MCP bridge pattern
3. **Y**: Wrap ACP as MCP tools for unified interface

**What we ship:**
- ✅ crow-acp-bridge (MCP wrapper for ACP)
- ✅ crow-mcp-server (file_editor, web_search, web_fetch)
- ✅ Agent sees unified MCP interface
- ✅ Works with ANY ACP client

**The final architecture:**
- ACP clients provide capabilities (terminal, files)
- ACP bridge exposes as MCP tools (mcp__acp__*)
- Agent uses unified MCP interface
- Everything just works

**This is the way.**

---

**Next Steps:**
1. Implement `HookRegistry` and `HookContext` in crow-core
2. Add hook points to `_react_loop` (minimal changes)
3. Extract current persistence → `crow-persistence` extension
4. Implement `crow-compact` extension
5. Implement `crow-skills` extension
6. Create `crow-agent` distribution package
7. Publish as `crow-ai` on PyPI
8. Document the extension API
9. Build kernel_kernel.py prototype
10. Write more essays as agent memory crystallizes

**The pragmatic ships. The clean scales. The synthesis endures.**
