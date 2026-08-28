"""Execution context for one ACP prompt turn.

:class:`TurnCtx` is the frozen bundle threaded from the react loop into the tool
executors, so call sites stop shuttling a dozen scalars down the stack and the
two derived ids (wire sessionId, ACP toolCallId) are computed once instead of
re-derived in every executor.

What belongs here: values fixed for the duration of a turn and local to the
tenant running it — the connection the prompt arrived on, the agent row it
belongs to, the turn id, the logger, the client's advertised capabilities.

What deliberately does NOT: shared per-session resources. MCP clients, tools,
cancel events, loggers, config values and stream accumulators stay in the
agent's registries — keyed by wire session id and resolved at call time,
because they are shared across sessions, replaced when a session is re-loaded
or a second connection attaches, and torn down by the agent's exit stack.
Caching one into a turn would freeze a single tenant's resolution and outlive
the object it came from.

Key spaces differ on purpose: an ACP ``sessionId`` is stable for a whole
conversation while compaction mints new agent rows inside it, so live sessions
are keyed by ``agent_id`` and per-session resources by wire id — see
:func:`crow_cli.memory.wire_session_id`.
"""

from dataclasses import dataclass, replace
from logging import Logger
from typing import TYPE_CHECKING

from acp.interfaces import Client
from acp.schema import ClientCapabilities

from crow_cli.agent.hooks import CommandHook, FileSnapshotHook
from crow_cli.config import Config
from crow_cli.memory import wire_session_id

if TYPE_CHECKING:
    from crow_cli.agent.session import AgentSession


@dataclass(frozen=True)
class TurnCtx:
    """Everything one prompt turn needs, fixed for the duration of the turn.

    Frozen: a turn's identity — which agent row, which turn, which connection —
    never changes mid-turn. Compaction is the one event that swaps the agent
    row, and it does so with :meth:`with_session` rather than by mutation.
    Shared per-session resources are not fields on this class; see the module
    docstring for why.
    """

    conn: Client
    config: Config
    session: "AgentSession"
    turn_id: str
    logger: Logger
    caps: ClientCapabilities | None = None
    hooks: tuple[CommandHook, ...] = ()
    snapshot_hooks: tuple[FileSnapshotHook, ...] = ()

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

        Falls back to the bare LLM id when there is no turn id (headless
        callers that never mint one).
        """
        return f"{self.turn_id}/{llm_tool_call_id}" if self.turn_id else llm_tool_call_id

    # Capability gates — computed from the client's advertised capabilities so
    # executors can branch on `ctx.writes_via_client` instead of digging
    # through ClientCapabilities.fs themselves.

    @property
    def terminal_via_client(self) -> bool:
        return bool(self.caps and getattr(self.caps, "terminal", False))

    @property
    def writes_via_client(self) -> bool:
        fs = getattr(self.caps, "fs", None) if self.caps else None
        return bool(fs and getattr(fs, "write_text_file", False))

    @property
    def reads_via_client(self) -> bool:
        fs = getattr(self.caps, "fs", None) if self.caps else None
        return bool(fs and getattr(fs, "read_text_file", False))

    def with_session(self, session: "AgentSession") -> "TurnCtx":
        """A copy of this turn bound to a different agent row.

        Used after compaction: the wire sessionId is unchanged (compaction
        forks ``agent_idx`` inside a stable session), but every subsequent
        write in this turn must land on the new agent.
        """
        return replace(self, session=session)
