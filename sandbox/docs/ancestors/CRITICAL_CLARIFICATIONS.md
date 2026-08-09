# Critical Clarifications & Revised Priorities

**Date**: February 15, 2026  
**Status**: Course Correction Based on User Feedback

---

## 🚨 What I Got Wrong

I misunderstood three critical things in the original pulse check:

### 1. **Terminal Strategy** ❌→✅
- ❌ **What I said**: "We use MCP terminal instead of client terminal"
- ✅ **Reality**: **PRIORITIZE client-provided terminal over built-in**
  - If ACP client exposes terminal capabilities → USE IT
  - Only fall back to built-in MCP terminal if client doesn't provide

### 2. **Session Management Methods** ❌→✅
- ❌ **What I said**: "Nice-to-have, not blocking"
- ✅ **Reality**: **WANTED and IMPORTANT**
  - `list_sessions()` - Query available sessions
  - `resume_session()` - Resume paused sessions
  - `set_session_config_option()` - Runtime config
  - `set_session_model()` - **ESPECIALLY IMPORTANT** for client control

### 3. **Compaction Priority** ❌→✅
- ❌ **What I said**: "Medium priority optimization"
- ✅ **Reality**: **CRITICAL** - Tests exist (TDD), implementation needed NOW

---

## Revised Priority Stack

### TIER 1: CRITICAL (Block Everything Else)

1. **Compaction** ❌ NOT STARTED
   - Tests exist (8 failing TDD tests)
   - REQUIRED for long conversations
   - Must preserve KV cache (use same session)
   - Mid-react hook point
   - **Estimate**: 2-3 days

2. **Hooks Framework** ❌ NOT PLANNED
   - Foundation for: compaction, skills, Ralph loops
   - Defines: Hook Protocol, HookContext, hook points
   - Plugin discovery via entry points
   - **Estimate**: 3-4 days (design + implementation)

### TIER 2: HIGH PRIORITY (Should Do Soon)

3. **Session Management ACP Methods** ❌ NOT STARTED
   - `list_sessions()` - Query DB for all sessions
   - `resume_session()` - Resume paused session
   - `set_session_model()` - **IMPORTANT** for client model switching
   - `set_session_config_option()` - Runtime config
   - **Estimate**: 1-2 days

4. **Client Terminal Integration** ❌ NOT STARTED
   - Check `ClientCapabilities.terminal_create`
   - If client provides terminal → USE IT
   - Otherwise fall back to MCP terminal (TODO)
   - **Estimate**: 1 day

5. **Cleanup Old Files** 🟡 PARTIAL
   - Remove old `acp_agent.py` and `agent/agent.py`
   - Fix 6 failing test imports
   - **Estimate**: 0.5 days

### TIER 3: MEDIUM PRIORITY (Nice-to-Have)

6. **Terminal MCP Tool** ❌ NOT STARTED
   - Only needed if client doesn't provide terminal
   - Study kimi-cli implementation
   - Add to crow-mcp-server
   - **Estimate**: 2-3 days

7. **Additional ACP Methods** ❌ NOT STARTED
   - `fork_session()` - Copy DB session
   - Other optional methods
   - **Estimate**: 1 day

8. **Documentation Updates** 🟡 PARTIAL
   - README with ACP-native architecture
   - ACP compliance guide
   - Hook development guide
   - **Estimate**: 1-2 days

---

## Hook Framework Deep Dive

Based on `docs/essays/02-hooks-realization-and-agent-core.md`:

### What Are Hooks?

**Hooks are plugin points in the react loop** where user code can:
1. Observe state (conversation, session, tokens, provider)
2. Modify state (inject context, append messages, trigger compaction)
3. Control flow (continue, pause, restart, delegate)

**Without modifying the agent's core code.**

### Hook Points in the React Loop

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

### Hook Interface (Proposed)

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

### Hook Types

1. **Skills** = Pre-Request Hooks
   - Context injection based on keywords
   - "@-mentions" of files, schemas, etc.
   - Example: User mentions "database" → Inject DB schema

2. **Compaction** = Mid-React Hooks  
   - Triggered when tokens > threshold
   - Summarize middle messages
   - **CRITICAL**: Must use same session for KV cache preservation

