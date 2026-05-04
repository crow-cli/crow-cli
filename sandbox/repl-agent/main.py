import asyncio
import sys
from pathlib import Path

import typer
from acp import run_agent
from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.hooks import uv_project_hook
from crow_cli.agent.main import AcpAgent

app = typer.Typer()


@app.command()
def agent_run(
    config_dir: Path = typer.Option(
        Path("/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow-test"),
        "--config-dir",
        "-d",
        help="Configuration directory",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable chunk-level JSONL logging for debugging",
    ),
) -> None:
    config = Config.load(config_dir=config_dir)
    # Move the home directory
    config.db_uri = f"sqlite:///{config_dir}/crow-agent-1.db"
    config.MAX_COMPACT_TOKENS = 190_000
    if debug:
        config.chunk_log = True
    # Pass custom hooks: e.g. just uv_project_hook, or [] for none,
    # or define your own CommandHook functions.
    agent = AcpAgent(config, hooks=[uv_project_hook])

    await run_agent(agent)


def main():
    app()


if __name__ == "__main__":
    main()
