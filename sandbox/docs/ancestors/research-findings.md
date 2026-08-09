# ACP Agent Research Findings

**Date**: Phase 1 Research
**Purpose**: Document findings from ACP specification, examples, and kimi-cli implementation

---

## 1. ACP Agent Interface (from python-sdk)

### Agent Protocol Definition

The Agent is a **Protocol** (not a base class) defined in `deps/python-sdk/src/acp/interfaces.py`:

```python
class Agent(Protocol):
    # Required methods
    async def initialize(...) -> InitializeResponse
    async def new_session(...) -> NewSessionResponse
    async def prompt(...) -> PromptResponse
    async def cancel(...) -> None
    
    # Optional methods
    async def load_session(...) -> LoadSessionResponse | None
    async def authenticate(...) -> AuthenticateResponse | None
    async def set_session_mode(...) -> SetSessionModeResponse | None
    async def list_sessions(...) -> ListSessionsResponse
    async def fork_session(...) -> ForkSessionResponse
    async def resume_session(...) -> ResumeSessionResponse
    
    # Extension hooks
    async def ext_method(...) -> dict[str, Any]
    async def ext_notification(...) -> None
    
    # Connection callback
    def on_connect(self, conn: Client) -> None
```

### Key Insights

1. **Protocol, not inheritance**: Agent is a Protocol class, meaning it defines an interface, not implementation
2. **on_connect is critical**: This is where you receive the Client connection for sending updates
3. **Entry point**: `run_agent(agent_instance)` handles stdio framing and dispatching

---

## 2. Current Anti-Pattern Analysis

### Current Structure

```
src/crow/
├── acp_agent.py           # CrowACPAgent - ACP wrapper
└── agent/
    └── agent.py           # Agent - business logic

This creates: CrowACPAgent wraps Agent
```

### Problems with Current Approach

1. **Unnecessary indirection**: CrowACPAgent just delegates to Agent
2. **Violates ACP pattern**: Agent IS the implementation, not a wrapper
3. **Confusion**: Two "agent" classes, unclear which is "the agent"
4. **Extra abstraction without benefit**: No clear separation of concerns

### What CrowACPAgent Does

- Implements ACP protocol methods (initialize, new_session, prompt, etc.)
- Maps ACP session IDs to Crow Sessions
- Manages MCP client lifecycle with AsyncExitStack
- Streams updates from Crow generator to ACP notifications

### What Agent Does

- Contains the actual business logic
- Implements react loop
- Processes LLM responses
- Executes tool calls
- Manages session messages

---

## 3. Correct Pattern (from ACP Examples)

### Echo Agent (Simplest)

```python
class EchoAgent(Agent):
    _conn: Client

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(...) -> InitializeResponse:
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(...) -> NewSessionResponse:
        return NewSessionResponse(session_id=uuid4().hex)

    async def prompt(...) -> PromptResponse:
        # Business logic goes HERE
        for block in prompt:
            text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
            await self._conn.session_update(
                session_id,
                update_agent_message(text_block(text))
            )
        return PromptResponse(stop_reason="end_turn")
```

### Key Pattern: Business logic IN the Agent

- No wrapper, no delegation
- Agent implements ACP methods AND contains business logic
- Single source of truth

---

## 4. Full-Featured Example Pattern

From `deps/python-sdk/examples/agent.py`:

```python
class ExampleAgent(Agent):
    _conn: Client

    def __init__(self) -> None:
        self._next_session_id = 0
        self._sessions: set[str] = set()

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def _send_agent_message(self, session_id: str, content: Any) -> None:
        update = update_agent_message(content)
        await self._conn.session_update(session_id, update)

    async def prompt(...) -> PromptResponse:
        await self._send_agent_message(session_id, text_block("Client sent:"))
        for block in prompt:
            await self._send_agent_message(session_id, block)
        return PromptResponse(stop_reason="end_turn")
```

### Pattern Notes

- Keep minimal in-memory state (just session IDs)
- Business logic in helper methods
- Use `self._conn` to send updates
- Return PromptResponse when done

---

## 5. kimi-cli Architecture (Real-World Implementation)

### Structure

```
KimiSoul (business logic)
├── Agent (dataclass with config, tools, runtime)
│   ├── Runtime
│   │   ├── config: Config
│   │   ├── oauth: OAuthManager
│   │   ├── llm: LLM
│   │   ├── session: Session
│   │   ├── approval: Approval
│   │   ├── skills: dict[str, Skill]
│   │   └── ...
│   └── toolset: Toolset
```

