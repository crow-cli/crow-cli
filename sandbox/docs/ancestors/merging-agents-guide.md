# Merging Agents: Step-by-Step Guide

This document provides the breadcrumb trail for merging Agent + CrowACPAgent into a single ACP-native agent.

---

## The Goal

**Before (Anti-Pattern)**:
```
CrowACPAgent (wrapper)
  └── wraps Agent (business logic)
       └── uses Session, MCP client, LLM
```

**After (Correct Pattern)**:
```
Agent(acp.Agent)
  └── has Session, MCP client, LLM as instance variables
  └── react_loop, send_request, process_response as methods
```

---

## Source Files to Merge

### From: `src/crow/acp_agent.py` (CrowACPAgent)

**Keep - These are ACP methods**:
- `on_connect(conn)` - Store connection for updates
- `initialize()` - Protocol handshake
- `authenticate()` - Auth handling
- `new_session()` - Create session with MCP + tools
- `load_session()` - Load existing session
- `set_session_mode()` - Mode changes
- `prompt()` - **Main entry point** - calls react loop
- `cancel()` - Cancellation handling
- `ext_method()` - Extension methods
- `ext_notification()` - Extension notifications
- `cleanup()` - AsyncExitStack cleanup

**Instance Variables**:
- `_conn: Client` - ACP connection
- `_sessions: dict[str, Session]` - Session storage  
- `_agents: dict[str, Agent]` - **DELETE THIS** - no nested agents
- `_exit_stack: AsyncExitStack` - Resource management
- `_llm: OpenAI` - LLM client

### From: `src/crow/agent/agent.py` (Agent)

**Move - These become methods on merged agent**:
- `send_request()` - Send LLM request
- `process_chunk()` - Process streaming chunk
- `process_response()` - Process full response
- `process_tool_call_inputs()` - Format tool calls
- `execute_tool_calls()` - Execute via MCP
- `react_loop()` - **Main loop** - call from prompt()

**Instance Variables** (already in merged agent):
- `session: Session` - Passed to prompt()
- `llm: OpenAI` - Same as _llm
- `mcp_client: Client` - Managed per-session
- `tools: list[dict]` - Tool definitions
- `model: str` - Model identifier

---

## Step-by-Step Merge Process

### Step 1: Create New Agent File

```bash
# Create merged agent
touch src/crow/agent_merged.py
```

Or rename and refactor:
```bash
# Option A: Rename agent.py, refactor acp_agent.py into it
mv src/crow/agent/agent.py src/crow/agent.py
# Then merge CrowACPAgent into it
```

### Step 2: Define Class Structure

```python
# src/crow/agent.py OR src/crow/agent_merged.py

from acp import Agent, PromptResponse
from contextlib import AsyncExitStack

class Agent(Agent):
    """ACP-native agent - all business logic in one class"""
    
    def __init__(self):
        # Resource management
        self._exit_stack = AsyncExitStack()
        
        # LLM configuration
        self._llm = configure_llm()
        
        # Session storage (maps session_id -> session data)
        self._sessions = {}
        self._session_resources = {}  # MCP clients per session
        
        # ACP connection (set via on_connect)
        self._conn = None
```

### Step 3: Move ACP Methods

Copy from `CrowACPAgent`:
- All ACP method implementations
- Keep AsyncExitStack usage
- Keep cleanup() method

### Step 4: Move Business Logic Methods

Copy from old `Agent`:
- `send_request()` - becomes `self._send_request(session)`
- `process_chunk()` - becomes `self._process_chunk(...)`
- `process_response()` - becomes `self._process_response(...)`
- `process_tool_call_inputs()` - becomes `self._process_tool_call_inputs(...)`
- `execute_tool_calls()` - becomes `self._execute_tool_calls(...)`
- `react_loop()` - becomes `self._react_loop(session)`

**Key Change**: Methods now take `session` as parameter instead of being instance variable.

### Step 5: Wire prompt() to react_loop()

```python
async def prompt(self, prompt, session_id, **kwargs):
    """ACP prompt method - calls react loop"""
    
    # Get session
    session_data = self._sessions.get(session_id)
    if not session_data:
        return PromptResponse(stop_reason="error")
    
    session = session_data["session"]
    
    # Add user message
    user_text = extract_text_from_blocks(prompt)
    session.add_message("user", user_text)
    
    # Run react loop from old Agent
    try:
        async for chunk in self._react_loop(session):
            # Stream updates to ACP client
            await self._conn.session_update(
                session_id,
                update_agent_message(text_block(chunk))
            )
        
        return PromptResponse(stop_reason="end_turn")
    
    except Exception as e:
        logger.error(f"Error in prompt: {e}")
        return PromptResponse(stop_reason="error")
```

### Step 6: Update new_session()

```python
async def new_session(self, cwd, mcp_servers, **kwargs):
    """Create new session with MCP client"""
    
    # Setup MCP client (managed by AsyncExitStack)
    mcp_client = setup_mcp_client("src/crow/mcp/search.py")
    mcp_client = await self._exit_stack.enter_async_context(mcp_client)
    
    # Get tools
    tools = await get_tools(mcp_client)
    
    # Create session
    session = Session.create(
        prompt_id="crow-v1",
        prompt_args={"workspace": cwd},
        tool_definitions=tools,
        request_params={"temperature": 0.7},
        model_identifier="glm-5",
    )
    
    # Store session data
    self._sessions[session.session_id] = {
        "session": session,
        "mcp_client": mcp_client,
        "tools": tools,
    }
    
    return NewSessionResponse(session_id=session.session_id)
```

### Step 7: Update _react_loop()

