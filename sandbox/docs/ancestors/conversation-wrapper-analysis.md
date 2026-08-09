# Conversation Wrapper Analysis: Do We Need One?

**QUESTION**: Do we need a Conversation wrapper like openhands-sdk?

**CARGO CULT ANSWER** (what I did before): "Yes, they have one so we should too!"

**REAL ANSWER**: Let me actually understand what they're solving first.

---

## What I Did Wrong

I looked at their API:
```python
conversation = Conversation(agent=agent, workspace=workspace)
conversation.send_message("text")
conversation.run()
```

Our API:
```python
session = Session.create(...)
await agent.prompt(prompt=[...], session_id=session.session_id)
```

And I thought: "We're missing a Conversation wrapper! Let's add one!"

**Without understanding WHY they have one or WHAT it does.**

Pure cargo cult bullshit.

---

## What I Should Have Done

READ. THE. CODE.

Let me actually understand what openhands-sdk's Conversation DOES.

---

## What Conversation Actually Is (After Reading)

### openhands-sdk Architecture:

```
Conversation (Factory + Wrapper)
├── __new__() → creates LocalConversation OR RemoteConversation
├── send_message() → adds user message to state
├── run() → while True: agent.step()
├── pause() → pause execution
├── resume() → resume execution
└── Stores ConversationState internally

ConversationState (Rich State Machine)
├── execution_status (IDLE/RUNNING/PAUSED/FINISHED/ERROR/STUCK)
├── events (event sourcing, not just messages)
├── max_iterations
├── stuck_detection
├── confirmation_policy
├── security_analyzer
├── activated_knowledge_skills
├── blocked_actions (from hooks)
├── blocked_messages (from hooks)
├── stats (LLM metrics)
├── secret_registry
├── agent_state (runtime state)
├── file_store (persistence abstraction)
├── lock (thread safety)
└── Autosave on every change

LocalConversation (Implementation)
├── Loads plugins lazily (from GitHub, local, etc)
├── Merges plugin skills into agent context
├── Merges plugin MCP config into agent
├── Sets up hooks (explicit + plugin)
├── Manages callbacks
├── Handles visualization
└── Thread-safe execution

Agent (Business Logic)
├── Has LLM config
├── Has tools
├── Has MCP config
├── step() method (one iteration)
└── init_state() method
```

### Our Architecture:

```
Session (Persistence Layer)
├── session_id
├── messages (just message list)
├── db_path
├── conv_index
├── add_message()
├── add_assistant_response()
├── create() (static)
├── load() (static)
└── _save_event()

Agent (ACP-Native)
├── Implements ACP protocol
├── new_session() → creates Session + MCP client
├── load_session() → loads Session + MCP client
├── prompt() → adds message, runs react loop, streams response
├── _react_loop() → while not done: llm call, tools, etc
├── cancel() → cancel running request
└── Manages _sessions, _mcp_clients in-memory
```

---

## The Real Difference

### What openhands-sdk's ConversationState Has That We Don't:

1. **Execution Status Machine**
   ```python
   IDLE → RUNNING → FINISHED
              ↓
            PAUSED → RUNNING
              ↓
            STUCK
              ↓
            ERROR
   ```
   We don't have this. We just have "running" or "not running".

2. **Event Sourcing**
   ```python
   events: list[Event]  # Action, Observation, Message, Error, etc
   ```
   We just have messages. They track everything as events.

3. **Plugin System**
   ```python
   # Load plugins from GitHub, local, etc
   plugins = [
       PluginSource(source="github:owner/repo", ref="v1.0"),
   ]
   # Always loads latest if no ref
   # Merges skills, MCP config, hooks
   ```
   We don't have this at all.

4. **Hook System**
   ```python
   hooks = HookConfig(
       session_start=[...],
       pre_tool_use=[...],
       post_tool_use=[...],
       stop=[...],
   )
   # Can block actions/messages
   # Can modify state
   ```
   We don't have this (but we PLANNED it).

5. **Security Analyzer**
   ```python
   security_analyzer = LLMSecurityAnalyzer()
   # Analyzes actions for risk
   # Can reject dangerous actions
   ```
   We don't have this.

