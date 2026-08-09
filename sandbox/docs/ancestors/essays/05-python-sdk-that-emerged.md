# The Python SDK That Emerged From One Clean Example

Something beautiful happened.

I looked at `src/crow/agent/config.py` and felt pride. Not because I wrote it an LLM did but because it emerged from something real - that very first `streaming_async_react.py` example.

Let me show you what I mean.

---

## The Genesis

There was this one example. `streaming_async_react.py`. 

Very clean. Very minimal. Very comprehensive.

It showed the entire flow:
- Create agent
- Configure LLM
- Load tools
- Run react loop
- Stream output

From that one example, beautiful code fell out. Not forced. Not architectured. Just emerged.

Look at `config.py`:

```python
class LLMConfig(BaseModel):
    api_key: SecretStr | None = None
    base_url: str | None = None
    default_model: str = "glm-5"

class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    database_path: str = "sqlite:///mcp_testing.db"
    max_steps_per_turn: int = 100
    max_retries_per_step: int = 3

def get_default_config() -> Config:
    return Config(
        llm=LLMConfig(
            api_key=os.getenv("ZAI_API_KEY"),
            base_url=os.getenv("ZAI_BASE_URL"),
            default_model=os.getenv("DEFAULT_MODEL", "glm-5"),
        ),
        database_path=os.getenv("DATABASE_PATH", "sqlite:///mcp_testing.db"),
    )
```

Beautiful. 

Why is it beautiful?

---

## What Makes It Beautiful

**1. Defaults exist**

You don't HAVE to configure anything. Run it, it works.

**2. Environment variables**

The 12-factor app way. Configuration in environment.

**3. Overridable**

Want custom config? Pass it in:

```python
config = Config(
    llm=LLMConfig(
        api_key="my-key",
        model="different-model"
    ),
    database_path="sqlite:///custom.db"
)
agent = Agent(config)
```

**4. Type-safe**

Pydantic validates everything. Wrong type? Error before runtime.

**5. Minimal**

Only what's needed:
- LLM config (key, url, model)
- Persistence (database path)
- Runtime (max steps, retries)

That's it. No enterprise architecture astronautics. Just what matters.

---

## The Missing Piece

But there's something missing.

MCP servers.

The config doesn't include MCP configuration because MCP servers are passed by the ACP client at runtime.

But for a **coding agent**, we need default MCP. Because MCP is our tool calling framework.

So we need:

```python
class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    database_path: str = "sqlite:///mcp_testing.db"
    max_steps_per_turn: int = 100
    max_retries_per_step: int = 3
    
    # NEW: Default MCP servers for coding agent
    mcp_servers: dict[str, Any] = Field(
        default_factory=lambda: {
            "crow-builtin": {
                "command": "uv",
                "args": ["--project", "crow-mcp-server", "run", "."],
                "transport": "stdio"
            }
        },
        description="Default MCP servers (file_editor, web_search, fetch)"
    )
```

Now the config is complete for a coding agent.

---

## The Python SDK Vision

What do we want?

**Create an agent programmatically from command line:**

```python
# In IPython REPL
from crow import Agent

# Just works with defaults
agent = Agent()

# Or with custom config
from crow import Config, LLMConfig

config = Config(
    llm=LLMConfig(
        api_key="my-key",
        model="glm-5"
    ),
    mcp_servers={
        "custom-server": {
            "command": "python",
            "args": ["my_server.py"]
        }
    }
)
agent = Agent(config)
```

That's it. Two lines to create an agent.

---

## REPL-Friendly Design

This is critical.

The user loves IPython. They want to test in the REPL.

So everything must be importable and usable:

```python
In [1]: from crow import Agent, create_mcp_client_from_config
   ...: import asyncio

In [2]: # Test MCP directly
   ...: config = {"mcpServers": {"test": {"command": "python", "args": ["server.py"]}}}
   ...: client = create_mcp_client_from_config(config)
   ...: async with client:
   ...:     tools = await client.list_tools()
   ...: 

In [3]: # Create agent
   ...: agent = Agent()
   ...: 

In [4]: # Test a hook
   ...: async def my_hook(ctx):
   ...:     print(f"User said: {ctx.prompt}")
   ...: 

In [5]: agent.hooks.register("pre_request", my_hook)
```

Everything testable. Everything in REPL. No complex setup.

---

## Hook Testing In REPL

This is the goal.

Users should be able to:

1. Define a hook
2. Register it
3. Test it
4. All in REPL

