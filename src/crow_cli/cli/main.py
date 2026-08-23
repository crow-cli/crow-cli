import asyncio
import contextlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from crow_cli.config import Config, apply_config_overrides
from crow_cli.agent.main import main as agent_main
from crow_cli.agent.mcp_client import fastmcp_config_to_acp_servers
from crow_cli.memory import build_agent_id
from crow_cli.agent.memory import MemoryClient, MemoryServiceError
from crow_cli.agent.session import AgentSession
from crow_cli.cli.init_cmd import init_command
from crow_cli.cli.install import app as install_app
from crow_cli.client.main import CrowClient, connect_client

app = typer.Typer(
    name="crow-cli",
    help=(
        "Transparent CLI for the Crow agent — full observability into agent state.\n\n"
        "Talk to an agent with `crow-cli run \"prompt\"` and continue a session with "
        "`-s <session-id>`. This is also how agents delegate to subagents: launch a "
        "worker with `run`, then read its thoughts via the query_session MCP tool. "
        "See `crow-cli run --help` for the full delegation recipe."
    ),
)

# Register command groups
app.add_typer(install_app, name="install")


console = Console()
# we need to work on a crow-cli init command to set up configuration
# until then...
client = CrowClient(console=console)


# ===========================================================================
# ACP Agent
@app.command("acp")
def run_agentmain(
    config_dir: Path = typer.Option(
        None,
        "--config-dir",
        "-d",
        help="Configuration directory (default: ~/.agents/crow)",
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
    model: str = typer.Option(
        None,
        "--model",
        "-m",
        help="Model to use (name from config.yaml models: section)",
    ),
    http: bool = typer.Option(
        False,
        "--http",
        help="Serve ACP over Streamable HTTP + WebSocket instead of stdio",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind address with --http (use 0.0.0.0 to expose)",
    ),
    port: int = typer.Option(
        2769,
        "--port",
        help="Port with --http (default 2769)",
    ),
):
    """Main entry point for the crow-cli agent."""
    if config_dir is None:
        config_dir = Path.home() / ".agents" / "crow"

    config = Config.load(config_dir=config_dir)
    config = apply_config_overrides(config, config_file)

    if system_prompt_path:
        config.system_prompt_path = system_prompt_path

    if debug:
        config.chunk_log = True

    agent_main(config=config, model=model, http=http, host=host, port=port)


@app.command("mcp")
def run_mcp(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        help="stdio = spawned child (default); http = streamable HTTP service",
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="bind address for the HTTP transport"),
    port: int = typer.Option(2769, "--port", help="port for the HTTP transport"),
):
    """Serve Crow's MCP tools — stdio child (default) or streamable HTTP."""
    # Lazy import: registering the tools pulls in every tool module (incl.
    # opencv); don't pay that for unrelated commands.
    from crow_cli.mcp.server.main import serve

    serve(transport, host, port)


