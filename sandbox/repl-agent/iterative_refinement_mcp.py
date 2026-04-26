"""FastMCP wrapper over iterative refinement.

Run:
    cd /home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent
    uv --project . run iterative_refinement_mcp.py
"""

from pathlib import Path
from rich.console import Console

from fastmcp import FastMCP

from iterative_refinement import iterative_refine

mcp = FastMCP(
    name="iterative-refinement",
    instructions="Run iterative refinement with worker + critic agents in a feedback loop.",
)


@mcp.tool()
async def refine(
    task: str,
    criteria: list[str],
    max_iterations: int = 5,
    cwd: str | None = None,
) -> str:
    """Run iterative refinement: worker agent + critic agent in a feedback loop.

    The critic always speaks last. It returns XML with score + task_complete.
    If task_complete is COMPLETE, the loop ends early.

    Args:
        task: What the worker should implement or produce.
        criteria: List of strings the critic evaluates the worker against.
        max_iterations: Maximum worker+critic cycles.
        cwd: Working directory for the spawned agents (defaults to current).

    Returns:
        Consolidated markdown summary of all iterations.
    """
    console = Console(force_terminal=True, width=120)
    result = await iterative_refine(
        task, criteria, max_iterations=max_iterations, console=console, cwd=cwd
    )
    return result


def main():
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
