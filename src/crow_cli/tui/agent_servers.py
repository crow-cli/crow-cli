"""Zed-style `agent_servers`, presented as the TUI's `Agent` store schema.

The registry itself — parsing, validation, protocol declaration, crow's own
fallback — lives in :mod:`crow_cli.agents`, which is client-side and knows
nothing about the TUI. This module is the adapter: it turns a resolved
:class:`~crow_cli.agents.AgentServer` into the `Agent` TypedDict the store
screen and the launcher consume, and it enforces the one thing only a v1 client
can know about itself.

**The TUI speaks ACP v1.** An entry that declares ``protocol: acp2`` is not
launchable from here, so it is refused rather than spawned into a handshake
that cannot complete: ``-a NAME`` raises, and the store listing skips it with a
warning. ``crow-cli run -a NAME`` is the client that drives v2 agents, and the
error says so.

    agent_servers:
      crow-execute:
        command: uv
        args: ["--project", "~/.agents/crow/src/crow-cli", "run", "crow-cli", "acp"]
      blast:
        command: /usr/bin/python3
        args: ["mock_acp_agent.py"]
        env:
          CROW_MOCK_CHUNKS: "50000"

Every entry is a command, honored exactly as written — crow never substitutes
its own agent for a configured one. Crow's own agent exists only as the
fallback when nothing is configured (see :func:`crow_agent`). Entries resolve
to the same `Agent` definition the TUI already consumes (agent_schema.Agent),
so nothing downstream changes.
"""

from __future__ import annotations

import logging
import shlex
import sys
from pathlib import Path
from typing import Any, Literal, TypedDict

from crow_cli.agents import (
    CROW_IDENTITY,
    V1,
    AgentServer,
    AgentServerError,
    crow_agent_server,
    parse_agent_server,
)
from crow_cli.agents import resolve_agent_server as _resolve_agent_server
from crow_cli.tui.agent_schema import Agent

logger = logging.getLogger(__name__)

__all__ = [
    "AgentServerError",
    "AgentServerSpec",
    "agent_from_server",
    "crow_agent",
    "custom_agent",
    "resolve_agent_server",
    "resolved_agent_servers",
]


class AgentServerSpec(TypedDict, total=False):
    """One `agent_servers` entry, as written in config."""

    type: Literal["custom"]
    """Optional — an entry is a command; ``custom`` is the only kind now."""
    command: str
    """Executable to spawn."""
    args: list[str]
    """Arguments for the executable."""
    env: dict[str, str]
    """Extra environment for the agent subprocess."""
    name: str
    """Optional display name; the config key stays the identity either way."""
    protocol: Literal["acp", "acp2"]
    """Which ACP the agent speaks. Optional, defaults to ``acp`` (v1) — and
    ``acp2`` is refused here, because this client is v1."""
    mcpServers: dict[str, Any]
    """Optional tool supply for this agent, shaped like the global key. Absent
    means the client's global ``mcpServers``."""


def crow_agent(
    config_dir: str | None = None,
    config_file: str | None = None,
) -> Agent:
    """Crow's own agent definition, flags embedded in the launch command.

    The fallback when nothing is configured: always the code that is actually
    running, and always v1 — the TUI is a v1 client, and crow's v2 agent is
    what ``crow-cli run`` falls back to instead.

    No ``--model`` here on purpose. Model choice is the CLIENT's job: it goes
    over ACP ``session/set_config_option`` once the session exists, which is
    the one path that works for every agent — crow's own and any custom
    ``agent_servers`` entry alike. Baking it into this argv would make ``-m``
    work for one agent and silently vanish for the others.
    """
    server = crow_agent_server(V1, config_dir, config_file)
    launching = "the frozen build" if getattr(sys, "frozen", False) else (
        "this crow-cli install"
    )
    return _agent(
        identity=CROW_IDENTITY,
        name="Crow",
        short_name="crow",
        description="The Crow agent — transparent, observable, self-orchestrating.",
        help=(
            "crow-cli's own ACP agent.\n\n"
            f"Launching from: {launching}."
        ),
        run_command={"*": _quoted(server.argv)},
    )


def custom_agent(name: str, spec: AgentServerSpec) -> Agent:
    """Build an Agent definition from a `custom` agent_servers entry."""
    return agent_from_server(parse_agent_server(name, spec))


def agent_from_server(server: AgentServer) -> Agent:
    """The store-facing definition for a resolved server.

    An entry that declares no protocol is driven as v1, which is what this
    client speaks and what such an entry meant before the handshake could be
    asked. Only an entry that declares the other one is refused.

    Raises:
        AgentServerError: the agent speaks a protocol this client does not.
    """
    if server.protocol not in (None, V1):
        raise AgentServerError(
            f"agent_servers {server.name!r} speaks {server.protocol}, which the "
            "TUI does not — drive it with `crow-cli run -a "
            f"{server.name}` instead."
        )
    argv = _quoted(server.argv)
    return _agent(
        identity=server.name,
        name=server.title,
        short_name=server.name,
        description=f"Custom ACP agent {server.name}.",
        help=f"Launched from config: `{argv}`",
        run_command={"*": argv},
        env=server.env,
    )


def resolve_agent_server(name: str, agent_servers: dict[str, Any]) -> Agent:
    """Resolve a configured agent server name into an Agent definition.

    The entry is honored exactly as written: its command, args and env ARE
    the launch. Crow never substitutes its own agent for a configured one —
    that is what ``-a NAME`` means.

    Raises:
        AgentServerError: The name is not configured, its entry is invalid, or
            it declares a protocol this client does not speak.
    """
    return agent_from_server(_resolve_agent_server(name, agent_servers))


def resolved_agent_servers(config_dir: str | None = None) -> dict[str, Agent]:
    """Every agent this client can launch: crow's own plus each v1 entry.

    Keyed by identity — what the launcher and LaunchAgent messages carry. A
    `custom` entry's identity is its config name; crow's own is
    ``crow-ai.dev``. Entries that fail to resolve are logged and skipped: one
    broken entry (or one v2 agent) must not take down the whole home screen.
    """
    from crow_cli.config import Config

    config = Config.load(config_dir=Path(config_dir) if config_dir else None)
    agents: dict[str, Agent] = {}
    default = crow_agent()
    agents[default["identity"]] = default
    for name in config.agent_servers:
        try:
            agent = resolve_agent_server(name, config.agent_servers)
        except AgentServerError as error:
            logger.warning("agent_servers %r: %s", name, error)
            continue
        if (identity := agent["identity"]) not in agents:
            agents[identity] = agent
    return agents


def _quoted(argv: list[str]) -> str:
    """An argv as one shell-safe line — the shape `run_command` carries."""
    return " ".join(shlex.quote(a) for a in argv)


def _agent(
    *,
    identity: str,
    name: str,
    short_name: str,
    description: str,
    help: str,
    run_command: dict[str, str],
    env: dict[str, str] | None = None,
) -> Agent:
    agent: Agent = {
        "identity": identity,
        "name": name,
        "short_name": short_name,
        "url": "https://crow-ai.dev",
        "protocol": "acp",
        "type": "chat",
        "author_name": "Crow AI",
        "author_url": "https://crow-ai.dev",
        "publisher_name": "Crow AI",
        "publisher_url": "https://crow-ai.dev",
        "description": description,
        "tags": [],
        "help": help,
        "run_command": run_command,  # type: ignore[typeddict-item]
        "actions": {},
    }
    if env:
        agent["env"] = env
    return agent
