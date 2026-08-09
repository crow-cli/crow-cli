# Design: Hooks as First-Class Extensions

**Core Vision**: The framework IS ACP + MCP. Hooks are how we extend the agent.

## What I Was Doing Wrong

I was about to cargo cult openhands-sdk's hook system without understanding:
1. Why they built it
2. What problems it solves
3. How ACP already provides extension points

## The Realization

ACP HAS BUILT-IN EXTENSION POINTS:

```python
async def ext_method(self, method: str, params: dict) -> dict: ...
async def ext_notification(self, method: str, params: dict) -> None: ...
```

These are in the protocol! (refs/python-sdk/src/acp/interfaces.py lines 220-223)

But there are TWO kinds of extension:

1. **Client → Agent Extensions** (via ACP's ext_method)
   - Client calls custom methods on agent
   - For client-triggered behavior
   
2. **Agent → Agent Hooks** (internal hooks)
   - Agent extends itself at specific points
   - For skills, compaction, etc.

## Reading Our Code: Where Do Hooks Go?

Looking at `acp_native.py` flow:

```python
prompt(prompt, session_id):
    add_message("user", text)
    
    # HOOK POINT #1: PRE-REQUEST
    # Skills go here - inject context before LLM sees it
    
    for turn in react_loop():
        response = send_request()  # LLM call
        (thinking, content, tools, usage) = process_response()
        
        # HOOK POINT #2: MID-REACT (POST-LLM-RESPONSE)
        # Compaction goes here - check usage, compact if needed
        # This is INSIDE the loop, after each LLM response
        
        if tools:
            results = execute_tool_calls()
            add_assistant_response()
    
    # End of react loop
    
    # HOOK POINT #3: POST-REACT-LOOP
    # After conversation finishes, before return
    
    return PromptResponse()

# POST-REQUEST: After prompt() returns
# Ralph loops go here - re-prompt for verification
```

## Different Levels of Post-Request

The user said there are "different levels of post-request hook":

1. **MID-REACT** (inside loop, after each LLM response)
   - Compaction
   - Token usage tracking
   - Stuck detection
   
2. **POST-REACT-LOOP** (after loop, before return)
   - Not currently used? Maybe metrics summary?

3. **POST-REQUEST** (after prompt() returns)
   - Ralph loops (re-prompt with "are you sure?")
   - Persistence (could be core or hook)

## What We Want To Build

A way to make it "stupidly easy" for people to program hooks.

### Hook Points (The Extension Points)

```python
class HookPoint:
    PRE_REQUEST = "pre_request"        # Before react loop
    MID_REACT = "mid_react"            # After each LLM response  
    POST_REACT_LOOP = "post_react_loop"  # After loop, before return
    POST_REQUEST = "post_request"      # After prompt() returns
```

### Hook Context (What Hooks Receive)

```python
@dataclass
class HookContext:
    """Context passed to every hook"""
    session: Session
    prompt: str | None = None
    usage: dict | None = None      # Token usage (for MID_REACT)
    response: str | None = None    # Final response (for POST_REQUEST)
    
    # Tools for hooks
    def inject_context(self, text: str):
        """Add context to conversation (for skills)"""
        self.session.add_message("user", text)
    
    def should_compact(self) -> bool:
        """Check if compaction needed (for compaction)"""
        return self.usage and self.usage["total_tokens"] > THRESHOLD
```

### Hook Interface (What Hooks Implement)

```python
class Hook(Protocol):
    """A hook that can be registered at an extension point"""
    
    async def __call__(self, ctx: HookContext) -> Optional[HookContext]:
        """
        Run the hook.
        
        Returns:
            Modified context or None to continue
        """
        ...
```

### How Hooks Are Registered

**Option 1: Direct Registration (Simplest)**
```python
from crow import Agent

agent = Agent()

# Register hooks directly
agent.hooks.register("pre_request", my_skill_hook)
agent.hooks.register("mid_react", compaction_hook)
```

**Option 2: Entry Points (Publishable)**
```toml
# In my-plugin/pyproject.toml
[project.entry-points."crow.hooks.pre_request"]
my_skill = "my_plugin:skill_hook"

[project.entry-points."crow.hooks.mid_react"]
compaction = "my_plugin:compaction_hook"
```

```python
# In Agent.__init__()
import importlib.metadata

for ep in importlib.metadata.entry_points(group="crow.hooks.pre_request"):
    hook = ep.load()
    self.hooks.register("pre_request", hook)
```

**Option 3: Via ACP ext_method (Protocol-Based)**
```python
# Client registers hooks via ACP
await client.ext_method(
    "crow.hooks.register",
    {
        "point": "pre_request",
        "name": "my_skill",
        "handler": "my_module:skill_hook",  # Importable path
    }
)
```

I think Option 1 + Option 2 are best. Option 3 is for client → agent extensions, not internal hooks.

## Builtin Hooks as Plugins

The beauty: skills and compaction are JUST REGULAR HOOKS.

```python
# crow/builtin_hooks/skills.py
async def skill_hook(ctx: HookContext):
    """
    Builtin skill hook - inject context based on keywords.
    
    Example: User mentions "database" → inject DB schema
    """
    if "database" in ctx.prompt.lower():
        schema = load_db_schema()
        ctx.inject_context(f"Context - Database Schema:\n{schema}")

# crow/builtin_hooks/compaction.py  
async def compaction_hook(ctx: HookContext):
    """
    Builtin compaction hook - summarize if over threshold.
    
    Keeps first K and last K messages, summarizes middle.
    Uses SAME session for KV cache preservation.
    """
    if ctx.should_compact():
        K = ctx.session.keep_last  # Configured per session
        head = ctx.session.messages[:K]
        tail = ctx.session.messages[-K:]
        middle = ctx.session.messages[K:-K]
        
        # Use LLM to summarize (same provider for KV cache!)
        summary = await ctx.llm.summarize(middle)
        
        # Create new compacted history
        ctx.session.messages = head + [summary] + tail

# crow/builtin_hooks/persistence.py
async def persistence_hook(ctx: HookContext):
    """
    Builtin persistence hook - save to DB after request.
    
    Alternative: persistence could be core (not a hook).
    """
    ctx.session.save_to_db()
```

## Agent Implementation

```python
# crow/agent/acp_native.py
class Agent(ACPAgent):
    def __init__(self, config=None):
        self.hooks = HookRegistry()
        self._load_builtin_hooks()
        self._load_plugin_hooks()
    
    def _load_builtin_hooks(self):
        """Load builtin hooks (skills, compaction)"""
        from crow.builtin_hooks import skills, compaction, persistence
        
        self.hooks.register("pre_request", skills.skill_hook)
        self.hooks.register("mid_react", compaction.compaction_hook)
        self.hooks.register("post_request", persistence.persistence_hook)
    
    def _load_plugin_hooks(self):
        """Load hooks from entry points"""
        import importlib.metadata
        
        for point in ["pre_request", "mid_react", "post_request"]:
            group = f"crow.hooks.{point}"
            for ep in importlib.metadata.entry_points(group=group):
                hook = ep.load()
                self.hooks.register(point, hook)
    
    async def prompt(self, prompt, session_id):
        # Get session
        session = self._sessions[session_id]
        user_text = extract_text(prompt)
        session.add_message("user", user_text)
        
        # HOOK POINT #1: PRE-REQUEST
        ctx = HookContext(session=session, prompt=user_text)
        await self.hooks.run("pre_request", ctx)
        
        # REACT LOOP
        async for chunk in self._react_loop(session_id):
            # Stream chunks to client...
            yield chunk
            
            # HOOK POINT #2: MID-REACT (after each LLM response)
            if chunk.get("type") == "final_response":
                ctx.usage = chunk.get("usage")
                await self.hooks.run("mid_react", ctx)
        
        # HOOK POINT #3: POST-REACT-LOOP
        await self.hooks.run("post_react_loop", ctx)
        
        return PromptResponse(stop_reason="end_turn")
    
    async def _after_prompt(self, session_id, response):
        """Called after prompt() returns"""
        # HOOK POINT #4: POST-REQUEST
        ctx = HookContext(
            session=self._sessions[session_id],
            response=response
        )
        await self.hooks.run("post_request", ctx)
```

## Hook Registry (The Infrastructure)

```python
# crow/hooks.py
class HookRegistry:
    """Manages hook registration and execution"""
    
    def __init__(self):
        self._hooks: dict[str, list[Hook]] = {
            "pre_request": [],
            "mid_react": [],
            "post_react_loop": [],
            "post_request": [],
        }
    
    def register(self, point: str, hook: Hook):
        """Register a hook at an extension point"""
        if point not in self._hooks:
            raise ValueError(f"Unknown hook point: {point}")
        self._hooks[point].append(hook)
    
    async def run(self, point: str, ctx: HookContext):
        """Run all hooks at an extension point"""
        for hook in self._hooks[point]:
            try:
                result = await hook(ctx)
                if result:
                    ctx = result  # Hooks can modify context
            except Exception as e:
                logger.error(f"Hook {hook} failed: {e}")
                # Continue running other hooks
```

## How Users Write Their Own Hooks

**Example: Custom Logging Hook**
```python
# my_logging_hook.py
from crow import HookContext

async def log_all_requests(ctx: HookContext):
    """Log every request to file"""
    with open("agent.log", "a") as f:
        f.write(f"Request: {ctx.prompt}\n")
        f.write(f"Usage: {ctx.usage}\n")

# Register via entry point
# pyproject.toml:
# [project.entry-points."crow.hooks.post_request"]
# logger = "my_logging_hook:log_all_requests"
```

**Example: Custom Skill Hook**
```python
# my_weather_skill.py
from crow import HookContext

async def weather_skill(ctx: HookContext):
    """Inject weather context when user mentions weather"""
    if "weather" in ctx.prompt.lower():
        weather_data = fetch_weather()
        ctx.inject_context(f"Current weather: {weather_data}")

# Register
# pyproject.toml:
# [project.entry-points."crow.hooks.pre_request"]
# weather = "my_weather_skill:weather_skill"
```

## The Python SDK

Users can also use programmatically:

```python
from crow import Agent, HookContext

# Create agent
agent = Agent()

# Define custom hook
async def my_hook(ctx: HookContext):
    print(f"User said: {ctx.prompt}")

# Register directly
agent.hooks.register("pre_request", my_hook)

# Run agent via ACP
from acp import run_agent
await run_agent(agent)
```

## Relationship to ACP Extensions

ACP's ext_method is for **client → agent** extensions:

```python
# Client calls custom method
result = await client.ext_method(
    "my_custom_capability",
    {"param": "value"}
)
```

Hooks are for **agent → agent** extensions (internal).

They're complementary:
- Use hooks for extending agent internals (skills, compaction)
- Use ext_method for client-triggered behavior (custom workflows)

## What About Persistence?

The user wondered if persistence should be a hook or core.

**Option 1: Persistence as Hook**
- Pros: Modular, can be disabled/replaced
- Cons: Too critical to be optional

**Option 2: Persistence as Core**
- Pros: Always works, no setup
- Cons: Less flexible

I think: Make it core, but allow hooks to augment.

```python
async def prompt(self, prompt, session_id):
    # ... react loop ...
    
    # CORE: Always persist
    session.save_to_db()
    
    # HOOKS: Can add more persistence
    await self.hooks.run("post_request", ctx)
```

## Summary

**The Design:**

1. **Hooks are first-class extension points** in the agent
2. **Four hook points**: pre_request, mid_react, post_react_loop, post_request
3. **Hooks are just async functions** that receive HookContext
4. **Builtin features (skills, compaction)** are just regular hooks
5. **Users can write hooks** as Python packages via entry points
6. **Can also register programmatically** for direct use
7. **ACP's ext_method** is separate (for client → agent, not internal hooks)

**The Framework:**
- ACP = protocol layer (session, cancel, extensions)
- MCP = tool layer (extensible tools)
- Hooks = agent layer (extensible behavior)

**Making it "stupidly easy":**
```python
# 1. Write a function
async def my_hook(ctx):
    if "database" in ctx.prompt:
        ctx.inject_context(load_schema())

# 2. Register it
# Either via entry point OR directly
agent.hooks.register("pre_request", my_hook)
```

That's it. No complex APIs, no XML configs, just Python functions.

**Next Steps:**
1. Implement HookRegistry
2. Add hook points to Agent
3. Migrate skills to pre_request hook
4. Migrate compaction to mid_react hook (when implemented)
5. Document the hook API
6. Publish example hooks
