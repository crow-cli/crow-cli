# Hooks Realization: Understanding Agent Extensibility

## The Moment of Understanding

I used to think hooks were unnecessary. "Just modify the code right there," I'd say. The agent is open source - why add an abstraction layer?

Then I tried to explain what a **skill** is. And what **compaction** is. And suddenly I realized: they're the same thing. They're hooks at different points in the process.

This essay documents that realization and what it means for our architecture.

---

## What is a Hook?

A hook is a **plugin point in the react loop** where user code can:

1. **Observe state** (conversation, session, tokens, provider)
2. **Modify state** (inject context, append messages, trigger compaction)
3. **Control flow** (continue, pause, restart, delegate)

Without modifying the agent's core code.

### Why This Matters

If you hardcode skills into the agent, every user needs to fork your code to add their own context injection.

If you hardcode compaction, every user needs to fork to change the threshold or algorithm.

Hooks let users **extend behavior without forking**. This is what frameworks are for.

---

## The Hook Points

```
USER REQUEST
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  PRE-REQUEST HOOKS                                  │
│                                                     │
│  Skills go here. Context injection based on        │
│  user request. "Oh they mentioned 'the database',   │
│  inject DB schema into the context."                │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
              ┌─────────────┐
              │  REACT LOOP │◄─────────────────────────────┐
              │             │                              │
              │  1. Build request (messages + tools)       │
              │  2. Call LLM                               │
              │  3. Process response                       │
              │  4. Execute tools?                         │
              │  5. Continue?                              │
              │                                             │
              └──────┬──────────────────────────────────────┘
                     │
                     │  MID-REACT HOOK POINT
                     │  (after each LLM response)
                     │
                     │  Compaction goes here.
                     │  "Token count > threshold?
                     │   Pause, summarize middle messages,
                     │   continue with compacted context."
                     │
                     └──────────────────────────────────────┘
                              │
                              ▼ (loop ends)
                     ┌────────────────────────────────────────┐
                     │  POST-REACT HOOKS                      │
                     │                                        │
                     │  Ralph loops go here.                  │
                     │  "Are you sure about that?"            │
                     │  Re-prompt with critique.              │
                     │  Self-verification without human.      │
                     └────────────────────────────────────────┘
                              │
                              ▼
                         DONE
```

---

## Skills Are Pre-Request Hooks

A **skill** is context injection based on user request keywords.

Example: User mentions "the database" → Skill detects keyword → Injects DB schema into system prompt or as a user message BEFORE the LLM sees it.

This requires:
1. Access to the raw user request
2. Access to the session (to add messages)
3. Access to tool definitions (to know what @-mentioned things exist)
4. Some pattern matching or more sophisticated NLP

**Implementation:**
```python
async def skill_hook(session: Session, request: str, provider: Provider) -> None:
    """A simple keyword-based skill."""
    if "database" in request.lower():
        schema = load_schema_from_file("schema.sql")
        session.add_message("user", f"Context: Database schema:\n{schema}")
```

---

## Compaction Is a Mid-React Hook

When tokens exceed threshold, pause the react loop, summarize middle messages, continue.

**Implementation:**
```python
async def compaction_hook(session: Session, usage: Usage, provider: Provider) -> Optional[Session]:
    """Compact if over threshold."""
    if usage.total_tokens > session.threshold:
        # Keep first K and last K messages
        preserved_head = session.messages[:K]
        preserved_tail = session.messages[-K:]
        to_compact = session.messages[K:-K]
        
        # Ask LLM to summarize (using SAME session for KV cache!)
        summary = await summarize(provider, to_compact)
        
        # Create new session with compacted history
        new_session = Session(
            messages=[*preserved_head, summary, *preserved_tail],
            # ... other session state
        )
        return new_session
    return None
```

**Critical insight**: Use the SAME session/provider for summarization to preserve KV cache. This is why local LLMs matter.

---

## Ralph Loops Are Post-React Hooks

A **Ralph loop** is self-verification: after the agent finishes, ask "are you sure about that?" and re-run the original prompt.

