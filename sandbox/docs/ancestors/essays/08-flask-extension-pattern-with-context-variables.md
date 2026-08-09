# Flask Extension Pattern with Context Variables

**Date**: February 15, 2026  
**Status**: Implemented - extension system in production

---

## The Problem with Direct Agent References

The initial extension design (essay 07) had extensions store `self.agent` directly:

```python
class MyExtension:
    def __init__(self, agent=None):
        self.agent = agent  # ❌ Stores reference to agent
        if agent is not None:
            self.init_agent(agent)
```

**Problems with this approach:**
1. **Circular imports**: Extension imports Agent, Agent imports Extension
2. **Testing difficulty**: Can't test extension without agent instance
3. **Application factory pattern**: Can't create extension before agent exists
4. **Memory leaks**: Extension holds reference to agent, agent holds reference to extension

---

## The Flask Solution: Context Variables

Flask extensions solve this with `current_app`:

```python
from flask import current_app

class FlaskExtension:
    def __init__(self, app=None):
        # Don't store app!
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        # Use current_app to access the app
        with app.app_context():
            # current_app is available here
            app.extensions['my_extension'] = self
```

**Key insight**: The extension doesn't store the app. It uses `current_app` to access it when needed.

---

## Applied to Crow: Context Variables

We use `contextvars` for the same pattern:

```python
import contextvars

# Context variable for current agent (like Flask's current_app)
_current_agent: contextvars.ContextVar["Agent"] = contextvars.ContextVar("crow_agent")


def get_current_agent() -> "Agent":
    """Get the current agent (like Flask's current_app)."""
    return _current_agent.get()


class Extension:
    def __init__(self, **config):
        # Don't store agent!
        self.config = config
        self._initialized = False
    
    def init_app(self, agent: "Agent"):
        """Initialize extension with agent."""
        self._initialized = True
        # Register hooks, but don't store agent
```

**Usage:**
```python
class MyExtension(Extension):
    def __init__(self, setting: str = "default"):
        self.setting = setting
    
    def init_app(self, agent: Agent):
        # Register hooks
        agent.hooks.register_hook("pre_request", self.pre_request)
    
    async def pre_request(self, ctx: ExtensionContext):
        # Use get_current_agent() to access the agent
        agent = get_current_agent()
        # ... do something ...
```

---

## ExtensionContext with Context Manager

The `ExtensionContext` manages the agent context:

```python
@dataclass
class ExtensionContext:
    session: Session
    config: Config
    db_session: SQLAlchemySession
    _agent_token: Any = field(repr=False, default=None)
    
    def __enter__(self):
        """Set this context as the current agent context."""
        self._agent_token = _current_agent.set(self)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Reset the agent context."""
        if self._agent_token is not None:
            _current_agent.reset(self._agent_token)
    
    def get_agent(self) -> "Agent":
        """Get the agent from the context."""
        return get_current_agent()
```

**Usage:**
```python
async def some_extension_method(ctx: ExtensionContext):
    with ctx:  # Sets up context
        agent = get_current_agent()
        # Use agent...
    # Context automatically cleaned up
```

---

## Why This Pattern?

### 1. No Circular Imports
- Extension doesn't import Agent
- Agent imports Extension
- No circular dependency!

### 2. Application Factory Pattern
- Can create extension before agent exists
- Extension can be configured before initialization
- Supports multiple agent instances

```python
# Can do this:
ext = MyExtension(setting="custom")

def create_agent():
    agent = Agent()
    ext.init_app(agent)
    return agent
```

### 3. Better Testing
- Can test extension without agent
- Can mock `get_current_agent()` in tests
- No need to create full agent instance

```python
def test_extension():
    ext = MyExtension(setting="test")
    # Test extension logic without agent
```

### 4. No Memory Leaks
- Extension doesn't hold reference to agent
- Agent doesn't hold reference to extension
- Context variables are cleaned up automatically

### 5. Thread-Safe
- Context variables are thread-local
- Each thread has its own agent context
- No race conditions

---

## The Architecture

```
Crow Agent (core)
├── Agent.__init__()
│   ├── Creates HookRegistry
│   ├── Creates ExtensionContext
│   └── Calls init_app() on each extension
├── ExtensionContext
│   ├── Manages _current_agent context variable
│   ├── Provides get_current_agent()
│   └── Supports context manager pattern
└── Extensions
    ├── Initialized with config, not agent
    ├── Register hooks during init_app()
    ├── Use get_current_agent() to access agent
    └── No direct reference to agent
```