6. **Stuck Detection**
   ```python
   stuck_detector = StuckDetector()
   # Detects loops: same action/observation repeating
   # Detects monologues: assistant talking to itself
   # Detects alternating patterns
   ```
   We don't have this.

7. **Thread Safety**
   ```python
   lock = FIFOLock()
   # Prevents concurrent modifications
   # Ensures safe pause/resume
   ```
   We don't have this.

8. **Remote Conversation Support**
   ```python
   # Factory creates LocalConversation or RemoteConversation
   if isinstance(workspace, RemoteWorkspace):
       return RemoteConversation(...)
   return LocalConversation(...)
   ```
   We don't have this.

9. **Secret Management**
   ```python
   secret_registry = SecretRegistry()
   # Stores secrets securely
   # Can encrypt/decrypt
   ```
   We don't have this.

10. **Metrics Tracking**
    ```python
    stats = ConversationStats()
    # Tracks LLM costs, tokens, latency
    # Per-LLM breakdown
    ```
    We don't have this.

11. **Callback System**
    ```python
    callbacks = [
        lambda event: logger.info(event),
        lambda event: save_to_db(event),
    ]
    # Composed callback chain
    # Every event goes through all callbacks
    ```
    We have ACP streaming, but not callbacks.

12. **Visualization Support**
    ```python
    visualizer = DefaultConversationVisualizer()
    # Renders conversation in real-time
    # CLI UI, web UI, etc
    ```
    We don't have this.

---

## What We Have That They Don't

1. **ACP-Native Architecture**
   - Our agent IS the ACP agent
   - Protocol compliance built-in
   - Client-server model by default

2. **Simpler Mental Model**
   - Session = persisted conversation
   - Agent = protocol implementation
   - No wrapper layers

3. **Database Persistence**
   - Our Session uses SQLAlchemy
   - Theirs uses FileStore (JSON files)
   - Both work, different tradeoffs

---

## The Key Question

**Is their ConversationState solving problems we have?**

YES:
- We DO want hooks (documented in essays/02-hooks-realization-and-agent-core.md)
- We DO want compaction (tests exist, not implemented)
- We DO want skills (documented)
- We DO want metrics tracking (useful)
- We MIGHT want stuck detection (useful)
- We MIGHT want thread safety (if multi-user)

NO:
- We DON'T need execution status machine (ACP has cancel)
- We DON'T need remote conversation (ACP is already client-server)
- We DON'T need plugin loading from GitHub (could use MCP)
- We DON'T need file-based persistence (DB is fine)

---

## The Real Insight

openhands-sdk built a **state machine + plugin system + hook system** because they DON'T have a protocol.

ACP IS the protocol. ACP handles:
- Session management (new_session, load_session)
- Cancellation (cancel)
- Client-server model (by design)

But ACP does NOT handle:
- Hooks
- Skills
- Compaction
- Metrics
- Stuck detection
- Thread safety

So we need to decide: **Where do these features live?**

### Option 1: In the Agent (Our Current Approach)
```python
class Agent(acp.Agent):
    async def prompt(self, prompt, session_id):
        # 1. Run pre-request hooks (skills)
        # 2. Run react loop
        #    - Run mid-react hooks (compaction)
        # 3. Run post-react hooks (Ralph loops)
        # 4. Track metrics
        # 5. Detect stuck
```

**Pros:**
- Simple, no extra layers
- ACP-native
- Everything in one place

**Cons:**
- Agent becomes monolithic
- Hard to extend
- Features coupled together

### Option 2: In a Conversation Wrapper (Like openhands-sdk)
```python
class Conversation:
    def __init__(self, agent, workspace, hooks=None, plugins=None):
        self.agent = agent
        self.state = ConversationState(...)
        self.hooks = hooks
        self.plugins = plugins
    
    async def send_message(self, message):
        # 1. Load plugins if needed
        # 2. Run session_start hooks
        # 3. Add message to state
        # 4. Inject skills if triggered
    
    async def run(self):
        # 1. Run loop with hooks
        # 2. Track metrics
        # 3. Detect stuck
        # 4. Handle pause/resume
```

