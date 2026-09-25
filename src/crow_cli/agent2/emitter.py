"""The one place agent2 touches ACP v2 schema.

Every other module in this package speaks plain Python — dicts, strings,
bytes, dataclasses — and calls a method here. That is deliberate: v1 spread
``conn.session_update(...)`` across 42 call sites in react.py and tools.py
*and* yielded ``{"type": ...}`` dicts that ``AcpAgent.prompt`` interleaved
into the same wire stream. Two output channels for one protocol. agent2 has
one. The react loop yields nothing.

Consequences worth knowing before editing this file:

* **v2 has no ``tool_call``.** Only ``tool_call_update``, whose
  ``toolCallId`` creates on first sight and patches thereafter (omitted =
  unchanged, null = cleared, value = replaced). v1's create/patch split —
  ``start_tool_call`` / ``update_tool_call`` — collapses into :meth:`tool_call`.
* **``messageId`` is required** on every content chunk, and all chunks of one
  message share it. The caller mints via :meth:`start_message` and signals
  boundaries; the emitter never guesses where a message ended.
* **Diffs are structured.** ``Diff.changes`` carries absolute paths and
  ``Diff.patch`` the unified text; our edit/write results already produce a
  real diff, so ``patch.text`` is a pass-through and ``changes`` derives from
  the operation.
* **Terminals are agent-owned display state**, not a client resource. v2
  deleted ``clientCapabilities.terminal`` along with ``terminal/create`` and
  friends; what remains is :meth:`terminal` (upsert state) and
  :meth:`terminal_chunk` (stream raw PTY bytes, base64, ANSI intact) for the
  client to render, while the LLM gets ANSI-stripped text through
  ``raw_output``. Two audiences, one execution.
"""

from __future__ import annotations

import base64
import logging
import uuid
from typing import Any, Literal, Optional, Sequence

from acp.experimental.v2 import schema as v2
from acp.experimental.v2.agent import AgentSideConnection

logger = logging.getLogger(__name__)

ToolCallStatus = Literal["pending", "in_progress", "completed", "failed", "cancelled"]
ToolKind = Literal["read", "edit", "delete", "move", "search", "execute", "think", "fetch", "other"]
CompactionStatus = Literal["in_progress", "completed", "failed", "cancelled"]


def present(**fields: Any) -> dict[str, Any]:
    """The kwargs to build an update with, minus the ones that are ``None``.

    The connection serializes with ``exclude_unset``, and since python-sdk
    1.0.0rc2 with nothing else — that release dropped ``exclude_none`` from
    ``_dump``. So a field handed an explicit ``None`` is a field the client
    receives as ``null``, and on an upsert ``null`` is not "unchanged", it is
    "cleared". Every optional below means "I have nothing to say", which is
    exactly what an absent key says and what a ``null`` contradicts.
    """
    return {name: value for name, value in fields.items() if value is not None}


def usage_model(raw: Any) -> Optional[v2.Usage]:
    """A provider usage dict -> v2 ``Usage``, or None when there is nothing.

    This conversion is not a convenience, it is the only thing standing
    between us and silent data loss: ``IdleStateUpdate`` carries a
    ``use_default_on_error_validator`` over ``stop_reason`` and ``usage``, so
    a dict whose keys do not match validates to ``None`` — no exception, no
    log, just a wire update with the usage missing. Providers report
    prompt/completion/total; v2 wants input/output/total, with reasoning and
    cached tokens broken out.
    """
    if raw is None or isinstance(raw, v2.Usage):
        return raw
    inp = raw.get("prompt_tokens", raw.get("input_tokens"))
    out = raw.get("completion_tokens", raw.get("output_tokens"))
    total = raw.get("total_tokens")
    if inp is None and out is None and total is None:
        return None
    completion_details = raw.get("completion_tokens_details") or {}
    prompt_details = raw.get("prompt_tokens_details") or {}
    return v2.Usage(
        total_tokens=total if total is not None else (inp or 0) + (out or 0),
        input_tokens=inp or 0,
        output_tokens=out or 0,
        **present(
            thought_tokens=completion_details.get("reasoning_tokens"),
            cached_read_tokens=prompt_details.get("cached_tokens"),
        ),
    )

