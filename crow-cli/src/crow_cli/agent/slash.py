"""
Slash command registry and handlers for crow-cli agent.
"""

import asyncio
import re
from typing import TYPE_CHECKING

from acp import Agent

from crow_cli.agent.compact import compact
from crow_cli.agent.llm import configure_llm

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
async def compact_command(agent_id: str, args: str, agent: Agent):
    """Compact the conversation."""

    session = agent._sessions.get(agent_id)
    if not session:
        return "Error: AgentSession not found"

    # Check if there's enough conversation to compact
    if len(session.messages) < 3:
        return f"Not enough conversation history to compact. Current message count: {len(session.messages)} (need at least 3: system + 2 messages)"

    agent._session_logger.info(
        f"Compacting agent {agent_id} with {len(session.messages)} messages"
    )

    try:
        # Get current model for compaction
        current_config = agent._config_values.get(agent_id, {})
        current_model_value = (
            current_config.get("model") or agent._default_model_value()
        )
        provider_name = (
            current_model_value.split(":", 1)[0] if ":" in current_model_value else ""
        )

        provider = agent._config.llm.providers.get(provider_name)
        if not provider and agent._config.llm.providers:
            provider = next(iter(agent._config.llm.providers.values()))
        if not provider:
            return "Error: No LLM provider configured"

        llm = configure_llm(provider=provider, debug=False)

        def on_compact(old_agent_id, compacted_session):
            new_agent_id = compacted_session.agent_id
            agent._sessions[new_agent_id] = compacted_session
            agent._agent_id = new_agent_id
            agent._session_logger.info(
                f"on_compact callback: updated agent_id {old_agent_id} -> {new_agent_id}, "
                f"{len(compacted_session.messages)} messages"
            )

        agent._session_logger.info(
            f"Before compact: session.messages has {len(session.messages)} messages"
        )
        result_session = await compact(
            session=session,
            llm=llm,
            cwd=session.cwd,
            on_compact=on_compact,
            logger=agent._session_logger,
        )
        agent._session_logger.info(
            f"After compact: session.messages has {len(session.messages)} messages, result_session.messages has {len(result_session.messages)} messages"
        )
        agent._session_logger.info(f"AgentSession same object: {session is result_session}")

        return f"Conversation compacted successfully! Reduced from {len(session.messages)} messages."
    except Exception as e:
        agent._session_logger.error(f"Compact failed: {e}", exc_info=True)
        return f"Error during compaction: {str(e)}"


@register_slash_command("help", "Show available slash commands")
async def help_command(session_id: str, args: str, agent: Agent):
    """Show available slash commands."""

    lines = ["Available slash commands:"]
    for cmd in _SLASH_COMMANDS:
        lines.append(f"  /{cmd['name']} - {cmd['description']}")
    return "\n".join(lines)


@register_slash_command("clear", "Clear the session context")
async def clear_command(agent_id: str, args: str, agent: Agent):
    """Clear the session context."""
    if agent_id in agent._sessions:
        session = agent._sessions[agent_id]
        # Keep system message, clear rest
        if session.messages and len(session.messages) > 0:
            # Keep first message (system prompt)
            system_msg = session.messages[0]
            session.messages = [system_msg]
        return "AgentSession context cleared."
    return "AgentSession not found."


@register_slash_command("stop", "Stop current operation")
async def stop_command(agent_id: str, args: str, agent: Agent):
    """Stop current operation."""
    if agent_id in agent._prompt_tasks:
        agent._prompt_tasks[agent_id].cancel()
        return "Operation stopped."
    return "No active operation to stop."


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
