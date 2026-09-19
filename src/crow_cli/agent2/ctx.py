"""Execution context for one turn.

v1's ``TurnCtx`` carried the ACP connection and the client's advertised
capabilities, and grew three derived gates around them —
``terminal_via_client``, ``writes_via_client``, ``reads_via_client`` — because
v1 could optionally execute filesystem and terminal work *in the client*.

v2 deleted that entire surface: ``clientCapabilities.fs``,
``fs/read_text_file``, ``fs/write_text_file``, ``clientCapabilities.terminal``
and ``terminal/create|output|release|wait_for_exit|kill`` are all gone.
Clients expose tools by advertising MCP servers instead. So those three gates
would be constant False forever, and every branch behind them dead. They are
not ported; they are deleted, along with the ``caps`` field that fed them.

What replaces ``conn`` is the :class:`~crow_cli.agent2.emitter.Emitter` — the
turn no longer holds a protocol connection, it holds the one object that knows
how to speak v2.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from logging import Logger
from typing import TYPE_CHECKING

from crow_cli.agent.hooks import CommandHook
from crow_cli.config import Config
from crow_cli.memory import wire_session_id

from .emitter import Emitter

if TYPE_CHECKING:
    from crow_cli.agent.session import AgentSession


@dataclass(frozen=True)
class TurnCtx:
    """Everything one turn needs, fixed for its duration.

    Frozen because a turn's identity never changes mid-turn. Compaction is
    the one event that swaps the agent row, and it does so with
    :meth:`with_session` rather than by mutation.

    Shared per-session resources — MCP clients, tools, cancel events, stream
    state — are deliberately NOT fields. They live in the driver's registries
    and are resolved at call time, because they outlive a turn, are replaced
    when a session is resumed or a second client attaches, and are torn down
    by the agent's exit stack. Caching one here would freeze a single turn's
    resolution and outlive the object it came from.
    """

    emitter: Emitter
    config: Config
    session: "AgentSession"
    turn_id: str
    logger: Logger
    hooks: tuple[CommandHook, ...] = ()

    @property
    def agent_id(self) -> str:
        return self.session.agent_id

    @property
    def session_id(self) -> str:
        """The ACP wire sessionId this turn reports against."""
        return wire_session_id(self.session.agent_id)

    @property
    def cwd(self) -> str:
        return self.session.cwd

    def tcid(self, llm_tool_call_id: str) -> str:
        """ACP toolCallId for an LLM tool call: ``<turn_id>/<llm id>``.

        The LLM's own ids repeat across turns and across providers; prefixing
        with the turn keeps every tool call in a session uniquely addressable,
        which matters now that ``tool_call_update`` is an upsert keyed on that
        id — a collision would silently patch the wrong call.
        """
        return f"{self.turn_id}/{llm_tool_call_id}" if self.turn_id else llm_tool_call_id

    def with_session(self, session: "AgentSession") -> "TurnCtx":
        """A copy bound to a different agent row.

        Used after compaction: the wire sessionId is unchanged (compaction
        forks ``agent_idx`` inside a stable session) but every later write in
        this turn must land on the new agent. A wake arriving after compaction
        targets the *session*; this is where it resolves to the current row.
        """
        return replace(self, session=session)
