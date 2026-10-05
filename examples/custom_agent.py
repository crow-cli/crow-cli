"""One custom agent, four ways to serve it.

A single pair of callables — a system prompt and a compaction strategy — is
everything crow needs to run your agent. This file plugs the same pair into
both runtimes (v1 ``AcpAgent``, v2 ``CrowAgentV2``) and both transports
(stdio, Streamable HTTP + WebSocket), so the runtime/transport choice is the
only thing that changes between the four subcommands.

The two callable contracts are spelled out in depth in
``examples/custom_compactor.py``; here they are kept short so the matrix is
what stands out. They are the SAME contracts on both runtimes — v2 reuses
``crow_cli.agent.prompt.SystemPromptFactory`` and
``crow_cli.agent.compact.Compactor`` verbatim.

Run:

    uv run python examples/custom_agent.py v1-stdio --config-dir ~/.agents/crow
    uv run python examples/custom_agent.py v1-http --config-dir ~/.agents/crow
    uv run python examples/custom_agent.py v2-stdio --config-dir ~/.agents/crow
    uv run python examples/custom_agent.py v2-http --config-dir ~/.agents/crow

``*-http`` serve Streamable HTTP at ``http://127.0.0.1:<port>/acp``. Streamable
HTTP requires HTTP/2, so they run hypercorn (already a crow-cli dependency),
not a plain WSGI server.
"""

import asyncio
from pathlib import Path

import typer
from acp import run_agent as run_agent_v1
from acp.experimental.v2.agent import run_agent as run_agent_v2

from crow_cli.agent.compact import CompactCtx, CompactResponse, default_compactor
from crow_cli.agent.hooks import uv_project_hook
from crow_cli.agent.main import AcpAgent
from crow_cli.agent.prompt import SystemPromptResponse, default_system_prompt
from crow_cli.agent2.agent import CrowAgentV2
from crow_cli.config import Config

app = typer.Typer()


# ---------------------------------------------------------------------------
# Contract 1: the system prompt. ``session/new`` renders this template once
# and stores it; everything that varies goes in ``template_args``.
# ---------------------------------------------------------------------------

TEMPLATE = """You are the operator for {{ workspace }}, generation {{ generation }}.

{{ display_tree }}
"""


def init_sys(config: Config, cwd: str, session_id: str | None = None) -> SystemPromptResponse:
    base = default_system_prompt(config, cwd, session_id)
    return SystemPromptResponse(
        template=TEMPLATE,
        template_args={**base.template_args, "generation": 1},
    )


def compact_sys(ctx: CompactCtx) -> SystemPromptResponse:
    fresh = default_system_prompt(ctx.config, ctx.session.cwd, ctx.session.session_id)
    return SystemPromptResponse(
        template=TEMPLATE,
        template_args={**fresh.template_args, "generation": ctx.session.agent_idx + 1},
    )


# ---------------------------------------------------------------------------
# Contract 2: compaction. Take the default summary, then tack on one line of
# the successor's handoff. ``ctx.system_prompt`` is ``compact_sys`` above.
# ---------------------------------------------------------------------------

async def custom_compactor(ctx: CompactCtx) -> CompactResponse:
    summary = await default_compactor(ctx)
    system_prompt = ctx.system_prompt(ctx)
    return CompactResponse(
        system_template=system_prompt.template,
        system_args=system_prompt.template_args,
        prompt=summary.prompt + "\n\nCarry on as the operator.",
    )


# ---------------------------------------------------------------------------
# The four servings. Everything above is transport- and runtime-agnostic; only
# these tails differ.
# ---------------------------------------------------------------------------

def _v1_agent(config: Config) -> AcpAgent:
    return AcpAgent(
        config,
        hooks=[uv_project_hook],
        system_prompt=init_sys,
        compactor=custom_compactor,
        compact_system_prompt=compact_sys,
    )


def _v2_agent(config: Config) -> CrowAgentV2:
    return CrowAgentV2(
        config,
        hooks=[uv_project_hook],
        system_prompt=init_sys,
        compactor=custom_compactor,
        compact_system_prompt=compact_sys,
    )


@app.command("v1-stdio")
def v1_stdio(
    config_dir: Path = typer.Option(..., "--config-dir", "-d"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """One v1 agent per process, on stdin/stdout."""
    config = Config.load(config_dir=config_dir)
    if debug:
        config.chunk_log = True
    asyncio.run(run_agent_v1(_v1_agent(config), use_unstable_protocol=True))


@app.command("v1-http")
def v1_http(
    config_dir: Path = typer.Option(..., "--config-dir", "-d"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(2769, "--port"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """One v1 agent per connection, over Streamable HTTP + WebSocket."""
    config = Config.load(config_dir=config_dir)
    if debug:
        config.chunk_log = True
    asyncio.run(_v1_http(config, host, port))


async def _v1_http(config: Config, host: str, port: int) -> None:
    import hypercorn.asyncio
    from acp.http.asgi import create_asgi_app
    from hypercorn.config import Config as HypercornConfig

    # A factory, not an instance: HTTP mints one agent per connection.
    app = create_asgi_app(lambda conn: _v1_agent(config))
    hcfg = HypercornConfig()
    hcfg.bind = [f"{host}:{port}"]
    hcfg.alpn_protocols = ["h2", "http/1.1"]  # Streamable HTTP requires HTTP/2
    await hypercorn.asyncio.serve(app, hcfg)


@app.command("v2-stdio")
def v2_stdio(
    config_dir: Path = typer.Option(..., "--config-dir", "-d"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """One v2 agent per process, on stdin/stdout."""
    config = Config.load(config_dir=config_dir)
    if debug:
        config.chunk_log = True
    asyncio.run(_v2_stdio(config))


async def _v2_stdio(config: Config) -> None:
    agent = _v2_agent(config)
    try:
        await run_agent_v2(agent)
    finally:
        await agent.cleanup()


@app.command("v2-http")
def v2_http(
    config_dir: Path = typer.Option(..., "--config-dir", "-d"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(2771, "--port"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """One v2 agent per connection, over Streamable HTTP + WebSocket."""
    from crow_cli.agent2.main import serve_http

    config = Config.load(config_dir=config_dir)
    if debug:
        config.chunk_log = True
    asyncio.run(
        serve_http(
            config,
            None,
            host,
            port,
            hooks=[uv_project_hook],
            system_prompt=init_sys,
            compactor=custom_compactor,
            compact_system_prompt=compact_sys,
        )
    )


if __name__ == "__main__":
    app()
