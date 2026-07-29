"""
crow-cli init - Interactive configuration setup wizard.

Builds config.yaml and .env in ~/.crow (or --config-dir).

Configuration priority (highest to lowest):
1. LLM_*_API_KEY / LLM_*_BASE_URL env vars
2. config.yaml in config_dir (if exists)
3. .env in current directory (loaded via load_dotenv)
4. Interactive prompts


"""

import base64
import getpass
import os
import secrets
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from crow_cli.agent.default import (
    COMPOSE_YAML,
    SEARXNG_SETTINGS_YML,
    SYSTEM_PROMPT,
)

load_dotenv()  # Load .env from current directory if present

console = Console()

# DashScope detection
DASHSCOPE_URL = "https://coding-intl.dashscope.aliyuncs.com/v1"

# Default models to use when DashScope is detected
DASHSCOPE_MODELS = {
    "qwen3.6-plus": {"provider": "dashscope", "model": "qwen3.6-plus"},
    "glm-5": {"provider": "dashscope", "model": "glm-5"},
}


def fetch_models(base_url: str, api_key: str) -> list[dict]:
    """Fetch available models from an OpenAI-compatible /models endpoint."""
    try:
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

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Model ID", style="green")
    table.add_column("Owner", style="dim")

    for i, model in enumerate(models, 1):
        table.add_row(str(i), model["id"], model["owned_by"])

    console.print(table)

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

    indices = [i for i in indices if 0 <= i < len(models)]

    selected = []
    for idx in indices:
        model_id = models[idx]["id"]
        default_name = model_id.split("/")[-1] if "/" in model_id else model_id
        friendly_name = Prompt.ask(
            f"  Friendly name for [green]{model_id}[/]", default=default_name
        )
        selected.append((friendly_name, model_id))

    return selected


