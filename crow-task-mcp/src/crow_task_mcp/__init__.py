"""
Crow Task MCP - Orchestration tools for agent-to-agent communication.

This package provides MCP tools for multi-agent workflows, enabling agents
to coordinate by sending prompts, spawning child agents, and managing sessions.
"""

from .main import mcp

__version__ = "0.1.0"
__all__ = ["mcp"]
