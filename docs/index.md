---
title: crow-cli Documentation
---

# crow-cli Documentation

Minimal Native ACP Agent Framework. No frameworks, just OpenAI SDK, FastMCP, and SQLAlchemy.

```{toctree}
:maxdepth: 2
:caption: Getting Started

getting-started/installation
getting-started/quickstart
```

---

## Quick Install

```bash
uv tool install crow-cli --python 3.14
```

## Features

- **Native ACP Agent**: No framework lock-in
- **FastMCP Integration**: Tool calling via MCP
- **Session Persistence**: SQLite-backed sessions
- **Streaming**: Real-time response streaming

## Why crow-cli?

Most agent frameworks are heavy abstractions. crow-cli is a reference implementation that shows you exactly how things work:

- OpenAI SDK for LLM calls
- FastMCP for tool integration
- SQLAlchemy for persistence

No magic, just code you can understand and modify.
