"""Execution context objects — the bundles threaded through a turn.

Two lifetimes, deliberately separate:

* :class:`TurnCtx` — one ACP prompt turn. Frozen. Carries what the react loop
  and the tool executors need so call sites stop threading a dozen scalars
  down the stack, and computes the two derived ids (wire session id, ACP tool
  call id) once instead of re-deriving them in every executor.
* :class:`SessionRecord` — one client-facing ACP session. Groups the
  per-session resources that used to live in parallel dicts on the agent.

The key spaces differ on purpose: an ACP ``sessionId`` is stable for a whole
conversation while compaction mints new agent rows inside it, so live sessions
are keyed by ``agent_id`` and per-session resources by wire id — see
:func:`crow_cli.memory.wire_session_id`.
"""

from dataclasses import dataclass, field, replace
from logging import Logger
from typing import TYPE_CHECKING

from acp.interfaces import Client
from acp.schema import ClientCapabilities

from crow_cli.agent.hooks import CommandHook, FileSnapshotHook
from crow_cli.config import Config
from crow_cli.memory import wire_session_id

if TYPE_CHECKING:
    from fastmcp import Client as MCPClient

    from crow_cli.agent.session import AgentSession


@dataclass(frozen=True)
class TurnCtx:
    """Everything one prompt turn needs, fixed for the duration of the turn.

    Frozen: a turn's identity (which agent, which turn, which client) never
    changes mid-turn. Compaction is the one event that swaps the agent row,
    and it does so with :meth:`with_session` rather than by mutation.
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


@dataclass
class SessionRecord:
    """Per-session resources for one client-facing ACP session.

    Replaces six parallel dicts (mcp clients, tools, cancel events, loggers,
    config values, state accumulators). Keyed by wire id upstream — the trunk's
    bare ``session_id``, a fork's full ``agent_id`` — because these resources
    outlive compaction: summarizing a conversation must not drop the MCP
    connection or the pending cancel.
    """

    mcp_client: "MCPClient | None" = None
    tools: list[dict] = field(default_factory=list)
    config_values: dict[str, str] = field(default_factory=dict)
    state_accumulator: dict = field(default_factory=dict)