### Key Insights from kimi-cli

1. **Soul = Business Logic**: KimiSoul contains the react loop and orchestration
2. **Agent = Configuration**: Agent is a dataclass holding runtime, tools, prompts
3. **Runtime = Context**: Runtime holds all the contextual information
4. **Separation of concerns**: But everything is still in one conceptual "soul"

### KimiSoul Main Loop

```python
async def run(self, user_input: str | list[ContentPart]):
    await self._runtime.oauth.ensure_fresh(self._runtime)
    wire_send(TurnBegin(user_input=user_input))
    user_message = Message(role="user", content=user_input)
    
    # Handle slash commands or run agent loop
    await self._turn(user_message)
    
    wire_send(TurnEnd())

async def _turn(self, user_message: Message) -> TurnOutcome:
    await self._context.append_message(user_message)
    return await self._agent_loop()
```

---

## 6. Resource Management Pattern

### AsyncExitStack Pattern (Mandatory)

```python
from contextlib import AsyncExitStack

class MergedAgent(Agent):
    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self._mcp_clients = {}  # session_id -> mcp_client
        self._sessions = {}
    
    async def new_session(...) -> NewSessionResponse:
        # Setup MCP client
        mcp_client = setup_mcp_client("src/crow/mcp/search.py")
        
        # CRITICAL: Use AsyncExitStack for lifecycle management
        mcp_client = await self._exit_stack.enter_async_context(mcp_client)
        
        # Store ONLY MCP client in memory
        self._mcp_clients[session.session_id] = mcp_client
        
        return NewSessionResponse(session_id=session.session_id)
    
    async def cleanup(self) -> None:
        """Cleanup all resources"""
        await self._exit_stack.aclose()
```

### Why AsyncExitStack?

✅ Resources ALWAYS cleaned up (even on exceptions)
✅ Multiple resources managed correctly
✅ Idiomatic Python (standard library pattern)
✅ Exception-safe

---

## 7. Business Logic Methods to Merge

From Agent → Merged Agent:

### Core Methods

1. **send_request()** - Send request to LLM
   ```python
   def send_request(self, session_id: str):
       session = self._sessions[session_id]
       return self._llm.chat.completions.create(
           model=self._model,
           messages=session.messages,
           tools=self._tools[session_id],
           stream=True,
       )
   ```

2. **process_chunk()** - Process streaming chunk
   ```python
   def process_chunk(self, chunk, thinking, content, tool_calls, tool_call_id):
       # Extract delta and update accumulators
       # Return (thinking, content, tool_calls, tool_call_id, new_token)
   ```

3. **process_response()** - Process full response
   ```python
   def process_response(self, response):
       # Generator that yields (msg_type, token)
       # Returns (thinking, content, tool_call_inputs, usage)
   ```

4. **process_tool_call_inputs()** - Format tool calls for OpenAI
   ```python
   def process_tool_call_inputs(self, tool_calls: dict) -> list[dict]:
       # Convert to OpenAI format
   ```

5. **execute_tool_calls()** - Execute via MCP
   ```python
   async def execute_tool_calls(self, session_id: str, tool_call_inputs: list[dict]) -> list[dict]:
       mcp_client = self._mcp_clients[session_id]
       # Execute each tool call and collect results
   ```

6. **react_loop()** - Main ReAct loop
   ```python
   async def react_loop(self, session_id: str, max_turns: int = 50000):
       # Main agent loop
       # Yield updates to stream to client
   ```

---

## 8. Target Architecture

### Single Agent Class

