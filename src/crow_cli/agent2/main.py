"""Entry point: run :class:`~crow_cli.agent2.agent.CrowAgentV2` over stdio.

Deliberately smaller than v1's. ``agent/main.py`` carried the agent class, the
HTTP server, the argparse block and the ``use_unstable_protocol`` flag that
unlocked ``session/fork``; here the agent is its own module and v2 has no
unstable-method gate to open — a method is available if the object has it, and
``MethodRouter`` answers ``method_not_found`` for the rest.

One thing worth knowing: ``run_agent`` builds the connection and then calls
``on_connect`` synchronously, so the agent has its connection before the first
request arrives. Cleanup runs in a ``finally`` because a stdio agent is killed
by its client far more often than it exits on its own, and the MCP clients it
spawned are child processes.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any, Optional

from acp.experimental.v2.agent import run_agent

from crow_cli.agent.hooks import CommandHook
from crow_cli.agent.prompt import SystemPromptFactory
from crow_cli.config import Config, apply_config_overrides

from .agent import CrowAgentV2


async def agent_run(
    config_dir: Optional[Path] = None,
    config: Optional[Config] = None,
    config_file: Optional[Path] = None,
    debug: bool = False,
    model: Optional[str] = None,
    hooks: Optional[list[CommandHook]] = None,
    system_prompt: Optional[SystemPromptFactory] = None,
    compactor: Any = None,
    compact_system_prompt: Any = None,
) -> None:
    """Build the agent and serve it on stdin/stdout until the client lets go."""
    if config is None:
        config = Config.load(config_dir=config_dir)
        config = apply_config_overrides(config, config_file)
    if debug:
        config.chunk_log = True
    agent = CrowAgentV2(
        config,
        hooks=hooks,
        model=model,
        system_prompt=system_prompt,
        compactor=compactor,
        compact_system_prompt=compact_system_prompt,
    )
    try:
        await run_agent(agent)
    finally:
        await agent.cleanup()


def main(
    config_dir: Optional[Path] = None,
    config: Optional[Config] = None,
    config_file: Optional[Path] = None,
    debug: bool = False,
    model: Optional[str] = None,
) -> None:
    asyncio.run(
        agent_run(
            config_dir=config_dir,
            config=config,
            config_file=config_file,
            debug=debug,
            model=model,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", type=Path, default=None)
    parser.add_argument("--config-file", type=Path, default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args()
    main(
        config_dir=args.config_dir,
        config_file=args.config_file,
        debug=args.debug,
        model=args.model,
    )
