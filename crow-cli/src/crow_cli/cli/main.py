import asyncio
import contextlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from crow_cli.agent.configure import Config
from crow_cli.agent.db import Agent as AgentModel
from crow_cli.agent.db import Message
from crow_cli.agent.main import main as agent_main
from crow_cli.agent.session import AgentSession
from crow_cli.cli.init_cmd import init_command
from crow_cli.cli.install import app as install_app
from crow_cli.client.main import CrowClient, connect_client
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SQLAlchemySession

app = typer.Typer(
    name="crow-cli",
    help=(
        "Transparent CLI for the Crow agent — full observability into agent state.\n\n"
        "Talk to an agent with `crow-cli run \"prompt\"` and continue a session with "
        "`-s <session-id>`. This is also how agents delegate to subagents: launch a "
        "worker with `run`, then read its thoughts via the query_memory MCP tool. "
        "See `crow-cli run --help` for the full delegation recipe."
    ),
)

# Register command groups
app.add_typer(install_app, name="install")


console = Console()
# we need to work on a crow-cli init command to set up configuration
# until then...
client = CrowClient(console=console)

# Tool kind -> icon mapping
TOOL_ICONS = {
    "read": "📖",
    "edit": "✏️",
    "write": "📝",
    "delete": "🗑️",
    "move": "📦",
    "search": "🔍",
    "fetch": "🌐",
    "execute": "⚡",
    "other": "🔧",
}

# Status -> indicator mapping
STATUS_ICONS = {
    "pending": "⏳",
    "in_progress": "🔄",
    "completed": "✅",
    "failed": "❌",
}


# ===========================================================================
# ACP Agent
@app.command("acp")
def run_agentmain(
    config_dir: Path = typer.Option(
        None,
        "--config-dir",
        "-d",
        help="Configuration directory (default: ~/.crow)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable chunk-level JSONL logging for debugging",
    ),
    system_prompt_path: Path = typer.Option(
        None,
        "--system-prompt-path",
        "-p",
        help="Path to a Jinja2 system prompt template file",
    ),
    config_file: Path = typer.Option(
        None,
        "--config-file",
        "-o",
        help="YAML file with config values to override",
    ),
):
    """Main entry point for the crow-cli agent."""
    if config_dir is None:
        config_dir = Path.home() / ".crow"

    config = Config.load(config_dir=config_dir)

    if config_file and config_file.exists():
        with open(config_file) as f:
            overrides = yaml.safe_load(f) or {}
        if "system_prompt_path" in overrides:
            config.system_prompt_path = Path(overrides["system_prompt_path"])
        if "db_uri" in overrides:
            config.db_uri = overrides["db_uri"]
        if "max_retries_per_step" in overrides:
            config.max_retries_per_step = int(overrides["max_retries_per_step"])
        if "MAX_COMPACT_TOKENS" in overrides:
            config.MAX_COMPACT_TOKENS = int(overrides["MAX_COMPACT_TOKENS"])
        if "MAX_TOKENS" in overrides:
            config.MAX_TOKENS = int(overrides["MAX_TOKENS"])
        if "chunk_log" in overrides:
            config.chunk_log = bool(overrides["chunk_log"])
        if "mcpServers" in overrides:
            config.mcp_servers = overrides["mcpServers"]

    if system_prompt_path:
        config.system_prompt_path = system_prompt_path

    if debug:
        config.chunk_log = True

    agent_main(config=config)


@app.command("init")
def run_init(
    config_dir: Path = typer.Option(
        None,
        "--config-dir",
        "-d",
        help="Configuration directory (default: ~/.crow)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip all confirmation prompts",
    ),
):
    """Initialize Crow configuration interactively."""
    if config_dir is None:
        config_dir = Path.home() / ".crow"
    init_command(config_dir=config_dir, yes=yes)


@app.command("auth")
def run_auth():
    """
    Declare authentication support for ACP Registry compliance.

    This agent supports authentication and is registered in the ACP Registry.
    No actual authentication is required for FOSS deployments.
    """
    console.print(
        Panel(
            "[green]✓ Authentication Support Declared[/green]\n\n"
            "This agent declares authentication support for ACP Registry compliance.\n"
            "No actual authentication is required for FOSS deployments.\n\n"
            "[dim]Agent is ready for use.[/dim]",
            title="[magenta]🪶 Crow[/magenta]",
            border_style="green",
        )
    )


# ============================================================================
# Database Inspection
# ============================================================================


