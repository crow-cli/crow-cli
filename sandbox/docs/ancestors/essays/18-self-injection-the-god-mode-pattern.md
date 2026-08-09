# Self-Injection: The God-Mode Pattern

## The Problem with "Clean" Plugin APIs

You've seen it before. A framework wants to be extensible, so it designs a "Plugin API":

```python
# The "clean" way
class PluginBase(ABC):
    @abstractmethod
    def on_event(self, context: PluginContext) -> PluginResult:
        pass

# The "safe" context object
class PluginContext:
    def get_user_input(self) -> str: ...
    def get_session_id(self) -> str: ...
    # But you can't access the raw agent state
```

This feels corporate. Restrictive. Every time a plugin author needs something that isn't exposed in `PluginContext`, they have to file a feature request. The framework author becomes a gatekeeper.

**This isn't composition. It's a prison with nice furniture.**

## The Insight: Python Doesn't Have Private Variables

Python's philosophy is "we are all consenting adults here." The `_` prefix is just a polite suggestion. You CAN access `_private_var` if you want to. The language doesn't stop you.

This means we can pass the ENTIRE object to extensions, not a sanitized subset. Extensions get the same access as the core code. No SDK layer. No gatekeeping.

**This is self-injection.**

## What Is Self-Injection?

Self-injection is passing `self` (the whole object) to hooks/extensions, giving them complete access to mutate state.

```python
# crow_acp/agent.py
class AcpAgent:
    def __init__(self, hooks: list = None):
        self.hooks = hooks or []
        self.messages = []
        self.model_name = "gpt-4"
        self._db_path = "~/.crow/crow.db"
    
    async def run(self, user_input: str):
        # Pass YOURSELF to the hook
        for hook in self.hooks:
            await hook.before_run(self)  # <- self-injection
        
        # ... do llm call ...
```

The hook receives the entire agent:

```python
# crow_skill_rag/plugin.py
class RAGHook:
    async def before_run(self, agent):  # <- receives full agent
        # Total access. No SDK required.
        context = self.vector_db.search(agent.messages[-1]["content"])
        
        # Mutate the agent's raw state directly
        agent.messages.insert(0, {"role": "system", "content": f"Context: {context}"})
        
        # Can even change the model on the fly
        if len(agent.messages) > 10:
            agent.model_name = "claude-3-haiku"
```

## The TYPE_CHECKING Escape Hatch

The only reason self-injection SEEMS to create a circular dependency is type hinting:

- `agent.py` imports `AgentHook` to type the hooks list
- `hooks.py` would need to import `AcpAgent` to type the `agent` parameter

Python gives us a built-in solution: `typing.TYPE_CHECKING`.

```python
# crow_acp/hooks.py
from typing import TYPE_CHECKING

# This is True for mypy/pyright, but FALSE at runtime
if TYPE_CHECKING:
    from crow_acp.agent import AcpAgent

class AgentHook:
    """
    Extensions get the raw Agent. Do whatever you want.
    We are all consenting adults here.
    """
    
    async def before_run(self, agent: "AcpAgent") -> None:
        """Called before the agent runs. Agent is fully accessible."""
        pass
    
    async def after_turn(self, agent: "AcpAgent", usage: dict) -> None:
        """Called after a turn completes. Agent is fully accessible."""
        pass
```

```python
# crow_acp/agent.py
from crow_acp.hooks import AgentHook

class AcpAgent:
    def __init__(self, hooks: list[AgentHook] = None):
        self.hooks = hooks or []
```

**How this works:**

1. At runtime, `TYPE_CHECKING` is `False`, so the `if TYPE_CHECKING:` block never runs
2. The string `"AcpAgent"` in the type hint is never evaluated as an actual type
3. No circular import occurs
4. But mypy/pyright still see the type hint and provide autocomplete/checking

## Why This Is Better Than Inheritance

With inheritance, you extend the class:

```python
# WRONG - Inheritance
class MyAgent(AcpAgent):
    async def run(self, user_input):
        # I have to override methods to change behavior
        result = await super().run(user_input)
        # Can't easily compose multiple behaviors
        return result
```

With self-injection, you compose behaviors:

```python
# RIGHT - Composition via self-injection
class PersistenceHook:
    async def after_turn(self, agent, usage):
        agent._save_to_db()

class RAGHook:
    async def before_run(self, agent):
        context = self.search(agent.messages[-1])
        agent.messages.insert(0, {"role": "system", "content": context})

# Compose them
agent = AcpAgent(hooks=[
    PersistenceHook(),
    RAGHook(),
    CompactionHook(),
])
```