3. **Ralph Loops** = Post-React Hooks
   - Self-verification: "Are you sure about that?"
   - Forces agent to self-critique
   - Bypasses "need human feedback" signal

### Plugin Architecture

Hooks are **separate Python packages**:

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

---

## What Needs to Be Done

### Phase 1: Hooks Framework (CRITICAL - FIRST)
**Estimate**: 3-4 days

1. **Design Hook Protocol**
   ```python
   # src/crow/hooks.py
   from typing import Protocol, Optional
   from dataclasses import dataclass

   @dataclass
   class HookContext:
       session: Session
       provider: Provider
       request: Optional[str] = None
       usage: Optional[Usage] = None  
       result: Optional[str] = None

   class PreRequestHook(Protocol):
       async def __call__(self, ctx: HookContext) -> Optional[HookContext]:
           """Pre-request hook. Can modify context."""
           ...

   class MidReactHook(Protocol):
       async def __call__(self, ctx: HookContext) -> Optional[HookContext]:
           """Mid-react hook. Can trigger compaction."""
           ...

   class PostReactHook(Protocol):
       async def __call__(self, ctx: HookContext) -> Optional[str]:
           """Post-react hook. Can trigger re-prompt."""
           ...
   ```

2. **Implement Hook Points in Agent**
   ```python
   # In acp_native.py
   class Agent:
       def __init__(self):
           self.pre_request_hooks = []
           self.mid_react_hooks = []
           self.post_react_hooks = []
           self._discover_hooks()

       def _discover_hooks(self):
           """Discover hooks via entry points."""
           import importlib.metadata
           for ep in importlib.metadata.entry_points(group="crow.hooks"):
               hook = ep.load()
               # Determine hook type and add to appropriate list
               ...

       async def prompt(self, prompt, session_id, **kwargs):
           # Load session
           session = Session.load(session_id)

           # PRE-REQUEST HOOKS
           ctx = HookContext(session=session, provider=self._llm, request=prompt)
           for hook in self.pre_request_hooks:
               ctx = await hook(ctx) or ctx

           # REACT LOOP
           async for chunk in self._react_loop(ctx.session, ...):
               # ... yield chunks ...

               # MID-REACT HOOK POINT (after each LLM response)
               for hook in self.mid_react_hooks:
                   ctx = await hook(ctx) or ctx
                   if ctx.session != session:
                       # Hook modified session (compaction)
                       session = ctx.session

           # POST-REACT HOOKS  
           ctx.result = final_result
           for hook in self.post_react_hooks:
               new_result = await hook(ctx)
               if new_result:
                   # Re-prompt with verification
                   ...
   ```

3. **Entry Point Discovery**
   - Support `crow.hooks` entry point group
   - Load hooks at agent init
   - Handle hook errors gracefully

4. **Tests for Hook Framework**
   - Test hook discovery
   - Test pre-request modification
   - Test mid-react compaction
   - Test post-react re-prompt

### Phase 2: Compaction as Mid-React Hook (CRITICAL)
**Estimate**: 2-3 days

1. **Implement Compaction Hook**
   ```python
   # Compaction package: crow-compaction
   # src/crow_compaction/__init__.py

   async def compaction_hook(ctx: HookContext) -> Optional[HookContext]:
       """Compact if over threshold."""
       if ctx.usage.total_tokens > ctx.session.threshold:
           # Keep first K and last K messages
           K = ctx.session.compaction_keep_last
           preserved_head = ctx.session.messages[:K]
           preserved_tail = ctx.session.messages[-K:]
           to_compact = ctx.session.messages[K:-K]

           # Ask LLM to summarize (using SAME session for KV cache!)
           summary = await summarize(ctx.provider, to_compact)

           # Create new session with compacted history
           new_session = Session(
               messages=[*preserved_head, summary, *preserved_tail],
               # ... other session state
           )
           
           # Update context with new session
           return HookContext(
               session=new_session,
               provider=ctx.provider,
               usage=ctx.usage
           )
       return None
   ```

2. **Make Existing Tests Pass**
   - 8 compaction tests exist (TDD)
   - Implement to make them pass

3. **Critical Requirements**:
   - Use SAME session for summarization (KV cache!)
   - Keep first K and last K messages
   - Create summary message for middle
   - Update session in place or create new