class Emitter:
    """Turns plain Python into ``session/update`` notifications.

    One emitter per session, owned by that session's driver and living as
    long as the driver does — across turns, across compaction, across
    idle/wake cycles. The connection may be replaced (a second client
    attaches, a resume re-connects) without disturbing the loop, because
    nothing else holds it.
    """

    def __init__(self, conn: AgentSideConnection, session_id: str) -> None:
        self._conn = conn
        self.session_id = session_id

    def rebind(self, conn: AgentSideConnection) -> None:
        """Point at a different connection, mid-session.

        A second client attaching or a resume re-connecting replaces the
        transport under a session that may be running a turn. The emitter is
        the only object holding a connection, so this is the whole operation:
        the driver and the react loop never learn it happened.
        """
        self._conn = conn

    # -- transport ---------------------------------------------------------

    async def _send(self, update: Any) -> None:
        """Emit one update. Propagates: a dead client should end the turn."""
        await self._conn.session_update(session_id=self.session_id, update=update)

    async def _best_effort(self, update: Any) -> None:
        """Emit one decorative update. A dead client must not kill the loop.

        Reserved for updates whose loss degrades the UI but not the
        conversation — the context meter and live terminal bytes. Message and
        tool-call updates go through :meth:`_send` and propagate.
        """
        try:
            await self._send(update)
        except Exception:
            logger.warning("session_update dropped", exc_info=True)

    # -- messages ----------------------------------------------------------

    @staticmethod
    def start_message() -> str:
        """Mint a messageId. All chunks of one message share it.

        Opaque and unique forever — no dependence on the agent row, so
        compaction minting a new row mid-turn cannot collide with ids already
        on the wire.
        """
        return uuid.uuid4().hex

    async def user_message(self, message_id: str, blocks: Sequence[Any]) -> None:
        """A whole user message — the accepted prompt, a replayed turn."""
        await self._send(v2.UserMessageUpdate(message_id=message_id, content=list(blocks)))

    async def user_chunk(self, message_id: str, text: str) -> None:
        """A user message arriving in pieces — an injected mailbox delivery."""
        await self._send(
            v2.UserMessageChunk(message_id=message_id, content=v2.TextContentBlock(text=text))
        )

    async def agent_message(self, message_id: str, blocks: Sequence[Any]) -> None:
        await self._send(v2.AgentMessageUpdate(message_id=message_id, content=list(blocks)))

    async def agent_thought(self, message_id: str, blocks: Sequence[Any]) -> None:
        """A whole reasoning message — a replayed turn's thinking.

        Live traffic streams :meth:`thought_chunk`; this is the upsert form,
        and replay uses it because a persisted ``reasoning_content`` is one
        string that was already assembled. Re-splitting it into chunks would
        be theatre: the client cannot tell, and it costs N notifications
        instead of one.
        """
        await self._send(v2.AgentThoughtUpdate(message_id=message_id, content=list(blocks)))

    async def agent_chunk(self, message_id: str, text: str) -> None:
        await self._send(
            v2.AgentMessageChunk(message_id=message_id, content=v2.TextContentBlock(text=text))
        )

    async def thought_chunk(self, message_id: str, text: str) -> None:
        await self._send(
            v2.AgentThoughtChunk(message_id=message_id, content=v2.TextContentBlock(text=text))
        )

    # -- session state -----------------------------------------------------

    async def running(self) -> None:
        """Foreground work started. Emitted by the driver, never the loop."""
        await self._send(v2.RunningSessionStateUpdate())

    async def idle(self, stop_reason: Optional[str] = None, usage: Any = None) -> None:
        """Foreground work stopped.

        Not a wire boundary: background activity MAY keep emitting updates
        while the session reports idle, and the driver is still alive, parked
        on its inbox. This is the single most important difference from v1,
        where "no more foreground work" meant "return".

        ``usage`` may be the provider's raw dict; it is converted here rather
        than passed through, because passing it through loses it silently —
        see :func:`usage_model`.
        """
        await self._send(
            v2.IdleSessionStateUpdate(
                **present(stop_reason=stop_reason, usage=usage_model(usage))
            )
        )

    async def requires_action(self) -> None:
        await self._send(v2.RequiresActionSessionStateUpdate())

    async def state(self, state: str, **extra: Any) -> None:
        """A crow-specific session state.

        v2 state enums are extensible: ``_``-prefixed values are ours and
        route through ``OtherSessionStateUpdate``. This is how the driver says
        "blocked on a long-running task" — a state distinct from both
        ``running`` and ``idle``, which is what lets a client show a task as
        in-flight without implying the agent is promptable-and-working.
        """
        await self._send(v2.OtherSessionStateUpdate(state=state, **extra))

    async def usage(self, used: int, size: int, cost: Any = None) -> None:
        """The context meter: tokens in context against the compaction ceiling."""
        await self._best_effort(v2.UsageUpdate(used=used, size=size, **present(cost=cost)))

    # -- tool calls --------------------------------------------------------

    async def tool_call(self, tool_call_id: str, **patch: Any) -> None:
        """Create-or-patch a tool call. There is no separate create.

        First sight of ``tool_call_id`` creates it; later calls patch. Only
        the fields passed are serialized — ``exclude_unset`` is what makes
        patch semantics work, so never pass a field you do not mean to change.
        """
        await self._send(v2.SessionToolCallUpdate(tool_call_id=tool_call_id, **patch))

    async def tool_content_chunk(self, tool_call_id: str, content: Any) -> None:
        """Stream one piece of a tool call's content while it runs."""
        await self._send(
            v2.ToolCallContentChunkUpdate(tool_call_id=tool_call_id, content=content)
        )

    # -- terminals ---------------------------------------------------------

    async def terminal(
        self,
        terminal_id: str,
        command: Optional[str] = None,
        cwd: Optional[str] = None,
        output_b64: Optional[str] = None,
        exit_code: Optional[int] = None,
        signal: Optional[str] = None,
    ) -> None:
        """Upsert agent-owned terminal state.

        ``output_b64`` is the whole-output snapshot path (a command that
        finished before we streamed anything); live output goes through
        :meth:`terminal_chunk` instead, and a client that saw chunks must not
        re-render the snapshot.
        """
        exit_status = None
        if exit_code is not None or signal is not None:
            exit_status = v2.TerminalExitStatus(
                **present(exit_code=exit_code, signal=signal)
            )
        await self._send(
            v2.SessionTerminalUpdate(
                terminal_id=terminal_id,
                **present(
                    command=command,
                    cwd=cwd,
                    output=v2.TerminalOutput(data=output_b64) if output_b64 else None,
                    exit_status=exit_status,
                ),
            )
        )

    async def terminal_chunk(self, terminal_id: str, raw: bytes) -> None:
        """Stream raw PTY bytes — ANSI intact — for the client to render.

        This is the half of the execute-as-terminal contract the *user* sees.
        The half the LLM sees is ANSI-stripped text in ``raw_output``; keeping
        them separate is the whole point, since color and cursor movement are
        signal for a human and noise for a model.
        """
        await self._best_effort(
            v2.SessionTerminalOutputChunk(
                terminal_id=terminal_id,
                data=base64.b64encode(raw).decode("ascii"),
            )
        )

    # -- compaction --------------------------------------------------------

    async def compaction(
        self,
        compaction_id: str,
        status: CompactionStatus,
        summary: Optional[Sequence[Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Compaction has a wire representation in v2; v1 only logged it."""
        await self._send(
            v2.SessionCompactionUpdate(
                compaction_id=compaction_id,
                status=status,
                **present(summary=list(summary) if summary else None, error=error),
            )
        )

    async def compaction_chunk(self, compaction_id: str, text: str) -> None:
        await self._send(
            v2.SessionCompactionSummaryChunk(
                compaction_id=compaction_id, content=v2.TextContentBlock(text=text)
            )
        )

    # -- misc --------------------------------------------------------------

    async def available_commands(self, commands: Sequence[Any]) -> None:
        """Advertise the session's slash commands.

        Sent on every path that attaches a session to the wire — new, resumed
        or forked — because a session that comes up without this has no
        agent-side commands in the client's palette.
        """
        await self._send(v2.AvailableCommandsUpdate(available_commands=list(commands)))

    async def config_options(self, config_options: Sequence[Any]) -> None:
        """Agent-initiated config change (v1's ``current_mode_update`` is gone)."""
        await self._send(v2.ConfigOptionUpdate(config_options=list(config_options)))

    async def session_info(
        self, title: Optional[str] = None, updated_at: Optional[str] = None
    ) -> None:
        """Patch the session's metadata. crow patches one field: its title.

        ``SessionInfoUpdate`` has patch semantics — an omitted field leaves the
        client's copy alone — and no response in the protocol carries a
        ``SessionInfo``, so this is the only channel a title has. A client
        watching a session list would otherwise show an untitled session until
        it thought to re-list.

        ``updated_at`` is never sent. A timestamp per message is a firehose
        whose loss costs a client nothing: ``session/list`` recomputes it from
        the store on every page.

        Through :meth:`_send`, not :meth:`_best_effort`. Once per session is
        not a decorative stream, and a client that has gone away should end
        the turn here rather than have the failure swallowed and surfaced
        three notifications later as something else.
        """
        await self._send(
            v2.SessionInfoUpdate(**present(title=title, updated_at=updated_at))
        )
