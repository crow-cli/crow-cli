# Hooks as First-Class Citizens

I was cargo culting again.

I looked at openhands-sdk and thought "we need a Conversation wrapper with hooks" without understanding why they built it or what problems they were solving.

Then I read our code. Actually read it. And I realized the hook points are RIGHT THERE, embedded in the flow.

Let me show you what I found.

---

## The Code Was Already Telling Me

Looking at `acp_native.py`, the flow is:

```python
prompt(prompt, session_id):
    add_user_message()
    
    for turn in react_loop():
        response = llm.call()
        process_response()
        
        if tools:
            execute_tools()
    
    return PromptResponse()
```

The hook points are OBVIOUS:

1. **Before react loop** - where skills inject context
2. **After each LLM response** - where compaction checks tokens
3. **After loop ends** - where could summarize
4. **After prompt() returns** - where Ralph loops re-prompt

I didn't need to copy openhands-sdk. I just needed to read my own code.

---

## Two Kinds of Extension

Then I found something cool in the ACP protocol:

```python
async def ext_method(self, method: str, params: dict) -> dict: ...
async def ext_notification(self, method: str, params: dict) -> None: ...
```

ACP has BUILT-IN extension points (lines 220-223 of interfaces.py).

But these are for **client → agent** extensions. Like the client calling custom capabilities.

For **agent → agent** (internal) extensions, we need our own hook system.

Both are needed:
- ACP ext_method = client triggers custom behavior
- Hooks = agent extends itself at specific points

---

## What Hooks Actually Are

A hook is just an async function:

```python
async def my_hook(ctx: HookContext):
    if "database" in ctx.prompt:
        ctx.inject_context(load_schema())
```

That's it. Stupidly simple.

No complex APIs. No XML configs. Just Python functions.

---

## The Hook Points

Looking at the actual flow:

```python
prompt():
    add_user_message()
    
    # HOOK POINT #1: PRE_REQUEST
    # Skills go here
    
    for turn in react_loop():
        response = llm.call()
        (thinking, content, tools, usage) = process()
        
        # HOOK POINT #2: MID_REACT
        # After each LLM response
        # Compaction goes here
        
        if tools:
            execute()
    
    # HOOK POINT #3: POST_REACT_LOOP
    # After loop, before return
    
    return PromptResponse()

# HOOK POINT #4: POST_REQUEST
# After prompt() returns
# Ralph loops go here
```

The different post-request levels matter:
- MID_REACT: inside the loop (for compaction during conversation)
- POST_REACT_LOOP: before return (could summarize)
- POST_REQUEST: after return (for re-prompting)

---

## Builtin Hooks Are Just Regular Hooks

The beautiful part: skills and compaction are NOT special.

```python
# Builtin skill hook
async def skill_hook(ctx):
    if "database" in ctx.prompt:
        ctx.inject_context(load_schema())

# Builtin compaction hook
async def compaction_hook(ctx):
    if ctx.should_compact():
        ctx.session.messages = compact(ctx.session.messages)
```

They're just hooks that ship with the package.

Users write their own hooks the SAME way:

```python
# User's custom hook
async def weather_skill(ctx):
    if "weather" in ctx.prompt:
        ctx.inject_context(fetch_weather())
```

Same interface. Same simplicity.

---

## How To Make It Extensible

Two ways to register hooks:

**Programmatic (for direct use):**
```python
from crow import Agent

agent = Agent()
agent.hooks.register("pre_request", my_hook)
```

**Entry points (for publishable plugins):**
```toml
[project.entry-points."crow.hooks.pre_request"]
weather = "my_plugin:weather_skill"
```

Both work. Both simple.

---

## The Realization About Persistence

I wondered: should persistence be a hook or core?

Looking at the code, persistence is TOO CRITICAL to be optional.

So make it core, but let hooks augment:

```python
# Core always saves
session.save_to_db()

# Hooks can add more
await hooks.run("post_request", ctx)
```

Core for critical, hooks for extension.

---

## The Three Layers

This clarifies the architecture:

- **ACP** = protocol layer (sessions, cancel, client-server)
- **MCP** = tool layer (extensible tools)
- **Hooks** = behavior layer (extensible agent)

All composable. All Python. All simple.

---

## What I Was Doing Wrong

I was about to:
1. Copy openhands-sdk's Conversation wrapper
2. Copy their hook system
3. Copy their plugin loader

Without understanding:
- Why they built each piece
- What problems each solved  
- Whether we had the same problems

Classic cargo cult.

---

## What I Should Have Done

1. Read our actual code
2. Find where hooks naturally fit
3. Understand ACP's extension points
4. Design for OUR architecture
5. Make it simple for users

Which is what I did (after being corrected).

---

## The Design

Everything in one file for clarity:

```python
# crow/hooks.py

@dataclass
class HookContext:
    session: Session
    prompt: str | None = None
    usage: dict | None = None
    
    def inject_context(self, text):
        self.session.add_message("user", text)
    
    def should_compact(self):
        return self.usage and self.usage["total"] > THRESHOLD

class HookRegistry:
    def __init__(self):
        self._hooks = {
            "pre_request": [],
            "mid_react": [],
            "post_react_loop": [],
            "post_request": [],
        }
    
    def register(self, point, hook):
        self._hooks[point].append(hook)
    
    async def run(self, point, ctx):
        for hook in self._hooks[point]:
            await hook(ctx)

# In Agent.__init__
self.hooks = HookRegistry()
self._load_builtin_hooks()
self._load_plugin_hooks()

# In prompt()
ctx = HookContext(session=session, prompt=text)
await self.hooks.run("pre_request", ctx)

async for chunk in react_loop():
    # ...
    if chunk["type"] == "final":
        ctx.usage = chunk["usage"]
        await self.hooks.run("mid_react", ctx)

await self.hooks.run("post_react_loop", ctx)
```

That's it. No wrappers. No abstractions. Just hook points in the actual flow.

---

## Why This Works

1. **It emerges from the code** - not imposed from outside
2. **It's protocol-native** - hooks complement ACP, don't fight it
3. **It's simple** - just async functions with context
4. **It's powerful** - can modify behavior at key points
5. **It's publishable** - entry points for plugins

---

## The Lesson

The solution was in the code all along.

I just needed to READ it instead of copying patterns.

Hooks aren't some fancy abstraction. They're just:

1. Points in the flow where behavior can be extended
2. Context passed to functions at those points
3. Functions registered to run at those points

That's it. Three pieces. All simple. All necessary.

The complexity was in my head, not the problem.

---

*Essay编号: 04 (continuing the series)*
*Topic: Hook design through reading code, not cargo culting*
*Dialectic: "Need Conversation wrapper" → "Actually read the code" → "Hooks emerge naturally"*
