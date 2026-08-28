"""
Slash command registry and handlers for crow-cli agent.

Every handler takes the live session, the raw argument string and the agent:

    async def command(session: AgentSession, args: str, agent: AcpAgent) -> str

The returned string is what the client sees, so a handler must not raise — an
exception turns into an ACP internal error (``RequestError``), which the client
reads as a failed turn. Handlers resolve per-session state through the agent's
registries, keyed by the **wire session id** (``session.session_id``); the
generation-keyed ``session.agent_id`` names an agent row and changes under
compaction, so it is never a registry key.
"""

import re
from typing import TYPE_CHECKING

from crow_cli.agent.compact import compact
from crow_cli.agent.llm import configure_llm

if TYPE_CHECKING:
    from crow_cli.agent.main import AcpAgent
    from crow_cli.agent.session import AgentSession

# Slash command registry
_SLASH_COMMANDS = []


def register_slash_command(name: str, description: str):
    """Decorator to register a slash command."""

    def decorator(func):
        _SLASH_COMMANDS.append({"name": name, "description": description, "func": func})
        return func

    return decorator


@register_slash_command(
    "compact", "Compact the conversation history to reduce context size"
)
async def compact_command(session: AgentSession, args: str, agent: AcpAgent) -> str:
    """Summarize the conversation into a new agent generation.

    The same path the react loop takes when the token threshold is crossed:
    ``compact()`` writes a new agent row inside the wire session id and the old
    history stays untouched. The DB is already authoritative by the time
    ``on_compact`` fires, so the only bookkeeping here is caching the live object.
    """
    logger = agent._logger_for(session.session_id)

    if len(session.messages) < 3:
        return (
            "Not enough conversation history to compact. "
            f"Current message count: {len(session.messages)} "
            "(need at least 3: system + 2 messages)"
        )

    # Model resolution mirrors the react loop: this session's configured model,
    # falling back to the agent default (-m or first in config.yaml).
    config_values = agent._config_values.get(session.session_id, {})
    model_value = config_values.get("model") or agent._default_model_value()
    provider_name = model_value.split(":", 1)[0] if ":" in model_value else ""
    provider = agent._config.llm.providers.get(provider_name)
    if not provider and agent._config.llm.providers:
        provider = next(iter(agent._config.llm.providers.values()))
    if not provider:
        return "Error: No LLM provider configured"

    def on_compact(old_agent_id: str, compacted_session: AgentSession) -> None:
        agent._sessions[compacted_session.agent_id] = compacted_session
        logger.info(
            "Compacted %s -> %s (%d messages)",
            old_agent_id,
            compacted_session.agent_id,
            len(compacted_session.messages),
        )

    before = len(session.messages)
    try:
        llm = configure_llm(
            provider=provider, debug=agent._config.chunk_log, logger=logger
        )
        result = await compact(
            session=session,
            llm=llm,
            config=agent._config,
            on_compact=on_compact,
            logger=logger,
        )
    except Exception as exc:
        logger.error("Compaction failed: %s", exc, exc_info=True)
        return f"Error during compaction: {exc}"

    return (
        f"Conversation compacted: {before} messages -> {len(result.messages)} "
        f"(agent {session.agent_id} -> {result.agent_id})"
    )


@register_slash_command("help", "Show available slash commands")
async def help_command(session: AgentSession, args: str, agent: AcpAgent) -> str:
    """Show available slash commands."""

    lines = ["Available slash commands:"]
    for cmd in _SLASH_COMMANDS:
        lines.append(f"  /{cmd['name']} - {cmd['description']}")
    return "\n".join(lines)


@register_slash_command("clear", "Clear the session context")
async def clear_command(session: AgentSession, args: str, agent: AcpAgent) -> str:
    """Clear the session context."""
    # Keep system message, clear rest
    if session.messages and len(session.messages) > 0:
        # Keep first message (system prompt)
        system_msg = session.messages[0]
        session.messages = [system_msg]
    return "AgentSession context cleared."


@register_slash_command("stop", "Stop current operation")
async def stop_command(session: AgentSession, args: str, agent: AcpAgent) -> str:
    """Stop current operation."""
    task = agent._prompt_tasks.get(session.session_id)
    if task:
        task.cancel()
        return "Operation stopped."
    return "No active operation to stop."
    """Decorator to register a slash command."""

    def decorator(func):
        _SLASH_COMMANDS.append({"name": name, "description": description, "func": func})
        return func

    return decorator


def parse_slash_command(text: str) -> tuple[str, str] | None:
    """Parse slash command from text. Returns (command_name, args) or None."""
    text = text.strip()
    if not text or not text.startswith("/"):
        return None

    match = re.match(r"^\/([a-zA-Z0-9_-]+)\s*(.*)", text)
    if not match:
        return None

    return (match.group(1), match.group(2).strip())


def get_slash_commands():
    """Get the list of registered slash commands."""
    return _SLASH_COMMANDS