```python
async def _react_loop(self, session, max_turns: int = 50000):
    """
    Main ReAct loop - moved from old Agent.
    Now takes session as parameter instead of self.session.
    """
    session_data = self._sessions[session.session_id]
    mcp_client = session_data["mcp_client"]
    tools = session_data["tools"]
    
    for _ in range(max_turns):
        # Send request (uses session.messages)
        response = self._send_request(session, tools)
        
        # Process streaming response
        gen = self._process_response(response)
        while True:
            try:
                msg_type, token = next(gen)
                yield token  # Stream to prompt()
            except StopIteration as e:
                thinking, content, tool_call_inputs, usage = e.value
                break
        
        # If no tool calls, we're done
        if not tool_call_inputs:
            session.add_assistant_response(thinking, content, [], [])
            return
        
        # Execute tools
        tool_results = await self._execute_tool_calls(
            tool_call_inputs, mcp_client
        )
        
        # Add to session
        session.add_assistant_response(
            thinking, content, tool_call_inputs, tool_results
        )
```

---

## Common Pitfalls

### Pitfall 1: Storing Agent instances
❌ **Wrong**:
```python
self._agents[session_id] = Agent(...)  # No nested agents!
```

✅ **Right**:
```python
self._sessions[session_id] = {
    "session": session,
    "mcp_client": mcp_client,
    "tools": tools,
}
```

### Pitfall 2: Session as instance variable
❌ **Wrong**:
```python
class Agent:
    def __init__(self, session):
        self.session = session  # One session per agent instance
```

✅ **Right**:
```python
class Agent(Agent):
    def _react_loop(self, session):  # Session as parameter
        # Multiple sessions handled by one agent
```

### Pitfall 3: Losing AsyncExitStack
❌ **Wrong**:
```python
async with mcp_client:  # Context closes too early!
    tools = await get_tools(mcp_client)
```

✅ **Right**:
```python
mcp_client = await self._exit_stack.enter_async_context(mcp_client)
# Client stays open until cleanup()
```

### Pitfall 4: Not streaming to ACP client
❌ **Wrong**:
```python
async for chunk in react_loop():
    pass  # Chunks lost!
```

✅ **Right**:
```python
async for chunk in self._react_loop(session):
    await self._conn.session_update(
        session_id,
        update_agent_message(text_block(chunk))
    )
```

---

## Testing Strategy

### Test 1: Agent Inherits from acp.Agent
```python
def test_agent_inherits_from_acp():
    from acp import Agent
    from crow.agent import Agent
    
    agent = Agent()
    assert isinstance(agent, Agent)
```

### Test 2: Has Required ACP Methods
```python
def test_agent_has_acp_methods():
    from crow.agent import Agent
    
    agent = Agent()
    
    # Check ACP methods exist
    assert hasattr(agent, 'on_connect')
    assert hasattr(agent, 'initialize')
    assert hasattr(agent, 'new_session')
    assert hasattr(agent, 'prompt')
    assert hasattr(agent, 'cleanup')
    
    # Check they're async
    import asyncio
    assert asyncio.iscoroutinefunction(agent.new_session)
    assert asyncio.iscoroutinefunction(agent.prompt)
```

### Test 3: Has Business Logic Methods
```python
def test_agent_has_business_logic():
    from crow.agent import Agent
    
    agent = Agent()
    
    # Check business logic methods exist (prefixed with _)
    assert hasattr(agent, '_send_request')
    assert hasattr(agent, '_process_chunk')
    assert hasattr(agent, '_process_response')
    assert hasattr(agent, '_react_loop')
    assert hasattr(agent, '_execute_tool_calls')
```

### Test 4: Resource Management
```python
@pytest.mark.asyncio
async def test_agent_resource_management():
    from crow.agent import Agent
    from contextlib import AsyncExitStack
    
    agent = Agent()
    
    # Should have AsyncExitStack
    assert hasattr(agent, '_exit_stack')
    assert isinstance(agent._exit_stack, AsyncExitStack)
    
    # cleanup() should close it
    await agent.cleanup()
```

### Test 5: Session Handling
```python
@pytest.mark.asyncio
async def test_agent_creates_session(mock_mcp_client):
    from crow.agent import Agent
    
    agent = Agent()
    
    # Create session
    response = await agent.new_session(
        cwd="/tmp/test",
        mcp_servers=[],
    )
    
    assert response.session_id is not None
    assert response.session_id in agent._sessions
```

---

## Verification Checklist

After merge, verify:

- [ ] Single `Agent(acp.Agent)` class exists
- [ ] No nested agent instances (`self._agents` deleted)
- [ ] All ACP methods implemented
- [ ] All business logic methods moved (with _ prefix if private)
- [ ] AsyncExitStack used for MCP clients
- [ ] cleanup() method closes all resources
- [ ] prompt() calls _react_loop()
- [ ] _react_loop() takes session parameter
- [ ] _react_loop() yields tokens for streaming
- [ ] All 28 existing tests still pass
- [ ] Works with ACP client (`python examples/client.py`)

---

## File Structure After

```
src/crow/
├── agent.py                 # Merged Agent(acp.Agent)
├── acp_agent.py            # DELETED or just imports agent.py
├── agent/
│   ├── __init__.py         # Exports Agent
│   ├── session.py          # Session management
│   ├── db.py               # Database models
│   ├── prompt.py           # Template rendering
│   ├── llm.py              # LLM utilities
│   ├── mcp.py              # MCP utilities
│   └── config.py           # Configuration
└── mcp/
    └── search.py           # MCP server
```

---

## Entry Point

```python
# src/crow/acp_agent.py (or delete and use agent.py directly)
from crow.agent import Agent
from acp import run_agent

async def main():
    await run_agent(Agent())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

---

**Remember**: The goal is ONE agent class that inherits from acp.Agent and contains ALL business logic. No wrappers, no nesting, no confusion.
