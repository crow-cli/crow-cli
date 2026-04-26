"""Iterative refinement: worker agent + critic agent in a feedback loop.

Pattern:
    worker(task) -> compact -> critic(task, criteria, summary) -> XML response
    -> if task_complete: stop -> else: worker(feedback) -> repeat

CLI usage:
    uv --project . run iterative_refinement.py refine "Implement a task" \
        --criteria "Criterion 1" --criteria "Criterion 2" --max-iterations 3

Config file usage:
    uv --project . run iterative_refinement.py refine --config task.yaml
"""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
import typer
import yaml

from client import ReplClient

AGENT_CMD = "uv"
AGENT_ARGS = (
    "--project",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent",
    "run",
    "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/scratch_db.py",
)

COMPACT_PROMPT = (
    "Summarize the conversation in RESTful markdown format and the "
    "steps you have taken. This is an interagent summary/compaction "
    "event. Respond directly. Call no tools."
)

CRITIC_RESPONSE_FORMAT = (
    "You MUST respond with XML in this exact format:\n"
    "<critique>\n"
    "  <score>0.0-1.0</score>\n"
    "  <task_complete>COMPLETE or INCOMPLETE</task_complete>\n"
    "  <summary>Brief summary of what was done well and what needs improvement</summary>\n"
    "</critique>\n"
    "Do NOT add any other text. Just the XML."
)


@dataclass
class CritiqueResult:
    score: float = 0.0
    task_complete: bool = False
    summary: str = ""
    raw: str = ""


