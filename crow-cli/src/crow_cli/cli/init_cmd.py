"""
crow-cli init - Interactive configuration setup wizard.

Builds config.yaml and .env in ~/.crow-test (or CROW_CONFIG_DIR).
"""

import getpass
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from crow_cli.agent.configure import get_default_config_dir

console = Console()


def fetch_models(base_url: str, api_key: str) -> list[dict]:
    """Fetch available models from an OpenAI-compatible /models endpoint."""
    try:
        # Ensure base_url doesn't end with slash
        base_url = base_url.rstrip("/")
        url = f"{base_url}/models"

        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get("data", []):
            models.append(
                {
                    "id": model.get("id", "unknown"),
                    "owned_by": model.get("owned_by", "unknown"),
                }
            )
        return sorted(models, key=lambda m: m["id"])
    except Exception as e:
        console.print(
            f"[yellow]Warning: Could not fetch models from {base_url}: {e}[/yellow]"
        )
        return []


def select_models(models: list[dict]) -> list[tuple[str, str]]:
    """Let user select models interactively. Returns list of (friendly_name, model_id)."""
    if not models:
        console.print(
            "[yellow]No models available. You can add them manually later.[/yellow]"
        )
        return []

    console.print(
        f"\n[cyan]Found {len(models)} models. Select which ones to add:[/cyan]"
    )

    # Show all models
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Model ID", style="green")
    table.add_column("Owner", style="dim")

    for i, model in enumerate(models, 1):
        table.add_row(str(i), model["id"], model["owned_by"])

    console.print(table)

    # Get selections
    console.print(
        "\n[dim]Enter model numbers to add (comma-separated, e.g., 1,3,5) or 'all' or 'none':[/dim]"
    )
    selection = Prompt.ask("Models", default="all")

    if selection.lower() == "none":
        return []

    if selection.lower() == "all":
        indices = list(range(len(models)))
    else:
        try:
            indices = [int(x.strip()) - 1 for x in selection.split(",") if x.strip()]
        except ValueError:
            console.print("[red]Invalid selection[/red]")
            return []

    # Filter valid indices
    indices = [i for i in indices if 0 <= i < len(models)]

    selected = []
    for idx in indices:
        model_id = models[idx]["id"]
        # Ask for friendly name
        default_name = model_id.split("/")[-1] if "/" in model_id else model_id
        friendly_name = Prompt.ask(
            f"  Friendly name for [green]{model_id}[/]", default=default_name
        )
        selected.append((friendly_name, model_id))

    return selected


