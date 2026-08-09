# Composition Over Inheritance: The Extension Design for crow-acp

## The Problem

I got stuck. I wanted to build an extension system for crow-acp where people could `uv add crow-something-something` and just have it work. But I kept running into the same mental wall:

**How do extensions depend on core while core also "calls" extensions?**

The traditional answer is inheritance. Core defines an abstract base class, extensions inherit from it:

```python
# WRONG - Inheritance
class SQLitePersistence(BasePersistence):  # Extension inherits from core
    def save(self, events):
        ...
```

This feels gross. It leads to:
- Brittle hierarchies
- Forks that don't interop
- Core needing to know about all possible extension points
- Decision paralysis about "the right way" to structure the API

I stared at the circular dependency diagram and felt stuck:

```
crow-acp ← depends on ← crow-sqlite-persistence
     ↑                           │
     └───────────────────────────┘ ???
```

## The Real Question

I was yak shaving. Obsessing over package structure before I even had the core right.

The real question wasn't "how do I structure PyPI packages?" It was:

**"How do I make the system composable without inheritance?"**

I don't like OOP. I think in functions that pass around state. But when I looked at Flask and VSCode extensions, they use classes. Was I being stubborn? Should I just "bite the bullet"?

## The Insight from Gemini

I asked Gemini to help me see what I was missing. It nailed it:

> You are struggling with **Inheritance vs. Composition**.
> 
> * **Inheritance (what you fear):** Creating `class MySuperAgent(AcpAgent)` just to add a system prompt. This leads to a brittle hierarchy.
> * **Composition (what you want):** `AcpAgent` remains a clean engine, and you "plug in" functionality.

This was exactly it. I didn't want extensions to BE agents. I wanted extensions to ATTACH to agents.

## The Solution: Hooks as the Plugin Interface

**Core defines WHEN to call, not WHAT to call.**

```python
# crow-acp/hooks.py
class AgentHook:
    """Base class for all agent extensions."""
    
    async def on_session_start(self, session) -> None:
        """Called once when a new session is created."""
        pass

    async def before_run(self, session, user_input) -> None:
        """Called when user sends a message, BEFORE the agent starts the loop.
        Good for: RAG, modifying user input, checking permissions."""
        pass

    async def before_llm_request(self, session, messages) -> list[dict]:
        """Called immediately before sending to LLM.
        Good for: Injecting system prompts, context window management.
        Returns: The modified list of messages to send."""
        return messages

    async def after_turn(self, session, usage) -> None:
        """Called after LLM responds and tools are executed (one full turn).
        Good for: Persistence, Logging, Compaction."""
        pass
```

The agent accepts a list of hooks:

```python
# crow-acp/agent.py
class AcpAgent(Agent):
    def __init__(self, hooks: list[AgentHook] = None):
        self.hooks = hooks or []
    
    async def _react_loop(self, session_id):
        for hook in self.hooks:
            messages = await hook.before_llm_request(session, messages)
        
        # ... do llm call ...
        
        for hook in self.hooks:
            await hook.after_turn(session, usage)
```

## Extensions Are Just Hook Classes

Now persistence, skills, compaction - they're all just classes that implement `AgentHook`:

```python
# crow-acp/plugins.py (IN THE SAME PACKAGE FOR NOW)

class PersistenceHook(AgentHook):
    async def after_turn(self, session, usage):
        # Save to SQLite
        session.save()

class CompactionHook(AgentHook):
    def __init__(self, token_limit=16000):
        self.limit = token_limit
    
    async def after_turn(self, session, usage):
        if usage and usage.get("total_tokens", 0) > self.limit:
            # Summarize and prune
            ...

class SystemPromptHook(AgentHook):
    def __init__(self, prompt_text: str):
        self.prompt_text = prompt_text
    
    async def before_llm_request(self, session, messages):
        messages.insert(0, {"role": "system", "content": self.prompt_text})
        return messages
```

## The User Experience (Now)

Everything in one package, configured at startup:

```python
# main.py
from crow_acp import AcpAgent
from crow_acp.plugins import PersistenceHook, SystemPromptHook

hooks = [
    SystemPromptHook("You are Crow, a helpful coding assistant."),
    PersistenceHook(db_path="~/.crow/crow.db"),
]

agent = AcpAgent(hooks=hooks)
await run_agent(agent)
```

