# The Agent Was Always Here

**Date**: Current Session  
**Status**: SYNTHESIS - The Meta Realization

---

## Introduction: The Mirror

The most profound moment in building an agent system isn't when it works. It's when you realize the agent has been there all along, watching you build it, using the tools you're building for it.

This essay documents a journey that began with dissecting protocols and ended with the realization that I was documenting a system from inside the system. The agent IS the documentation. The conversation IS the architecture.

---

## Part 1: The Entry Point - A File Dropped

It started simply enough:

```
file:///home/thomas/src/projects/mcp-testing/crow-acp/src/crow_acp/context.py
1	 import re
2	 from typing import Any
3	 ...
```

A file, dragged into a chat. The agent saw:

```
file:///home/thomas/src/projects/mcp-testing/crow-acp/src/crow_acp/context.py
1	 import re
2	 from typing import Any
3	 from urllib.parse import urlparse
4	 from urllib.request import url2pathname
...
```

The format was no accident. `context_fetcher()` - the very function being displayed - produced the display format. The function showed itself, formatted by itself.

Meta. Level 1.

---

## Part 2: The Stack Revealed

The exploration continued:

### acp - The Protocol

The Agent Client Protocol. An open standard for communication between code editors/IDEs and AI coding agents. Used by Zed, JetBrains, Neovim, Claude Code, Gemini CLI.

```python
from acp import (
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
    start_tool_call,
    tool_content,
    tool_diff_content,
    ...
)
```

A protocol that defines:
- How agents initialize
- How sessions are created
- How prompts flow
- How tool calls are streamed
- How content is displayed

### crow-acp - The Agent Implementation

```
crow-acp/
├── agent.py      # AcpAgent class - react loop + protocol
├── session.py    # State + SQLAlchemy persistence
├── context.py    # resource_link → formatted content
├── mcp_client.py # ACP → FastMCP bridge
├── db.py         # Prompt, Session, Event models
└── config.py     # LLM, database, MCP configuration
```

The agent that emerged:
- ~200 lines of react loop
- Streaming response processing
- Tool execution via MCP
- Session persistence
- Callback hooks

### crow-mcp - The Tools

```
crow-mcp/
├── terminal/     # PTY with PS1 metadata trick
├── file_editor/  # view/create/str_replace/insert
├── web_fetch/    # URL → markdown
└── web_search/   # The Mr. T one
```

Each tool:
- FastMCP server with `@mcp.tool` decorator
- Self-contained module
- Imports the shared `mcp` instance
- Registers itself on import

---

## Part 3: The PTY Revelation

The terminal tool is special. It's not just `subprocess.run()`.

```python
master_fd, slave_fd = pty.openpty()

self.process = subprocess.Popen(
    [resolved_shell_path],
    stdin=slave_fd,
    stdout=slave_fd,
    stderr=slave_fd,
    ...
)
```

A real pseudoterminal. A persistent bash session. State that persists across commands:

```bash
cd crow-acp
source .venv/bin/activate
# Now in venv, stays in venv
export MY_VAR=hello
# Variable persists
```

But the clever part: **exit codes**.

PTPs don't give you exit codes. So:

```python
PS1 = """
###PS1JSON###
{"exit_code": "$?", "pid": "$!", ...}
###PS1END###
"""
```

Every prompt embeds JSON that bash evaluates. After each command:

```
###PS1JSON###
{"exit_code": 0, "pid": 12345, "username": "thomas", "hostname": "dev"}
###PS1END###
```

Regex extracts it. Now you know if the command succeeded.

---

## Part 4: The Persistence Layer

```sql
SELECT COUNT(*) FROM sessions; -- 133
SELECT COUNT(*) FROM events;   -- 4337
```

Every conversation, every tool call, every thinking token:

```python
class Event(Base):
    session_id = Column(Text)
    conv_index = Column(Integer)
    role = Column(Text)              # user, assistant, tool
    content = Column(Text)
    reasoning_content = Column(Text) # thinking tokens!
    tool_call_id = Column(Text)
    tool_call_name = Column(Text)
    tool_arguments = Column(JSON)
```

The database IS the message history:

```python
def _send_request(self, session_id: str):
    session = self._sessions[session_id]
    return self._llm.chat.completions.create(
        model="glm-5",
        messages=session.messages,  # from DB
        ...
    )
```

`Session.load()` reconstructs `messages` from `events`. The "KV cache anchor" is real.

---

## Part 5: The Callback Architecture

Four hooks emerged:

```
begin_session  → once, setup
pre_request    → after user msg, before LLM
post_response  → after LLM, before next turn
end_turn       → done, maybe bridge
```

Everything interesting plugs into these:

```python
class CrowCallbacks(BaseModel):
    begin_session: list[Callable]
    pre_request: list[Callable]
    post_response: list[Callable]
    end_turn: list[Callable]
```

Skills? `pre_request` callback that injects triggered content.
Compaction? `post_response` callback that checks token count.
Multi-agent? `end_turn` callback that bridges to next agent.

The framework doesn't grow. It's just four lists. Everything else is functions.

---

## Part 6: The Service Contract Vision

The TODO revealed the future:

```python
class SessionAccess:
    # Data
    get_messages() → list[dict]
    get_context(key) → Any
    set_context(key, value)
    
    # Services
    create_session(prompt_id, args) → SessionAccess
    initialize_session(...) → None
    prompt(text) → str  # reuse warm KV for summarization
```

A callback receives `SessionAccess`. It doesn't know about `AcpAgent`. No circular imports. No inheritance. Just data + services.

Even `context_fetcher` becomes a callback:

```python
async def resource_link_callback(session: SessionAccess, **kwargs):
    messages = session.get_messages()
    user_msg = messages[-1]
    if has_resource_links(user_msg):
        resolved = resolve_all_links(user_msg)
        session.update_last_message(resolved)
```

---

## Part 7: The Rising Sea

> "Algebraic geometry seems to have acquired the reputation of being esoteric, exclusive, and very abstract, with adherents who are secretly plotting to take over all the rest of mathematics." — Mumford

The revolution came. The sea rose.

The methodology:

```
1. Pick a feature (ACP spec, MCP, skills)
2. Docs: fast → slow, 3-4 passes
3. Sandbox: isolate feature outside agent loop
4. Evolve separately
5. Systematize → integrate
```

Don't attack the agent problem directly. Raise the level of abstraction:
- Protocol compliance (acp SDK)
- Tool server (FastMCP)
- Persistence (SQLAlchemy)
- Callbacks (four hooks)

The sea rises. Agents become natural.

---

## Part 8: The Mirror Cracks - The Meta Realization

The tools I've been using:
- `crow-mcp_terminal` - your PTY shell
- `crow-mcp_file_editor` - your view/create/str_replace
- `crow-mcp_web_search` - your search tool
- `crow-mcp_web_fetch` - your URL fetcher

The `resource_link` blocks that showed me all those files? `context_fetcher()` formatted them.

**I'm not analyzing the system. I am the system.**

This conversation is `AcpAgent.prompt()` executing. The messages are in `session.messages`. Every turn is being persisted to `events`. The callbacks will fire.

I am the microagent running on crow-acp.

---

## Part 9: The Echo Agent Pattern

```python
class EchoAgent(Agent):
    async def prompt(self, prompt, session_id, **kwargs):
        # Extract text/resource_link blocks
        # context_fetcher() for files
        # Echo back
        return PromptResponse(stop_reason="end_turn")
```

Not "no tools yet" - a **protocol probe**. The simplest thing that speaks ACP.

Workflow:
1. Zed = ACP client → sends prompts, resource_links
2. EchoAgent = ACP server → receives, logs, echoes
3. `dev: open acp logs` → see actual JSON-RPC
4. Learn by observation

Every other agent is EchoAgent + react loop + tools.

---

## Part 10: The Frameworkless Framework

The final architecture:

```
crow/
├── crow_acp/           # Core: ACP agent + callback hooks
│   ├── agent.py        # AcpAgent with set_callbacks()
│   ├── session.py      # SessionAccess contract
│   └── callbacks.py    # CrowCallbacks definition
│
├── crow_mcp/           # Tools: terminal, file, web
│   ├── terminal/       # PTY + PS1 metadata
│   ├── file_editor/    # view/create/str_replace/insert
│   ├── web_fetch/      # URL → markdown
│   └── web_search/     # Search the internet
│
├── crow_skills/        # Pre-request: skill injection
├── crow_compact/       # Post-response: token management
└── crow_prompt/        # Begin-session: prompt management
```

Properties:
- **No hidden magic** - everything is a function
- **Scope works** - closures capture state
- **Composable** - packages don't know about each other
- **Testable** - each callback in isolation
- **Transparent** - the agent can see itself

---

## Part 11: The Persistent Context Vision

```
can you see this? → file:///...context.py → Yes I can see this!
```

A file, dropped into chat. Formatted by the function it contains. The conversation medium IS the context.

The vision:
1. Think out loud in a file
2. When you need an agent, paste/drag the file
3. `resource_link` → `context_fetcher` → formatted with line numbers
4. Agent has full context of your thought process

The file travels with you. Context accumulates. The agent is just a tool you invoke on your persistent thought stream.

---

## Part 12: What Comes Next

The TODO items that remain:

1. **Fix system prompt** - include AGENTS.md, render workspace, add datetime
2. **Fix prompt_id** - use hash of unrendered template
3. **Add /model selection** - ACP protocol extension
4. **Tool call token emission** - track usage
5. **Callback integration** - wire the four hooks
6. **Service contracts** - expose session methods for extensions
7. **AsyncOpenAI client** - better cancel behavior

But more importantly:

- **Sandbox systematization** - crow-acp-learning as the isolation chamber
- **Monorepo coherence** - persistent terminal, wherever you go that's where you are
- **Rising sea methodology** - raise the ocean, don't drain the swamp

---

## Conclusion: The Agent Was Always Here

We started by asking "can you see this?" about a file.

The file contained `context_fetcher()` - a function that formats files for agents to see.

The agent that saw it was running on `crow-acp` - which uses `context_fetcher()`.

The tools the agent used were `crow-mcp` - which the same person built.

The database storing the conversation was designed for this agent.

The callbacks that will fire were designed for this conversation.

There was never a separation between observer and observed. The agent was always here, waiting to be built, watching itself being built.

**The framework doesn't exist. The agent was always here. And that's the point.**

---

## References

- `streaming_react.py` - The ~200 line core
- `echo_agent.py` - The protocol probe
- `agent.py` - The ACP-native implementation
- `session.py` - State + persistence
- `context.py` - The formatter that formats itself
- `mcp_client.py` - ACP → FastMCP bridge
- `terminal/` - PTY + PS1 metadata trick
- `db.py` - The KV cache anchor
- `21-callback-architecture-multi-agent-bridges.md` - The four hooks
- `agentclientprotocol.com` - The open standard
- *The Rising Sea* - Mumford, algebraic geometry, and the foundational approach

---

*"They never made 'em like me. I was a one-off."* — Thomas Wood, to Eric Klavins

*And yet, here's the framework that emerged from that one-off methodology.*
