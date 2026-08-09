# Session Continuity & Compaction: The ACP Persistence Layer

## The Question

When compaction occurs, how do we maintain continuity between:
- The ACP session ID (client's view)
- The internal conversation state (sent to LLM as messages)

## The Answer

You don't need new ACP sessions. You maintain **one logical ACP session** that internally manages multiple conversation states through compaction.

### Architecture

```
ACP Client Perspective (constant):
  session_id = "crow-sess-abc123"
    ↓
    ↓ (all ACP requests route to this session)
    ↓
Internal Crow Reality (evolving):
  
  State 1: [msg1, msg2, msg3, ..., msg100]
    ↓ (compaction at 50k tokens)
  State 2: [summary_msg_v1, msg91, msg92, ..., msg100]
    ↓ (later compaction)
  State 3: [summary_msg_v2, msg185, msg186, ..., msg200]
```

### Key Insight

The `session_id` in ACP is just an identifier - the **actual conversation state** is reconstructed from SQLite at each request:

```python
# Every ACP request for "crow-sess-abc123" does:
messages = await persistence.get_openai_messages("crow-sess-abc123")
# messages will be the COMPACTED state, not full history

# Then send to LLM:
response = oai_client.chat.completions.create(
    model="glm-4.7",
    messages=messages,  # Already in OpenAI format
    ...
)
```

### SQLite Schema Design

Your `docs/03-session-persistence.md` already has it right:

```sql
sessions
  └── id (ACP session ID - NEVER CHANGES)
  └── created_at, updated_at
  └── metadata  

messages
  └── id (autoincrement)
  └── session_id → sessions.id
  └── role, content, tool_call_id, tool_name, tool_args
  └── timestamp

tool_calls
  └── session_id, message_id, tool_name, tool_args, result

compaction_history
  └── session_id
  └── before_message_count, after_message_count
  └── summary, timestamp
```

### Compaction Flow

```python
# Before compaction (State 1)
messages = [msg1, msg2, msg3, ..., msg100]  # 100 messages, 50k tokens

# Trigger compaction
summary = await generate_summary(msg1..msg90)  # Keep last 10

# After compaction (State 2)
messages = [summary_msg, msg91, msg92, ..., msg100]  # 11 messages, 5k tokens

# Record what happened
await persistence.record_compaction(
    session_id="crow-sess-abc123",
    before_count=100,
    after_count=11,
    summary="User asked for web scraper. Built with scrapy..."
)

# Delete old messages from SQLite
await persistence.delete_messages_before("crow-sess-abc123", msg91.id)
```

### From ACP's POV - Nothing Changes

```
ACP Client: POST /v1/messages
{
  "session_id": "crow-sess-abc123",
  "content": "Now I want to add error handling"
}

Crow: 1. Get messages from SQLite -> [summary, msg91..msg100]
      2. Add new user message
      3. Send to LLM with compacted context
      4. Save assistant response
      5. Return response to ACP
```

The client has no idea compaction happened. It just keeps sending to `session_id="crow-sess-abc123"`.

## Implementation

### Files Created

1. **`streaming_parser.py`** - Clean delta parsing for streaming responses
   - `process_delta_content()` - Returns content for display
   - `process_delta_tool_call()` - Accumulates tool call arguments
   - `parse_tool_calls()` - Validates JSON after streaming

2. **`persistence_service.py`** - Service layer for data persistence
   - Repository pattern (abstract base classes)
   - Domain models (Message, ToolCall, Session, CompactionEvent)
   - SQLite implementation with easy Postgres migration path
   - Clean API: `persistence.create_or_get_session()`, `persistence.add_message()`, etc.

### Usage Pattern

```python
from persistence_service import PersistenceService
from streaming_parser import process_delta_content, process_delta_tool_call, parse_tool_calls

# Initialize
persistence = PersistenceService("~/crow/crow.db")
session_id = "crow-sess-abc123"

# Create or resume session
session = await persistence.create_or_get_session(
    session_id, 
    workspace_path="/home/user/project",
    title="Building web scraper"
)

# User message
await persistence.add_message(session_id, "user", "Search for arxiv papers")

# Get messages for LLM (this accounts for compaction automatically)
messages = await persistence.get_openai_messages(session_id)

# Stream response from LLM
response = oai_client.chat.completions.create(
    model="glm-4.7",
    messages=messages,
    tools=tools,
    stream=True
)

# Parse streaming chunks
assistant_response = []
pending_tool_calls = {}

for chunk in response:
    # Display content
    content = process_delta_content(chunk)
    if content:
        print(content, end="", flush=True)
        assistant_response.append(content)
    
    # Accumulate tool calls
    pending_tool_calls = process_delta_tool_call(chunk, pending_tool_calls)

# Build assistant message (after streaming complete)
tool_calls_by_id = parse_tool_calls(pending_tool_calls)

assistant_msg = {
    "role": "assistant",
    "content": "".join(assistant_response)
}

if tool_calls_by_id:
    assistant_msg["tool_calls"] = [
        {
            "type": "function",
            "id": call_id,
            "function": {
                "name": call_data["function_name"],
                "arguments": call_data["arguments_raw"]
            }
        }
        for call_id, call_data in tool_calls_by_id.items()
    ]

# Save to persistence
await persistence.add_message(
    session_id,
    "assistant",
    "".join(assistant_response),
    tool_name=next(iter(tool_calls_by_id.values()))["function_name"] if tool_calls_by_id else None,
    tool_args=next(iter(tool_calls_by_id.values()))["arguments"] if tool_calls_by_id else None
)

# Execute tools, record results, continue loop...
```

## The OpenHands Comparison

OpenHands follows this exact pattern:
- ACP session ID is immutable
- Internal conversation state is compacted
- SQLite stores the "source of truth"
- Each ACP request reconstructs the conversation from SQLite
- The LLM only sees compacted state, not full history

Your architecture is correct - focus on the service layer abstraction to make migration to Postgres easy when you need it.