**Multiple inheritance is a nightmare. Composition is a list.**

## Real-World Example: pytest

pytest uses this exact pattern. Hooks receive the entire test session:

```python
# pytest plugin
def pytest_collection_modifyitems(session, config, items):
    # session is the FULL session object
    # config is the FULL config object
    # items is the FULL list of test items
    
    # You can mutate anything
    items[:] = [item for item in items if "slow" not in item.name]
```

pytest doesn't give you a sanitized `TestContext` object. It gives you the real thing. That's why pytest has 1400+ plugins - plugin authors aren't blocked by the framework.

## The Philosophy: "Consenting Adults"

Python's design philosophy, from Guido van Rossum:

> "We are all consenting adults here."

The language assumes you know what you're doing. It doesn't hide things behind `private` keywords. It trusts you.

Self-injection extends this philosophy to plugin design:

- The framework gives you access to everything
- The framework defines WHEN hooks run (the lifecycle)
- The hook defines WHAT happens
- If you break something, that's on you

**This is the opposite of "defensive programming." It's "trusting programming."**

## The Trade-offs

| Aspect | SDK/Guarded Approach | Self-Injection |
|--------|---------------------|----------------|
| Safety | Framework protects internals | Hook can break anything |
| Flexibility | Limited to what SDK exposes | Unlimited access |
| Boilerplate | Context classes, getters/setters | None |
| Learning curve | Must learn SDK API | Just read the source |
| Maintenance | SDK must be maintained | No SDK to maintain |
| Debugging | Clear boundary | Hook could mutate anywhere |

**The choice is philosophical, not technical.**

Do you trust your extension authors? Then self-injection.

## Implementation for crow-acp

```python
# crow_acp/hooks.py
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crow_acp.agent import AcpAgent
    from crow_acp.session import Session

class AgentHook:
    """Base class for agent extensions. Receives full agent access."""
    
    async def on_session_start(self, agent: "AcpAgent", session: "Session") -> None:
        """Called when a new session starts."""
        pass
    
    async def before_run(self, agent: "AcpAgent", user_input: str) -> None:
        """Called when user sends a message, before the agent loop starts.
        
        Good for: RAG, modifying input, checking permissions, injecting context.
        The agent is fully mutable - add to agent.messages, change agent config, etc.
        """
        pass
    
    async def before_llm_request(self, agent: "AcpAgent", session: "Session", messages: list[dict]) -> list[dict]:
        """Called immediately before sending to LLM.
        
        Good for: System prompts, context window management, message transformation.
        Returns: The modified list of messages to send.
        
        Example:
            messages.insert(0, {"role": "system", "content": "You are helpful."})
            return messages
        """
        return messages
    
    async def after_turn(self, agent: "AcpAgent", session: "Session", usage: dict | None) -> None:
        """Called after LLM responds and tools execute (one full turn).
        
        Good for: Persistence, logging, analytics, compaction.
        The agent and session are fully accessible - read messages, save state, etc.
        """
        pass
    
    async def on_shutdown(self, agent: "AcpAgent") -> None:
        """Called when the agent shuts down.
        
        Good for: Flushing buffers, cleanup, final saves.
        """
        pass
```

```python
# crow_acp/agent.py
from crow_acp.hooks import AgentHook

class AcpAgent(Agent):
    def __init__(self, hooks: list[AgentHook] = None, config: Config = None):
        self.hooks = hooks or []
        self._config = config or get_default_config()
        self._sessions = {}
        self._mcp_clients = {}
        # ... all the state ...
    
    async def new_session(self, cwd, mcp_servers, **kwargs):
        # ... create session ...
        
        # Self-injection: pass the whole agent
        for hook in self.hooks:
            await hook.on_session_start(self, session)
        
        return NewSessionResponse(session_id=session.session_id)
    
    async def prompt(self, prompt, session_id, **kwargs):
        session = self._sessions[session_id]
        user_text = self._extract_text(prompt)
        
        # Self-injection: pass the whole agent
        for hook in self.hooks:
            await hook.before_run(self, user_text)
        
        session.add_message("user", user_text)
        
        async for chunk in self._react_loop(session_id):
            yield chunk
    
    async def _react_loop(self, session_id):
        session = self._sessions[session_id]
        
        for turn in range(max_turns):
            # Self-injection before LLM call
            messages = session.messages.copy()
            for hook in self.hooks:
                messages = await hook.before_llm_request(self, session, messages)
            
            response = self._llm.chat.completions.create(
                model=self._config.llm.default_model,
                messages=messages,
                tools=self._tools[session_id],
                stream=True,
            )
            
            # ... process response, execute tools ...
            
            # Self-injection after turn
            for hook in self.hooks:
                await hook.after_turn(self, session, usage)
            
            if not tool_calls:
                break
```

