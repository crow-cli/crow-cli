"""
crow-cli init - Interactive configuration setup wizard.

Builds config.yaml and .env in ~/.crow (or --config-dir).

Configuration priority (highest to lowest):
1. LLM_*_API_KEY / LLM_*_BASE_URL env vars
2. config.yaml in config_dir (if exists)
3. .env in current directory (loaded via load_dotenv)
4. Interactive prompts
"""

import getpass
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

load_dotenv()  # Load .env from current directory if present

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


def wait_for_searxng_ready(config_dir: Path, port: str, max_wait: int = 30) -> bool:
    """Wait for SearXNG to be ready.

    Checks both:
    1. settings.yml exists on host (container started + volume mounted)
    2. HTTP endpoint responds (container is actually listening)

    Returns True if ready, False if timed out.
    """
    searxng_dir = config_dir / "searxng"
    settings_file = searxng_dir / "settings.yml"
    elapsed = 0

    console.print(f"  [dim]Waiting for SearXNG to start...[/dim]")
    while elapsed < max_wait:
        # Check HTTP endpoint (primary readiness signal)
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"http://localhost:{port}/search?q=test&format=json",
                    timeout=3,
                )
                if response.status_code == 200:
                    console.print(f"  [green]✓[/green] SearXNG ready ({elapsed}s)")
                    return True
        except httpx.ConnectError:
            pass  # Not ready yet
        except httpx.RequestError:
            pass  # Not ready yet

        # Fallback: check if settings.yml exists on host
        if settings_file.exists():
            console.print(f"  [green]✓[/green] SearXNG ready ({elapsed}s)")
            return True

        time.sleep(2)
        elapsed += 2

    console.print(f"  [red]✗[/red] SearXNG did not start within {max_wait}s")
    return False