### Phase 3: Session Management Methods (HIGH PRIORITY)
**Estimate**: 1-2 days

```python
# In acp_native.py

async def list_sessions(self, **kwargs) -> ListSessionsResponse:
    """List available sessions from DB."""
    sessions = Session.list_all()  # Add this method to Session
    return ListSessionsResponse(sessions=sessions)

async def resume_session(self, session_id: str, **kwargs) -> ResumeSessionResponse:
    """Resume a paused session."""
    # Similar to load_session but with different lifecycle
    session = Session.load(session_id)
    # ... setup MCP client, etc
    return ResumeSessionResponse()

async def set_session_model(self, session_id: str, model: str, **kwargs) -> SetSessionModelResponse:
    """Let client switch models mid-session!"""
    session = Session.load(session_id)
    session.model_identifier = model
    session.save()
    return SetSessionModelResponse()

async def set_session_config_option(self, session_id: str, key: str, value: Any, **kwargs) -> SetSessionConfigOptionResponse:
    """Set runtime config options."""
    session = Session.load(session_id)
    session.config[key] = value
    session.save()
    return SetSessionConfigOptionResponse()
```

### Phase 4: Client Terminal Integration (HIGH PRIORITY)
**Estimate**: 1 day

```python
# In new_session()
async def new_session(self, cwd, mcp_servers, **kwargs):
    # Check if client provides terminal
    client_caps = kwargs.get('client_capabilities', {})
    
    if client_caps.get('terminal_create'):
        # Client provides terminal - use ACP terminal methods
        self._use_client_terminal = True
        logger.info("Using client-provided terminal")
    else:
        # Fall back to our MCP terminal tool (TODO)
        self._use_client_terminal = False
        logger.info("Using built-in terminal MCP tool")

    # ... rest of session setup
```

---

## Revised Roadmap

### Week 1: Critical Foundation
- **Day 1-2**: Design and implement hooks framework
- **Day 3-5**: Implement compaction as mid-react hook

### Week 2: High Priority Features  
- **Day 1-2**: Session management ACP methods
- **Day 3**: Client terminal integration
- **Day 4**: Cleanup old files
- **Day 5**: Testing and documentation

### Week 3: Medium Priority (If Time)
- **Day 1-3**: Terminal MCP tool (if client doesn't provide)
- **Day 4**: Additional ACP methods
- **Day 5**: Documentation updates

---

## Success Criteria

After completing TIER 1 & 2:

1. ✅ **Hooks Framework Working**
   - Can write plugins
   - Discovery via entry points
   - Three hook points (pre/mid/post)

2. ✅ **Compaction Working**
   - Long conversations don't fail
   - KV cache preserved
   - All 8 tests passing

3. ✅ **Session Management Complete**
   - Can list sessions
   - Can resume sessions
   - **Can switch models mid-session**

4. ✅ **Terminal Strategy Clear**
   - Uses client terminal if available
   - Falls back to MCP if not

5. ✅ **Code Clean**
   - Old files removed
   - All tests passing (>95%)
   - Documentation updated

---

## What's Working NOW (65% Complete)

✅ **Core Agent Architecture**
- Single Agent class
- ACP protocol (core methods)
- AsyncExitStack resources
- Session persistence

✅ **MCP Configuration**  
- ACP-centered (user's use case!)
- Multi-server support
- Stdio/HTTP/SSE

✅ **Basic MCP Tools**
- File editor
- Web search
- Web fetch

✅ **Testing Framework**
- 100/120 tests passing
- E2E with real components
- TDD approach

---

## What's NOT Working (35% Remaining)

❌ **Hooks Framework** - 0% (not started)
❌ **Compaction** - 11% (tests exist, no impl)
❌ **Session Management** - 0% (not started)
❌ **Client Terminal** - 0% (not started)
🟡 **Cleanup** - 30% (old files still there)

---

## Bottom Line

**The system is 65% complete. The remaining 35% is CRITICAL:**

1. **Hooks Framework** - Foundation for extensibility
2. **Compaction** - Required for production use
3. **Session Management** - Important for client control
4. **Client Terminal** - Important for integration

**Timeline**: 2-3 weeks to complete critical features.

**Priority**: Hooks → Compaction → Session Management → Terminal → Cleanup

The foundation is solid, but we need these features for real-world usage.
