from importlib.resources import files
import asyncio
import logging
from pathlib import Path
import tomllib

from crow_cli.config import get_default_config_dir, resolve_env_vars
from crow_cli.tui.agent_schema import Agent

logger = logging.getLogger(__name__)


class AgentReadError(Exception):
    """Problem reading the agents."""


def agents_dir(config_dir: Path | str | None = None) -> Path:
    """The user-editable agent store: <config dir>/agents, seeded once from the bundled TOMLs."""
    path = get_default_config_dir(config_dir) / "agents"
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        bundled = files("crow_cli.tui.data").joinpath("agents")
        for entry in bundled.iterdir():
            (path / entry.name).write_bytes(entry.read_bytes())
    return path


async def read_agents(config_dir: Path | str | None = None) -> dict[str, Agent]:
    """Read agent information from <config dir>/agents/*.toml

    Raises:
        AgentReadError: If the files could not be read.

    Returns:
        A mapping of identity on to Agent dict.
    """

    def read_agents() -> list[Agent]:
        """Read agent information.

        Returns:
            List of agent dicts.
        """
        agents: list[Agent] = []
        missing: set[str] = set()
        try:
            for file in sorted(agents_dir(config_dir).glob("*.toml")):
                with file.open("rb") as fh:
                    agent = tomllib.load(fh)
                agent = resolve_env_vars(agent, missing)
                if agent.get("active", True):
                    agents.append(agent)
        except Exception as error:
            raise AgentReadError(f"Failed to read agents; {error}")

        if missing:
            logger.warning(
                "Agent config references unset env vars: %s",
                ", ".join(sorted(missing)),
            )
        return agents

    agents = await asyncio.to_thread(read_agents)
    agent_map = {agent["identity"]: agent for agent in agents}

    return agent_map
