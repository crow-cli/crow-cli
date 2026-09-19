"""``execute`` — a persistent IPython kernel, presented as an ACP v2 terminal.

The tool the agent actually lives in. A spawned crow agent is handed
``execute`` and nothing else; its file, web, memory, vision and delegation
work happens through subtools ambient in the kernel. So this is not one tool
among many, it is the surface.

What changed from ``mcp/execute`` is the output contract, and it changed
because ACP v2 gave terminals to the agent. v1 returned a string and that was
the end of it — the client rendered the same text the model read. v2 splits
the audience in two, which means splitting the payload in two:

``raw_bytes_b64``
    Every byte the cell wrote, ANSI intact. The agent lifts this out and turns
    it into ``TerminalUpdate.output`` (snapshot) or has already streamed it as
    ``terminal_output_chunk`` (live). It never reaches the model.

``output``
    The same bytes ANSI-stripped and capped. This is what the model reads, and
    what lands in ``ToolCallUpdate.raw_output``.

Live streaming rides MCP progress notifications: each iopub chunk is base64'd
into the notification's ``message`` field as it arrives, and the agent relays
it as a ``terminal_output_chunk``. This is the same mechanism crow-mcp's Rust
terminal tool used — ``ProgressNotificationParam.message`` as the data channel
— and the same one its renderer was written against. A caller that sent no
``progressToken`` simply gets no notifications; the snapshot in the result
covers it either way, and a client that DID watch the bytes arrive is the one
that knows not to render the snapshot again.

The kernel work runs in a thread. v1 called the blocking ZMQ drain directly
inside an ``async def`` tool, which froze the MCP server's event loop for the
whole cell — every other session's tool call queued behind it. Here the loop
stays live, which is also what makes relaying progress possible at all.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import os
import sys
from logging import getLogger
from typing import Optional

from fastmcp import Context

from crow_cli.mcp2.server import mcp
from crow_cli.tools import PRELUDE_V2

from .kernel import CrowKernel

logger = getLogger(__name__)

# Kernels keyed by ACP session id: one persistent REPL per session. A bare
# caller (no _meta) is keyed by cwd instead.
_kernels: dict[str, CrowKernel] = {}


def _kernel_context(
    ctx: Context,
) -> tuple[
    str, str, Optional[str], Optional[str], Optional[str], Optional[str], str, int
]:
    """Return ``(key, cwd, session_id, parent_tcid, db_uri, images_dir,
    redis_url, rlm_depth)`` from the caller-injected ``_meta``.

    The agent injects these so the kernel is keyed per session and starts in
    the session's working directory. The Context parameter is filtered out of
    the LLM-facing schema, so the model never sees — and cannot forge — any of
    it. No meta means a bare caller: key and cwd fall back to the server
    process's cwd.

    ``parent_tcid`` (the execute call's own ACP tool-call id) and ``db_uri``
    feed the per-cell begin_cell prologue: they stamp subtool register entries
    and point the write-through sink at crow.db so the server-side drain can
    re-emit in-cell tool calls to the ACP client. ``images_dir`` points the
    kernel's image sink at the session's ImageStore directory so vision bytes
    land where the drain hydrates them. ``redis_url`` is the wake bus an
    in-cell task publishes on after it commits a delivery, so the owner wakes
    now instead of at its next backstop poll; "" is the bus being off.
    ``rlm_depth`` is how many delegations deep the calling session is, so an
    in-cell rlm can enforce its budget.
    """
    meta = ctx.request_context.meta if ctx.request_context else None
    cwd = getattr(meta, "cwd", None) or os.getcwd()
    session_id = getattr(meta, "session_id", None)
    parent_tcid = getattr(meta, "tool_call_id", None)
    db_uri = getattr(meta, "db_uri", None)
    images_dir = getattr(meta, "images_dir", None)
    bus = getattr(meta, "redis_url", None)
    depth = getattr(meta, "rlm_depth", None)
    return (
        session_id or cwd,
        cwd,
        session_id,
        parent_tcid,
        db_uri,
        images_dir,
        bus or "",
        depth if isinstance(depth, int) and depth > 0 else 0,
    )


def _progress_token(ctx: Context) -> Optional[object]:
    """The caller's progressToken, or None if it did not send one.

    No token means no live stream is possible, so there is no point encoding
    chunks nobody will receive — the snapshot in the result covers that caller.
    """
    meta = ctx.request_context.meta if ctx.request_context else None
    return getattr(meta, "progressToken", None) if meta is not None else None


def _prologue(
    session_id: Optional[str],
    parent_tcid: Optional[str],
    db_uri: Optional[str],
    images_dir: Optional[str],
    redis_url: str = "",
    rlm_depth: int = 0,
) -> str:
    """Identity injection prepended to every non-empty cell: stamps the
    subtool register before the model's code runs. Fail-open — a broken
    prologue warns on stderr and the cell still runs; the tools work without
    identity (entries record None)."""
    return (
        "try:\n"
        "    from crow_cli.tools.register import begin_cell as _crow_begin\n"
        f"    _crow_begin(session_id={session_id!r},"
        f" parent_tool_call_id={parent_tcid!r}, db_uri={db_uri!r},"
        f" images_dir={images_dir!r}, redis_url={redis_url!r},"
        f" rlm_depth={rlm_depth!r})\n"
        "except Exception as _crow_e:\n"
        "    import sys as _crow_sys\n"
        "    print(f'crow prologue: {_crow_e}', file=_crow_sys.stderr)\n"
    )


def get_kernel(key: str, cwd: str) -> CrowKernel:
    """Get or lazily start the persistent kernel for a key."""
    kernel = _kernels.get(key)
    if kernel is None:
        logger.info("Starting new IPython kernel for %s in %s", key, cwd)
        kernel = CrowKernel(python_path=sys.executable, cwd=cwd)
        _run_prelude(kernel)
        _kernels[key] = kernel
    return kernel


def _run_prelude(kernel: CrowKernel) -> None:
    """Zero-day imports: every fresh kernel (start AND reset both come through
    get_kernel) comes up with crow_cli.tools ambient. Best effort — a broken
    prelude logs, it never bricks the kernel."""
    try:
        result = kernel.execute(PRELUDE_V2)
        if result.text.strip():
            logger.warning("Kernel prelude produced output: %s", result.text[:200])
    except Exception:
        logger.warning("Kernel prelude failed", exc_info=True)


def shutdown_all() -> None:
    """Shut down every live kernel (test cleanup / server teardown)."""
    for key in list(_kernels):
        kernel = _kernels.pop(key, None)
        if kernel:
            kernel.shutdown()


@mcp.tool
async def execute(
    ctx: Context,
    code: str,
    reset: bool = False,
    timeout: float | None = 30.0,
) -> str:
    """Execute one cell in this session's persistent IPython kernel.

    This is a Jupyter-style REPL, not a fresh Python process per call. Every
    non-reset call runs in the same kernel for this session, so variables,
    imports, function definitions, open handles, and the working directory
    survive from one call to the next. Write multi-step work as successive
    cells and reuse names already defined. Do not re-import or redefine setup
    merely because this is a new tool call; inspect ``dir()`` if unsure what
    the kernel already contains. The kernel is isolated per session id, so
    state does not leak between sessions.

    A fresh kernel starts with Crow's async helpers (``fs``, ``memory``,
    ``rlm``, ``vision``, ``web``, ``write``, ``edit``, and ``reload``) already
    available. They are async: call them with ``await``. ``reload()`` refreshes
    Crow's tool modules in the current kernel without clearing your variables,
    imports, or cwd. Use ``reset=True`` only when you intentionally want a
    completely new kernel; it discards all state and starts the prelude again.

    It runs with crow-cli's own Python interpreter, so crow's libraries are
    available and you can interrogate crow.db. Use it for multi-step Python
    work where you want to build on previous results.

    Args:
        code: Python code to execute. print() is how the code talks back: the
              returned output is everything the cell wrote, or its traceback
              on error. The last expression's value is NOT returned (no REPL
              Out[n]) — assign it, print it, or use it.
        reset: If True, shut down the kernel and start a fresh one, clearing
               all state (variables, imports). Use if the kernel is in a bad
               state. With empty code, just resets. Cannot clear a single
               variable — reset clears everything.
        timeout: seconds to wait for the cell to finish (default 30). The cell
               is NOT killed on timeout — IPython keeps running it — so a
               long-running process returns a "(kernel busy: …)" notice and
               its output stays collectable on a later call. Pass a larger
               value, or None to wait indefinitely, for a cell you know runs
               long: a blocking rlm() delegation (slow on a local model), a
               build, a big query, a sleep.

    Returns:
        A JSON object: ``exit_code``, ``output`` (ANSI-stripped text),
        ``timed_out``, and ``raw_bytes_b64`` (the same output with ANSI
        intact, for the client to render). The agent lifts ``raw_bytes_b64``
        into the ACP Terminal schema and strips it before the model sees the
        result. Vision tools running inside the cell have hydrated image
        blocks prepended by the server — the one and only addition to
        execute's output.

    Examples:
        execute("x = 42")                 # set a variable (no output)
        execute("print(x * 2)")           # -> "84"
        execute("import sqlalchemy; print(sqlalchemy.__version__)")
        execute("", reset=True)           # fresh kernel, all state cleared
    """
    try:
        (
            key,
            cwd,
            session_id,
            parent_tcid,
            db_uri,
            images_dir,
            redis_url,
            rlm_depth,
        ) = _kernel_context(ctx)

        if reset:
            old = _kernels.pop(key, None)
            if old:
                old.shutdown()
                logger.info("Reset kernel for %s", key)
            if not code.strip():
                return json.dumps(
                    {
                        "exit_code": 0,
                        "output": "Kernel reset successfully. All previous state lost.",
                        "timed_out": False,
                        "raw_bytes_b64": "",
                    }
                )

        kernel = get_kernel(key, cwd)
        if code.strip():
            code = (
                _prologue(
                    session_id, parent_tcid, db_uri, images_dir, redis_url, rlm_depth
                )
                + code
            )

        result = await _execute_streaming(ctx, kernel, code, timeout)
        # The same shape crow-mcp's Rust terminal tool returns, because the
        # agent-side lift and the client-side dedupe are both written against
        # it: exit_code / output / timed_out / raw_bytes_b64.
        #
        # raw_bytes_b64 is ALWAYS present, even when every byte already went
        # out live as a progress notification. That is not redundancy, it is
        # the split of responsibility: the server does not know who is
        # listening (a second client may attach mid-cell, a resume replays
        # from the snapshot), so it always ships the whole buffer, and the
        # client — which does know whether it watched the chunks arrive —
        # decides not to render it twice.
        return json.dumps(
            {
                "exit_code": result.exit_code,
                "output": result.text or "[no output]",
                "timed_out": result.status == "busy",
                "raw_bytes_b64": base64.b64encode(result.raw).decode("ascii"),
            },
            ensure_ascii=False,
        )

    except Exception as exc:
        logger.error("Execute error: %s", exc, exc_info=True)
        # An empty str(exc) — queue.Empty from a timed-out get_shell_msg, the
        # bare "Error:" that read as "broken" — names its type instead, so the
        # failure is never invisible.
        detail = str(exc).strip() or type(exc).__name__
        return json.dumps(
            {
                "exit_code": 1,
                "output": f"Error: {detail}",
                "timed_out": False,
                "raw_bytes_b64": "",
            },
            ensure_ascii=False,
        )


async def _execute_streaming(
    ctx: Context, kernel: CrowKernel, code: str, timeout: Optional[float]
):
    """Run the cell off-loop, relaying each chunk as an MCP progress note.

    The kernel drain is blocking ZMQ, so it runs in a thread and the loop
    stays live — which is the only reason relaying is possible at all. Chunks
    are marshalled back with ``run_coroutine_threadsafe``, which preserves
    submission order, and the queued notifications are awaited before the
    result returns so a client never sees the completion before the bytes.
    """
    token = _progress_token(ctx)
    if token is None:
        return await asyncio.to_thread(kernel.execute, code, timeout)

    loop = asyncio.get_running_loop()
    sent: list[concurrent.futures.Future] = []
    counter = [0]

    def on_output(chunk: bytes) -> None:
        counter[0] += 1
        sent.append(
            asyncio.run_coroutine_threadsafe(
                ctx.report_progress(
                    float(counter[0]),
                    None,
                    base64.b64encode(chunk).decode("ascii"),
                ),
                loop,
            )
        )

    try:
        return await asyncio.to_thread(kernel.execute, code, timeout, on_output)
    finally:
        if sent:
            # run_coroutine_threadsafe hands back a *concurrent* Future;
            # wrap it so gather can await it on this loop.
            await asyncio.gather(
                *(asyncio.wrap_future(f) for f in sent), return_exceptions=True
            )
