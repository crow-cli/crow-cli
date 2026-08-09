# pluggy: The Missing Piece

## The Discovery

We had designed self-injection. We had the hook lifecycle mapped out. We had the `TYPE_CHECKING` escape hatch. But something was missing.

The question kept nagging: "Do I really need to build my own hook registry? My own plugin discovery? My own call ordering?"

And then: **pluggy**.

> `pluggy` is the crystallized core of plugin management and hook calling for pytest. It enables 1400+ plugins to extend and customize pytest's default behaviour.

This is it. This is exactly what we need.

## What Is pluggy?

pluggy is a **battle-tested plugin framework** extracted from pytest. It powers:

- **pytest** (1400+ plugins)
- **tox** (testing automation)
- **devpi** (PyPI staging)
- **kedro** (data pipelines)

It provides:

1. **Hook specifications** (`@hookspec`) - the contract the host defines
2. **Hook implementations** (`@hookimpl`) - the plugins that fulfill the contract
3. **PluginManager** - connects host and plugins
4. **Entry point discovery** - `uv add my-plugin` just works
5. **Call ordering** - `tryfirst`, `trylast`
6. **Wrappers** - wrap around other hooks like middleware
7. **Result collection** - gather results from all plugins

## How It Works

### The Host Defines Specs

```python
# crow_acp/hookspecs.py
import pluggy

hookspec = pluggy.HookspecMarker("crow-acp")

class CrowSpec:
    """Hook specifications for crow-acp."""
    
    @hookspec
    def on_session_start(self, agent, session):
        """Called when a new session starts."""
        pass
    
    @hookspec
    def before_run(self, agent, user_input):
        """Called before the agent loop starts."""
        pass
    
    @hookspec(firstresult=True)  # Stop at first non-None result
    def before_llm_request(self, agent, session, messages):
        """Called before sending to LLM. Return modified messages."""
        pass
    
    @hookspec
    def after_turn(self, agent, session, usage):
        """Called after a turn completes."""
        pass
    
    @hookspec
    def on_shutdown(self, agent):
        """Called when the agent shuts down."""
        pass
```

### The Agent (Host) Uses PluginManager

```python
# crow_acp/agent.py
import pluggy
from crow_acp.hookspecs import CrowSpec

class AcpAgent(Agent):
    def __init__(self, config: Config = None):
        self._config = config or get_default_config()
        
        # Set up plugin manager
        self._pm = pluggy.PluginManager("crow-acp")
        self._pm.add_hookspecs(CrowSpec)
        
        # Auto-discover installed plugins via entry points
        self._pm.load_setuptools_entrypoints("crow-acp")
        
        # The hook namespace for calling
        self.hook = self._pm.hook
        
        # ... rest of init ...
    
    async def prompt(self, prompt, session_id, **kwargs):
        session = self._sessions[session_id]
        user_text = self._extract_text(prompt)
        
        # Call hooks - self-injection style
        await self.hook.before_run(agent=self, user_input=user_text)
        
        session.add_message("user", user_text)
        
        async for chunk in self._react_loop(session_id):
            yield chunk
    
    async def _react_loop(self, session_id):
        session = self._sessions[session_id]
        
        for _ in range(max_turns):
            # Call hooks before LLM
            messages = await self.hook.before_llm_request(
                agent=self, 
                session=session, 
                messages=session.messages
            ) or session.messages
            
            # ... llm call, tool execution ...
            
            # Call hooks after turn
            await self.hook.after_turn(
                agent=self,
                session=session,
                usage=usage
            )
            
            if not tool_calls:
                break
```

### Plugins Implement Hooks

```python
# crow_persistence/plugin.py
from crow_acp import hookimpl

class SQLitePersistence:
    def __init__(self, db_path="~/.crow/crow.db"):
        self.db_path = db_path
        self._queue = []
    
    @hookimpl
    async def after_turn(self, agent, session, usage):
        """Save session state after each turn."""
        events = self._extract_events(session)
        self._queue.extend(events)
        
        if len(self._queue) >= 50:
            await self._flush()
    
    @hookimpl
    async def on_shutdown(self, agent):
        """Flush remaining events on shutdown."""
        await self._flush()

# Register as entry point in pyproject.toml:
# [project.entry-points."crow-acp"]
# persistence = "crow_persistence.plugin:SQLitePersistence"
```

```python
# crow_skills_rag/plugin.py
from crow_acp import hookimpl

class RAGHook:
    def __init__(self, vector_db_path):
        self.db = load_vector_db(vector_db_path)
    
    @hookimpl(tryfirst=True)  # Run before other hooks
    async def before_run(self, agent, user_input):
        """Inject relevant context from vector DB."""
        results = self.db.search(user_input, top_k=5)
        if results:
            context = "\n".join(results)
            session = agent._sessions.get(agent._session_id)
            if session:
                session.add_message("system", f"Context:\n{context}")
```

## Entry Points: The `uv add` Dream

The magic is in entry points. A plugin registers itself in `pyproject.toml`:

```toml
# crow-persistence/pyproject.toml
[project]
name = "crow-persistence"
dependencies = ["crow-acp", "sqlalchemy"]

[project.entry-points."crow-acp"]
persistence = "crow_persistence:SQLitePersistence"
```

Then the user just does:

```bash
uv add crow-persistence
```

And the host auto-discovers it:

```python
self._pm.load_setuptools_entrypoints("crow-acp")
```

**No manual registration. No config files. Just install and it works.**

This is exactly how pytest plugins work. You `pip install pytest-xdist` and suddenly you have `pytest -n auto` for parallel testing. No config needed.

## Call Ordering: tryfirst and trylast

One problem with hook systems is ordering. What if two plugins both implement `before_llm_request`? Which runs first?

pluggy solves this elegantly:

```python
@hookimpl(tryfirst=True)
async def before_llm_request(self, agent, session, messages):
    # Runs first - good for security/validation
    if contains_pii(messages):
        raise ValueError("PII detected!")
    return messages

@hookimpl(trylast=True)
async def before_llm_request(self, agent, session, messages):
    # Runs last - good for final modifications
    messages.insert(0, {"role": "system", "content": "Be helpful."})
    return messages
```

Within each priority level, plugins are called in LIFO (last registered, first called) order.

## Wrappers: The Middleware Pattern

pluggy supports **hook wrappers** - plugins that wrap around other plugins:

```python
@hookimpl(wrapper=True)
async def after_turn(self, agent, session, usage):
    """Wrap all after_turn hooks with logging."""
    logger.info(f"Turn starting for session {session.session_id}")
    
    # Call all other after_turn implementations
    result = yield
    
    logger.info(f"Turn complete, usage: {usage}")
    
    return result
```

This is exactly like Express.js middleware or Python context managers. The wrapper can:
- Run code before other hooks
- Run code after other hooks
- Modify the result
- Handle exceptions

## Result Collection

When multiple plugins implement the same hook, pluggy collects all results:

```python
# Multiple plugins implement this hook
results = await self.hook.after_turn(agent=self, session=session, usage=usage)
# results is a list of all return values (excluding None)
```

Or use `firstresult=True` to stop at the first non-None result:

```python
@hookspec(firstresult=True)
def before_llm_request(self, agent, session, messages):
    """Stop at first plugin that returns modified messages."""
    pass
```

## Why This Is Better Than Rolling Our Own

| Aspect | Roll Your Own | pluggy |
|--------|---------------|--------|
| Entry point discovery | Build it yourself | Built-in |
| Call ordering | Build it yourself | `tryfirst`/`trylast` |
| Wrappers | Build it yourself | `wrapper=True` |
| Result collection | Build it yourself | Built-in |
| Validation | Build it yourself | `@hookspec` validates `@hookimpl` |
| Battle-testing | Untested | Powers 1400+ pytest plugins |
| Documentation | Write it yourself | Excellent docs |
| Community | Just you | pytest, tox, devpi, kedro |

**The choice is obvious.**

## The New Architecture

```
crow-acp/
├── __init__.py           # Exports hookimpl marker
├── agent.py              # Uses PluginManager
├── hookspecs.py          # Defines @hookspec contracts
├── session.py            # Pure in-memory state
└── plugins/              # Built-in plugins (optional)
    ├── __init__.py
    ├── persistence.py    # SQLite via @hookimpl
    └── system.py         # System prompt via @hookimpl

crow-persistence/         # Separate package (future)
├── __init__.py
└── plugin.py             # @hookimpl implementations

crow-skills-rag/          # Separate package (future)
├── __init__.py
└── plugin.py             # @hookimpl implementations
```

## The User Experience

**Default (no plugins):**

```python
from crow_acp import AcpAgent

agent = AcpAgent()  # Just works, no plugins
await run_agent(agent)
```

**With built-in plugins:**

```python
from crow_acp import AcpAgent
from crow_acp.plugins import PersistenceHook, SystemPromptHook

agent = AcpAgent()
agent._pm.register(PersistenceHook())
agent._pm.register(SystemPromptHook("You are Crow."))
await run_agent(agent)
```

**With external plugins (just install):**

```bash
uv add crow-persistence
uv add crow-skills-rag
```

```python
from crow_acp import AcpAgent

agent = AcpAgent()  # Auto-discovers installed plugins!
await run_agent(agent)
```

## The Self-Injection + pluggy Combination

Self-injection and pluggy are perfect together:

1. **pluggy provides the plumbing** - registration, discovery, ordering, validation
2. **Self-injection provides the power** - passing the whole agent to hooks

```python
@hookimpl
async def after_turn(self, agent, session, usage):
    # pluggy calls this at the right time
    # self-injection gives us the whole agent
    # we can do whatever we want
    agent._some_internal_thing = "modified"
    session.messages.append({"role": "system", "content": "Turn complete."})
```

pluggy handles the **when**. Self-injection handles the **what**.

## Migration Path

### Phase 1: Add pluggy to crow-acp

1. Add `pluggy` to dependencies
2. Create `hookspecs.py` with our hook specifications
3. Modify `AcpAgent` to use `PluginManager`
4. Add hook calls at lifecycle points

### Phase 2: Extract persistence into a plugin

1. Create `plugins/persistence.py` with `@hookimpl`
2. Remove persistence from `session.py`
3. Make `session.py` pure in-memory

### Phase 3: Create external plugin packages

1. Extract `crow-persistence` as separate package
2. Add entry point registration
3. Test `uv add crow-persistence` auto-discovery

### Phase 4: Build the ecosystem

1. `crow-skills-rag` - vector DB context injection
2. `crow-compaction` - automatic context compaction
3. `crow-analytics` - usage tracking
4. Community plugins...

## Conclusion

pluggy is the missing piece. It gives us:

- **Entry point discovery** - `uv add` just works
- **Call ordering** - `tryfirst`/`trylast`
- **Wrappers** - middleware pattern
- **Validation** - specs validate implementations
- **Battle-testing** - powers pytest's 1400+ plugins

Combined with self-injection, we get a plugin system that is:

- **Powerful** - hooks get the whole agent
- **Simple** - just decorate functions with `@hookimpl`
- **Discoverable** - entry points auto-load
- **Ordered** - explicit control over execution order
- **Composable** - multiple plugins work together

We don't need to build this ourselves. The pytest team already did. And they did it well.

---

*"Do not reinvent the wheel. Use the wheel that powers 1400+ pytest plugins."*

**Next step: Add pluggy as a dependency and create `hookspecs.py`.**