This forces the agent to self-critique without requiring human feedback.

**Why this matters**: Anthropic and OpenAI want humans in the loop. Their models are trained to ask for clarification. Ralph loops provide feedback through stateful agent self-talk, bypassing that signal.

**Implementation:**
```python
async def ralph_hook(session: Session, result: str, provider: Provider) -> Optional[str]:
    """Ask agent to verify its own work."""
    verification_prompt = f"""
    Original request: {session.original_request}
    Your response: {result}
    
    Are you sure about that? Review your work critically.
    If something is wrong, explain what and how to fix it.
    """
    
    # Re-run react loop with verification prompt
    verification = await react_loop(session, verification_prompt, provider)
    return verification
```

---

## The Hook Interface Problem

We need to define what hooks receive and what they can do.

### What hooks need access to:

1. **Session** - The conversation state (messages, tools, config)
2. **Provider** - The LLM provider (to make additional calls)
3. **Request** - The raw user request (for skills)
4. **Usage** - Token counts (for compaction)
5. **Result** - The final response (for post-react hooks)

### What hooks can do:

1. **Read state** - Observe anything
2. **Modify session** - Add messages, change tools
3. **Call LLM** - Use provider for additional work
4. **Return modifications** - New session, new messages, etc.
5. **Signal control flow** - "Continue", "Restart", "Abort"

### The interface sketch:

```python
from typing import Protocol, Optional
from dataclasses import dataclass

@dataclass
class HookContext:
    session: Session
    provider: Provider  # The OpenAI client wrapper
    request: Optional[str] = None
    usage: Optional[Usage] = None
    result: Optional[str] = None

class Hook(Protocol):
    async def __call__(self, ctx: HookContext) -> Optional[HookContext]:
        """Run the hook. Return modified context or None to continue."""
        ...
```

---

## Python Packaging with uv

Hooks are **plugins**. This means:

1. **Hooks live in separate packages** - Users publish their hooks to PyPI
2. **Agent discovers hooks at runtime** - Entry points or config
3. **Hooks depend on our SDK** - They need access to Session, Provider, etc.

This requires **deep understanding of Python packaging**:

### Entry Points Pattern

```toml
# In hook package's pyproject.toml
[project.entry-points."crow.hooks"]
my_skill = "my_package.hooks:skill_hook"
```

```python
# In agent core
import importlib.metadata

def discover_hooks() -> list[Hook]:
    """Discover hooks via entry points."""
    hooks = []
    for ep in importlib.metadata.entry_points(group="crow.hooks"):
        hook = ep.load()
        hooks.append(hook)
    return hooks
```

### uv's Role

`uv` handles:
- **Virtual environments** - Isolated dependencies
- **Package installation** - `uv pip install my-hook-package`
- **Dependency resolution** - Hook depends on `crow-sdk`, agent provides it
- **Script running** - `uv --project . run python script.py`

The challenge: Hook packages need a stable SDK version to depend on.

---

## The Minimal Architecture

Before hooks, before skills, before compaction - we need the core agent.

### What's minimal ACP?

```
ACP Protocol (implemented)
├── initialize()
├── authenticate()
├── new_session()
├── load_session()
├── prompt()  ← React loop lives here
└── cancel()
```

Plus:
- **OpenAI SDK** - The LLM call abstraction
- **MCP Client** - Tool execution (via FastMCP)
- **Persistence** - Session and events in SQLite

That's it. No hooks yet. Just the loop.

### The Built-in MCP Server

We'll combine into ONE MCP server:
- `terminal` - Shell execution
- `file_editor` - View/create/edit/delete files
- `fetch` - HTTP requests
- `web_search` - Search the web

This server has its own `pyproject.toml` and `.venv`. The agent depends on it as a separate package.

**Why combine?**
- Simpler deployment (one MCP server to start)
- Shared dependencies (no duplication)
- Pypi-friendly (separate package, same repo)

---

## ACP Client vs. Built-in Tools

