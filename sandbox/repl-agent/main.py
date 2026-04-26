import asyncio
import sys
from pathlib import Path

from acp import run_agent
from crow_cli.agent.configure import Config, get_default_config_dir
from crow_cli.agent.hooks import uv_project_hook
from crow_cli.agent.main import AcpAgent


async def agent_run() -> None:
    config_dir = get_default_config_dir()
    config = Config.load(config_dir=config_dir)
    # Move the home directory
    config.config_dir = Path(
        "/home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow"
    )
    config.db_uri = "sqlite:////home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/crow-agent.db"
    config.murder_db_uri = "sqlite:////home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/crow-snapshots.db"
    config.MAX_COMPACT_TOKENS = 190_000

    # Pass custom hooks: e.g. just uv_project_hook, or [] for none,
    # or define your own CommandHook functions.
    agent = AcpAgent(config, hooks=[uv_project_hook])

    await run_agent(agent)


def main():
    asyncio.run(agent_run())


if __name__ == "__main__":
    main()
