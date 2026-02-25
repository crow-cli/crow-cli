import asyncio
import contextlib
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from crow_cli.agent.main import main as agent_main
from crow_cli.cli.init_cmd import init_command

# from crow_cli.agent.config import settings
from crow_cli.client.main import CrowClient, connect_client

app = typer.Typer(
    name="crow-cli",
    help="Transparent CLI for Crow agent - full observability into agent state",
)


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
def run_agentmain():
    """Main entry point for the crow-cli agent."""
    agent_main()


@app.command("init")
def run_init():
    """Initialize Crow configuration interactively."""
    init_command()


# ============================================================================
# Database Inspection
# ============================================================================


def get_db_uri() -> str:
    """Get the default database path."""
    return os.path.expanduser("~/.crow/crow.db")


@app.command("inspect")
def inspect_db(
    session_id: str | None = typer.Option(
        None, "--session", "-s", help="Session ID to inspect"
    ),
    messages: bool = typer.Option(False, "--messages", "-m", help="Show messages"),
    limit: int = typer.Option(20, "--limit", "-l", help="Limit number of rows"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Inspect the Crow database - see session state, messages, etc."""
    import json

    db_uri = get_db_uri()

    if not os.path.exists(db_uri):
        if json_output:
            print(json.dumps({"error": f"Database not found at {db_uri}"}))
        else:
            client._console.print(f"[red]Database not found at {db_uri}[/red]")
        raise SystemExit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if session_id:
        # Show specific session
        cur.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        session = cur.fetchone()

        if not session:
            if json_output:
                print(json.dumps({"error": f"Session '{session_id}' not found"}))
            else:
                client._console.print(f"[red]Session '{session_id}' not found[/red]")
            raise SystemExit(1)

        # Build session dict
        session_data = {}
        for key in session.keys():
            val = session[key]
            if key in ("tool_definitions", "request_params", "system_prompt"):
                continue
            session_data[key] = val

        # Get messages if requested
        msgs_data = []
        if messages:
            cur.execute(
                "SELECT id, role, created_at, data FROM messages WHERE session_id = ? ORDER BY id LIMIT ?",
                (session_id, limit),
            )
            msgs = cur.fetchall()

            for msg in msgs:
                msg_data = json.loads(msg["data"])
                msgs_data.append(
                    {
                        "id": msg["id"],
                        "role": msg["role"],
                        "created_at": msg["created_at"],
                        "data": msg_data,
                    }
                )

        if json_output:
            output = {"session": session_data}
            if messages:
                output["messages"] = msgs_data
            print(json.dumps(output, indent=2, default=str))
        else:
            # Session info table
            table = Table(title=f"Session: {session_id}", show_header=False)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")

            for key, val in session_data.items():
                table.add_row(key, str(val))

            client._console.print(table)

            # Show messages if requested
            if messages:
                msg_table = Table(title=f"Messages ({len(msgs_data)} shown)")
                msg_table.add_column("ID", style="dim")
                msg_table.add_column("Role", style="cyan")
                msg_table.add_column("Created", style="dim")
                msg_table.add_column("Content Preview", style="white")

                for msg in msgs_data:
                    content = msg["data"].get("content", "")
                    preview = content[:100] + "..." if len(content) > 100 else content
                    msg_table.add_row(
                        str(msg["id"]),
                        msg["role"],
                        msg["created_at"][:19] if msg["created_at"] else "",
                        preview.replace("\n", " "),
                    )

                client._console.print(msg_table)
    else:
        # List all sessions
        cur.execute(
            """
            SELECT s.session_id, s.created_at, s.model_identifier, COUNT(m.id) as message_count
            FROM sessions s
            LEFT JOIN messages m ON s.session_id = m.session_id
            GROUP BY s.session_id
            ORDER BY s.created_at DESC
            LIMIT ?
        """,
            (limit,),
        )
        sessions = cur.fetchall()

        if not sessions:
            if json_output:
                print(json.dumps({"sessions": []}))
            else:
                client._console.print("[yellow]No sessions found[/yellow]")
            raise SystemExit(0)

        sessions_data = []
        for sess in sessions:
            sessions_data.append(
                {
                    "session_id": sess["session_id"],
                    "created_at": sess["created_at"],
                    "model_identifier": sess["model_identifier"],
                    "message_count": sess["message_count"],
                }
            )

        if json_output:
            print(json.dumps({"sessions": sessions_data}, indent=2, default=str))
        else:
            table = Table(title="Crow Sessions")
            table.add_column("Session ID", style="cyan")
            table.add_column("Created", style="dim")
            table.add_column("Model", style="green")
            table.add_column("Messages", style="yellow")

            for sess in sessions_data:
                table.add_row(
                    sess["session_id"],
                    sess["created_at"][:19] if sess["created_at"] else "",
                    sess["model_identifier"] or "",
                    str(sess["message_count"]),
                )

            client._console.print(table)
            client._console.print(
                f"\n[dim]Use --session <id> --messages to inspect a specific session[/dim]"
            )

    conn.close()


# ============================================================================
# Main Commands
# ============================================================================


@app.command()
def run(
    prompt: str = typer.Argument(
        None, help="Prompt to send (optional in interactive mode)"
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
):
    """
    Run the Crow client.

    Default mode: Send a single prompt and exit after response.
    Interactive mode (-i): Start a REPL loop.
    """
    import logging

    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Validate arguments
    if not interactive and prompt is None:
        client._console.print(
            "[red]Error: Either provide a prompt or use -i for interactive mode[/red]"
        )
        client._console.print("\n[yellow]Examples:[/yellow]")
        client._console.print("  crow-client 'list the files'")
        client._console.print("  crow-client -i")
        client._console.print("  crow-client -s <session-id> -i")
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
