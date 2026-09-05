"""Execute MCP tool — a persistent IPython kernel (REPL) per session.

Complements the terminal tool: ``terminal`` runs fresh bash shells, this runs
Python in a persistent kernel where state (variables, imports, cwd) survives
across calls. The kernel is a subprocess launched with crow-cli's own
interpreter, so crow's libraries are available and code can interrogate
crow.db. One kernel per ACP session, keyed by the session id riding the call's
``_meta``.
"""

import os
import sys
from logging import getLogger

from fastmcp import Context

from crow_cli.mcp.server.app import mcp

from .kernel import CrowKernel

logger = getLogger(__name__)

# Kernels keyed by ACP session id: one persistent REPL per session. A bare
# caller (no _meta) is keyed by cwd instead.
_kernels: dict[str, CrowKernel] = {}


def _kernel_context(ctx: Context) -> tuple[str, str]:
    """Return ``(key, cwd)`` from the caller-injected ``_meta``.

    The agent injects these (``execute_acp_execute``) so the kernel is keyed
    per session and starts in the session's working directory. The Context
    parameter is filtered out of the LLM-facing schema, so the model never
    sees — and cannot forge — either value. No meta means a bare caller: key
    and cwd fall back to the server process's cwd.
    """
    meta = ctx.request_context.meta if ctx.request_context else None
    cwd = getattr(meta, "cwd", None) or os.getcwd()
    session_id = getattr(meta, "session_id", None)
    return (session_id or cwd, cwd)


def get_kernel(key: str, cwd: str) -> CrowKernel:
    """Get or lazily start the persistent kernel for a key."""
    kernel = _kernels.get(key)
    if kernel is None:
        logger.info(f"Starting new IPython kernel for {key} in {cwd}")
        kernel = CrowKernel(python_path=sys.executable, cwd=cwd)
        _run_prelude(kernel)
        _kernels[key] = kernel
    return kernel


def _run_prelude(kernel: CrowKernel) -> None:
    """Zero-day imports: every fresh kernel (start AND reset both come
    through get_kernel) comes up with crow_cli.tools ambient. Best effort —
    a broken prelude logs, it never bricks the kernel."""
    from crow_cli.tools import PRELUDE

    try:
        output = kernel.execute(PRELUDE)
        if output.strip():
            logger.warning(f"Kernel prelude produced output: {output[:200]}")
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
) -> str:
    """Execute Python code in a persistent IPython kernel (a REPL).

    Unlike the terminal tool (a fresh bash shell each call), this kernel keeps
    state across calls: variables, imports, and the working directory persist.
    It runs with crow-cli's own Python interpreter, so crow's libraries are
    available and you can interrogate crow.db. Use it for multi-step Python
    work where you want to build on previous results. For bash/shell commands,
    use the terminal tool instead.

    Args:
        code: Python code to execute. The last expression's value is returned
              (like a REPL's Out[n]). print() output, warnings, and tracebacks
              are captured.
        reset: If True, shut down the kernel and start a fresh one, clearing
               all state (variables, imports). Use if the kernel is in a bad
               state. With empty code, just resets. Cannot clear a single
               variable — reset clears everything.

    Returns:
        REPL-style output: stdout, stderr, and the last expression's value, or
        an ANSI-stripped traceback on error.

    Examples:
        execute("x = 42")                 # set a variable
        execute("x * 2")                  # -> "84" (state persisted)
        execute("import sqlalchemy; sqlalchemy.__version__")
        execute("", reset=True)           # fresh kernel, all state cleared
    """
    try:
        key, cwd = _kernel_context(ctx)

        if reset:
            old = _kernels.pop(key, None)
            if old:
                old.shutdown()
                logger.info(f"Reset kernel for {key}")
            if not code.strip():
                return "Kernel reset successfully. All previous state lost."

        kernel = get_kernel(key, cwd)
        output = kernel.execute(code)
        return output if output else "[no output]"

    except Exception as e:
        logger.error(f"Execute error: {e}", exc_info=True)
        return f"Error: {e}"