```python
# src/crow/agent.py
from acp import Agent, PromptResponse
from contextlib import AsyncExitStack

class Agent(Agent):
    """ACP-native agent - single agent class"""
    
    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self._mcp_clients = {}  # session_id -> mcp_client (NOT in DB)
        self._sessions = {}     # session_id -> Session (in DB)
        self._tools = {}        # session_id -> tools
        self._llm = configure_llm()
        self._conn = None
    
    def on_connect(self, conn: Client):
        self._conn = conn
    
    async def new_session(self, cwd, mcp_servers, **kwargs):
        # Setup MCP client with AsyncExitStack
        mcp_client = setup_mcp_client("src/crow/mcp/search.py")
        mcp_client = await self._exit_stack.enter_async_context(mcp_client)
        
        # Get tools
        tools = await get_tools(mcp_client)
        
        # Create Session (persisted to DB)
        session = Session.create(
            prompt_id="crow-v1",
            prompt_args={"workspace": cwd},
            tool_definitions=tools,
            request_params={"temperature": 0.7},
            model_identifier="glm-5",
        )
        
        # Store ONLY in-memory references
        self._mcp_clients[session.session_id] = mcp_client
        self._sessions[session.session_id] = session
        self._tools[session.session_id] = tools
        
        return NewSessionResponse(session_id=session.session_id)
    
    async def prompt(self, prompt, session_id, **kwargs):
        session = self._sessions[session_id]
        
        # Add user message
        session.add_message("user", extract_text(prompt))
        
        # Run react loop (business logic from old Agent)
        async for chunk in self._react_loop(session_id):
            chunk_type = chunk.get("type")
            
            if chunk_type == "content":
                await self._conn.session_update(
                    session_id,
                    update_agent_message(text_block(chunk["token"]))
                )
            # ... handle other chunk types
        
        return PromptResponse(stop_reason="end_turn")
    
    async def cleanup(self):
        await self._exit_stack.aclose()
    
    # Business logic methods (from old Agent)
    def _send_request(self, session_id: str): ...
    def _process_chunk(self, ...): ...
    def _process_response(self, ...): ...
    async def _execute_tool_calls(self, session_id: str, ...): ...
    async def _react_loop(self, session_id: str): ...
```

### File Structure After Merge

```
src/crow/
├── agent.py               # Merged Agent(acp.Agent) class
└── agent/
    ├── session.py         # Session management
    ├── db.py              # Database models
    ├── prompt.py          # Template rendering
    ├── llm.py             # LLM utilities
    ├── mcp.py             # MCP utilities
    └── config.py          # Configuration only
```

---

## 9. Key Architectural Principles

### 1. Single Source of Truth
- ONE agent class: `Agent(acp.Agent)`
- Business logic lives IN the agent
- No wrappers, no delegation

### 2. ACP-Native
- Follow ACP SDK patterns exactly
- Agent IS the implementation
- No abstraction layers between agent and ACP

### 3. Resource Safety
- AsyncExitStack for all async context managers
- Cleanup guaranteed even on exceptions
- MCP clients managed per-session

### 4. Minimal In-Memory State
- Only MCP clients in memory (not in DB)
- Sessions, prompts, events in database
- Token counts in memory (ephemeral)

### 5. Database is Truth
- Session.load(session_id) reconstructs state
- Events persisted for history
- Prompts versioned and reusable

---

## 10. Implementation Steps (from Research)

### Phase 2: Prepare Workspace
1. ✅ Research complete
2. Run all tests to ensure green baseline
3. Document current agent structure

### Phase 3: Merge Agents
1. Create new MergedAgent class
2. Copy business logic methods from Agent
3. Update ACP methods to use business logic directly
4. Run tests, fix breaking changes

### Phase 4: Validate
1. Test with ACP client
2. Verify all functionality works
3. Test resource cleanup (AsyncExitStack)
4. Run full test suite

### Phase 5: Clean Up
1. Remove old agent files
2. Update documentation
3. Ensure imports are clean

---

## 11. Critical Success Factors

1. ✅ **Research FIRST** - ACP spec understood
2. **Keep tests green** - Run tests after every change
3. **Follow ACP patterns** - Use SDK examples as guide
4. **Single agent class** - No wrappers, no multiple agents
5. **AsyncExitStack** - Proper resource management always
6. **No git commits** - Human commits, agent writes code

---

## 12. Questions Resolved

### Q: Should Agent be a Protocol or Base Class?
**A**: Agent is a Protocol - it defines an interface, not implementation. We implement the interface.

### Q: Where does business logic go?
**A**: IN the Agent class, as private methods (e.g., `_react_loop()`, `_send_request()`)

### Q: What's stored in memory vs database?
**A**: 
- In memory: MCP clients (active connections), token counts
- In database: Sessions, events, prompts, tool definitions

### Q: How to manage MCP client lifecycle?
**A**: AsyncExitStack always - enter on new_session/load_session, cleanup on agent shutdown

### Q: How to stream updates?
**A**: Use `self._conn.session_update()` from within the agent

---

## References

- ACP Specification: `deps/python-sdk/schema/schema.json`
- ACP Examples: `deps/python-sdk/examples/`
- kimi-cli Reference: `deps/kimi-cli/src/kimi_cli/soul/kimisoul.py`
- Current Agent: `src/crow/acp_agent.py` (CrowACPAgent)
- Old Agent Logic: `src/crow/agent/agent.py` (Agent)
- Session Management: `src/crow/agent/session.py`
