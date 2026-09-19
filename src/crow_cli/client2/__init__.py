"""Client-side ACP v2: the machinery that talks TO an agent.

Mirrors :mod:`crow_cli.client`, which speaks v1 and is frozen. The split is
the same one v1 drew — ACP is the client<->agent contract, so what drives an
agent lives here, while MCP is the agent<->tool contract and the ``task``
subtool lives with the tools. The two halves couple through sqlite, never
in-process.
"""

from .subagent import ChildExited, HeadlessClient, SubagentDriver, child_config

__all__ = ["ChildExited", "HeadlessClient", "SubagentDriver", "child_config"]
