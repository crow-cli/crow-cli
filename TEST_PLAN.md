# Crow Agent Test Plan

## Philosophy

**Test the behavior, not the implementation.** We're protecting critical invariants and user-facing guarantees, not achieving 100% code coverage.

**Unit tests** = Fast, isolated, in-memory, mock external dependencies  
**Integration tests** = Slower, real subsystems, test actual workflows  
**E2E tests** = Full agent loop with real LLM (handled separately by you)

---

## Critical Areas to Test

### 1. Session Management (`crow_cli/agent/session.py`)

**Why it matters:** This is the persistence layer - conversations must survive restarts and be reloadable.

**Unit Tests:**
- [ ] `test_session_create()` - Create session with prompt, tools, params
- [ ] `test_session_load()` - Load existing session from DB
- [ ] `test_session_add_message()` - Add message persists to DB
- [ ] `test_session_message_order()` - Messages maintain insertion order
- [ ] `test_session_swap_ids()` - Compaction swaps IDs atomically
- [ ] `test_session_tool_definitions()` - Tool definitions persist correctly

**Integration Tests:**
- [ ] `test_session_roundtrip()` - Create → reload → verify all fields match
- [ ] `test_session_with_complex_tools()` - Complex tool definitions survive serialization
- [ ] `test_session_compaction()` - Archive old session, compacted session takes over

---

### 2. Prompt System (`crow_cli/agent/prompt.py`)

**Why it matters:** System prompts define agent behavior and must render correctly.

**Unit Tests:**
- [ ] `test_lookup_or_create_prompt_new()` - New prompt gets created
- [ ] `test_lookup_or_create_prompt_existing()` - Existing prompt reused by template
- [ ] `test_prompt_template_rendering()` - Jinja2 templates render with args
- [ ] `test_prompt_template_args()` - Template args substitute correctly

**Integration Tests:**
- [ ] `test_prompt_persistence()` - Prompt survives DB reload
- [ ] `test_prompt_versioning()` - Same template = same prompt ID

---

### 3. Configuration (`crow_cli/agent/configure.py`)

**Why it matters:** Config drives all behavior - LLM providers, models, tools.

**Unit Tests:**
- [ ] `test_config_load_default()` - Loads from ~/.crow/config.yaml
- [ ] `test_config_load_custom_dir()` - Loads from custom directory
- [ ] `test_config_env_var_interpolation()` - ${VAR} replaced with env values
- [ ] `test_config_missing_env_var()` - Missing env vars become empty strings
- [ ] `test_config_llm_parsing()` - Providers and models parsed from YAML
- [ ] `test_config_db_uri_sqlite()` - SQLite URI handling (with/without leading /)
- [ ] `test_config_mcp_servers()` - MCP servers config loaded
- [ ] `test_config_tool_overrides()` - Tool name overrides from config

**Integration Tests:**
- [ ] `test_config_roundtrip()` - Save config → load → verify all fields
- [ ] `test_config_env_file()` - .env file loaded before config.yaml

---

### 4. MCP Client Integration (`crow_cli/agent/mcp_client.py`)

**Why it matters:** MCP servers = tools = agent capabilities.

**Unit Tests:**
- [ ] `test_get_tools_empty()` - Empty tool list when no servers
- [ ] `test_get_tools_single_server()` - Tools extracted from single server
- [ ] `test_get_tools_multiple_servers()` - Tools merged from multiple servers
- [ ] `test_create_mcp_client_builtin()` - Built-in crow-mcp server loads
- [ ] `test_create_mcp_client_custom()` - Custom MCP server config works

**Integration Tests:**
- [ ] `test_mcp_server_connect()` - Actual connection to MCP server
- [ ] `test_mcp_tool_discovery()` - Tools discovered and callable
- [ ] `test_mcp_server_error_handling()` - Server errors handled gracefully

---

### 5. Tool Execution (`crow_cli/agent/tools.py`)

**Why it matters:** Tools are how the agent interacts with the world.

**Unit Tests:**
- [ ] `test_tool_match_by_name()` - Correct tool selected by name
- [ ] `test_tool_missing()` - Missing tool raises error
- [ ] `test_execute_acp_terminal()` - Terminal tool executes command
- [ ] `test_execute_acp_write()` - Write tool creates file
- [ ] `test_execute_acp_read()` - Read tool reads existing file
- [ ] `test_execute_acp_edit()` - Edit tool performs string replacement
- [ ] `test_execute_acp_tool()` - Generic tool forwarding works

**Integration Tests:**
- [ ] `test_tool_chain_write_read()` - Write → Read → Verify content
- [ ] `test_tool_chain_edit_verify()` - Edit → Read → Verify changes
- [ ] `test_tool_error_propagation()` - Tool errors propagate to agent
- [ ] `test_tool_concurrent()` - Multiple tools execute without conflict

---

### 6. React Loop (`crow_cli/agent/react.py`)

**Why it matters:** This is the agent's brain - the reasoning/acting loop.

