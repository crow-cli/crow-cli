"""Zed-style `agent_servers`: name an agent server in config, launch it in the TUI.

Mirrors Zed's `agent_servers` settings block so an arbitrary ACP agent can be
selected without touching code:

    agent_servers:
      crow-cli:
        type: registry
        default_config_options:
          model: alibaba:qwen3.8-max-preview
      blast:
        type: custom
        command: /usr/bin/python3
        args: ["mock_acp_agent.py"]
        env:
          CROW_MOCK_CHUNKS: "50000"

`registry` entries launch an agent crow-cli knows about (currently crow itself),
optionally pinning config options. `custom` entries launch any command that
speaks ACP over stdio. Both resolve to the same `Agent` definition the TUI
already consumes (agent_schema.Agent), so nothing downstream changes.
"""

from __future__ import annotations

import shlex
import sys
from typing import Any, Literal, NotRequired, TypedDict

from crow_cli.tui.agent_schema import Agent


class AgentServerSpec(TypedDict, total=False):
    """One `agent_servers` entry, as written in config."""

    type: Literal["registry", "custom"]
    """`registry` (default) launches a known agent; `custom` a command."""
    command: str
    """Executable to spawn (`custom`)."""
    args: list[str]
    """Arguments for the executable (`custom`)."""
    env: dict[str, str]
    """Extra environment for the agent subprocess (`custom`)."""
    default_config_options: dict[str, Any]
    """Options applied to the agent, e.g. `model`."""


class AgentServerError(Exception):
    """An `agent_servers` entry is missing or malformed."""


def crow_agent(
    model: str | None = None,
    config_dir: str | None = None,
    config_file: str | None = None,
) -> Agent:
    """The crow-cli agent definition, flags embedded in the launch command.

    Frozen builds call the binary's `acp` subcommand; dev runs call the module.
    """
    args: list[str] = []
    if config_dir is not None:
        args += ["--config-dir", shlex.quote(str(config_dir))]
    if config_file is not None:
        args += ["--config-file", shlex.quote(str(config_file))]
    if model is not None:
        args += ["--model", shlex.quote(model)]
    flag_str = (" " + " ".join(args)) if args else ""

    if getattr(sys, "frozen", False):
        command = f"{shlex.quote(sys.executable)} acp{flag_str}"
    else:
        command = f"{shlex.quote(sys.executable)} -m crow_cli.agent.main{flag_str}"

    return _agent(
        identity="crow-ai.dev",
        name="Crow",
        short_name="crow",
        description="The Crow agent — transparent, observable, self-orchestrating.",
        help="crow-cli's own ACP agent.",
        run_command={"*": command},
    )


def custom_agent(name: str, spec: AgentServerSpec) -> Agent:
    """Build an Agent definition from a `custom` agent_servers entry."""
    command = spec.get("command")
    if not command:
        raise AgentServerError(
            f"agent_servers {name!r}: type 'custom' requires a 'command'."
        )
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


def resolve_agent_server(
    name: str,
    agent_servers: dict[str, Any],
    config_dir: str | None = None,
    config_file: str | None = None,
    model: str | None = None,
) -> Agent:
    """Resolve a configured agent server name into an Agent definition.

    `model` (from -m) overrides the entry's `default_config_options.model`;
    it applies to `registry` entries only — a `custom` entry owns its argv.

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

    kind = spec.get("type", "registry")
    options = spec.get("default_config_options") or {}
    if not isinstance(options, dict):
        raise AgentServerError(
            f"agent_servers {name!r}: 'default_config_options' must be a mapping."
        )
    if kind == "custom":
        agent = custom_agent(name, spec)
    elif kind == "registry":
        agent = crow_agent(
            model=model or options.get("model"),
            config_dir=config_dir,
            config_file=config_file,
        )
    else:
        raise AgentServerError(
            f"agent_servers {name!r}: unknown type {kind!r}; use 'registry' or 'custom'."
        )

    # A configured display name wins over the derived one.
    if display := spec.get("name"):
        agent["name"] = str(display)
    return agent


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
