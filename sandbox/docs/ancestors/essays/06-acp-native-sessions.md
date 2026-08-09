# ACP-Native Sessions - Understanding the Dialectic

## The Problem: Two Different Session Types

We have **two** session types in the codebase:

1. **Custom SQLAlchemy Session** (`src/crow/agent/session.py`)
   - Has `session_id` (UUID)
   - Has `prompt_id`, `prompt_args`, `system_prompt`, etc.
   - Persists to SQLite database
   - Manages conversation messages in-memory

2. **ACP Session Types** (`refs/python-sdk/src/acp/schema.py`)
   - `NewSessionRequest` / `NewSessionResponse`
   - `LoadSessionRequest` / `LoadSessionResponse`
   - `PromptRequest` with `session_id`
   - `SessionNotification` for streaming updates

These two systems are **not aligned**. The custom Session creates its own UUID, but ACP also generates a session_id. We end up with **two different session IDs** for the same logical session.

## The Misunderstanding: "We Need Our Own Session Class"

**Assumption (X)**: We need a custom Session class to manage conversation state, persistence, and KV cache anchoring.

**Reality (What ACP Already Provides)**: ACP already defines a complete session lifecycle:
- `new_session()` → creates session, returns `session_id`
- `prompt(session_id, ...)` → processes messages in that session
- `load_session(session_id, ...)` → reloads existing session
- `cancel(session_id)` → cancels ongoing operations

The ACP `session_id` IS the primary key for our persistence layer. We don't need a separate ID.

## The Dialectical Process

### Thesis (X): Custom Session Class
- We need to manage conversation state
- We need persistence across restarts
- We need KV cache anchoring
- Therefore: custom Session class with SQLAlchemy

### Antithesis (~X): ACP Already Has Sessions
- ACP defines `new_session`, `load_session`, `prompt`, `cancel`
- These methods already handle session lifecycle
- The `session_id` from ACP is the natural primary key
- Custom Session class creates unnecessary complexity and ID mismatch

### Synthesis (Y): ACP-Native Session Management

**What Sessions Actually Are**:
1. **ACP Session**: The protocol-level concept. Created by `new_session()`, identified by `session_id`.
2. **In-Memory State**: Messages, tool calls, turn state for that session.
3. **Persistence Layer**: SQLite records keyed by ACP `session_id`.

**The Correct Architecture**:

```
Agent (extends acp.Agent)
├── new_session(cwd, mcp_servers) → NewSessionResponse
│   ├── Generate or use ACP's session_id (it's already provided!)
│   ├── Create in-memory session state (messages, tools, etc.)
│   ├── Persist to DB with session_id as primary key
│   └── Return NewSessionResponse(session_id=ACP_session_id)
│
├── load_session(cwd, session_id, mcp_servers) → LoadSessionResponse
│   ├── Load session state from DB using session_id
│   ├── Reconstruct in-memory state
│   └── Return LoadSessionResponse()
│
├── prompt(session_id, prompt) → PromptResponse
│   ├── Get in-memory session state for session_id
│   ├── Process prompt through ReAct loop
│   ├── Stream updates via session_update()
│   └── Update session state in DB
│
└── cancel(session_id) → None
    ├── Cancel ongoing operations for session_id
    └── Clean up in-memory state
```

**Key Insight**: The ACP `session_id` is the **source of truth**. Our persistence layer should use it as the primary key, not generate our own.

## The SQLAlchemy Debate

**Is SQLAlchemy overwrought?** NO.

SQLAlchemy is **perfect** for persistence. The question is: **what should we persist and how?**

**Current Mistake**:
- We have a `Session` model with `session_id` as primary key
- But we're also generating a separate UUID in the custom Session class
- We end up with two different IDs pointing to the same logical session

**Correct Approach**:
- Use ACP's `session_id` as the primary key
- Store session state (messages, tool calls, etc.) keyed by that ID
- SQLAlchemy is the right tool for this

## Implementation Strategy