**Unit Tests:**
- [ ] `test_send_request_simple()` - Simple message sent to LLM
- [ ] `test_send_request_with_tools()` - Request includes tool definitions
- [ ] `test_process_response_content()` - Content tokens extracted
- [ ] `test_process_response_tool_calls()` - Tool calls parsed from response
- [ ] `test_process_tool_call_inputs()` - Tool inputs formatted correctly
- [ ] `test_execute_tool_calls_single()` - Single tool call executes
- [ ] `test_execute_tool_calls_multiple()` - Multiple tool calls execute in parallel

**Integration Tests:**
- [ ] `test_react_loop_simple_task()` - Simple task completes in one turn
- [ ] `test_react_loop_multi_turn()` - Complex task takes multiple turns
- [ ] `test_react_loop_tool_errors()` - Tool errors don't crash loop
- [ ] `test_react_loop_max_steps()` - Loop respects max_steps_per_turn

---

### 7. ACP Protocol (`crow_cli/agent/main.py`)

**Why it matters:** This is the agent's public API - must comply with ACP spec.

**Unit Tests:**
- [ ] `test_initialize_response()` - Returns correct protocol version/capabilities
- [ ] `test_new_session_creates_session()` - NewSessionResponse has session_id
- [ ] `test_load_session_exists()` - Loaded session matches saved session
- [ ] `test_load_session_not_found()` - Missing session raises error
- [ ] `test_set_session_mode()` - Session mode changes
- [ ] `test_set_config_option()` - Config option updates
- [ ] `test_prompt_creates_task()` - Prompt starts async task
- [ ] `test_cancel_stops_task()` - Cancel stops running prompt

**Integration Tests:**
- [ ] `test_acp_initialize_flow()` - Full init sequence works
- [ ] `test_acp_session_lifecycle()` - New → Prompt → Load → Cancel
- [ ] `test_acp_concurrent_sessions()` - Multiple sessions run simultaneously

---

### 8. Database Schema (`crow_cli/agent/db.py`)

**Why it matters:** Schema must support all persistence needs.

**Unit Tests:**
- [ ] `test_create_database()` - Tables created successfully
- [ ] `test_message_serialization()` - Message dict → JSON → dict roundtrip
- [ ] `test_session_cascade_delete()` - Deleting session deletes messages
- [ ] `test_prompt_cascade_delete()` - Deleting prompt deletes sessions

**Integration Tests:**
- [ ] `test_db_concurrent_access()` - Multiple sessions write simultaneously
- [ ] `test_db_large_messages()` - Large message content persists
- [ ] `test_db_index_usage()` - Queries use indexes (role, session_id)

---

## Test Structure

```
crow-cli/
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures
│   ├── unit/
│   │   ├── test_session.py
│   │   ├── test_prompt.py
│   │   ├── test_config.py
│   │   ├── test_mcp_client.py
│   │   ├── test_tools.py
│   │   ├── test_react.py
│   │   ├── test_acp.py
│   │   └── test_db.py
│   ├── integration/
│   │   ├── test_session_integration.py
│   │   ├── test_mcp_integration.py
│   │   ├── test_tools_integration.py
│   │   └── test_react_integration.py
│   └── fixtures/
│       ├── config.yaml
│       ├── prompts/
│       └── test_files/
```

---

## Key Fixtures (conftest.py)

```python
# Temp database
@pytest.fixture
def temp_db_uri(tmp_path):
    db_path = tmp_path / "test.db"
    return f"sqlite:///{db_path}"

# Test config
@pytest.fixture
def test_config_dir(tmp_path):
    # Create ~/.crow structure with test config.yaml
    ...

# Mock LLM
@pytest.fixture
def mock_llm_response():
    # Return predictable LLM responses for testing
    ...

# Mock MCP server
@pytest.fixture
def mock_mcp_server():
    # In-memory MCP server with test tools
    ...
```

---

## Test Priorities

**Phase 1 (Week 1):** Session, Prompt, Config, DB  
**Phase 2 (Week 2):** MCP Client, Tools  
**Phase 3 (Week 3):** React Loop, ACP Protocol  
**Phase 4 (Week 4):** Integration tests, edge cases

---

## What NOT to Test

- ❌ LLM behavior (that's the model's responsibility)
- ❌ Terminal persistence (that's crow-mcp's job)
- ❌ Network connectivity (assume it works or fails)
- ❌ Third-party library internals

---

## Success Criteria

- ✅ All unit tests pass (< 1 second each)
- ✅ All integration tests pass (< 10 seconds each)
- ✅ Test coverage > 80% on core modules
- ✅ CI runs tests on every PR
- ✅ Tests run in parallel

---

## Notes

- Use `pytest-asyncio` for async tests
- Use `pytest-mock` for mocking
- Use `temp_path` for isolated filesystem tests
- Use `temp_db_uri` for isolated database tests
- Mock LLM calls - don't hit real APIs in unit tests
- Integration tests can use real MCP servers (crow-mcp)
