"""The `agent_servers` registry: what a CLIENT launches, and how it speaks.

Config-driven, client-side, and the reason ``crow-cli run`` and the TUI can
both launch somebody else's agent without a code change:

    agent_servers:
      crow-execute:
        command: uv
        args: ["--project", "~/.agents/crow/src/crow-cli", "run", "crow-cli", "acp"]
      crow-v2:
        protocol: acp2
        command: uv
        args: ["--project", "~/src/crow-cli", "run", "crow-cli", "acp2"]

Every entry is a command, honored exactly as written — crow never substitutes
its own agent for a configured one. Crow's own agent exists only as the
fallback when nothing is configured (:func:`crow_agent_server`).

``protocol`` is the half that decides which CLIENT drives the entry: ``acp``
(v1, the default, :mod:`crow_cli.client`) or ``acp2`` (v2,
:mod:`crow_cli.client2`). It is declared by the entry because nothing else can
know it — an argv is opaque, and guessing from a substring like ``acp2`` in
``args`` would be a heuristic that fails on the first agent whose path happens
to contain it. A client that speaks only one protocol refuses an entry for the
other rather than launching it and failing the handshake.

``mcpServers`` is the other client-owned half: the tools this agent is handed
at ``session/new``. Absent means the client's global ``mcpServers`` supply,
which is what every session gets today. Present, it REPLACES that supply for
this agent only — which is how a v2 agent gets crow-mcp2 (whose ``execute``
returns the terminal envelope) without changing what the v1 sessions on the
same box are handed. Both shapes are the same mapping the global key uses, so
an entry can be copied between them.

This module knows nothing about the TUI's Agent store schema and nothing about
either wire protocol: it turns config into an argv, an environment and a
protocol name. :mod:`crow_cli.tui.agent_servers` builds the store-facing
``Agent`` TypedDict on top of it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from crow_cli.cli.source import spawn_argv

logger = logging.getLogger(__name__)

#: ACP v1 — :mod:`crow_cli.client`, ``crow-cli acp``.
V1 = "acp"

#: ACP v2 — :mod:`crow_cli.client2`, ``crow-cli acp2``.
V2 = "acp2"

#: What an entry's ``protocol`` may say. Order is the order they are listed in
#: an error message, so the default comes first.
PROTOCOLS = (V1, V2)

#: The identity crow's own agent is listed under, when a client lists the
#: registry plus the fallback. A domain, matching the store's convention.
CROW_IDENTITY = "crow-ai.dev"


class AgentServerError(Exception):
    """An `agent_servers` entry is missing or malformed."""


@dataclass(frozen=True)
class AgentServer:
    """One launchable agent: an argv, an environment, and a protocol.

    ``argv`` is what a client spawns and ``launch`` is what a human reads; the
    list is the truth and the string is decoration, because a shell-quoted
    round trip is how an argv with a space in it gets lost.
    """

    name: str
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    protocol: str = V1
    display_name: str = ""
    mcp_servers: Optional[dict[str, Any]] = None
    builtin: bool = False

    @property
    def argv(self) -> list[str]:
        """The spawn: command then args, exactly as configured."""
        return [self.command, *self.args]

    @property
    def title(self) -> str:
        """What a client shows: the configured display name, else the key."""
        return self.display_name or self.name

    @property
    def launch(self) -> str:
        """The argv as one line, for help text and error messages."""
        return " ".join(self.argv)


def parse_agent_server(name: str, spec: Any) -> AgentServer:
    """Validate one `agent_servers` entry.

    Raises:
        AgentServerError: the entry is not a mapping, has no command, or says
            something untrue about its args, env, protocol or mcpServers.
    """
    if not isinstance(spec, dict):
        raise AgentServerError(f"agent_servers.{name!r} must be a mapping.")

    kind = spec.get("type", "custom")
    if kind != "custom":
        raise AgentServerError(
            f"agent_servers {name!r}: unknown type {kind!r}; an agent server "
            "is a command (type 'custom' or none at all)."
        )

    command = spec.get("command")
    if not command:
        raise AgentServerError(f"agent_servers {name!r}: requires a 'command'.")
    args = spec.get("args") or []
    if not isinstance(args, list):
        raise AgentServerError(f"agent_servers {name!r}: 'args' must be a list.")
    env = spec.get("env") or {}
    if not isinstance(env, dict):
        raise AgentServerError(f"agent_servers {name!r}: 'env' must be a mapping.")

    protocol = spec.get("protocol") or V1
    if protocol not in PROTOCOLS:
        raise AgentServerError(
            f"agent_servers {name!r}: unknown protocol {protocol!r}; expected "
            f"one of {', '.join(PROTOCOLS)}."
        )

    servers = spec.get("mcpServers")
    if servers is not None and not isinstance(servers, dict):
        raise AgentServerError(
            f"agent_servers {name!r}: 'mcpServers' must be a mapping of name to "
            "server, shaped like the global mcpServers key."
        )

    return AgentServer(
        name=name,
        command=str(command),
        args=tuple(str(a) for a in args),
        env={str(k): str(v) for k, v in env.items()},
        protocol=protocol,
        display_name=str(spec["name"]) if spec.get("name") else "",
        mcp_servers=servers,
    )


def resolve_agent_server(name: str, agent_servers: dict[str, Any]) -> AgentServer:
    """Resolve a configured name into an :class:`AgentServer`.

    The entry is honored exactly as written: its command, args and env ARE the
    launch. Crow never substitutes its own agent for a configured one — that is
    what ``-a NAME`` means.

    Raises:
        AgentServerError: the name is not configured, or its entry is invalid.
    """
    if name not in agent_servers:
        known = ", ".join(agent_servers) or "none configured"
        raise AgentServerError(
            f"No agent_servers entry named {name!r}. Configured: {known}."
        )
    return parse_agent_server(name, agent_servers[name] or {})


def parse_agent_servers(agent_servers: dict[str, Any]) -> dict[str, AgentServer]:
    """Every launchable entry, in config order (the top one is the default).

    An entry that fails to resolve is logged and skipped rather than raised:
    one broken entry must not take down the client that lists them.
    """
    servers: dict[str, AgentServer] = {}
    for name in agent_servers or {}:
        try:
            servers[name] = parse_agent_server(name, agent_servers[name] or {})
        except AgentServerError as error:
            logger.warning("agent_servers %r: %s", name, error)
    return servers


def crow_agent_server(
    protocol: str = V1,
    config_dir: Any = None,
    config_file: Any = None,
) -> AgentServer:
    """Crow's own agent, for whichever protocol the client speaks.

    The fallback when nothing is configured: always the code that is actually
    running (see :func:`crow_cli.cli.source.spawn_argv`). Pointing at a source
    checkout is an ``agent_servers`` entry the user writes instead.

    No ``--model`` here on purpose. Model choice is the CLIENT's job: it goes
    over ``session/set_config_option`` once the session exists, which is the one
    path that works for every agent — crow's own and any custom entry alike.
    Baking it into this argv would make ``-m`` work for one agent and silently
    vanish for the others.
    """
    flags: list[str] = []
    if config_dir is not None:
        flags += ["--config-dir", str(config_dir)]
    if config_file is not None:
        flags += ["--config-file", str(config_file)]
    argv, _kind = spawn_argv(flags, protocol)
    return AgentServer(
        name=CROW_IDENTITY,
        command=argv[0],
        args=tuple(argv[1:]),
        protocol=protocol,
        display_name="Crow",
        builtin=True,
    )


def default_agent_server(
    agent_servers: dict[str, Any],
    fallback_protocol: str = V1,
    config_dir: Any = None,
    config_file: Any = None,
) -> AgentServer:
    """The agent a client launches when nobody named one.

    The TOP config entry, which is the rule bare ``crow-cli`` already uses, so
    one config orders both surfaces. Crow's own agent when the registry is
    empty — and then ``fallback_protocol`` decides which of crow's entry points
    a client gets, because there is no entry left to declare it: a v2 client
    asks for ``acp2``, the v1 TUI for ``acp``.
    """
    top = next(iter(parse_agent_servers(agent_servers).values()), None)
    if top is not None:
        return top
    return crow_agent_server(fallback_protocol, config_dir, config_file)


def select_agent_server(
    name: Optional[str],
    agent_servers: dict[str, Any],
    fallback_protocol: str = V1,
    config_dir: Any = None,
    config_file: Any = None,
) -> AgentServer:
    """The agent a client launches: ``-a NAME``, else the default.

    Raises:
        AgentServerError: NAME is not configured, or its entry is invalid. An
            unknown name is an error rather than a fallback, because silently
            launching a different agent than the one asked for is the kind of
            wrong answer nobody notices.
    """
    if name:
        return resolve_agent_server(name, agent_servers)
    return default_agent_server(
        agent_servers, fallback_protocol, config_dir, config_file
    )


def tool_supply(server: AgentServer, config_mcp_servers: dict[str, Any]) -> dict[str, Any]:
    """The mcpServers map a client hands this agent at ``session/new``.

    The entry's own supply when it declares one, else the client's global one.
    The client owns tool supply either way — the agent never reads config for
    this, so what is returned here is exactly what the session gets.
    """
    if server.mcp_servers is not None:
        return server.mcp_servers
    return config_mcp_servers or {}