**Key insight from kimi-cli**: The ACP client may expose its own tools (like terminal access). If it does, we should use those INSTEAD of our built-in MCP.

Flow:
1. ACP client calls `new_session()`
2. Client exposes capabilities (e.g., "I have terminal access")
3. Agent checks: "Do I need my built-in terminal MCP, or does client provide it?"
4. If client provides, use client's tools
5. Otherwise, fall back to built-in MCP

This makes the agent work in multiple contexts:
- **Full client** - Client provides terminal, we don't need built-in
- **Minimal client** - We use our built-in MCP
- **No client (script mode)** - We use built-in MCP

---

## Script Mode: The Delegation Interface

Remember `kernel_kernel.py`? Not a replacement for bash anymore, but **a replacement for subagent delegation**.

**The vision:**
```python
# In user's script
from crow import Agent, Conversation

# Create agent programmatically
agent = Agent(
    instructions="You are a research assistant",
    mcp_servers=["./mcp-servers/builtin"],
    skills=["./skills/research.md"],
)

# Create conversation
conv = Conversation(agent=agent, workspace="/tmp/workspace")

# Run
response = conv.send_message("Research Python packaging with uv")
print(response)

# Or delegate from within a hook!
async def delegation_hook(ctx: HookContext) -> None:
    """Delegate complex research to subagent."""
    subagent = Agent(instructions="You are a research specialist")
    research = await subagent.prompt(ctx.request)
    ctx.session.add_message("user", f"Research results: {research}")
```

**This is how we do delegation**: Python scripts with crow-ai preinstalled. The same interface used by hooks, skills, and end users.

---

## The Path Forward

### Phase 1: Minimal Core (No Hooks Yet)
1. Document current agent architecture
2. Write tests for existing react loop
3. Ensure ACP compliance (spec-driven)
4. Build builtin MCP server (terminal/file_editor/fetch/web_search)
5. Test via ACP client AND via Python scripts

### Phase 2: Hook Framework
1. Design Hook interface (Protocol)
2. Implement hook points in react loop
3. Entry point discovery
4. Write tests for hook execution
5. Document how to write a hook

### Phase 3: Implement Hooks
1. Skills as pre-request hooks
2. Compaction as mid-react hook
3. Ralph loops as post-react hook
4. Each is a separate package (dogfooding our own plugin system!)

### Phase 4: Delegation
1. Ensure Python script mode works beautifully
2. Document delegation pattern
3. kernel_kernel becomes the "subagent kernel"

---

## The Repository as Stateful Agent

This repo is a stateful agent. The essays directory is its memory. Each numbered essay is a checkpoint in its understanding.

We're not just writing code. We're building understanding through dialectic:

```
THESIS (X) → TEST (~X) → SYNTHESIS (Y)
     │           │            │
   "Hooks     "Compiler    "Hooks are
    aren't     says you     pre/mid/post
    needed"    need them"   plugin points"
```

Each essay captures a synthesis. Each test is the negation. Each implementation is the new thesis.

---

## What We Need to Do Now

1. **Write the minimal core** - ACP + MCP + React, tested, documented
2. **Build the builtin MCP server** - One package, four tools
3. **Test both interfaces** - ACP client AND Python scripts
4. **THEN** design hooks

We don't need hooks yet. We need a solid foundation to hang hooks ON.

---

## Summary

- **Hooks** are plugin points for extending the react loop
- **Skills** = pre-request hooks (context injection)
- **Compaction** = mid-react hooks (summarization)
- **Ralph loops** = post-react hooks (self-verification)
- Hook interface needs access to: Session, Provider, Request, Usage, Result
- Python packaging with uv is critical for plugin discovery
- Minimal core first: ACP + MCP + React
- Builtin MCP server as separate package
- Script mode is how delegation works
- Essays are the agent's memory

**Next essay**: Deep dive into the minimal ACP core and what we actually need to implement.

---

*Essay编号: 02*
*Topic: Architecture realization - hooks as extensibility*
*Dialectic: "Just modify code" → "Need plugin system" → "Hooks at react loop points"*
