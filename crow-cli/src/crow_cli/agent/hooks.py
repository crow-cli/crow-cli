"""
Command hooks for terminal execution.

Each hook takes a command string and returns None (allow) or a rejection message.
Hooks are passed to AcpAgent at construction time — no global registry.
"""

import re
from typing import Callable

CommandHook = Callable[[str], str | None]


def uv_project_hook(command: str) -> str | None:
    """Reject uv commands that don't use --project in ephemeral terminals."""
    segments = re.split(r"\s*&&\s*|\s*;\s*", command)
    for segment in segments:
        seg = segment.strip()
        if seg.startswith("uv ") and not seg.startswith("uvx"):
            if re.match(r"uv\s+(venv|tool)\b", seg):
                continue
            if "--project" not in seg:
                return (
                    "❌ REJECTED: 'uv' commands MUST use the --project flag in ephemeral terminals.\n"
                    "Example: cd path/to/package && uv --project . run script.py\n"
                    "Refusing to execute without --project."
                )
    return None