def parse_critique_response(text: str) -> CritiqueResult:
    """Parse the critic's XML response."""
    score_match = re.search(r"<score>([\d.]+)</score>", text)
    score = float(score_match.group(1)) if score_match else 0.0

    complete_match = re.search(r"<task_complete>([^<]+)</task_complete>", text)
    if complete_match:
        val = complete_match.group(1).strip().upper()
        task_complete = val in ("COMPLETE", "TRUE")
    else:
        task_complete = False

    summary_match = re.search(r"<summary>(.*?)</summary>", text, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else "(no summary)"

    return CritiqueResult(
        score=score,
        task_complete=task_complete,
        summary=summary,
        raw=text,
    )


app = typer.Typer(
    name="iterative-refinement",
    help="Run worker + critic agents in an iterative refinement loop.",
)


def last_compacted(client: ReplClient) -> str:
    """Get the last assistant message from the client's conversation."""
    conversation = client.conversation.get(client.session_id, [])
    for msg in reversed(conversation):
        if msg["role"] == "assistant":
            return msg["content"]
    return "(no response)"


async def iterative_refine(
    task: str,
    criteria: list[str],
    *,
    max_iterations: int = 5,
    console: Console | None = None,
    cwd: str | Path | None = None,
) -> str:
    """Run worker and critic agents in a refinement loop.

    The critic always speaks last. It returns XML with score + task_complete.
    If task_complete is COMPLETE, the loop ends early.

    Args:
        task: What the worker should implement or produce.
        criteria: List of strings the critic evaluates the worker against.
        max_iterations: Maximum worker+critic cycles.
        console: Optional rich console for output.
        cwd: Working directory for the spawned agents.

    Returns:
        Consolidated summary of all iterations.
    """
    console = console or Console()
    criteria_block = "\n".join(f"- {c}" for c in criteria)

    worker = ReplClient(AGENT_CMD, *AGENT_ARGS, console=console, cwd=cwd)
    critic = ReplClient(AGENT_CMD, *AGENT_ARGS, console=console, cwd=cwd)

    iteration_summaries: list[dict] = []

    try:
        # --- initial pass: worker does work ---
        console.print(
            Panel(f"[bold cyan]Task:[/bold cyan] {task}", border_style="cyan")
        )
        console.print()
        await worker.send(f"You must implement: {task}")
        await worker.send(COMPACT_PROMPT)
        worker_summary = last_compacted(worker)

        for iteration in range(1, max_iterations + 1):
            console.print(
                Panel(
                    f"[bold yellow]Iteration {iteration}/{max_iterations}[/bold yellow]",
                    border_style="yellow",
                )
            )

            # --- critic evaluates ---
            console.print("[bold red]Critic evaluating...[/bold red]")
            await critic.send(
                f"You must evaluate the agent's performance.\n\n"
                f"Task: {task}\n"
                f"Criteria to evaluate against:\n{criteria_block}\n"
                f"Here is a summary of what it did:\n{worker_summary}\n\n"
                f"{CRITIC_RESPONSE_FORMAT}"
            )
            critique_text = last_compacted(critic)
            critique = parse_critique_response(critique_text)

            console.print(
                Panel(
                    f"**Score:** {critique.score}\n"
                    f"**Status:** {'COMPLETE' if critique.task_complete else 'INCOMPLETE'}\n\n"
                    f"{critique.summary}",
                    title="[red]Critique[/red]",
                    border_style="red",
                )
            )
            console.print()

            iteration_summaries.append(
                {
                    "iteration": iteration,
                    "worker_summary": worker_summary,
                    "critique": critique,
                }
            )

            if critique.task_complete:
                console.print("[green]Task marked complete — stopping.[/green]")
                break

            # --- feed back to worker for next iteration ---
            console.print("[bold purple]Worker refining...[/bold purple]")
            await worker.send(
                f"Here is feedback on your work:\n{critique.summary}\n"
                f"Please improve your work based on the suggestions given."
            )
            await worker.send(COMPACT_PROMPT)
            worker_summary = last_compacted(worker)

        # --- final consolidated summary ---
        final_summary = build_consolidated_summary(
            task, criteria, iteration_summaries
        )

        return final_summary

    finally:
        await worker.close()
        await critic.close()


def build_consolidated_summary(
    task: str,
    criteria: list[str],
    iteration_summaries: list[dict],
) -> str:
    """Build a consolidated summary of all iterations."""
    lines = [f"# Iterative Refinement Report\n\n", f"**Task:** {task}\n\n", "**Criteria:**\n"]
    for c in criteria:
        lines.append(f"- {c}\n")

    lines.append(f"\n**Iterations completed:** {len(iteration_summaries)}\n")

    last_critique = iteration_summaries[-1]["critique"] if iteration_summaries else None

    lines.append(f"\n## Final Result\n\n")
    if last_critique:
        lines.append(f"- **Score:** {last_critique.score}\n")
        lines.append(f"- **Status:** {'COMPLETE' if last_critique.task_complete else 'INCOMPLETE'}\n")
        lines.append(f"- **Summary:** {last_critique.summary}\n")

    lines.append(f"\n## Iteration Details\n")
    for s in iteration_summaries:
        lines.append(f"\n### Iteration {s['iteration']}\n")
        lines.append(f"**Worker:** {s['worker_summary']}\n\n")
        lines.append(f"**Critic (score={s['critique'].score}):** {s['critique'].summary}\n")

    return "".join(lines)


@app.command()
def refine(
    task: str | None = typer.Argument(
        None, help="Task description for the worker agent to implement."
    ),
    criteria: list[str] = typer.Option(
        [],
        "--criteria",
        "-c",
        help="Evaluation criteria (can be specified multiple times).",
    ),
    max_iterations: int = typer.Option(
        None, "--max-iterations", "-n", help="Maximum refinement iterations."
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-f",
        help="YAML config file with task, criteria, and max_iterations.",
    ),
) -> None:
    """Run iterative refinement with worker + critic agents.

    Provide arguments directly or via a YAML config file:

        task: "Implement a task"
        criteria:
          - "Criterion 1"
          - "Criterion 2"
        max_iterations: 3
    """
    if config:
        with open(config) as fh:
            cfg = yaml.safe_load(fh) or {}
        task = cfg.get("task", task)
        criteria = cfg.get("criteria", criteria)
        max_iterations = cfg.get("max_iterations", max_iterations)

    if not task:
        typer.echo("Error: TASK argument or 'task' key in config is required.", err=True)
        raise typer.Exit(1)
    if not criteria:
        typer.echo(
            "Error: At least one --criteria or 'criteria' key in config is required.",
            err=True,
        )
        raise typer.Exit(1)

    asyncio.run(
        iterative_refine(task, criteria, max_iterations=max_iterations or 5)
    )


@app.callback()
def global_callback():
    """Iterative refinement CLI - multi-agent feedback loop."""
    pass


def main():
    app()


if __name__ == "__main__":
    main()