## Example Plugins Using Self-Injection

### Persistence Hook

```python
class PersistenceHook(AgentHook):
    def __init__(self, db_path: str = "~/.crow/crow.db"):
        self.db_path = db_path
        self._queue = []
    
    async def after_turn(self, agent, session, usage):
        # Access agent state directly
        events = self._extract_events(session)
        self._queue.extend(events)
        
        if len(self._queue) >= 50:
            await self._flush()
    
    async def on_shutdown(self, agent):
        await self._flush()
    
    async def _flush(self):
        # Save to SQLite
        ...
```

### System Prompt Hook

```python
class SystemPromptHook(AgentHook):
    def __init__(self, prompt: str):
        self.prompt = prompt
    
    async def before_llm_request(self, agent, session, messages):
        # Mutate messages directly
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": self.prompt})
        return messages
```

### Compaction Hook

```python
class CompactionHook(AgentHook):
    def __init__(self, token_limit: int = 16000):
        self.token_limit = token_limit
    
    async def after_turn(self, agent, session, usage):
        if usage and usage.get("total_tokens", 0) > self.token_limit:
            # Access agent's LLM directly to summarize
            summary = await self._summarize(agent._llm, session.messages)
            
            # Mutate session state directly
            session.messages = [
                session.messages[0],  # Keep system prompt
                {"role": "system", "content": f"Summary of conversation: {summary}"},
                *session.messages[-2:]  # Keep last 2 exchanges
            ]
    
    async def _summarize(self, llm, messages):
        # Use the agent's LLM to summarize
        ...
```

### RAG/Skills Hook

```python
class RAGHook(AgentHook):
    def __init__(self, vector_db_path: str):
        self.db = load_vector_db(vector_db_path)
    
    async def before_run(self, agent, user_input):
        # Search for relevant context
        results = self.db.search(user_input, top_k=5)
        
        if results:
            context = "\n".join(results)
            # Inject context into agent's session
            session = agent._sessions.get(agent._session_id)
            if session:
                session.add_message("system", f"Relevant context:\n{context}")
```

## The Circular Dependency Non-Problem

Let's be explicit about why there's no circular dependency:

```
crow-acp/
├── hooks.py      # Defines AgentHook, uses TYPE_CHECKING for AcpAgent
├── agent.py      # Imports AgentHook (one-way dependency)
└── plugins/
    ├── persistence.py  # Imports AgentHook from crow_acp.hooks
    └── rag.py          # Imports AgentHook from crow_acp.hooks
```

The dependency graph:

```
        hooks.py
       ↑        ↑
       │        │
   agent.py   plugins/*
```

**Nothing depends on agent.py.** Agent.py depends on hooks.py. Plugins depend on hooks.py.

The `agent: "AcpAgent"` type hint in hooks.py is a STRING. It's only evaluated by the type checker, never at runtime.

## Why Julia Developers Love This

Julia has multiple dispatch - you can define methods that operate on any type, without the type needing to inherit from anything.

```julia
# Julia style - just define a function that takes the type
function process(agent::Agent)
    # Do whatever you want with agent
end
```

Self-injection in Python gives you the same freedom. You don't need the agent to inherit from a base class. You just receive the agent as a parameter and operate on it.

**It's functional composition, not object-oriented inheritance.**

## Conclusion

Self-injection is the "God Mode" pattern because:

1. **No SDK layer.** Extensions get the real object, not a sanitized wrapper.
2. **No circular dependencies.** TYPE_CHECKING solves the type hint problem.
3. **Maximum flexibility.** Extensions can do anything the core can do.
4. **Minimal boilerplate.** No context classes, no getters/setters.
5. **Composable.** Multiple hooks can be mixed freely, unlike multiple inheritance.

The trade-off is trust. You're trusting extension authors not to break things. But in Python, you were already trusting them - `_private` is just a convention.

**We are all consenting adults here.**

---

*Next step: Implement AgentHook with self-injection, refactor AcpAgent to call hooks at lifecycle points, extract persistence into a hook.*
