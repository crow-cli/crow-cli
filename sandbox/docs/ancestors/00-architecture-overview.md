# Crow Agent Architecture Overview

## Vision

Crow Agent is an ACP-native, MCP-first AI coding agent. We don't build frameworks - we connect protocols.

## Core Philosophy

```
Frameworkless Framework: We don't build agent frameworks. We connect protocols.

The protocols (ACP, MCP, Agentskills) handle the hard parts.
Crow Agent just orchestrates them elegantly.
```

**What we are:**
- ACP-first agent implementation (single agent class, no wrappers)
- MCP-first tool calling (via FastMCP, no custom tool framework)
- Minimal, purpose-specific code
- Protocol compliance over framework features

**What we are NOT:**
- Another agent SDK (not like kimi-cli, software-agent-sdk, openhands.sdk)
- A tool calling framework (FastMCP has this covered)
- A type system for agents (use ACP schema)
- A state management framework (use ACP session/load)

## The 6 Core Components

### 1. ACP-First Agent
**Status**: In progress (merging agents into single ACP-native implementation)

Single `Agent(acp.Agent)` class:
- Business logic lives IN the agent
- No wrapper, no separate framework
- ACP protocol compliance IS the architecture
- Implements session/load from ACP spec

**Reference**: `deps/python-sdk/schema/schema.json`

### 2. MCP-First Frameworkless Framework
**Status**: ✅ Complete (via FastMCP)

All agent frameworks are just sophisticated tool calling frameworks. FastMCP already solves this:
- Tool definitions and execution via MCP
- No custom tool calling layer
- MCP is the standard, we just consume it
- Framework-free: MCP + react loop = agent

**Implementation**: `src/crow/mcp/search.py`, `src/crow/agent/mcp.py`

### 3. Persistence (ACP session/load)
**Status**: ✅ Complete

Our persistence layer implements ACP's session/load specification:
- **Prompts**: Versioned system prompt templates
- **Sessions**: The "DNA" of the agent (KV cache anchor)
- **Events**: The "wide" transcript (all conversation turns)

**This isn't just "persistence"** - it's ACP session management implemented correctly.

**Implementation**: `src/crow/agent/session.py`, `src/crow/agent/db.py`

### 4. SKILLS (CRITICAL - NOT YET IMPLEMENTED)
**Status**: ❌ NOT BEGUN

Skills are the project's extension mechanism:
- Specification: `https://agentskills.io/llms.txt`
- Skills allow agents to have specialized capabilities
- Separate protocol from ACP/MCP
- Mondo critical feature

**Action Required**: Read spec, design implementation, TDD

### 5. Prompt Management
**Status**: ✅ Partially Complete

System prompt versioning and rendering:
- Templates stored in database
- Jinja2 rendering with arguments
- Lookup-or-create pattern
- Deterministic session IDs for KV cache reuse

**Implementation**: `src/crow/agent/prompt.py`, `src/crow/agent/prompts/`

### 6. Compaction
**Status**: ❌ NOT YET IMPLEMENTED

Conversation compaction to manage token limits:

**The Algorithm**:
```
Post-request hook:
1. Check total tokens (input + output of request + response)
2. If > threshold:
   - Keep first K turns
   - Keep last K turns  
   - Replace middle M-2K turns with summary
3. Summary prompt:
   "Calling no tools, please accurately summarize the part of 
   the conversation between {K-th message} and {M-K-th message} 
   such that the conversation is greatly compacted in length 
   without losing the crucial context, especially files changed. 
   Use file paths as pointers to use the filesystem as persistent 
   state. Do this often!"
```

**Why This Matters**:
- Prevents token limit errors
- Maintains crucial context (especially file changes)
- Filesystem becomes persistent state
- Enables long-running sessions

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ACP Clients (UI Layer)                   │
│  - Toad TUI (terminal)                                      │
│  - VSCode extensions                                        │
│  - Zed editor                                              │
│  - Custom clients via ACP protocol                          │
└──────────────────────┬──────────────────────────────────────┘
                       │ ACP Protocol (stdio/JSON-RPC)
                       │
         ┌─────────────┴─────────────┐
         │    Agent(acp.Agent)    │ ← Single ACP-native agent
         │  - Business logic IN agent│
         │  - AsyncExitStack         │
         │  - Session management     │
         │  - React loop             │
         └─────────────┬─────────────┘
                       │
         ┌─────────────┴─────────────┐
         │   Tool Execution (MCP)    │ ← Frameworkless tool calling
         │  - FastMCP client         │
         │  - Python REPL (MCP)      │
         │  - Search (MCP)           │
         │  - File ops (MCP)         │
         └─────────────┬─────────────┘
                       │
         ┌─────────────┴─────────────┐
         │   Persistence (ACP impl)  │ ← Implements ACP session/load
         │  - SQLite (sessions)      │
         │  - SQLAlchemy models      │
         │  - Prompt templates       │
         │  - Event history          │
         └────────────────────────────┘