def run_init():
    """Run the interactive initialization wizard."""
    config_dir = get_default_config_dir()

    console.print(
        Panel.fit(
            "[bold]🪶 Crow CLI Setup[/bold]\n\n"
            f"This will create your configuration in [cyan]{config_dir}[/cyan]\n"
            "You can override with CROW_CONFIG_DIR environment variable.",
            border_style="magenta",
        )
    )

    # Check if config already exists
    config_file = config_dir / "config.yaml"
    env_file = config_dir / ".env"

    if config_file.exists():
        if not Confirm.ask(
            f"\n[yellow]{config_file} already exists. Overwrite?[/]", default=False
        ):
            console.print("[red]Aborted.[/red]")
            return

    # Data structures
    providers: dict[str, dict] = {}
    models: dict[str, dict] = {}
    env_vars: dict[str, str] = {}

    # =========================================================================
    # STEP 1: Add providers
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 1: LLM Providers ═══[/bold cyan]\n")

    while True:
        console.print("[dim]--- Add a provider ---[/dim]")

        provider_name = (
            Prompt.ask("Provider name (e.g., openai, anthropic, openrouter)")
            .strip()
            .lower()
        )
        if not provider_name:
            console.print("[red]Provider name required[/red]")
            continue

        base_url = Prompt.ask("Base URL (e.g., https://api.openai.com/v1)").strip()
        if not base_url:
            console.print("[red]Base URL required[/red]")
            continue

        api_key = getpass.getpass("API key (hidden): ").strip()
        if not api_key:
            console.print(
                "[yellow]Warning: No API key provided. You'll need to set it manually.[/yellow]"
            )

        # Store provider
        providers[provider_name] = {
            "base_url": base_url,
            "api_key": f"${{{provider_name.upper()}_API_KEY}}",
        }
        env_vars[f"{provider_name.upper()}_API_KEY"] = api_key

        # Try to fetch models
        if api_key and base_url:
            console.print(f"\n[cyan]Fetching models from {provider_name}...[/cyan]")
            available_models = fetch_models(base_url, api_key)
            selected = select_models(available_models)

            for friendly_name, model_id in selected:
                models[friendly_name] = {
                    "provider": provider_name,
                    "model": model_id,
                }
        else:
            console.print(
                "[yellow]Skipping model fetch (no API key or base URL)[/yellow]"
            )

        if not Confirm.ask("\nAdd another provider?", default=False):
            break

    # =========================================================================
    # STEP 2: SearXNG
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 2: SearXNG (Local Search) ═══[/bold cyan]\n")

    setup_searxng = Confirm.ask(
        "Set up local SearXNG search instance? (Requires Docker)",
        default=True,
    )

    if setup_searxng:
        searxng_port = Prompt.ask("SearXNG port", default="2946")
        env_vars["SEARXNG_PORT"] = searxng_port
    else:
        searxng_port = None

    # =========================================================================
    # STEP 3: PostgreSQL
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 3: Database ═══[/bold cyan]\n")

    setup_postgres = Confirm.ask(
        "Set up PostgreSQL database? (Recommended for production, requires Docker)\n"
        "  [dim]If no, will use SQLite (simpler, good for development)[/dim]",
        default=True,
    )

    if setup_postgres:
        pg_password = getpass.getpass(
            "PostgreSQL password (hidden, or press Enter for random): "
        ).strip()
        if not pg_password:
            import secrets

            pg_password = secrets.token_urlsafe(32)
            console.print("[dim]Generated random password[/dim]")

        pg_port = Prompt.ask("PostgreSQL port", default="3492")
        env_vars["POSTGRES_PASSWORD"] = pg_password
        env_vars["POSTGRES_PORT"] = pg_port
        db_uri = f"postgresql://postgres:${{POSTGRES_PASSWORD}}@localhost:${{POSTGRES_PORT}}/crow"
    else:
        db_uri = f"sqlite:///{config_dir / 'crow.db'}"
        console.print(f"[dim]Using SQLite at {config_dir / 'crow.db'}[/dim]")

    # =========================================================================
    # STEP 4: Review
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 4: Review ═══[/bold cyan]\n")

    # Show providers table
    if providers:
        p_table = Table(title="Providers", show_header=True)
        p_table.add_column("Name", style="cyan")
        p_table.add_column("Base URL", style="dim")
        for name, data in providers.items():
            p_table.add_row(name, data["base_url"])
        console.print(p_table)

    # Show models table
    if models:
        m_table = Table(title="Models", show_header=True)
        m_table.add_column("Friendly Name", style="green")
        m_table.add_column("Provider", style="cyan")
        m_table.add_column("Model ID", style="dim")
        for name, data in models.items():
            m_table.add_row(name, data["provider"], data["model"])
        console.print(m_table)

    # Show services
    s_table = Table(title="Services", show_header=True)
    s_table.add_column("Service", style="cyan")
    s_table.add_column("Status", style="green")
    s_table.add_row("SearXNG", "✓ Docker" if setup_searxng else "✗ Skip")
    s_table.add_row("PostgreSQL", "✓ Docker" if setup_postgres else "✗ SQLite")
    console.print(s_table)

    console.print(f"\n[dim]Config directory: {config_dir}[/dim]")
    console.print(f"[dim]Database: {db_uri}[/dim]")

    if not Confirm.ask("\nLooks good?", default=True):
        console.print("[red]Aborted. No files were written.[/red]")
        return

    # =========================================================================
    # STEP 5: Write files
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 5: Writing Configuration ═══[/bold cyan]\n")

    # Ensure directory exists
    config_dir.mkdir(parents=True, exist_ok=True)

    # Build config.yaml
    config_data: dict[str, Any] = {
        "mcpServers": {
            "crow-mcp": {
                "transport": "stdio",
                "command": "uv",
                "args": [
                    "--project",
                    str(Path(__file__).parent.parent.parent.parent.parent / "crow-mcp"),
                    "run",
                    "crow-mcp",
                ],
            }
        },
        "db_uri": db_uri,
        "providers": providers,
        "models": models,
        "TERMINAL_TOOL": "terminal",
        "WRITE_TOOL": "write",
        "READ_TOOL": "read",
        "EDIT_TOOL": "edit",
        "SEARCH_TOOL": "web_search",
        "FETCH_TOOL": "web_fetch",
        "MAX_COMPACT_TOKENS": 120000,
        "N_STEPS_BACK_COMPACT": 8,
        "max_steps_per_turn": 100,
        "max_retries_per_step": 3,
    }

    # Write config.yaml
    with open(config_file, "w") as f:
        yaml.dump(
            config_data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    console.print(f"[green]✓[/green] Written {config_file}")

    # Write .env
    env_lines = [f"{k}={v}" for k, v in env_vars.items()]
    with open(env_file, "w") as f:
        f.write("\n".join(env_lines) + "\n")
    console.print(f"[green]✓[/green] Written {env_file}")

    # Write docker-compose.yml if needed
    if setup_searxng or setup_postgres:
        compose_data: dict[str, Any] = {"services": {}, "volumes": {}}

        if setup_searxng:
            compose_data["services"]["searxng"] = {
                "image": "searxng/searxng",
                "restart": "always",
                "ports": ["${SEARXNG_PORT}:8080"],
                "environment": [
                    "BASE_URL=http://0.0.0.0:${SEARXNG_PORT}",
                    "INSTANCE_NAME=crow-search",
                ],
                "volumes": ["./searxng:/etc/searxng"],
            }
            # Create searxng config directory
            (config_dir / "searxng").mkdir(exist_ok=True)

        if setup_postgres:
            compose_data["services"]["db"] = {
                "image": "postgres",
                "restart": "always",
                "environment": [
                    "POSTGRES_USER=postgres",
                    "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}",
                ],
                "ports": ["${POSTGRES_PORT}:5432"],
                "volumes": ["./postgres:/var/lib/postgresql"],
                "healthcheck": {
                    "test": ["CMD-SHELL", "pg_isready -U postgres"],
                    "interval": "5s",
                    "timeout": "5s",
                    "retries": 5,
                },
            }
            compose_data["volumes"]["database_data"] = {"driver": "local"}

        compose_file = config_dir / "compose.yaml"
        with open(compose_file, "w") as f:
            yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
        console.print(f"[green]✓[/green] Written {compose_file}")

    # Create logs directory
    (config_dir / "logs").mkdir(exist_ok=True)

    # =========================================================================
    # STEP 6: Start Docker
    # =========================================================================
    if setup_searxng or setup_postgres:
        console.print("\n[bold cyan]═══ Step 6: Starting Services ═══[/bold cyan]\n")

        if Confirm.ask("Start Docker services now?", default=True):
            try:
                subprocess.run(
                    ["docker", "compose", "up", "-d"],
                    cwd=config_dir,
                    check=True,
                )
                console.print("[green]✓[/green] Docker services started")
            except subprocess.CalledProcessError as e:
                console.print(f"[red]Failed to start Docker services: {e}[/red]")
            except FileNotFoundError:
                console.print(
                    "[red]Docker not found. Please start services manually.[/red]"
                )

    # =========================================================================
    # Done
    # =========================================================================
    console.print(
        "\n"
        + Panel.fit(
            "[bold green]✓ Configuration complete![/bold green]\n\n"
            f"Config: [cyan]{config_file}[/cyan]\n"
            f"Secrets: [cyan]{env_file}[/cyan]\n\n"
            '[dim]Test with: crow-cli run "hello"[/dim]',
            border_style="green",
        )
    )


# For typer integration
def init_command():
    """Initialize Crow configuration interactively."""
    run_init()