---

## Hook Points

### 1. pre_request
- Called before the react loop starts
- Used for: Skills, context injection, message modification
- Can: Modify messages, inject context, stop current turn

### 2. mid_react
- Called after each LLM response, before tool execution
- Used for: Compaction, token tracking, stuck detection
- Can: Check token count, stop current turn, modify messages

### 3. post_react_loop
- Called after the react loop ends, before return
- Used for: Summarization, metrics, cleanup
- Can: Modify final response, save state

### 4. post_request
- Called after prompt() returns
- Used for: Re-prompting, logging, persistence
- Can: Trigger re-prompt, save to DB

---

## Example: Skill Extension

```python
# my_skills/weather_skill.py
from crow import Agent, Extension, get_current_agent

class WeatherSkill(Extension):
    name = "weather_skill"
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
    
    def init_app(self, agent: Agent):
        # Register hook
        agent.hooks.register_hook("pre_request", self.pre_request)
    
    async def pre_request(self, ctx):
        """Inject weather context when user mentions weather"""
        
        # Get the latest user message
        user_message = await ctx.get_latest_user_message()
        
        if not user_message:
            return
        
        # Check if skill is relevant
        if "weather" in user_message.lower():
            # Load weather data
            weather_data = fetch_weather_data(self.api_key)
            
            # Inject context
            context_text = f"Current weather: {weather_data}"
            await ctx.inject_context(context_text)
```

**Registration:**
```toml
# In pyproject.toml
[project.entry-points."crow.extensions"]
weather_skill = "my_skills.weather_skill:WeatherSkill"
```

---

## Example: Compaction Extension

```python
# my_extensions/compaction.py
from crow import Agent, Extension, get_current_agent

class Compaction(Extension):
    name = "compaction"
    COMPACT_THRESHOLD = 100000  # 100k tokens
    
    def __init__(self, threshold: int | None = None):
        self.threshold = threshold or self.COMPACT_THRESHOLD
    
    def init_app(self, agent: Agent):
        # Register hook
        agent.hooks.register_hook("mid_react", self.mid_react)
    
    async def mid_react(self, ctx):
        """Compact conversation history if over threshold"""
        
        # Get token count
        token_count = await ctx.get_token_count()
        
        if token_count["total_tokens"] > self.threshold:
            # Stop current turn
            await ctx.stop_current_turn()
            
            # Compress history
            messages = await ctx.get_messages()
            compressed = compress_history(messages)
            
            # Create new session
            new_session_id = await ctx.restart_with_new_session()
            
            # Load compressed history into new session
            # (This would be done by the agent, not the extension)
            
            # Continue with new session
            await ctx.continue_with_current_session()
```

**Registration:**
```toml
[project.entry-points."crow.extensions"]
compaction = "my_extensions.compaction:Compaction"
```

---

## Integration with Agent

```python
class Agent(ACPAgent):
    def __init__(self, config=None, extensions=None):
        # ... existing initialization ...
        
        # Extension system
        self._extensions: dict[str, Extension] = {}
        self._hook_registry = HookRegistry()
        
        # Initialize extensions
        if extensions:
            for ext in extensions:
                self.register_extension(ext)
    
    def register_extension(self, extension: Extension):
        """Register an extension with the agent."""
        extension.init_app(self)
        self._extensions[extension.name] = extension
    
    def get_extension(self, name: str) -> Extension:
        """Get an extension by name."""
        return self._extensions[name]
```

---

## Why Context Variables Over Direct References?

### Flask's Reasoning (from their docs):

> "It is important that the app is not stored on the extension, don't do `self.app = app`. The only time the extension should have direct access to an app is during `init_app`, otherwise it should use `current_app`."

**Why?**
1. **Application factory pattern**: Extensions can be created before apps exist
2. **No circular imports**: Extensions don't need to import app
3. **Testing**: Can test extensions without apps
4. **Multiple app support**: Each app has its own context

**Same applies to Crow!**

---

## Summary

**The Flask extension pattern with context variables:**

1. **Extensions are initialized with config, not the agent**
2. **Extensions use `init_app(agent)` to register with the agent**
3. **Extensions don't store the agent directly**
4. **Extensions use `get_current_agent()` to access the agent when needed**
5. **Context variables manage the current agent context**

**Benefits:**
- No circular imports
- Application factory pattern support
- Better testing
- No memory leaks
- Thread-safe

**This is the right pattern for Crow** - it's simple, powerful, and follows proven Python patterns.