def enable_searxng_json(config_dir: Path, port: str) -> bool:
    """Test that SearXNG JSON endpoint works.

    We already wrote settings.yml with JSON enabled before docker started.
    Just wait for the container and test.
    """
    if not wait_for_searxng_ready(config_dir, port):
        return False

    console.print("  [dim]Testing JSON endpoint...[/dim]")
    try:
        base_url = f"http://localhost:{port}"
        with httpx.Client() as client:
            response = client.get(
                f"{base_url}/search",
                params={"q": "test", "format": "json"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

        if data.get("results") is not None:
            count = len(data["results"])
            console.print(f"  [green]✓[/green] JSON endpoint working! ({count} results)")
            return True
        else:
            console.print("  [yellow]Warning: No results in JSON response[/yellow]")
            return True  # Still working, just no results yet
    except httpx.HTTPError as e:
        console.print(f"  [red]✗ JSON endpoint failed: {e}[/red]")
        return False


def run_init(config_dir: Path, yes: bool = False):
    """Run the interactive initialization wizard."""
    config_dir = Path(os.path.expanduser(str(config_dir)))

    console.print(
        Panel.fit(
            "[bold]🪶 Crow CLI Setup[/bold]\n\n"
            f"This will create your configuration in [cyan]{config_dir}[/cyan]",
            border_style="magenta",
        )
    )

    # Load existing config if present (for merging)
    config_file = config_dir / "config.yaml"
    env_file = config_dir / ".env"
    existing_config = None
    if config_file.exists() and not yes:
        if not Confirm.ask(
            f"\n[yellow]{config_file} already exists. Overwrite?[/]", default=False
        ):
            console.print("[red]Aborted.[/red]")
            return
        existing_config = yaml.safe_load(config_file.read_text())

    # Data structures
    providers: dict[str, dict] = {}
    models: dict[str, dict] = {}
    env_vars: dict[str, str] = {}

    # =========================================================================
    # STEP 1: Add providers
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 1: LLM Providers ═══[/bold cyan]\n")

    if yes:
        # In --yes mode, check env vars for provider config
        console.print("[dim]→ --yes mode: checking env vars for providers...[/dim]")
        # Look for LLM_{PROVIDER}_API_KEY / LLM_{PROVIDER}_BASE_URL patterns
        for key, value in os.environ.items():
            if key.startswith("LLM_") and key.endswith("_API_KEY"):
                provider = key[len("LLM_"):-len("_API_KEY")].lower()
                base_url_key = f"LLM_{provider.upper()}_BASE_URL"
                base_url = os.environ.get(base_url_key, "")
                if base_url and value:
                    console.print(
                        f"  [cyan]✓[/cyan] Found provider: [green]{provider}[/green] "
                        f"from env vars"
                    )
                    providers[provider] = {
                        "base_url": base_url,
                        "api_key": f"${{{key}}}",
                    }
                    env_vars[key] = value
                    # Try to fetch models
                    try:
                        available_models = fetch_models(base_url, value)
                        for model in available_models[:5]:  # Take first 5
                            models[model["id"]] = {
                                "provider": provider,
                                "model": model["id"],
                            }
                    except Exception:
                        pass  # Best effort, not critical
        if not providers:
            console.print(
                "[yellow]  No providers found in env vars. "
                "Add LLM_<PROVIDER>_API_KEY + LLM_<PROVIDER>_BASE_URL.[/yellow]"
            )
        console.print()
    else:
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

            base_url = Prompt.ask(
                "Base URL (e.g., https://api.openai.com/v1)"
            ).strip()
            if not base_url:
                console.print("[red]Base URL required[/red]")
                continue

            api_key = getpass.getpass("API key (hidden): ").strip()
            if not api_key:
                console.print(
                    "[yellow]Warning: No API key provided. "
                    "You'll need to set it manually.[/yellow]"
                )

            # Store provider
            providers[provider_name] = {
                "base_url": base_url,
                "api_key": f"${{{provider_name.upper()}_API_KEY}}",
            }
            env_vars[f"{provider_name.upper()}_API_KEY"] = api_key

            # Try to fetch models
            if api_key and base_url:
                console.print(
                    f"\n[cyan]Fetching models from {provider_name}...[/cyan]"
                )
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

    setup_searxng = None
    if yes:
        # In --yes mode, default to installing
        setup_searxng = True
        searxng_port = os.environ.get("SEARXNG_PORT", "2946")
        env_vars["SEARXNG_PORT"] = searxng_port
        console.print("[dim]→ --yes mode: defaulting to SearXNG install[/dim]")
    elif os.environ.get("YES_INSTALL_SEARXNG", "").lower() in ("1", "true", "yes"):
        setup_searxng = True
        console.print("[dim]→ YES_INSTALL_SEARXNG=1 detected, skipping prompt[/dim]")
        searxng_port = os.environ.get("SEARXNG_PORT", "2946")
        env_vars["SEARXNG_PORT"] = searxng_port
    else:
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
    # STEP 3: Review
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 3: Review ═══[/bold cyan]\n")

    db_uri = f"sqlite:///{config_dir / 'crow.db'}"
    murder_db_uri = f"sqlite:///{config_dir / 'crow.db'}"
    console.print(f"[dim]Using SQLite at {config_dir / 'crow.db'}[/dim]")

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
    s_table.add_row("Database", "SQLite")
    console.print(s_table)

    console.print(f"\n[dim]Config directory: {config_dir}[/dim]")
    console.print(f"[dim]Database: {db_uri}[/dim]")

    if not yes and not Confirm.ask("\nLooks good?", default=True):
        console.print("[red]Aborted. No files were written.[/red]")
        return

    # =========================================================================
    # STEP 4: Write files
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 4: Writing Configuration ═══[/bold cyan]\n")

    # Ensure directory exists
    config_dir.mkdir(parents=True, exist_ok=True)

    # Copy system prompt template from repo config directory
    repo_prompts = Path(__file__).parents[3] / "config" / "prompts"
    dest_prompts = config_dir / "prompts"
    dest_prompts.mkdir(parents=True, exist_ok=True)
    for template_file in repo_prompts.glob("*.jinja2"):
        shutil.copy2(template_file, dest_prompts / template_file.name)
    console.print(f"[green]✓[/green] Copied prompt templates to {dest_prompts}")

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
        "murder_db_uri": murder_db_uri,
        "providers": providers,
        "models": models,
        "MAX_COMPACT_TOKENS": 190000,
        "N_STEPS_BACK_COMPACT": 8,
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
    if setup_searxng:
        compose_data: dict[str, Any] = {"services": {}, "volumes": {}}

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
        searxng_dir = config_dir / "searxng"
        searxng_dir.mkdir(exist_ok=True)

        # Write settings.yml with JSON enabled BEFORE docker starts.
        # The container will see this mounted file and use it.
        settings = {"search": {"formats": ["html", "json"]}}
        with open(searxng_dir / "settings.yml", "w") as f:
            yaml.dump(settings, f, default_flow_style=False)
        console.print(f"[green]✓[/green] Wrote SearXNG settings with JSON output")

        compose_file = config_dir / "compose.yaml"
        with open(compose_file, "w") as f:
            yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
        console.print(f"[green]✓[/green] Written {compose_file}")

    # Create logs directory
    (config_dir / "logs").mkdir(exist_ok=True)

    # =========================================================================
    # STEP 5: Start Docker
    # =========================================================================
    if setup_searxng:
        console.print("\n[bold cyan]═══ Step 5: Starting Services ═══[/bold cyan]\n")

        start_docker = True
        if not yes:
            start_docker = Confirm.ask("Start Docker services now?", default=True)

        if start_docker:
            # Start SearXNG container first (it writes settings.yml to volume)
            console.print("  [dim]Starting SearXNG container...[/dim]")
            try:
                result = subprocess.run(
                    ["docker", "compose", "up", "-d"],
                    cwd=config_dir,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    console.print("  [green]✓[/green] SearXNG container started")

                    # Now enable JSON output and validate
                    searxng_ok = enable_searxng_json(config_dir, searxng_port)
                    if searxng_ok:
                        console.print(
                            "  [green]✓[/green] SearXNG configured and validated"
                        )
                    else:
                        console.print(
                            "  [yellow]Warning: SearXNG validation failed. "
                            "You may need to configure it manually.[/yellow]"
                        )
                else:
                    console.print(
                        f"  [red]Failed to start SearXNG: {result.stderr}[/red]"
                    )
            except subprocess.CalledProcessError as e:
                console.print(f"  [red]Failed to start SearXNG: {e}[/red]")
            except FileNotFoundError:
                console.print(
                    "  [yellow]Docker not found. "
                    "Please start services manually.[/yellow]"
                )

    # =========================================================================
    # Done
    # =========================================================================
    console.print()
    console.print(
        Panel.fit(
            "[bold green]✓ Configuration complete![/bold green]\n\n"
            f"Config: [cyan]{config_file}[/cyan]\n"
            f"Secrets: [cyan]{env_file}[/cyan]\n\n"
            '[dim]Test with: crow-cli run "hello"[/dim]',
            border_style="green",
        )
    )


# For typer integration
def init_command(config_dir: Path = None, yes: bool = False):
    """Initialize Crow configuration interactively."""
    if config_dir is None:
        config_dir = Path(os.path.expanduser("~/.crow"))
    run_init(config_dir=config_dir, yes=yes)
