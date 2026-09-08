"""Zed-style `agent_servers`: name an agent server in config, launch it in the TUI.

Mirrors Zed's `agent_servers` settings block so an arbitrary ACP agent can be
selected without touching code:

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
from pathlib import Path
from typing import Any, Literal, TypedDict

from crow_cli.cli.source import spawn_command
from crow_cli.tui.agent_schema import Agent

logger = logging.getLogger(__name__)


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


class AgentServerError(Exception):
    """An `agent_servers` entry is missing or malformed."""


def crow_agent(
    model: str | None = None,
    config_dir: str | None = None,
    config_file: str | None = None,
) -> Agent:
    """Crow's own agent definition, flags embedded in the launch command.

    The fallback when nothing is configured: always the code that is actually
    running (see :func:`crow_cli.cli.source.spawn_command`). Pointing at a
    source checkout is an ``agent_servers`` entry the user writes instead.
    """
    args: list[str] = []
    if config_dir is not None:
        args += ["--config-dir", str(config_dir)]
    if config_file is not None:
        args += ["--config-file", str(config_file)]
    if model is not None:
        args += ["--model", model]

    # spawn_command shell-quotes; hand it raw values.
    command, kind = spawn_command(args)

    return _agent(
        identity="crow-ai.dev",
        name="Crow",
        short_name="crow",
        description="The Crow agent — transparent, observable, self-orchestrating.",
        help=(
            "crow-cli's own ACP agent.\n\n"
            f"Launching from: {'the frozen build' if kind == 'binary' else 'this crow-cli install'}."
        ),
        run_command={"*": command},
    )


def custom_agent(name: str, spec: AgentServerSpec) -> Agent:
    """Build an Agent definition from a `custom` agent_servers entry."""
    command = spec.get("command")
    if not command:
        raise AgentServerError(f"agent_servers {name!r}: requires a 'command'.")
    args = spec.get("args") or []
    if not isinstance(args, list):
        raise AgentServerError(f"agent_servers {name!r}: 'args' must be a list.")

    argv = " ".join([shlex.quote(str(command)), *(shlex.quote(str(a)) for a in args)])
    env = spec.get("env") or {}
    if not isinstance(env, dict):
        raise AgentServerError(f"agent_servers {name!r}: 'env' must be a mapping.")

    return _agent(
        identity=name,
        name=name,
        short_name=name,
        description=f"Custom ACP agent {name}.",
        help=f"Launched from config: `{argv}`",
        run_command={"*": argv},
        env={str(k): str(v) for k, v in env.items()},
    )


def resolve_agent_server(name: str, agent_servers: dict[str, Any]) -> Agent:
    """Resolve a configured agent server name into an Agent definition.

    The entry is honored exactly as written: its command, args and env ARE
    the launch. Crow never substitutes its own agent for a configured one —
    that is what ``-a NAME`` means.

    Raises:
        AgentServerError: The name is not configured, or its entry is invalid.
    """
    if name not in agent_servers:
        known = ", ".join(sorted(agent_servers)) or "none configured"
        raise AgentServerError(
            f"No agent_servers entry named {name!r}. Configured: {known}."
        )
    spec = agent_servers[name] or {}
    if not isinstance(spec, dict):
        raise AgentServerError(f"agent_servers.{name!r} must be a mapping.")

    kind = spec.get("type", "custom")
    if kind != "custom":
        raise AgentServerError(
            f"agent_servers {name!r}: unknown type {kind!r}; an agent server "
            "is a command (type 'custom' or none at all)."
        )

    agent = custom_agent(name, spec)

    # A configured display name wins over the derived one.
    if display := spec.get("name"):
        agent["name"] = str(display)
    return agent


def resolved_agent_servers(config_dir: str | None = None) -> dict[str, Agent]:
    """Every launchable agent: crow's own plus each configured entry.

    Keyed by identity — what the launcher and LaunchAgent messages carry. A
    `custom` entry's identity is its config name; crow's own is
    ``crow-ai.dev``. Entries that fail to resolve are logged and skipped:
    one broken entry must not take down the whole home screen.
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