```

## Key Components

### 1. ReAct Loop with Parallel Tool Execution

The core agent loop with intelligent tool calling:

```python
# User input
    ↓
# Search & analysis (parallel searches, memory lookup)
    ↓
# LLM streaming response with reasoning
    ↓
# PARALLEL tool execution (gather results)
    ↓
# Continue or finish
```

**Key innovation:** Execute ALL tools in parallel using `asyncio.gather()`, not sequentially.

### 2. Session Persistence (SQLite)

Persist everything:

```
sessions → messages → tool_calls → compaction_history → skills
```

- Reconstructible history
- Session resumption
- Compaction triggers
- Learning capture

### 3. Conversation Compaction

When context gets too large:

1. Summarize old messages with cheap model
2. Replace N messages with 1 summary
3. Preserve last K messages for context
4. Record compaction event for debugging

### 4. Multi-Agent Loop Detection

Lightweight monitoring:

```
Primary Agent (GLM-4.7, full context)
  ↓ every output
Loop Detector Agent (gpt-4o-mini, short context)
  ↓ if stuck
Recovery Handler
```

Detects:
- Repeating action cycles (4+ times)
- Repeating error cycles (3+ times)
- Agent monologues (3+ messages)
- Alternating patterns (6+ cycles)
- Context window errors

### 5. The Finish Tool

Only built-in, non-MCP tool:

```python
finish() → {
    1. Session summary
    2. Learning extraction
    3. Skill assessment
    4. State updates (SQLite + Qdrant)
    5. Resource cleanup
}
```

Captures insights, identifies missing skills, updates vector store.

### 6. Cancellation with State Preservation

For local models taking 15+ minutes:

```python
User hits cancel
    ↓
Stop HTTP stream
    ↓
Save partial tokens
    ↓
Preserve KV cache (if possible)
    ↓
Resumable without degradation
```

### 7. Python REPL (MCP)

Primary reasoning environment:

```python
execute_python(code)
    ↓
Jupyter kernel (persistent state)
    ↓
Environment (uv .venv, packages)
```

Features:
- Variable persistence across calls
- Jupyter-style `!bash`, `%%bash`, `%pip install`
- Package installation with `uv`
- Variable inspection

### 8. Parallel Search Strategy

Agent encouraged to search in parallel:

```
"Search for ML papers"
    ↓
ArXiv search + GitHub search + SearXNG web search
    ↓ (all in parallel)
Synthesize results
```

Prompt: "Launch multiple searches across sources simultaneously"

## Data Flow

### Typical Request

```
1. User: "Build a web scraper for ArXiv"
   ↓
2. Compaction check: Is conversation too long?
   ↓
3. Pre-analysis: Search conversation history, load skills
   ↓
4. Parallel searches:
   - ArXiv API documentation
   - Web scraping Python libraries
   - GitHub example projects
   ↓
5. LLM generates plan with tool calls
   ↓
6. PARALLEL tool execution:
   - execute_python: "try scrapy..."
   - search: "arxiv crawler"
   - shell: "mkdir src"
   ↓
7. Loop detection check: Is agent stuck?
   ↓
8. LLM processes results, generates next action
   ↓
9. Repeat until user cancels or agent calls finish()
```

### Cancellation

```
Long-running generation...
    ↓
User: Ctrl+C
    ↓
Stop HTTP stream immediately
    ↓
Save partial tokens to SQLite
    ↓
Mark message as "partial, cancelled"
    ↓
User can resume or start new
```

### Session End

```
Agent:finish(success=True, summary="Built scraper...")
    ↓
