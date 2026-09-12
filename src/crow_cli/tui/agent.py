from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from textual.content import Content
from textual.message import Message


class AgentReady(Message):
    """Agent is ready."""


@dataclass
class AgentFail(Message):
    """Agent failed to start."""

    message: str
    details: str = ""
    help: str = "fail"


class AgentBase(ABC):
    """Base class for an 'agent'."""

    def __init__(self, project_root: Path) -> None:
        self.project_root_path = project_root
        super().__init__()

    @abstractmethod
    async def send_prompt(self, prompt: str) -> str | None:
        """Send a prompt to the agent.

        Args:
            prompt: Prompt text.

        Returns:
            str: The stop reason.
        """

    async def set_mode(self, mode_id: str) -> str | None:
        """Put the agent in a new mode.

        Args:
            mode_id: Mode id.

        Returns:
            str: The stop reason.
        """

    async def set_config_option(self, config_id: str, value: str | bool) -> str | None:
        """Set one session config option (model, mode, reasoning level…).

        Config options supersede modes; an agent that publishes them is driven
        entirely from here.

        Args:
            config_id: The option's `id`.
            value: A value id for `select` options, a bool for `boolean` ones.

        Returns:
            str: An error message, or `None` on success.
        """
        return None

    def begin_cancel(self) -> bool:
        """Cancel the current turn without awaiting anything.

        Cancelling has to work while the message pump is saturated, so this is
        synchronous by contract: implementations put `session/cancel` on the
        wire before returning.

        Returns:
            `True` if a cancel was sent, `False` if there was no turn to cancel.
        """
        return False

    async def cancel(self) -> bool:
        """Cancel prompt.

        Returns:
            bool: `True` if success, `False` if the turn wasn't cancelled.

        """
        return False

    async def set_session_name(self, name: str) -> None:
        """Set the session name.

        Args:
            name: New name for the session.
        """

    def get_info(self) -> Content:
        return Content("")

    async def stop(self) -> None:
        """Stop the agent (gracefully exit the process)"""