### Step 1: Remove Custom Session Class
Don't create a separate Session class that manages its own ID. Instead:

```python
class Agent(acp.Agent):
    def __init__(self):
        self._sessions: dict[str, SessionState] = {}
        # session_id (ACP's ID) → in-memory state
    
    async def new_session(self, cwd, mcp_servers, **kwargs) -> NewSessionResponse:
        # ACP will generate session_id or we can use our own
        session_id = generate_session_id()  # or use ACP's generated ID
        
        # Create in-memory state
        state = SessionState(
            session_id=session_id,
            messages=[system_prompt],
            tools=[],
            # ... other state
        )
        
        # Persist to DB with session_id as primary key
        db_session = DBSession(
            session_id=session_id,  # ACP's ID!
            system_prompt=state.system_prompt,
            tool_definitions=state.tools,
            # ... other fields
        )
        db.add(db_session)
        db.commit()
        
        # Store in memory
        self._sessions[session_id] = state
        
        return NewSessionResponse(session_id=session_id)
```

### Step 2: Use ACP session_id as DB primary key
```python
class DBSession(Base):
    __tablename__ = "sessions"
    
    session_id = Column(Text, primary_key=True)  # ACP's session_id!
    system_prompt = Column(Text)
    tool_definitions = Column(JSON)
    # ... other fields
```

### Step 3: Session state is in-memory, DB is for persistence
- In-memory: Fast access to messages, tool calls, turn state
- DB: Persist across restarts, enable `load_session()`
- They're the same data, different storage layers

## Testing the Understanding

### Test 1: ACP Protocol Compliance
```python
async def test_new_session_returns_acp_session_id():
    agent = Agent()
    response = await agent.new_session(cwd="/tmp", mcp_servers=[])
    
    # Response must have session_id
    assert response.session_id is not None
    
    # Session should be accessible
    assert response.session_id in agent._sessions
```

### Test 2: Load Session from DB
```python
async def test_load_session_restores_state():
    # Create session
    agent1 = Agent()
    response1 = await agent1.new_session(cwd="/tmp", mcp_servers=[])
    session_id = response1.session_id
    
    # Add some messages
    agent1._sessions[session_id].messages.append({"role": "user", "content": "test"})
    
    # Save to DB
    save_session_to_db(session_id)
    
    # Create new agent instance
    agent2 = Agent()
    
    # Load session
    await agent2.load_session(cwd="/tmp", session_id=session_id, mcp_servers=[])
    
    # State should be restored
    assert len(agent2._sessions[session_id].messages) == 2  # system + user
```

### Test 3: No Duplicate IDs
```python
async def test_no_duplicate_session_ids():
    agent = Agent()
    
    # Create multiple sessions
    resp1 = await agent.new_session(cwd="/tmp1", mcp_servers=[])
    resp2 = await agent.new_session(cwd="/tmp2", mcp_servers=[])
    
    # All session_ids should be unique
    assert resp1.session_id != resp2.session_id
    
    # All should be accessible
    assert resp1.session_id in agent._sessions
    assert resp2.session_id in agent._sessions
```

## The Dialectic in Practice

1. **Research**: Read ACP spec, understand session lifecycle
2. **Assumption**: We need custom Session class (X)
3. **Contradiction**: ACP already has sessions, we have ID mismatch (~X)
4. **Synthesis**: Use ACP's session_id as primary key (Y)
5. **Test**: Write tests that encode understanding
6. **Implement**: Make tests pass
7. **Refactor**: Clean up while keeping understanding valid

## Conclusion

**The key insight**: ACP's `session_id` is not just an identifier - it's the **semantic anchor** for the entire session lifecycle. Our persistence layer should use it as the primary key, not generate a separate ID.

**SQLAlchemy is not the problem**. The problem is that we're using it to create a parallel session system that conflicts with ACP's native session management.

**The correct approach**: ACP-native sessions with SQLAlchemy for persistence, where ACP's `session_id` is the source of truth for both.