Finish subagent:
    1. Generate comprehensive summary
    2. Extract learnings (breakthroughs, failures)
    3. Assess skills (used, missing, new)
    4. Update SQLite (sessions, learnings, skills)
    5. Update Qdrant (searchable learning vectors)
    6. Cleanup resources
    ↓
Session marked "completed"
```

## Extension Points

### Adding a Tool (MCP)

```python
# Create MCP server
from fastmcp import FastMCP

mcp = FastMCP("MyTools")

@mcp.tool()
async def my_tool(param: str) -> str:
    """Tool description"""
    return f"Result: {param}"

# Crow auto-discovers and uses it
```

### Adding a Skill

Skills are loaded from standard locations:

```
~/.crow/skills/
├── python_debugging.skill
├── web_scraping.skill
└── data_analysis.skill
```

Auto-discovery at startup, lazy loading when needed.

### Adding an ACP Client

Any client implementing ACP works:

```bash
# Toad
toad connect crow

# VSCode extension
# (native in crow-ai extension)

# JetBrains
# Menu → AI → Connect to Crow
```

## Performance Characteristics

### Streaming Benefits

- **Local models**: 15+ minute generations are tolerable
- **Remote models**: Faster time to first token
- **Cancellation**: Can stop mid-generation

### Parallel Tool Execution

- Searches: 3-5x faster (searxng + arxiv + github)
- Independent tool calls: Nx faster vs sequential
- Memory tradeoff: All results in memory simultaneously

### Compaction

- Reduced tokens: 50-90% reduction in context size
- Better focus: Recent conversation not buried
- Preserve learnings: Summaries capture key insights

## Technology Stack

- **Language**: Python 3.11+
- **Package manager**: uv
- **Persistence**: SQLite (aiosqlite for async)
- **Vector search**: Qdrant
- **Protocols**: MCP (FastMCP), ACP (custom implementation)
- **LLMs**: Any OpenAI-compatible API (GLM-4.7, local via llama.cpp, etc.)
- **REPL**: Jupyter Kernel Gateway or IPython
- **CLI**: Click

## Comparison to Other Frameworks

| Framework | Approach | Philosophy |
|-----------|-----------|-------------|
| Crow | **Thin orchestration** | Connect protocols, don't rebuild |
| OpenHands | Heavyweight SDK | Comprehensive with opinionated patterns |
| LangGraph | Graph-based workflows | Orchestrate across many tools |
| AutoGen | Multi-agent conversation | Agents talking to each other |

**Crow is distinct**: It's primarily a **protocol layer** with minimal agent logic, focusing on streaming, persistence, and extensibility.

## Getting Started

```bash
# Install crow
uv tool install crow-ai

# Initialize project
cd /path/to/project
crow init

# Start ACP server (for editor integration)
crow start

# Or send single message
crow start --message "Help me fix bug in file.py"
```

## Documentation

- [01. Parallel Tool Calling](01-parallel-tool-calling.md)
- [02. Toad Integration](02-toad-integration.md)
- [03. Session Persistence](03-session-persistence.md)
- [04. Cancellation and State](04-cancellation-and-state.md)
- [05. Loop Detection](05-loop-detection.md)
- [06. The Finish Tool](06-finish-tool.md)
- [07. Python REPL Integration](07-python-repl.md)

## Roadmap

### Phase 1: Core (Current)
- [x] ReAct loop with streaming
- [ ] Parallel tool execution
- [ ] SQLite persistence
- [ ] Session resumption
- [ ] Basic compaction

### Phase 2: Reliability
- [ ] Loop detection
- [ ] Cancellation handling
- [ ] Finish tool subagent
- [ ] Error recovery

### Phase 3: Intelligence
- [ ] Skill system
- [ ] Qdrant integration
- [ ] Learning capture
- [ ] Semantic search over past sessions

### Phase 4: Integration
- [ ] ACP implementation
- [ ] Toad registry submission
- [ ] VSCode extension
- [ ] Web interface (included)

## Contributing

Crow is built on open protocols. Contribute by:

1. **Creating MCP servers** for new tools
2. **Building skills** for the skill repository
3. **Submitting PRs** to core Crow
4. **Reporting bugs** in loop detection or compaction

## License

MIT - building on the open ecosystem of protocols.

---

**Crow: Thin but Powerful. Protocol-First. Extension-Centric.**
