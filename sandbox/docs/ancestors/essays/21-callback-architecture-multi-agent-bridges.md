# Callback Architecture and Multi-Agent Bridges

**Date**: Current Session  
**Status**: ARCHITECTURAL DECISION - The Final Piece

---

## Introduction: The Contract Emerges

After building a frameworkless framework around ACP + MCP protocols, a natural question arises: how do you extend it without creating abstractions?

The answer isn't a plugin system. It isn't a registry. It isn't inheritance.

**It's just callbacks with session access.**

This essay documents the callback architecture that emerged from the realization that skills, compaction, persistence, and multi-agent handoffs all happen at the same points in the agent lifecycle. Instead of building separate systems for each, we define four hook points and let callbacks compete for them.

---

## Part 1: The Four Hook Points

Every agent session has a predictable lifecycle:

```
begin_session → pre_request → [react_loop] → post_response → end_turn
                     ↑              ↑              ↑            ↑
                     │              │              │            │
                 skills inject   LLM calls    compact check   bridge?
```

This gives us four natural extension points:

### 1. `begin_session`

**When**: Once, when a new session is created  
**Purpose**: Initialize state, load resources, set up the environment  
**Examples**:
- Load skills from `~/.crow/skills/`
- Initialize prompt templates
- Set up workspace-specific context

### 2. `pre_request`

**When**: After user message, before sending to LLM  
**Purpose**: Inspect and modify the request context  
**Examples**:
- Check for skill triggers, inject matching skill content
- Add progressive disclosure of documentation
- Inject conversation history summaries

### 3. `post_response`

**When**: After LLM responds, before checking for more tool calls  
**Purpose**: Process the response, check thresholds  
**Examples**:
- Check token count, trigger compaction if needed
- Log telemetry
- Update session metadata

### 4. `end_turn`

**When**: After agent finishes, before returning control to user  
**Purpose**: Finalize state, hand off to next agent  
**Examples**:
- Multi-agent bridges
- Final persistence flush
- Spawn background tasks

---

## Part 2: The Callback Contract

Callbacks are just async functions that receive session access:

```python
from typing import Callable, Awaitable
from pydantic import BaseModel, Field

class CrowCallbacks(BaseModel):
    """Four hook points for session lifecycle extensions."""
    
    begin_session: list[Callable] = Field(
        default_factory=list,
        description="Callbacks run once at session initialization"
    )
    pre_request: list[Callable] = Field(
        default_factory=list,
        description="Callbacks run after user message, before LLM"
    )
    post_response: list[Callable] = Field(
        default_factory=list,
        description="Callbacks run after LLM responds"
    )
    end_turn: list[Callable] = Field(
        default_factory=list,
        description="Callbacks run after agent finishes, before return"
    )
```

### The Session Contract

Callbacks receive a session object with CRUD methods:

```python
class SessionAccess:
    """The contract between callbacks and session state."""
    
    # Read
    def get_messages(self) -> list[dict]: ...
    def get_context(self, key: str) -> Any: ...
    def get_summary(self) -> str: ...
    
    # Write
    def add_message(self, role: str, content: str): ...
    def set_context(self, key: str, value: Any): ...
    
    # Control
    async def prompt(self, text: str) -> str: ...
    def trigger_compaction(self): ...
```

This is the SDK. Everything else is implementation.

---

## Part 3: Building Callbacks

### Example: Skills as Pre-Request Callback

```python
# crow_skills/__init__.py

from pathlib import Path
import yaml

class Skill:
    def __init__(self, name: str, triggers: list[str], content: str, path: Path):
        self.name = name
        self.triggers = triggers
        self.content = content
        self.path = path
    
    def match(self, message: str) -> str | None:
        msg_lower = message.lower()
        for trigger in self.triggers:
            if trigger.lower() in msg_lower:
                return trigger
        return None

def load_skills(dirs: list[Path]) -> list[Skill]:
    """Discover skills from directories."""
    skills = []
    for d in dirs:
        if not d.exists():
            continue
        for skill_md in d.rglob("SKILL.md"):
            skills.append(Skill.from_file(skill_md))
    return skills

def default_skills(skills_dir: Path = None) -> Callable:
    """Factory that creates a skills callback."""
    if skills_dir is None:
        skills_dir = Path.home() / ".crow" / "skills"
    
    skills = load_skills([skills_dir])
    
    async def skills_callback(session: SessionAccess, **kwargs):
        """Pre-request callback: inject triggered skills."""
        user_message = session.get_messages()[-1].get("content", "")
        
        triggered = []
        for skill in skills:
            trigger = skill.match(user_message)
            if trigger:
                triggered.append({
                    "trigger": trigger,
                    "content": skill.content,
                    "location": str(skill.path)
                })
        
        if triggered:
            extra = render_skill_template(triggered)
            session.add_message("system", extra)
    
    return skills_callback
```

### Example: Compaction as Post-Response Callback

```python
# crow_compact/__init__.py

def default_compact(threshold: int = 100000) -> Callable:
    """Factory that creates a compaction callback."""
    
    async def compact_callback(session: SessionAccess, **kwargs):
        """Post-response callback: check token threshold, compact if needed."""
        messages = session.get_messages()
        token_count = estimate_tokens(messages)
        
        if token_count > threshold:
            summary = await summarize_messages(messages[:-10])
            session.set_context("compaction_summary", summary)
            session.compact_messages(keep_last=10)
    
    return compact_callback
```

---

## Part 4: Multi-Agent Bridges

The `end_turn` hook enables multi-agent patterns. A "bridge" is a callback that hands off to another agent:

