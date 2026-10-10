"""The caller-injected ``_meta`` channel, read defensively.

A crow MCP tool that needs to know WHO is calling — which session, which
tool-call id, where crow.db lives, where images go — reads it off the request's
``_meta``, which the agent fills in and the model never sees. That value's
shape belongs to the SDK, not to us, and it changed under us:

* mcp 1.x / fastmcp 3.x — ``RequestParams.Meta``, a pydantic model with extra
  keys allowed: attribute access.
* mcp 2.x / fastmcp 4.x — ``RequestParamsMeta``, a TypedDict: a plain dict at
  runtime, where ``getattr(meta, "session_id", None)`` is None for every key.

Silently None is the whole danger. An unread rail raises nothing; it just hands
``begin_cell`` no identity, so memory, rlm, vision, task and goal refuse at
call time while ``execute`` keeps running cells as if nothing were wrong — and
kernels stop being keyed per session and start being keyed per cwd, which
quietly puts every session in a directory into ONE kernel. Read through
:func:`meta_get`, which takes either shape, and let the servers say so out loud
when :func:`rail_unread` fires.
"""

from collections.abc import Mapping
from typing import Any


def meta_get(meta: Any, key: str, default: Any = None) -> Any:
    """One value out of a request's ``_meta``, dict-shaped or model-shaped.

    ``meta`` is whatever ``ctx.request_context.meta`` handed back, including
    None for a bare caller that sent no rail at all — which is a legitimate
    call, not an error, and gets ``default``.
    """
    if meta is None:
        return default
    if isinstance(meta, Mapping):
        return meta.get(key, default)
    return getattr(meta, key, default)


def rail_unread(meta: Any, session_id: Any) -> bool:
    """True when a caller SENT a rail and we could not read it.

    The session id is the one key every crow caller injects, so a non-empty
    ``_meta`` that yields no session id means the channel changed shape again.
    An absent ``_meta`` is a bare caller and stays quiet: tests and direct MCP
    clients are supposed to be able to call these tools with no identity.
    """
    return bool(meta) and session_id is None