def is_dashscope_url(base_url: str) -> bool:
    """Detect if base_url points to DashScope's coding-intl endpoint."""
    return "coding-intl.dashscope.aliyuncs.com" in base_url




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

    config_file = config_dir / "config.yaml"
    env_file = config_dir / ".env"
    if config_file.exists() and not yes:
        if not Confirm.ask(
            f"\n[yellow]{config_file} already exists. Overwrite?[/]", default=False
        ):
            console.print("[red]Aborted.[/red]")
            return

    # Data structures
    providers: dict[str, dict] = {}
    models: dict[str, dict] = {}
    env_vars: dict[str, str] = {}
    dashscope_api_key = None

    # =========================================================================
    # STEP 1: Add providers
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 1: LLM Providers ═══[/bold cyan]\n")

    if yes:
        console.print("[dim]→ --yes mode: checking env vars for providers...[/dim]")
        for key, value in os.environ.items():
            if key.startswith("LLM_") and key.endswith("_API_KEY"):
                provider = key[len("LLM_") : -len("_API_KEY")].lower()
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
                    try:
                        available_models = fetch_models(base_url, value)
                        for model in available_models[:5]:
                            models[model["id"]] = {
                                "provider": provider,
                                "model": model["id"],
                            }
                    except Exception:
                        pass
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

            base_url = Prompt.ask("Base URL (e.g., https://api.openai.com/v1)").strip()
            if not base_url:
                console.print("[red]Base URL required[/red]")
                continue

            api_key = getpass.getpass("API key (hidden): ").strip()
            if not api_key:
                console.print(
                    "[yellow]Warning: No API key provided. "
                    "You'll need to set it manually.[/yellow]"
                )


            providers[provider_name] = {
                "base_url": base_url,
                "api_key": f"${{{provider_name.upper()}_API_KEY}}",
            }
            env_vars[f"{provider_name.upper()}_API_KEY"] = api_key

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

    setup_searxng = None
    if yes:
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

    memory_url = "http://localhost:8901"
    console.print(f"[dim]Using crow-memory service at {memory_url}[/dim]")

    if providers:
        p_table = Table(title="Providers", show_header=True)
        p_table.add_column("Name", style="cyan")
        p_table.add_column("Base URL", style="dim")
        for name, data in providers.items():
            p_table.add_row(name, data["base_url"])
        console.print(p_table)

    if models:
        m_table = Table(title="Models", show_header=True)
        m_table.add_column("Friendly Name", style="green")
        m_table.add_column("Provider", style="cyan")
        m_table.add_column("Model ID", style="dim")
        for name, data in models.items():
            m_table.add_row(name, data["provider"], data["model"])
        console.print(m_table)

    s_table = Table(title="Services", show_header=True)
    s_table.add_column("Service", style="cyan")
    s_table.add_column("Status", style="green")
    s_table.add_row("SearXNG", "✓ Docker" if setup_searxng else "✗ Skip")
    s_table.add_row("Memory", "crow-memory service")
    console.print(s_table)

    console.print(f"\n[dim]Config directory: {config_dir}[/dim]")
    console.print(f"[dim]Memory service: {memory_url}[/dim]")

    if not yes and not Confirm.ask("\nLooks good?", default=True):
        console.print("[red]Aborted. No files were written.[/red]")
        return

    # =========================================================================
    # STEP 4: Write files
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 4: Writing Configuration ═══[/bold cyan]\n")

    config_dir.mkdir(parents=True, exist_ok=True)

    # System prompt template
    dest_prompts = config_dir / "prompts"
    dest_prompts.mkdir(parents=True, exist_ok=True)
    prompt_file = dest_prompts / "system_prompt.jinja2"
    if not prompt_file.exists():
        prompt_file.write_text(SYSTEM_PROMPT)
        console.print(f"[green]✓[/green] Wrote prompt template to {prompt_file}")
    else:
        console.print(f"[yellow]⊘[/yellow] Prompt template already exists, skipping")

    # config.yaml — single source of truth for crow-cli config
    config_data: dict[str, Any] = {
        "mcpServers": {
            "crow-mcp": {
                "transport": "stdio",
                "command": "uvx",
                "args": ["crow-mcp"],
            }
        },
        "memory_url": memory_url,
        "providers": providers,
        "models": models,
        "MAX_COMPACT_TOKENS": 190000,
        "max_retries_per_step": 3,
    }

    with open(config_file, "w") as f:
        yaml.dump(
            config_data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    console.print(f"[green]✓[/green] Written {config_file}")

    # .env — secrets live here, not in config.yaml
    env_lines = [f"{k}={v}" for k, v in env_vars.items()]
    with open(env_file, "w") as f:
        f.write("\n".join(env_lines) + "\n")
    console.print(f"[green]✓[/green] Written {env_file}")



    # SearXNG compose + settings (written but NOT started)
    if setup_searxng:
        searxng_dir = config_dir / "searxng"
        searxng_dir.mkdir(exist_ok=True)

        with open(searxng_dir / "settings.yml", "w") as f:
            f.write(SEARXNG_SETTINGS_YML)
        console.print(f"[green]✓[/green] Wrote SearXNG settings.yml")

    # Build compose.yaml from defaults — selectively include services
    compose_template = yaml.safe_load(COMPOSE_YAML)
    available_services = compose_template.get("services", {})
    active_services: dict[str, Any] = {}

    # crow-memory is always included — it's the persistence layer
    if "crow-memory" in available_services:
        active_services["crow-memory"] = available_services["crow-memory"]

    if setup_searxng and "searxng" in available_services:
        active_services["searxng"] = available_services["searxng"]

    if active_services:
        compose_data: dict[str, Any] = {
            "services": active_services,
            "volumes": compose_template.get("volumes", {}),
        }
        compose_file = config_dir / "compose.yaml"
        with open(compose_file, "w") as f:
            yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
        console.print(f"[green]✓[/green] Written {compose_file}")

    # Logs directory
    (config_dir / "logs").mkdir(exist_ok=True)

    # =========================================================================
    # STEP 5: Start services (just instructions)
    # =========================================================================
    console.print("\n[bold cyan]═══ Step 5: Start Services ═══[/bold cyan]\n")

    services_list = ["crow-memory"]
    if setup_searxng:
        services_list.append("SearXNG")

    console.print(
        Panel(
            f"[bold white]cd {config_dir} && docker compose up -d[/bold white]\n\n"
            f"[dim]Starts: {', '.join(services_list)}[/dim]",
            title="[yellow]Start " + " + ".join(services_list) + "[/yellow]",
            border_style="yellow",
        )
    )

    # =========================================================================
    # Done
    # =========================================================================
    config_logs = config_dir / "logs"
    system_prompt_dir = config_dir / "prompts"

    console.print()
    console.print(
        Panel.fit(
            "[bold green]✓ Configuration complete![/bold green]\n\n"
            f"Config:   [cyan]{config_file}[/cyan]\n"
            f"Memory:   [cyan]{config_dir / 'memory.lance'}[/cyan]\n"
            f"Logs:     [cyan]{config_logs}[/cyan]\n"
            f"Prompt:   [cyan]{system_prompt_dir}/system_prompt.jinja2[/cyan]\n"
            f"Secrets:  [cyan]{env_file}[/cyan]\n"
            f"Compose:  [cyan]{compose_file}[/cyan]\n\n"
            "[dim]Start services with:[/dim]\n"
            f"    [bold red]cd {config_dir} && docker compose up -d[/bold red]\n"
            f"[dim]Then to test:\n"
            f'    [bold white]crow-cli run "hey"[/bold white]',
            border_style="green",
        )
    )


# For typer integration
def init_command(config_dir: Path = None, yes: bool = False):
    """Initialize Crow configuration interactively."""
    if config_dir is None:
        config_dir = Path(os.path.expanduser("~/.crow"))
    run_init(config_dir=config_dir, yes=yes)