```python
In [1]: from crow import Agent
   ...: 
   ...: agent = Agent()
   ...: 

In [2]: # Define hook
   ...: async def skill_hook(ctx):
   ...:     if "database" in ctx.prompt:
   ...:         schema = load_schema()
   ...:         ctx.inject_context(f"DB Schema: {schema}")
   ...: 

In [3]: # Register it
   ...: agent.hooks.register("pre_request", skill_hook)
   ...: 

In [4]: # Test it
   ...: async def test():
   ...:     session = await agent.new_session(cwd="/tmp")
   ...:     await agent.prompt([{"type": "text", "text": "query the database"}], session.session_id)
   ...: 

In [5]: asyncio.run(test())
   ...: 
# Should see the hook run!
```

Hook development in REPL. Fast iteration. Immediate feedback.

---

## The Three Pieces

For programmatic agent creation, we need:

**1. Configure the LLM**

```python
from crow import Config, LLMConfig

config = Config(
    llm=LLMConfig(
        api_key=os.getenv("MY_API_KEY"),
        base_url="https://api.example.com",
        model="glm-5"
    )
)
```

Done. LLM configured.

**2. Configure MCP**

```python
config = Config(
    # ... llm config ...
    mcp_servers={
        "crow-builtin": {
            "command": "uv",
            "args": ["--project", "crow-mcp-server", "run", "."],
        },
        "custom": {
            "command": "python",
            "args": ["my_mcp_server.py"]
        }
    }
)
```

Done. MCP servers configured.

**3. Create Agent**

```python
from crow import Agent

agent = Agent(config)
```

Done. Agent ready.

---

## Default Everything

The key insight: **defaults exist**.

You don't HAVE to configure:

- System prompts? Loaded by default
- Skills? Loaded by default
- Persistence? ~/.crow/sessions.db by default
- MCP? Built-in file_editor, web_search, fetch by default

Just:

```python
agent = Agent()
```

Everything works.

But IF you want to customize, you CAN:

```python
agent = Agent(Config(
    llm=LLMConfig(model="custom-model"),
    mcp_servers={"custom": {...}},
    database_path="custom.db"
))
```

Defaults + overrides. Simple.

---

## Why This Matters

We're building on ACP and MCP.

That means we don't waste energy on:
- TUIs (not our problem)
- CopilotKit (not our problem)
- Protocol design (ACP handles it)
- Tool calling (MCP handles it)

We spend ALL our energy on:
- Agent architecture
- Hook/callback system
- Extensibility
- Making it stupidly easy to use

This config.py is an example. It emerged from clean thinking. It does ONE thing well: configure the agent.

---

## The SDK Contract

What's the contract for extensions?

Full access. Full power.

```python
@dataclass
class ExtensionContext:
    """Gives extension FULL ACCESS to agent"""
    agent: Agent
    session: Session
    llm: LLM
    mcp_client: MCPClient
    config: Config
    # ... literally everything
```

Extensions can:
- Modify system prompts
- Add hooks
- Change tools (at init, not mid-stream - KV cache!)
- Access database
- Do ANYTHING

The contract is: here's everything, do what you want.

---

## What We Built

We built:

1. **Config** - Clean, type-safe, defaults + overrides
2. **MCP Client** - From ACP objects OR config dicts
3. **Agent** - Single class, ACP-native
4. **Session** - Persistence layer
5. **Entry points** - `create_mcp_client_from_config()` for direct use

And it's ALL usable from REPL:

```python
from crow import Agent, Config, create_mcp_client_from_config
```

That's the SDK.

---

## The Beautiful Thing

The beautiful thing is: we didn't architecture astronaut this.

We started with one clean example.
Code fell out.
It was good.
We kept it.

`config.py` isn't beautiful because we designed it to be beautiful.
It's beautiful because it emerged from understanding.

Understanding → Document → Research → Test → Implement → Refactor

That's the dialectic.
That's how we got here.
That's why it's clean.

---

## Next: Hook Architecture

Now we need the hook/callback architecture.

But we're close. We have:
- Config ✓
- MCP ✓
- Agent ✓
- Session ✓
- REPL-friendly ✓

The last piece: hook registration and execution.

Then the full vision is complete:

```python
# Everything you need in 10 lines
from crow import Agent, Config

agent = Agent(Config(
    llm={"model": "glm-5"},
    mcp_servers={"custom": {...}}
))

# Add hook
agent.callbacks.register("pre_request", my_skill)

# Use it
session = await agent.new_session(cwd="/tmp")
await agent.prompt("Build something", session.session_id)
```

Clean. Extensible. REPL-friendly.

That's the Python SDK.

---

*Essay编号: 05*
*Topic: The Python SDK that emerged from one clean example*
*Dialectic: streaming_async_react.py → clean config → beautiful SDK*