@app.command("inspect")
def inspect_db(
    session_id: str | None = typer.Option(
        None, "--session", "-s", help="Session ID to inspect"
    ),
    messages: bool = typer.Option(False, "--messages", "-m", help="Show messages"),
    limit: int = typer.Option(20, "--limit", "-l", help="Limit number of rows"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    config_dir: Path = typer.Option(
        None,
        "--config-dir",
        "-d",
        help="Configuration directory (default: ~/.crow)",
    ),
):
    """Inspect the Crow database - see session state, messages, etc."""
    if config_dir is None:
        config_dir = Path.home() / ".crow"
    db_uri = f"sqlite:///{config_dir / 'crow.db'}"
    db_path = str(config_dir / "crow.db")

    if not os.path.exists(db_path):
        if json_output:
            print(json.dumps({"error": f"Database not found at {db_path}"}))
        else:
            client._console.print(f"[red]Database not found at {db_path}[/red]")
        raise SystemExit(1)

    if session_id:
        # Use existing AgentSession methods to get the latest agent for this session
        max_idx = AgentSession.get_max_agent_idx(session_id, db_uri=db_uri)
        if max_idx < 0:
            if json_output:
                print(json.dumps({"error": f"Session '{session_id}' not found"}))
            else:
                client._console.print(f"[red]Session '{session_id}' not found[/red]")
            raise SystemExit(1)

        agent_id = f"{session_id}-{max_idx}"
        session_obj = AgentSession.load(agent_id, db_uri=db_uri)

        session_data = {
            "agent_id": session_obj.agent_id,
            "session_id": session_obj.session_id,
            "cwd": session_obj.cwd,
            "model_identifier": session_obj.model_identifier,
            "agent_idx": session_obj.agent_idx,
        }

        msgs_data = []
        if messages:
            for msg in session_obj.messages[:limit]:
                msgs_data.append({"role": msg["role"], "data": msg})

        if json_output:
            output = {"session": session_data}
            if messages:
                output["messages"] = msgs_data
            print(json.dumps(output, indent=2, default=str))
        else:
            table = Table(title=f"Session: {session_id}", show_header=False)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")
            for key, val in session_data.items():
                table.add_row(key, str(val))
            client._console.print(table)

            if messages:
                msg_table = Table(title=f"Messages ({len(msgs_data)} shown)")
                msg_table.add_column("ID", style="dim")
                msg_table.add_column("Role", style="cyan")
                msg_table.add_column("Content Preview", style="white")
                for i, msg in enumerate(msgs_data):
                    content = msg["data"].get("content", "")
                    if isinstance(content, list):
                        content = str(content)
                    preview = content[:100] + "..." if len(content) > 100 else content
                    msg_table.add_row(str(i), msg["role"], preview.replace("\n", " "))
                client._console.print(msg_table)
    else:
        # List all sessions — use AgentSession.get_max_agent_idx to enumerate
        engine = create_engine(db_uri)
        db = SQLAlchemySession(engine)
        agents = db.query(AgentModel).order_by(AgentModel.created_at.desc()).all()

        # Deduplicate by session_id, keep highest idx
        seen: dict[str, dict] = {}
        for agent in agents:
            sid = agent.session_id
            if sid not in seen or agent.agent_idx > seen[sid]["agent_idx"]:
                msg_count = db.query(Message).filter_by(agent_id=agent.agent_id).count()
                seen[sid] = {
                    "session_id": sid,
                    "created_at": agent.created_at.isoformat(),
                    "model_identifier": agent.model_identifier,
                    "agent_idx": agent.agent_idx,
                    "message_count": msg_count,
                }
        db.close()

        sessions_list = list(seen.values())[:limit]

        if not sessions_list:
            if json_output:
                print(json.dumps({"sessions": []}))
            else:
                client._console.print("[yellow]No sessions found[/yellow]")
            raise SystemExit(0)

        if json_output:
            print(json.dumps({"sessions": sessions_list}, indent=2, default=str))
        else:
            table = Table(title="Crow Sessions")
            table.add_column("Session ID", style="cyan")
            table.add_column("Created", style="dim")
            table.add_column("Model", style="green")
            table.add_column("Messages", style="yellow")
            for sess in sessions_list:
                table.add_row(
                    sess["session_id"],
                    sess["created_at"][:19],
                    sess["model_identifier"] or "",
                    str(sess["message_count"]),
                )
            client._console.print(table)
            client._console.print(
                f"\n[dim]Use --session <id> --messages to inspect a specific session[/dim]"
            )


# ============================================================================
# Main Commands
# ============================================================================


@app.command()
def run(
    prompt: str = typer.Argument(
        None, help="Prompt to send (optional in interactive mode; '-' reads stdin)"
    ),
    prompt_file: Path | None = typer.Option(
        None,
        "--prompt-file",
        "-f",
        help="Read the prompt from a file (useful for long subagent delegation prompts)",
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Run in interactive mode"
    ),
    session_id: str | None = typer.Option(
        None, "--session", "-s", help="Load existing session"
    ),
    cwd: str = typer.Option(os.getcwd(), "--cwd", "-c", help="Working directory"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging"
    ),
    config_dir: Path = typer.Option(
        None,
        "--config-dir",
        "-d",
        help="Configuration directory (default: ~/.crow)",
    ),
):
    """
    Run the Crow client — send a prompt to an agent (one-shot) or start a REPL.

    MODES: default sends one prompt, prints the response, and exits;
    -i/--interactive starts a REPL loop.

    PROMPT SOURCES: the prompt can be a positional argument, a file
    (--prompt-file/-f), or stdin (pass '-' as the prompt).

    DELEGATION — this command is also how agents launch subagents. Every
    session persists in the shared sqlite memory, so you can launch a worker,
    keep talking to it by session id, and read its thoughts from any other
    agent. The loop:

    1. Launch a worker (it gets a coolname session id):

        crow-cli run "refactor the parser into its own module"

    2. Continue that session with -s (give it a hellacious timeout if the
    prompt is big):

        crow-cli run -s <session-id> "now add tests"

    3. Send a long, pre-written delegation prompt from a file or stdin:

        crow-cli run -f delegation.md -s <session-id>
        cat delegation.md | crow-cli run -

    4. From another agent, read what the worker did with the query_memory MCP
    tool: query_memory(session_id="<session-id>", limit=1).

    That's the whole mechanism: delegate with `run -s`, read thoughts with
    query_memory, verify artifacts on disk. No bespoke agent-to-agent protocol
    — just a shared database and a read query.
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Resolve the prompt source: --prompt-file > stdin ('-') > positional arg.
    if prompt_file is not None:
        if prompt is not None:
            client._console.print(
                "[red]Error: provide a prompt OR --prompt-file, not both[/red]"
            )
            raise SystemExit(1)
        if not prompt_file.exists():
            client._console.print(
                f"[red]Error: prompt file not found: {prompt_file}[/red]"
            )
            raise SystemExit(1)
        prompt = prompt_file.read_text()
    elif prompt == "-":
        prompt = sys.stdin.read()

    # Validate arguments
    if not interactive and prompt is None:
        client._console.print(
            "[red]Error: Either provide a prompt or use -i for interactive mode[/red]"
        )
        client._console.print("\n[yellow]Examples:[/yellow]")
        client._console.print("  crow-cli run 'list the files'")
        client._console.print("  crow-cli run -i")
        client._console.print("  crow-cli run -s <session-id> -i")
        client._console.print("  crow-cli run -f prompt.md -s <session-id>")
        client._console.print("  cat prompt.md | crow-cli run -")
        raise SystemExit(1)

    # Run the async main
    asyncio.run(_run_async(prompt, interactive, session_id, cwd))


async def _run_async(
    prompt: str | None,
    interactive: bool,
    session_id: str | None,
    cwd: str,
) -> None:
    """Async implementation of run command."""
    client._console.print(
        Panel(
            "[bold]Crow ACP Client[/bold]\n\n"
            f"Working directory: [cyan]{cwd}[/cyan]\n"
            f"Mode: {'[green]Interactive[/green]' if interactive else '[yellow]Single-shot[/yellow]'}\n"
            f"Session: {session_id or '[dim]New session[/dim]'}",
            title="[magenta]🪶 Crow[/magenta]",
            border_style="magenta",
        )
    )

    # Spawn agent
    proc = await client.spawn_agent(cwd)

    try:
        # Connect
        conn = await connect_client(proc, client)

        # Create or load session
        if session_id:
            client._console.print(f"[cyan]Loading session: {session_id}[/cyan]")
            await conn.load_session(session_id=session_id, mcp_servers=[], cwd=cwd)
            actual_session_id = session_id
        else:
            client._console.print("[cyan]Creating new session...[/cyan]")
            session = await conn.new_session(mcp_servers=[], cwd=cwd)
            actual_session_id = session.session_id
            client._console.print(
                f"[green]Session created: {actual_session_id}[/green]"
            )

        # Run
        if interactive:
            await client.interactive_loop(conn, actual_session_id)
        else:
            await client.send_prompt(conn, actual_session_id, prompt)
            client._console.print(f"\n[dim]Session: {actual_session_id}[/dim]")
            client._console.print(
                f'[dim]Use crow-cli run -s {actual_session_id} "<your—message>" to continue this conversation[/dim]'
            )
    except Exception as e:
        # If something went wrong, try to get stderr before re-raising
        try:
            if hasattr(proc, "_stderr_reader") and not proc._stderr_reader.done():
                stderr_output = await proc._stderr_reader
                if stderr_output and stderr_output.strip():
                    client._console.print()
                    client._console.print("[red]═══ Agent subprocess failed ═══[/red]")
                    client._console.print()
                    client._console.print(stderr_output.decode())
                    client._console.print()
                    client._console.print(
                        "[yellow]The agent subprocess exited with an error. "
                        "The traceback above shows what went wrong.[/yellow]"
                    )
        except Exception:
            # If we can't read stderr, just continue with the original error
            pass
        raise e

    finally:
        # Cleanup
        if proc.returncode is None:
            proc.terminate()
            with contextlib.suppress(ProcessLookupError):
                await proc.wait()


# ============================================================================
# Entry Point
# ============================================================================


@app.callback()
def global_callback():
    """Crow ACP Client - Transparent, observable agent client."""
    pass


def main():
    app()


if __name__ == "__main__":
    main()
