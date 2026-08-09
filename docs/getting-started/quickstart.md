---
title: Quick Start
---

# Quick Start

## Create an Agent

```python
from crow_cli import Agent

agent = Agent(
    model="gpt-4",
    system_prompt="You are a helpful assistant."
)

response = await agent.run("Hello!")
print(response)
```

## Add Tools

```python
from crow_cli import Agent
from fastmcp import FastMCP

mcp = FastMCP("my-tools")

@mcp.tool()
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city}: Sunny, 72°F"

agent = Agent(
    model="gpt-4",
    mcp_servers=[mcp]
)

response = await agent.run("What's the weather in Tokyo?")
```

## Session Persistence

```python
from crow_cli import Agent

agent = Agent(
    model="gpt-4",
    session_id="my-session"  # Persists to SQLite
)

# First message
await agent.run("My name is Alice")

# Later... remembers context
await agent.run("What's my name?")  # "Your name is Alice"
```