## The User Experience (Future, Maybe)

When a hook gets big enough to split out:

```bash
uv add crow-skill-rag
```

```python
# main.py
from crow_acp import AcpAgent
from crow_acp.plugins import PersistenceHook
from crow_skill_rag import RAGHook  # Separate package!

hooks = [
    RAGHook(vector_db="./embeddings"),
    PersistenceHook(),
]

agent = AcpAgent(hooks=hooks)
```

## How This Resolves the Circular Dependency

The separate package `crow-skill-rag`:
- Depends on `crow-acp` (imports `AgentHook`)
- Defines a class that implements `AgentHook`
- User manually adds it to `hooks=[]` list

Core never imports the extension. Extension imports core. **No circular dependency.**

```
crow-acp (defines AgentHook)
    ↑
    └── crow-skill-rag (imports AgentHook, implements it)
```

The user is the glue. They import both and wire them together.

## The Plan

1. **Don't create separate packages yet.** Put all hooks in `crow-acp/plugins.py`
2. **Refactor `AcpAgent` to accept `hooks` list**
3. **Move persistence, compaction, system prompts into hook classes**
4. **Keep session.py as pure in-memory state**
5. **Later:** If a hook gets big (requires heavy deps like numpy/faiss), split it out

## Hook Lifecycle

```
new_session()
    └── hook.on_session_start()

prompt()
    └── hook.before_run(user_input)
    └── session.add_message("user", ...)

_react_loop()
    ┌─────────────────────────────────┐
    │  hook.before_llm_request()      │
    │  llm.chat.completions.create()  │
    │  process stream                 │
    │  execute tools                  │
    │  hook.after_turn()              │
    └─────────────────────────────────┘
```

## Special Cases Mapped to Hooks

| Feature | Hook | Trigger |
|---------|------|---------|
| System prompt | `before_llm_request` | Insert at index 0 if not present |
| Skills | `before_run` | Keyword search, inject context |
| Persistence | `after_turn` | Batch save (or on shutdown) |
| Compaction | `after_turn` | If tokens > limit, summarize |

## Why This Works

1. **No inheritance hierarchy.** Extensions don't extend Agent. They implement a tiny interface.
2. **No circular dependencies.** Extensions import core, not the other way around.
3. **No premature package splitting.** Keep everything together until something genuinely needs to be separate.
4. **The agent remains dumb.** It just knows *when* to call hooks, not *what* they do.
5. **The user is the composer.** They wire together what they need at startup.

## The Fear I Had to Confront

I was worried about "doing OOP but in a roundabout way." Passing state to functions vs storing state on `self` - isn't that the same thing?

Yes. They're isomorphic. `self.method(events)` is just `method(self, events)` with syntactic sugar.

The real question isn't "functional vs OOP." It's "how does state flow through the system?"

With hooks:
- State lives on the Agent (`self._sessions`, `self._mcp_clients`, etc.)
- Hooks receive the agent (or session) as a parameter
- Hooks can read agent state, and in some cases modify it
- The hook itself may have its own internal state (like a batch queue)

This is composition. The hook doesn't BECOME the agent. It SITS BESIDE the agent and gets called at specific moments.

## A Note on Async and Shared State

One concern I had: "What about async state when everything is concurrent?"

But in the ACP model, each client spawns its own agent process:

```
Client A spawns → Agent Process A (own memory, own event loop)
Client B spawns → Agent Process B (own memory, own event loop)
```

Each agent has its own `_sessions` dict, its own event loop, its own everything. No shared state between clients. The async concerns only exist within one agent, and even then - one agent typically handles one session at a time through the ACP protocol.

The callback pattern doesn't add any new async problems. It just exposes the same state that already exists.

## Conclusion

The extension system isn't about package structure. It's about defining a clean composition interface.

- `AgentHook` is the interface
- `AcpAgent.hooks` is the registry
- Hook classes are the extensions
- The user is the composer

Don't split packages until you need to. Don't inherit when you can compose. Don't over-engineer the "plugin system" - it's just a list of objects with methods that get called at specific times.

The frameworkless framework. Just Python, just functions (okay, classes with methods), just composition.

---

*Next step: Implement `AgentHook` base class, refactor `AcpAgent` to accept hooks, extract persistence into `PersistenceHook`.*
