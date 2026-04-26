import asyncio
import sys
from pathlib import Path

# Patch acp.stdio to avoid asyncio pipe transport bugs on this system
# import acp.stdio as _acp_stdio
# async def _patched_posix_stdio_streams(loop, limit=None):
#     reader = asyncio.StreamReader(limit=limit) if limit is not None else asyncio.StreamReader()
#     _acp_stdio._start_stdin_feeder(loop, reader)
#     write_protocol = _acp_stdio._WritePipeProtocol()
#     transport = _acp_stdio._StdoutTransport()
#     writer = asyncio.StreamWriter(transport, write_protocol, None, loop)
#     return reader, writer
# _acp_stdio._posix_stdio_streams = _patched_posix_stdio_streams
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
    config.db_uri = "sqlite:////home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent/.crow/crow-from-scratch.db"
    config.MAX_COMPACT_TOKENS = 990_000

    agent = AcpAgent(config, hooks=[uv_project_hook])

    await run_agent(agent)


def main():
    asyncio.run(agent_run())


if __name__ == "__main__":
    main()
