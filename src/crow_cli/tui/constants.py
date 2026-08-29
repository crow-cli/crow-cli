"""
This module contains constants, which may be set in environment variables.
"""

from __future__ import annotations

import os
from typing import Final

get_environ = os.environ.get


def _get_environ_bool(name: str, default: bool = False) -> bool:
    """Check an environment variable switch.

    Args:
        name: Name of environment variable.

    Returns:
        `True` if the env var is "1", otherwise `False`.
    """
    has_environ = get_environ(name, "1" if default else "0") == "1"
    return has_environ


def _get_environ_int(
    name: str, default: int, minimum: int | None = None, maximum: int | None = None
) -> int:
    """Retrieves an integer environment variable.

    Args:
        name: Name of environment variable.
        default: The value to use if the value is not set, or set to something other
            than a valid integer.
        minimum: Optional minimum value.

    Returns:
        The integer associated with the environment variable if it's set to a valid int
            or the default value otherwise.
    """
    try:
        value = int(os.environ[name])
    except KeyError:
        return default
    except ValueError:
        return default
    if minimum is not None:
        return max(minimum, value)
    if maximum is not None:
        return min(maximum, value)
    return value


ACP_INITIALIZE: Final[bool] = _get_environ_bool("TOAD_ACP_INITIALIZE", True)
"""Initialize ACP agents?"""

DEBUG: Final[bool] = _get_environ_bool("DEBUG", False)
"""Debug flag."""
