"""The in-kernel subtool register — identity and emission bookkeeping.

Raw tool functions have zero ambient context: they are just Python. Identity
arrives per cell: the execute tool injects a prologue calling
:func:`begin_cell` with the session id and the PARENT tool-call-id (the
execute call's own ACP-mapped id) before the model's code runs. The model
never sees and cannot forge either value — the same rail as the ``_meta``
injection at the MCP boundary (``crow_cli.agent.tools.execute_acp_execute``).

The :func:`subtool` decorator records one :class:`SubtoolEntry` per call —
args, status, the result's ACP payload and LLM image refs — then returns the
Python result untouched (or re-raises, after recording the failure; a cell
that died halfway still made real edits, and the client deserves to see
them). Entries are JSON-native so the server-side drain can emit ACP tool
calls, hydrate image_urls for the LLM, and write through to the
subtool_calls table keyed by parent_tool_call_id.

Identity is stamped at CALL time via a contextvar — async tasks spawned
inside the cell inherit it, so background work never bleeds into the next
cell's drain. Outside execute (plain scripts, tests) no cell context exists
and entries record None identity: the tools stay usable as ordinary Python.
"""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from functools import wraps
from typing import Any

from .results import ToolResult


@dataclass
class CellContext:
    session_id: str | None = None
    parent_tool_call_id: str | None = None
    cell_seq: int | None = None
    agent_id: str | None = None


_current_cell: ContextVar[CellContext | None] = ContextVar(
    "crow_current_cell", default=None
)


def begin_cell(
    session_id: str | None = None,
    parent_tool_call_id: str | None = None,
    cell_seq: int | None = None,
    agent_id: str | None = None,
) -> None:
    """Set the identity for the cell about to run (execute's prologue)."""
    _current_cell.set(
        CellContext(session_id, parent_tool_call_id, cell_seq, agent_id)
    )


def current_cell() -> CellContext | None:
    return _current_cell.get()


@dataclass
class SubtoolEntry:
    tool: str
    mode: str | None
    args: dict[str, Any]
    status: str  # completed | failed
    result_kind: str  # diff | image | text | error
    acp_payload: dict[str, Any] | None
    llm_images: list[dict[str, Any]]  # ImageStore refs: {"key", "mime"}
    error: str | None
    session_id: str | None
    parent_tool_call_id: str | None
    cell_seq: int | None
    agent_id: str | None
    started_at: float
    ended_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_entries: list[SubtoolEntry] = []


def record(entry: SubtoolEntry) -> None:
    _entries.append(entry)
    # Write-through to the subtool_calls table joins here, so records
    # survive a wedged kernel — the table is the queue.


def pending(cell_seq: int | None = None) -> list[SubtoolEntry]:
    if cell_seq is None:
        return list(_entries)
    return [e for e in _entries if e.cell_seq == cell_seq]


def drain(cell_seq: int | None = None) -> list[SubtoolEntry]:
    """Remove and return recorded entries (the server drains after each cell)."""
    global _entries
    out = pending(cell_seq)
    if cell_seq is None:
        _entries = []
    else:
        _entries = [e for e in _entries if e.cell_seq != cell_seq]
    return out


def clear() -> None:
    """Test hygiene."""
    _entries.clear()


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _bind_args(fn: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
    try:
        bound = inspect.signature(fn).bind(*args, **kwargs)
    except TypeError:
        return {
            "args": [_json_safe(a) for a in args],
            "kwargs": {k: _json_safe(v) for k, v in kwargs.items()},
        }
    bound.apply_defaults()
    return {k: _json_safe(v) for k, v in bound.arguments.items()}


def subtool(tool: str, mode: str | None = None):
    """Mark an async tool function for register recording.

    The function's contract stays pure Python — raise on failure, return a
    result object. The decorator adds the other two channels: it snapshots
    args + cell identity, derives the ACP payload and LLM image refs from
    the ToolResult protocol, and records completed/failed entries around
    the call.
    """

    def decorator(fn: Callable[..., Awaitable[Any]]):
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"@subtool requires an async function, got {fn!r}")

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            ctx = current_cell() or CellContext()
            call_args = _bind_args(fn, args, kwargs)
            started = time.time()
            try:
                result = await fn(*args, **kwargs)
            except Exception as exc:
                record(
                    SubtoolEntry(
                        tool=tool,
                        mode=mode,
                        args=call_args,
                        status="failed",
                        result_kind="error",
                        acp_payload=None,
                        llm_images=[],
                        error=f"{type(exc).__name__}: {exc}",
                        session_id=ctx.session_id,
                        parent_tool_call_id=ctx.parent_tool_call_id,
                        cell_seq=ctx.cell_seq,
                        agent_id=ctx.agent_id,
                        started_at=started,
                        ended_at=time.time(),
                    )
                )
                raise
            payload = None
            images: list[dict[str, Any]] = []
            kind = "text"
            if isinstance(result, ToolResult):
                payload = result.acp_payload()
                images = result.llm_images()
                kind = result.result_kind
            record(
                SubtoolEntry(
                    tool=tool,
                    mode=mode,
                    args=call_args,
                    status="completed",
                    result_kind=kind,
                    acp_payload=payload,
                    llm_images=images,
                    error=None,
                    session_id=ctx.session_id,
                    parent_tool_call_id=ctx.parent_tool_call_id,
                    cell_seq=ctx.cell_seq,
                    agent_id=ctx.agent_id,
                    started_at=started,
                    ended_at=time.time(),
                )
            )
            return result

        return wrapper

    return decorator