### The Bridge Pattern

```python
def agent_bridge(next_agent: "AcpAgent") -> Callable:
    """Factory that creates a bridge callback to another agent.
    
    The closure captures `next_agent` in its scope.
    """
    async def bridge_callback(session: SessionAccess, **kwargs):
        """End-turn callback: hand off to next agent."""
        # Extract relevant context from current session
        context = session.get_summary()
        
        # Call the next agent
        await next_agent.prompt(
            prompt=[{"type": "text", "text": context}],
            session_id=next_agent._session_id
        )
    
    return bridge_callback
```

### Building Agent Chains

To chain agents a → b → c (entry at a, exit at c):

```python
from crow_acp import AcpAgent, MultiAgent
from crow_skills import default_skills
from crow_compact import default_compact

def get_base_callbacks():
    return CrowCallbacks(
        begin_session=[],
        pre_request=[default_skills()],
        post_response=[default_compact()],
        end_turn=[],
    )

def add_agent_callback(callbacks: CrowCallbacks, next_agent: AcpAgent) -> CrowCallbacks:
    """Add a bridge to next_agent in the end_turn hooks."""
    new_callbacks = callbacks.model_copy()
    new_callbacks.end_turn.append(agent_bridge(next_agent))
    return new_callbacks

def build_chain():
    """Build a → b → c chain."""
    agent_a = AcpAgent()
    agent_b = AcpAgent()
    agent_c = AcpAgent()
    
    # Base callbacks (no bridges)
    base = get_base_callbacks()
    
    # Build chain backwards: c gets no bridge, b → c, a → b
    callbacks_c = base  # c is terminal, no bridge
    callbacks_b = add_agent_callback(callbacks_c, agent_c)  # b → c
    callbacks_a = add_agent_callback(callbacks_b, agent_b)  # a → b
    
    # Apply callbacks
    agent_a.set_callbacks(callbacks_a)
    agent_b.set_callbacks(callbacks_b)
    agent_c.set_callbacks(callbacks_c)
    
    # Entry point
    return MultiAgent(entry_agent=agent_a)
```

### The Chain Direction Bug (Caught in Review)

**Wrong** (this creates c → b → a):

```python
callbacks_c = add_agent_callback(callbacks, agent_b)  # c → b
callbacks_b = add_agent_callback(callbacks, agent_a)  # b → a
agent_a.set_callbacks(callbacks)                       # a → done
```

**Correct** (this creates a → b → c):

```python
callbacks_c = base                                       # c → done
callbacks_b = add_agent_callback(callbacks_c, agent_c)  # b → c
callbacks_a = add_agent_callback(callbacks_b, agent_b)  # a → b
```

The key insight: `add_agent_callback(callbacks, agent)` adds a bridge **TO** that agent. So whoever gets those callbacks will call `agent` on their end_turn.

---

## Part 5: The Final Package Structure

```
crow/
├── crow_acp/           # Core: ACP agent + callback hooks
│   ├── agent.py        # AcpAgent with set_callbacks()
│   ├── session.py      # SessionAccess contract
│   └── callbacks.py    # CrowCallbacks definition
│
├── crow_skills/        # Pre-request: skill injection
│   └── __init__.py     # default_skills() factory
│
├── crow_compact/       # Post-response: token management
│   └── __init__.py     # default_compact() factory
│
├── crow_prompt/        # Begin-session: prompt management
│   └── __init__.py     # default_prompt() factory
│
└── crow/               # Assembly: patterns and presets
    ├── patterns/       # Multi-agent patterns
    └── __init__.py     # Convenient exports
```

### Usage

```python
from crow_acp import AcpAgent, MultiAgent
from crow_skills import default_skills
from crow_compact import default_compact
from crow_prompt import default_prompt

# Simple single agent
agent = AcpAgent()
agent.set_callbacks(CrowCallbacks(
    begin_session=[default_prompt()],
    pre_request=[default_skills()],
    post_response=[default_compact()],
    end_turn=[],
))

# Or use a preset pattern
from crow.patterns import coder_agent
agent = coder_agent()
```

---

## Part 6: Why This Works

### 1. No Hidden Magic

Everything is a function. The callback list is just a list. Hooks are called at obvious points. No decorators, no registries, no metaclasses.

### 2. Scope Works

Closures capture what they need. `agent_bridge(next_agent)` creates a callback that knows about `next_agent` without any global state.

### 3. Composable

`crow-skills` doesn't know about `crow-compact`. They both just plug into callback slots. You can mix and match.

### 4. Testable

Each callback is a pure function (given session). Test it in isolation.

### 5. The Framework Stays Small

The core `crow_acp` is still just:
- ~200 lines of streaming react loop
- ACP protocol implementation
- MCP client connection
- Four lists of callbacks

Everything else lives in separate packages.

---

## Conclusion: The Frameworkless Framework Complete

We started with the observation that you can build an agent in ~200 lines by just connecting ACP + MCP protocols with streaming logic.

Now we have the extension story:

- **Four hook points** cover all lifecycle events
- **Callbacks with session access** provide a simple contract
- **Closures capture state** for multi-agent bridges
- **Separate packages** for skills, compaction, prompts

The framework doesn't grow. It just provides hooks. Everything interesting happens in callbacks.

**There is no there there. And that's the point.**

---

## References

- `12-hook-based-architecture-and-the-frameworkless-framework.md` - The original hook realization
- `17-composition-over-inheritance-extension-design.md` - Why composition wins
- `streaming_async_react.py` - The ~200 line core
- OpenHands SDK skill system - The trigger pattern reference
