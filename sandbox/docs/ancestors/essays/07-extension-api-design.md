# Extension API Design - Flask Extension Pattern for Crow

**Date**: February 15, 2026  
**Status**: Design phase - implementing in next session

---

## The Contradiction

**Question**: Should we design a custom extension interface (like a service/API)?
**Or**: Should we just use the existing Python code as the interface?

**Resolution**: We're building a **Python SDK**, not a service. People will run this locally, not through a proprietary API. We can use the actual Python code as the interface!

---

## The Flask Extension Pattern

Flask extensions follow this pattern:

```python
class MyExtension:
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        # Register hooks on app
        app.before_request(self.before_request)
        # Store reference on app.extensions
        app.extensions['my_extension'] = self
```

**Key insight**: The extension receives a reference to the app and can call any method on it!

---

## Applied to Crow

```python
class MyExtension:
    def __init__(self, agent=None):
        self.agent = agent
        if agent is not None:
            self.init_agent(agent)
    
    def init_agent(self, agent):
        # Register hooks
        agent.hooks.register("pre_request", self.pre_request)
        # Store reference
        agent.extensions['my_extension'] = self
    
    def pre_request(self, ctx):
        # Access agent state directly
        messages = self.agent._sessions[ctx.session_id].messages
        # Do whatever you want with the agent!
```

**This is it!** The extension system is simple:
1. Extensions are Python classes
2. They have an `init_agent(agent)` method
3. They receive a reference to the Agent
4. They can call any method on the Agent
5. They can register hooks on the Agent

---

## The Architecture

```
Crow Agent (core)
├── Built-in "extensions" (skills, compaction, persistence)
│   ├── These are just regular Python classes
│   ├── They receive a reference to the Agent
│   ├── They can call any method on the Agent
│   └── They can register hooks on the Agent
└── User extensions (external packages)
    ├── Same pattern as built-in extensions
    ├── Can be installed via pip
    ├── Can be registered via entry points
    └── Can call any method on the Agent
```

---

## Implementation

```python
class Agent(ACPAgent):
    def __init__(self, config=None):
        # ... existing initialization ...
        
        # Extension system
        self.extensions: dict[str, Any] = {}
        self.hooks = HookRegistry()
        
        # Load extensions
        self._load_extensions()
    
    def _load_extensions(self):
        # Load built-in extensions
        self._load_builtin_extensions()
        
        # Load external extensions via entry points
        self._load_external_extensions()
    
    def _load_builtin_extensions(self):
        # Import and initialize built-in extensions
        from crow.agent.extensions import skills, compaction, persistence
        
        skills.init_agent(self)
        compaction.init_agent(self)
        persistence.init_agent(self)
    
    def _load_external_extensions(self):
        # Load extensions from entry points
        import importlib.metadata
        
        for ep in importlib.metadata.entry_points(group="crow.extensions"):
            ext_class = ep.load()
            ext = ext_class()
            ext.init_agent(self)
```

---

## Extension Interface

**The extension interface IS the Agent interface.** Extensions have full access to the Agent through `self.agent`.

Extensions can:
1. Call any public method on the Agent
2. Access any public attribute on the Agent
3. Register hooks on the Agent
4. Modify the Agent's behavior

**No custom ExtensionContext needed!** Extensions have direct access to the agent.

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
from crow import Agent

class WeatherSkill:
    def __init__(self, agent=None):
        self.agent = agent
        if agent is not None:
            self.init_agent(agent)
    
    def init_agent(self, agent: Agent):
        # Register hook
        agent.hooks.register("pre_request", self.pre_request)
        # Store reference
        agent.extensions['weather_skill'] = self
    
    async def pre_request(self, ctx):
        """Inject weather context when user mentions weather"""
        
        # Get the latest user message
        user_message = await ctx.get_latest_user_message()
        
        if not user_message:
            return
        
        # Check if skill is relevant
        if "weather" in user_message.lower():
            # Load weather data
            weather_data = fetch_weather_data()
            
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
from crow import Agent

class Compaction:
    COMPACT_THRESHOLD = 100000  # 100k tokens
    
    def __init__(self, agent=None):
        self.agent = agent
        if agent is not None:
            self.init_agent(agent)
    
    def init_agent(self, agent: Agent):
        # Register hook
        agent.hooks.register("mid_react", self.mid_react)
        # Store reference
        agent.extensions['compaction'] = self
    
    async def mid_react(self, ctx):
        """Compact conversation history if over threshold"""
        
        # Get token count
        token_count = await ctx.get_token_count()
        
        if token_count["total_tokens"] > self.COMPACT_THRESHOLD:
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

## Why This Design?

### Direct Access
- Extensions have full access to the Agent
- No need for a custom interface
- Extensions can do anything the Agent can do

### Simple
- Extensions are just Python classes
- No complex API to learn
- Follows the Flask pattern (familiar to Python developers)

### Flexible
- Extensions can be loaded via entry points OR direct registration
- Extensions can be built-in or external
- Extensions can modify any aspect of the Agent

### Maintainable
- No custom interface to maintain
- Extensions use the Agent's public API
- Clear separation of concerns

---

## Next Steps

1. Implement HookRegistry class
2. Add extension loading to Agent.__init__
3. Implement simple extensions (skills)
4. Test with real use cases
5. Iterate and refine

---

## Summary

**The extension system is simple**:
1. Extensions are Python classes with an `init_agent(agent)` method
2. Extensions receive a reference to the Agent
3. Extensions can call any method on the Agent
4. Extensions are loaded via entry points during Agent.__init__

**No custom interface needed!** The Agent IS the interface.

**This is perfect** - it's simple, powerful, and follows the Flask extension pattern.