@app.command("init")
def run_init(
    config_dir: Path = typer.Option(
        None,
        "--config-dir",
        "-d",
        help="Configuration directory (default: ~/.agents/crow)",
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
        config_dir = Path.home() / ".agents" / "crow"
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
# Session Inspection
# ============================================================================


@app.command("inspect")
def inspect_db(
    session_id: str | None = typer.Option(
        None, "--session", "-s", help="Session ID to inspect"
    ),
    messages: bool = typer.Option(False, "--messages", "-m", help="Show messages"),
    limit: int = typer.Option(20, "--limit", "-l", help="Limit number of rows"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    include_forks: bool = typer.Option(
        False,
        "--include-forks",
        help="Fold fork agents into counts/listings (hidden by default)",
    ),
):
    """Inspect Crow sessions — state, messages, etc."""
    asyncio.run(_inspect_db(session_id, messages, limit, json_output, include_forks))


async def _inspect_db(session_id, messages, limit, json_output, include_forks=False):
    if session_id:
        # Use existing AgentSession methods to get the latest agent for this session
        max_idx = await AgentSession.get_max_agent_idx(session_id)
        if max_idx < 1:
            if json_output:
                print(json.dumps({"error": f"Session '{session_id}' not found"}))
            else:
                client._console.print(f"[red]Session '{session_id}' not found[/red]")
            raise SystemExit(1)

        agent_id = build_agent_id(session_id, max_idx)
        session_obj = await AgentSession.load(agent_id)

        session_data = {
            "agent_id": session_obj.agent_id,
            "session_id": session_obj.session_id,
            "cwd": session_obj.cwd,
            "model_identifier": session_obj.model_identifier,
            "agent_idx": session_obj.agent_idx,
        }
        if include_forks:
            # Fork ids never appear unless explicitly asked for.
            mc = MemoryClient()
            try:
                agents = await mc.list_agents(session_id)
            finally:
                await mc.close()
            session_data["forks"] = [a.agent_id for a in agents if a.fork_idx > 1]

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
        # List all sessions, most-recently-active first.
        try:
            sessions_list = await AgentSession.list_sessions(
                limit=limit, include_forks=include_forks
            )
        except MemoryServiceError as e:
            if json_output:
                print(json.dumps({"error": f"memory error: {e.detail}"}))
            else:
                client._console.print(f"[red]memory error: {e.detail}[/red]")
            raise SystemExit(1)

        if not sessions_list:
            if json_output:
                print(json.dumps({"sessions": []}))
            else:
                client._console.print("[yellow]No sessions found[/yellow]")
            raise SystemExit(0)

        if json_output:
            print(
                json.dumps(
                    {"sessions": [s.to_dict() for s in sessions_list]}, indent=2
                )
            )
        else:
            table = Table(title="Crow Sessions")
            table.add_column("Session ID", style="cyan")
            table.add_column("Last active", style="dim")
            table.add_column("Model", style="green")
            table.add_column("Agents", style="magenta")
            table.add_column("Messages", style="yellow")
            for sess in sessions_list:
                table.add_row(
                    sess.session_id,
                    sess.last_activity[:19],
                    sess.model_identifier or "",
                    str(sess.agent_count),
                    str(sess.message_count),
                )
            client._console.print(table)
            client._console.print(
                f"\n[dim]Use --session <id> --messages to inspect a specific session[/dim]"
            )


# ============================================================================
# Telemetry — the MCP query tools as CLI surfaces.
# Same functions, two facades: the agent meets them as MCP tools
# (list_sessions/query_memory/query_session), the human meets them here.
# ============================================================================


def _telemetry_db_override(config_file: Path | None) -> None:
    """Point the memory store at the SAME db the rest of the CLI would use.

    The store resolves CROW_DB_URI env -> config.yaml; --config-file must
    win here exactly like it does for `run` (e.g. dev overrides pointing at
    a fresh db).
    """
    if config_file is None:
        return
    config = apply_config_overrides(Config.load(), config_file)
    os.environ["CROW_DB_URI"] = config.db_uri


def _print_telemetry(result: str, raw: bool) -> None:
    if raw:
        print(result)
    else:
        from rich.markdown import Markdown

        console.print(Markdown(result))


def _content_mode(value: str):
    from crow_cli.mcp.memory.main import ContentMode

    try:
        return ContentMode(value)
    except ValueError:
        choices = ", ".join(m.value for m in ContentMode)
        console.print(f"[red]Invalid --mode '{value}' (one of: {choices})[/red]")
        raise typer.Exit(1)


@app.command("list-sessions")
def cli_list_sessions(
    limit: int = typer.Option(50, "--limit", "-l", help="Max sessions (cap 200)"),
    offset: int = typer.Option(0, "--offset", help="Pagination offset"),
    include_forks: bool = typer.Option(
        False,
        "--include-forks",
        help="Fold fork agents into the listing (hidden by default)",
    ),
    config_file: Path = typer.Option(
        None, "--config-file", "-o", help="YAML file with config values to override"
    ),
    raw: bool = typer.Option(
        False, "--raw", help="Print the raw markdown instead of rendering it"
    ),
):
    """List agent sessions, most-recently-active first (who's working now).

    Same implementation as the list_sessions MCP tool."""
    _telemetry_db_override(config_file)
    from crow_cli.mcp.memory.main import list_sessions

    result = asyncio.run(
        list_sessions(limit=limit, offset=offset, include_forks=include_forks)
    )
    _print_telemetry(result, raw)


@app.command("query-memory")
def cli_query_memory(
    query: str = typer.Argument(..., help="Search term"),
    mode: str = typer.Option(
        "conversation",
        "--mode",
        "-m",
        help="conversation | with_thinking | with_tools | full",
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Max matches (cap 200)"),
    offset: int = typer.Option(0, "--offset", help="Pagination offset"),
    include_forks: bool = typer.Option(
        False,
        "--include-forks",
        help="Include matches from fork agents' own rows (hidden by default)",
    ),
    config_file: Path = typer.Option(
        None, "--config-file", "-o", help="YAML file with config values to override"
    ),
    raw: bool = typer.Option(
        False, "--raw", help="Print the raw markdown instead of rendering it"
    ),
):
    """Search conversation history ACROSS all sessions (BM25 discovery).

    Same implementation as the query_memory MCP tool."""
    _telemetry_db_override(config_file)
    from crow_cli.mcp.memory.main import query_memory

    result = asyncio.run(
        query_memory(
            query=query,
            mode=_content_mode(mode),
            limit=limit,
            offset=offset,
            include_forks=include_forks,
        )
    )
    _print_telemetry(result, raw)


@app.command("query-session")
def cli_query_session(
    session_id: str = typer.Argument(..., help="The session to read"),
    query: str = typer.Option(None, "--query", "-q", help="Search within the session"),
    agent_idx: int = typer.Option(
        None, "--agent-idx", help="Narrow to one agent (default: all agents)"
    ),
    mode: str = typer.Option(
        "conversation",
        "--mode",
        "-m",
        help="conversation | with_thinking | with_tools | full",
    ),
    order: str = typer.Option(
        "desc", "--order", help="desc = newest-first (default); asc = oldest-first"
    ),
    context: int = typer.Option(
        0, "--context", "-C", help="Messages around each match (search only)"
    ),
    after: str = typer.Option(None, "--after", help="ISO datetime lower bound"),
    before: str = typer.Option(None, "--before", help="ISO datetime upper bound"),
    limit: int = typer.Option(
        None, "--limit", "-l", help="Max messages (browse default 1, search 20; cap 200)"
    ),
    offset: int = typer.Option(0, "--offset", help="Pagination offset into the past"),
    search_type: str = typer.Option(
        "semantic", "--search-type", help="semantic (BM25) | keyword | both"
    ),
    include_forks: bool = typer.Option(
        False,
        "--include-forks",
        help="Fold fork agents into the view (hidden by default)",
    ),
    config_file: Path = typer.Option(
        None, "--config-file", "-o", help="YAML file with config values to override"
    ),
    raw: bool = typer.Option(
        False, "--raw", help="Print the raw markdown instead of rendering it"
    ),
):
    """Read or search one session's history across all its agents.

    Browse (no --query) returns the tail by default; --query searches.
    Same implementation as the query_session MCP tool."""
    _telemetry_db_override(config_file)
    from crow_cli.mcp.memory.main import SearchType, query_session

    try:
        st = SearchType(search_type)
    except ValueError:
        choices = ", ".join(s.value for s in SearchType)
        console.print(
            f"[red]Invalid --search-type '{search_type}' (one of: {choices})[/red]"
        )
        raise typer.Exit(1)

    result = asyncio.run(
        query_session(
            session_id=session_id,
            query=query,
            agent_idx=agent_idx,
            mode=_content_mode(mode),
            order=order,
            context=context,
            after=after,
            before=before,
            limit=limit,
            offset=offset,
            search_type=st,
            include_forks=include_forks,
        )
    )
    _print_telemetry(result, raw)


# ============================================================================
# Main Commands
# ============================================================================


def _sampling_label(model) -> str:
    """One-line sampling summary for the models table: effort when set,
    else temperature plus whichever optional params are configured."""
    if model.reasoning_effort:
        return model.reasoning_effort
    parts = [f"temp={model.temperature}"]
    for label, value in (
        ("top_p", model.top_p),
        ("top_k", model.top_k),
        ("min_p", model.min_p),
        ("presence", model.presence_penalty),
        ("repeat", model.repetition_penalty),
    ):
        if value is not None:
            parts.append(f"{label}={value}")
    return " ".join(parts)


@app.command()
def models(
    config_dir: Path = typer.Option(
        None,
        "--config-dir",
        "-d",
        help="Configuration directory (default: ~/.agents/crow)",
    ),
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Machine-readable JSON output"
    ),
):
    """List the models available from config.yaml (first one is the default)."""
    config = Config.load(config_dir=config_dir)
    rows = [
        {
            "name": m.name,
            "provider": m.provider_name,
            "model_id": m.model_id,
            "modality": ",".join(m.modality),
            "sampling": _sampling_label(m),
            "fallbacks": list(m.fallbacks),
            "default": i == 0,
        }
        for i, m in enumerate(config.llm.models.values())
    ]
    if json_out:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        console.print("[yellow]No models configured.[/yellow]")
        return
    table = Table(title="Models")
    table.add_column("", justify="center")  # default marker
    table.add_column("name", style="bold", overflow="fold")
    table.add_column("provider", overflow="fold")
    table.add_column("model_id", overflow="fold")
    table.add_column("modality", overflow="fold")
    table.add_column("sampling", overflow="fold")
    table.add_column("fallbacks", overflow="fold")
    for r in rows:
        table.add_row(
            "[green]*[/green]" if r["default"] else "",
            r["name"],
            r["provider"],
            r["model_id"],
            r["modality"],
            r["sampling"],
            ",".join(r["fallbacks"]),
        )
    console.print(table)
    console.print("[dim]* = default (first in config.yaml); text,image = default (assume vision)[/dim]")


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
    fork: bool = typer.Option(
        False,
        "--fork",
        help="Spawn a FORK of -s/--session and run inside it (requires -s). "
        "The fork shares the source's history (no copying) and persists under "
        "its own three-part id, which is printed so you can continue it with -s.",
    ),
    fork_idx: int | None = typer.Option(
        None,
        "--fork-idx",
        help="Continue existing fork N of -s/--session (requires -s). "
        "Fork 1 is the trunk — plain -s already does that.",
    ),
    cwd: str = typer.Option(os.getcwd(), "--cwd", "-c", help="Working directory"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging"
    ),
    config_dir: Path = typer.Option(
        None,
        "--config-dir",
        "-d",
        help="Configuration directory (default: ~/.agents/crow)",
    ),
    config_file: Path = typer.Option(
        None,
        "--config-file",
        "-o",
        help="YAML override file applied on top of the loaded config (forwarded to the agent)",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Model to use (name from config.yaml models:); overrides the session's saved model",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Machine-readable JSONL to stdout (one event per line; disables rich rendering)",
    ),
):
    """
    Run the Crow client — send a prompt to an agent (one-shot) or start a REPL.

    MODES: default sends one prompt, prints the response, and exits;
    -i/--interactive starts a REPL loop.

    MODELS: the agent uses the first model in config.yaml's models: section
    by default. Override with -m/--model <name> (see `crow-cli models`);
    the override also wins over a resumed session's saved model.

    MACHINE OUTPUT: -j/--json emits JSONL to stdout — one event per line
    (session, thinking, message, tool_call, usage, result, error), rich
    rendering disabled. Pipe to a .jsonl file or jq. One-shot only.

    PROMPT SOURCES: the prompt can be a positional argument, a file
    (--prompt-file/-f), or stdin (pass '-' as the prompt).

    DELEGATION — this command is also how agents launch subagents. Every
    session persists in the shared LanceDB store, so you can launch a worker,
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

    4. From another agent, read what the worker did with the query_session MCP
    tool: query_session(session_id="<session-id>") — a bare call returns the
    worker's latest message.

    That's the whole mechanism: delegate with `run -s`, read thoughts with
    query_session, verify artifacts on disk. No bespoke agent-to-agent protocol
    — just a shared database and a read query.

    FORKS — branch a session's history without copying it:

    1. Spawn a fork of a session and run inside it (the fork sees the whole
       trunk history; the trunk never sees the fork):

        crow-cli run -s <session-id> --fork "what would you do differently?"

    2. The fork persists under its own three-part id (printed on creation).
       Continue it like any session:

        crow-cli run -s <session-id>-<agent-idx>-<fork-idx> "keep going"

    3. Or continue fork N of a session directly:

        crow-cli run -s <session-id> --fork-idx 2 "keep going"

    Forks are hidden from the telemetry surfaces (inspect, query_session,
    query_memory, list_sessions) unless include_forks/--include-forks is set.
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    if json_out and interactive:
        print(json.dumps({"type": "error", "error": "--json is one-shot only; not supported with --interactive"}))
        raise SystemExit(1)

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
    if fork and fork_idx is not None:
        client._console.print(
            "[red]Error: --fork and --fork-idx are mutually exclusive "
            "(spawn a fork OR continue one)[/red]"
        )
        raise SystemExit(1)
    if (fork or fork_idx is not None) and not session_id:
        client._console.print(
            "[red]Error: --fork/--fork-idx require -s/--session (the fork source)[/red]"
        )
        raise SystemExit(1)

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
    asyncio.run(
        _run_async(
            prompt, interactive, session_id, cwd, config_dir, model, json_out,
            config_file, fork=fork, fork_idx=fork_idx,
        )
    )


def _emit_json(**event: Any) -> None:
    print(json.dumps(event), flush=True)


async def _run_async(
    prompt: str | None,
    interactive: bool,
    session_id: str | None,
    cwd: str,
    config_dir: Path | None = None,
    model: str | None = None,
    json_out: bool = False,
    config_file: Path | None = None,
    fork: bool = False,
    fork_idx: int | None = None,
) -> None:
    """Async implementation of run command."""
    client._json_mode = json_out
    if not json_out:
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

    # The CLIENT owns tool supply: load config here and hand our mcpServers
    # to the agent in new_session/load_session (config.yaml -> FastMCP dict ->
    # ACP server objects, the inverse of the agent's acp_to_fastmcp_config).
    # `crow-cli mcp` rides along because it is an mcpServers entry like any
    # other. Empty/absent mcpServers = the session runs with zero tools.
    config = Config.load(config_dir)
    apply_config_overrides(config, config_file)
    mcp_servers = fastmcp_config_to_acp_servers(config.mcp_servers)
    if not json_out:
        client._console.print(
            f"[cyan]MCP servers: {', '.join(s.name for s in mcp_servers) or '[dim]none — zero tools[/dim]'}[/cyan]"
        )

    # Spawn agent
    proc = await client.spawn_agent(cwd, config_dir, model=model, config_file=config_file)

    try:
        # Connect
        conn = await connect_client(proc, client)

        # Create, fork, or load session
        if fork:
            # session/fork (UNSTABLE): the fork shares the source's history
            # (prefix rows, never copied) and gets its own three-part wire id.
            if not json_out:
                client._console.print(f"[cyan]Forking session: {session_id}[/cyan]")
            forked = await conn.fork_session(
                session_id=session_id, cwd=cwd, mcp_servers=mcp_servers
            )
            actual_session_id = forked.session_id
            if not json_out:
                client._console.print(f"[green]Fork created: {actual_session_id}[/green]")
        elif session_id:
            wire_id = session_id
            if fork_idx is not None:
                # Continue fork N: resolve its three-part wire id through the
                # shared db. A fork shares its agent_idx with the trunk HEAD
                # it was spawned from; trunk HEAD resolution follows fork 1.
                mc = MemoryClient(path=config.db_uri, config_dir=config_dir)
                try:
                    max_agent = await mc.get_max_agent_idx(session_id)
                finally:
                    await mc.close()
                if max_agent < 1:
                    client._console.print(
                        f"[red]Session '{session_id}' not found[/red]"
                    )
                    raise SystemExit(1)
                wire_id = build_agent_id(session_id, max_agent, fork_idx)
            if not json_out:
                client._console.print(f"[cyan]Loading session: {wire_id}[/cyan]")
            await conn.load_session(
                session_id=wire_id, mcp_servers=mcp_servers, cwd=cwd
            )
            actual_session_id = wire_id
        else:
            if not json_out:
                client._console.print("[cyan]Creating new session...[/cyan]")
            session = await conn.new_session(mcp_servers=mcp_servers, cwd=cwd)
            actual_session_id = session.session_id
            if not json_out:
                client._console.print(
                    f"[green]Session created: {actual_session_id}[/green]"
                )
        if json_out:
            _emit_json(
                type="session",
                session_id=actual_session_id,
                cwd=cwd,
                mode="interactive" if interactive else "one_shot",
                model=model,
            )

        # Run
        if interactive:
            await client.interactive_loop(conn, actual_session_id)
        else:
            await client.send_prompt(conn, actual_session_id, prompt)
            if json_out:
                client._flush_json()
                _emit_json(type="result", session_id=actual_session_id)
            else:
                client._console.print(f"\n[dim]Session: {actual_session_id}[/dim]")
                client._console.print(
                    f'[dim]Use crow-cli run -s {actual_session_id} "<your—message>" to continue this conversation[/dim]'
                )
    except Exception as e:
        # Surface the agent's stderr (e.g. a startup failure like an unknown
        # -m model) before re-raising. Wait briefly for the process to die so
        # the stderr read completes — the old .done() check raced the reader.
        stderr_output = b""
        reader = getattr(proc, "_stderr_reader", None)
        if reader is not None:
            try:
                if proc.returncode is None:
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(proc.wait(), timeout=2)
                if proc.returncode is not None:
                    stderr_output = await asyncio.wait_for(
                        asyncio.shield(reader), timeout=3
                    )
            except Exception:
                pass
        if stderr_output and stderr_output.strip():
            text = stderr_output.decode(errors="replace")
            if json_out:
                _emit_json(type="error", error=text.strip())
            else:
                client._console.print()
                client._console.print("[red]═══ Agent subprocess failed ═══[/red]")
                client._console.print()
                client._console.print(text)
                client._console.print(
                    "[yellow]The agent subprocess exited with an error. "
                    "The traceback above shows what went wrong.[/yellow]"
                )
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
