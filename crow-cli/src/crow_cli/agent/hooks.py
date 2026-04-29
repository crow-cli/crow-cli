"""
Command hooks for terminal execution and file snapshot capture.

Each hook takes a command string and returns None (allow) or a rejection message.
Hooks are passed to AcpAgent at construction time — no global registry.
"""

import re
from logging import Logger
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from crow_cli.agent.session import AgentSession

CommandHook = Callable[[str], str | None]

# File snapshot hooks capture pre-mutation file state for Monaco diffs.
# They don't reject - they just record.
FileSnapshotHook = Callable[["AgentSession", str, str, str, Logger], None]


def uv_project_hook(command: str) -> str | None:
    """Reject uv commands that don't use --project in ephemeral terminals."""
    segments = re.split(r"\s*&&\s*|\s*;\s*", command)
    for segment in segments:
        seg = segment.strip()
        if seg.startswith("uv ") and not seg.startswith("uvx"):
            if re.match(r"uv\s+(venv|tool|init|sync)\b", seg):
                continue
            if "--project" not in seg:
                return (
                    "❌ REJECTED: 'uv' commands MUST use the --project flag in ephemeral terminals.\n"
                    "Example: cd path/to/package && uv --project . run script.py\n"
                    "Refusing to execute without --project."
                )
    return None
