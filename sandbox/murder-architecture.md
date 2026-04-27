# Murder Architecture Summary

## Pattern
**Single-layer orchestration via MCP tools. No agent-client nesting.**

Orchestrator agent → Murder-MCP (FastMCP tools) → FastAPI backend → Frontend (ACP client) → Agent subprocess

The frontend IS the ACP client. The backend routes tool calls to frontend sessions via WebSocket. Agents are controlled by the frontend, not by other agents.

## Murder-MCP Tools
- `kill_agent` / `cancel_agent` — stop sessions
- `list_sessions` / `get_session` — query shared DB
- `fork_session` / `continue_session` — branch from any conversation turn
- `inspect_agent` / `extract_reasoning` — walk past reasoning at key points
- `summarize_session` — leverage compaction for summaries

## RLAIF Loop
Agent acts → orchestrator forks & interrogates → structured feedback for training. Better than watching the tapes.