**Pros:**
- Agent stays simple
- Features are modular
- Extensible via hooks/plugins
- Can have remote conversations

**Cons:**
- Extra abstraction layer
- Not ACP-native (need to adapt)
- More complex

### Option 3: Hybrid
```python
# Agent handles ACP protocol
class Agent(acp.Agent):
    async def prompt(self, prompt, session_id):
        # Just protocol implementation
        pass

# Conversation handles richness
class Conversation:
    def __init__(self, agent):
        self.agent = agent
    
    async def send_message(self, message):
        # Hooks, plugins, etc
        return await self.agent.prompt(...)
```

**Pros:**
- Best of both worlds
- ACP-native core
- Rich wrapper when needed

**Cons:**
- Two ways to do things
- Confusion about which to use

---

## Which Approach is Better?

**Depends on what you're optimizing for:**

### Optimize for Simplicity → Our Current Approach
- Everything in agent
- No extra layers
- ACP-native
- But: monolithic, hard to extend

### Optimize for Extensibility → openhands-sdk Approach
- Modular features
- Hook/plugin system
- But: more abstraction, not ACP-native

### Optimize for Both → Hybrid
- Simple core (ACP)
- Rich wrapper when needed
- But: two APIs to learn

---

## My Recommendation

**We should NOT blindly copy openhands-sdk.**

But we SHOULD learn from what they built:

1. **Hooks are essential** - We need them anyway (documented in essays)
2. **Plugin system is powerful** - But could use MCP instead of custom format
3. **Metrics tracking is useful** - Should add to our Session
4. **Stuck detection is useful** - Should add
5. **Thread safety matters** - If multi-user, we need it

**Implementation path:**

Phase 1: Add hooks to Agent (not wrapper)
```python
class Agent(acp.Agent):
    def __init__(self, config=None):
        self.hooks = HookRegistry()
        self._load_hooks()
    
    async def prompt(self, prompt, session_id):
        # Run hooks at appropriate points
        await self.hooks.run_pre_request(...)
        async for chunk in self._react_loop(...):
            await self.hooks.run_mid_react(...)
        await self.hooks.run_post_react(...)
```

Phase 2: Add plugin support via MCP
```python
# Use MCP for plugin tools, not custom plugin format
mcp_servers = [
    McpServerStdio(name="skills", command="uv", args=["skills-server"]),
]
```

Phase 3: Add metrics to Session
```python
class Session:
    def __init__(self, session_id):
        self.stats = SessionStats()
        self.stats.track_llm_call(...)
```

Phase 4: Consider Conversation wrapper IF NEEDED
- Only if we want pause/resume independent of ACP
- Only if we want local+remote conversations
- Only if the simple approach isn't enough

---

## Conclusion

openhands-sdk's Conversation is NOT just a wrapper. It's a **state machine + plugin system + hook system** that solves real problems.

Our Session is just a **persistence layer**.

The question isn't "Do we need a Conversation wrapper?"

The question is: **"Do we need hooks/plugins/metrics/stuck-detection? And if so, where do they live?"**

**Answer:**
- YES we need hooks (already documented)
- YES we need compaction (tests exist)
- MAYBE plugins (could use MCP)
- YES metrics (useful)
- MAYBE stuck detection (useful)

**Where they should live:**
- Start in Agent (keep it simple)
- Extract to wrapper if it gets too complex
- Don't cargo cult - solve real problems

**The most important thing:**
Don't just copy openhands-sdk's architecture because "they're successful."
Understand WHAT problems they're solving and WHY.
Then decide if we have the same problems and how WE want to solve them.

---

**NEXT STEPS:**

1. Implement hooks framework (documented in essays/02...)
2. Add metrics tracking to Session
3. Add stuck detection if useful
4. Evaluate plugin approach (MCP vs custom)
5. Only add Conversation wrapper if we actually need it

**DO NOT:**
- Add Conversation wrapper "just because"
- Copy their API without understanding
- Build abstractions before we have concrete problems

**DO:**
- Understand the problems they're solving
- Evaluate if we have the same problems
- Design OUR solution to OUR problems
