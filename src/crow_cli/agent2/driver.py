"""The session driver: react reports, the driver decides.

v1 conflated two different facts — "the loop has no more foreground work" and
"the session is done" — because ``react_loop`` was a generator and
``AcpAgent.prompt`` awaited it. When the generator ended, the prompt handler
returned a ``stop_reason``, and with it went all awareness of the session: no
inbox, no task, nothing listening. A subagent finishing three seconds later
had nowhere to land. That is why v1 needed the delegation hold — block
*inside* the turn, polling the mailbox every two seconds, because a returned
loop was a deaf loop.

agent2 splits the two. :func:`crow_cli.agent2.react.react` runs foreground
work and returns a :class:`~crow_cli.agent2.react.Done` saying why it stopped.
The driver — one per session, living as long as the session does — decides
what that means:

* more prompts queued, or a mailbox row pending -> ``state_update: running``,
  another turn;
* nothing -> ``state_update: idle`` and park on the inbox.

Idle means idle, INCLUDING with a delegated task still running. The spec says
background activity may continue and emit updates while the agent reports
``idle``, and that those notifications do not change the state; and that an
agent ready for a new prompt MUST report ``idle``. A session waiting on a
subagent is promptable, so it says so — a client that reads a non-idle state as
"input closed" would be right to.

The park is ``asyncio.wait_for(inbox.get(), PARK_BACKSTOP_S)``. The timeout is
a backstop, not the mechanism: the mailbox is level-triggered underneath the
redis edge trigger, so a missed publish is not a lost wake — the next poll
reads the same rows. Thirty seconds rather than v1's two because nothing is
being held open while we wait, and a session that parks for an hour costs one
query an hour.

``session/prompt`` in v2 is inverted: the agent accepts the prompt, hands it
here, and returns ``PromptResponse()`` immediately. The turn's outcome travels
as ``state_update`` notifications, not as a response body — which is what makes
a wake indistinguishable from a prompt, and therefore possible at all.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from logging import Logger
from typing import Any, Optional

from acp.experimental.v2 import schema as v2

from crow_cli.agent.hooks import CommandHook
from crow_cli.agent.session import AgentSession
from crow_cli.config import Config
from crow_cli.memory import (
    GOAL_ACTIVE,
    GOAL_BLOCKED,
    GOAL_PAUSED,
    active_goal,
    build_agent_id,
    get_goal,
    pending_deliveries,
    session_title,
)
from crow_cli.memory.writes import account_goal_usage, queue_delivery, update_goal_status

from .ctx import TurnCtx
from .emitter import Emitter
from .events import Cancel, Event, Prompt, new_inbox
from .goal import continuation_text, eligible
from .llm import StreamState, normalize_prompt
from .react import Deps, Done, react

logger = logging.getLogger(__name__)

#: How long a parked driver waits before re-reading the mailbox anyway.
PARK_BACKSTOP_S = 30.0

#: A slash command handler: (session, args) -> reply text, or None if the text
#: was not a command this agent knows. Kept as a seam because the command
#: table belongs to the agent, not the driver.
SlashHandler = Callable[[AgentSession, str], Awaitable[Optional[str]]]


@dataclass
class DriverDeps:
    """Session-scoped resources the driver uses but does not own.

    The agent builds one of these per session and keeps ownership of the
    lifetimes inside it — MCP clients are entered on the agent's exit stack,
    the engine is shared process-wide. Everything here outlives a turn and
    most of it outlives a compaction, which is exactly why it is not on
    :class:`~crow_cli.agent2.ctx.TurnCtx`.
    """

    config: Config
    engine: Any
    mcp_clients: dict[str, Any]
    tools: list[dict]
    #: Persistent across turns on purpose: a cancel mid-stream persists the
    #: half-finished completion, and the accumulator holding it has to be the
    #: same object the stream was writing into.
    state: StreamState
    #: Resolved per turn, not per session — ``set_config_option`` can change
    #: the model between turns, and the provider follows the model.
    make_llm: Callable[[AgentSession, Logger], Any]
    hooks: tuple[CommandHook, ...] = ()
    compactor: Any = None
    compact_system_prompt: Any = None
    chunk_log_dir: Optional[str] = None
    max_turns: int = 50000


class SessionDriver:
    """One session's life, from ``session/new`` to ``close_session``.

    Owns the inbox, the in-flight turn, and the session's wire state. Does not
    own the connection (the emitter does), the MCP clients, or the database —
    see :class:`DriverDeps`.
    """

    def __init__(
        self,
        *,
        session_id: str,
        session: AgentSession,
        emitter: Emitter,
        deps: DriverDeps,
        logger: Logger,
        slash: Optional[SlashHandler] = None,
    ) -> None:
        self.session_id = session_id
        self.session = session
        self.emitter = emitter
        self.deps = deps
        self.log = logger
        self.slash = slash
        self.inbox: asyncio.Queue[Event] = new_inbox()

        self._task: Optional[asyncio.Task] = None
        self._turn: Optional[asyncio.Task] = None
        self._stopping = False
        self._cancel_requested = False
        self._state: Optional[str] = None
        #: The last turn's outcome, reported on the idle that follows it. A
        #: client that only watches state transitions still gets to know why
        #: the turn ended and what it cost. None until a turn has actually
        #: ended: the spec says an idle carries a stop reason "when the
        #: transition ends foreground work", so the park a fresh session does
        #: before its first prompt reports idle and nothing else.
        self._last_stop: Optional[str] = None
        self._last_usage: Optional[dict] = None
        #: How many tool calls the last turn ran. Not reported on the wire —
        #: no client asks — but the goal continuation cannot decide without it,
        #: and the driver cannot infer it from a stop reason.
        self._last_tools_used: int = 0
        #: What the last turn was billed across all of its model calls. The
        #: goal's token budget charges this rather than ``_last_usage``, which
        #: is the last call's context size — see :attr:`.react.Done.tokens_spent`.
        self._last_tokens_spent: int = 0
        #: Goal bookkeeping. ``_continuation_in_flight`` is set when this
        #: driver writes a continuation to the mailbox and consumed by the next
        #: turn, which is how the no-progress rule tells a turn the GOAL caused
        #: from one the USER caused — see :mod:`crow_cli.agent2.goal`. Lost on
        #: restart, which costs one extra continuation and then self-corrects.
        self._continuation_in_flight = False
        self._last_was_continuation = False
        #: Whether this driver has already told the client what the session is
        #: called. One attempt, not one success: the title is the root agent's
        #: FIRST user message, so if it is not knowable now it never will be,
        #: and re-deciding on every prompt is a query bought for nothing.
        self._title_announced = False

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Begin driving. Idempotent; the agent calls this once per session."""
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(
                self.run(), name=f"crow-driver-{self.session_id}"
            )

    async def stop(self) -> None:
        """Tear down: cancel any turn in flight, then the driver itself."""
        self._stopping = True
        self.cancel()
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except BaseException:  # noqa: BLE001 - teardown swallows its own mess
                pass

    def submit(self, event: Event) -> None:
        """Queue an event. Never blocks — the inbox is unbounded by design.

        A prompt that arrives while a turn is running is not an error and not
        a reason to make the client wait; it is the next thing the driver
        does. Bounding the queue would mean applying backpressure to a
        ``session/prompt`` that has already been accepted.
        """
        self.inbox.put_nowait(event)

    def cancel(self) -> None:
        """Cancel the foreground work, keeping the driver alive.

        v2 cancellation is per-turn, not per-connection: after a cancel the
        session is still there, still parked, still able to receive a wake.
        """
        self._cancel_requested = True
        turn = self._turn
        if turn is not None and not turn.done():
            self.log.info("Cancelling turn for session %s", self.session_id)
            turn.cancel()

    @property
    def running(self) -> bool:
        return self._turn is not None and not self._turn.done()

    # -- the loop ----------------------------------------------------------

    async def run(self) -> None:
        """Drive until stopped. One turn at a time; the inbox sets the pace."""
        self.log.info("Driver started for session %s", self.session_id)
        try:
            while not self._stopping:
                events = self._drain()
                # The mailbox is checked here, not only on an event: a wake is
                # a redis poke over a durable row, and the poke can be missed.
                # Rows are the truth, so an unempty mailbox is work even with
                # an empty inbox.
                if events or self._mailbox_pending():
                    await self._run_turn(events)
                    continue
                if not await self._park():
                    break
        except asyncio.CancelledError:
            self.log.info("Driver cancelled for session %s", self.session_id)
            raise
        except Exception as exc:
            # The driver dying silently would leave a session that accepts
            # prompts and never answers them. Say so on the wire, then go.
            self.log.error("Driver crashed: %s", exc, exc_info=True)
            try:
                mid = self.emitter.start_message()
                await self.emitter.agent_message(
                    mid, [v2.TextContentBlock(text=f"agent error: {exc}")]
                )
                await self._set_state("idle", stop_reason="error")
            except Exception:
                self.log.warning("could not report driver crash", exc_info=True)
        finally:
            self.log.info("Driver stopped for session %s", self.session_id)

    def _drain(self) -> list[Event]:
        """Take everything queued, without blocking.

        All queued prompts go into ONE turn rather than one turn each: a user
        who sends "do X" and then "actually, do Y" while the agent is busy
        wants the agent to see both, and v1's per-session lock would have run
        them as two turns with the first one already committed to X.

        A ``Cancel`` in the batch discards the prompts queued with it — that
        is the only thing the event is for, since :meth:`cancel` handles a
        cancel that lands mid-turn directly.
        """
        events: list[Event] = []
        while True:
            try:
                events.append(self.inbox.get_nowait())
            except asyncio.QueueEmpty:
                break
        if any(isinstance(e, Cancel) for e in events):
            kept = [e for e in events if not isinstance(e, (Cancel, Prompt))]
            dropped = len(events) - len(kept)
            if dropped:
                self.log.info("Cancel discarded %d queued prompt(s)", dropped)
            return kept
        return events

    async def _run_turn(self, events: list[Event]) -> None:
        """Persist what arrived, then run foreground work to completion."""
        started = time.monotonic()
        # Consumed at the top rather than at the end: this method has two early
        # returns (another process claimed the mailbox row; a slash command
        # answered) and a flag left set would be inherited by the next turn,
        # which would then be judged as a continuation it was not.
        self._last_was_continuation = self._continuation_in_flight
        self._continuation_in_flight = False
        prompts = [e for e in events if isinstance(e, Prompt)]
        if not prompts and not self._mailbox_pending():
            # Woken for a mailbox row another consumer already claimed (two
            # processes share the db; react's own consult points race for the
            # same rows). Running a turn here would call the model over
            # unchanged history and get the previous answer again.
            return
        for prompt in prompts:
            if not await self._accept_prompt(prompt):
                # No model turn: a slash command answered, or the prompt
                # carried nothing the model could see. The client is still
                # owed a turn boundary — it got {} from session/prompt and
                # drives its UI from state_update, so a missing idle is a
                # spinner that never stops. _set_state dedupes, so this only
                # fires when _accept_prompt bailed before announcing running.
                await self._set_state("running")
                self._last_stop, self._last_usage = "end_turn", None
                # A slash command ran no tools and billed nothing, and saying
                # otherwise would let the previous turn's numbers vouch for a
                # turn that never called the model.
                self._last_tools_used = 0
                self._last_tokens_spent = 0
                return
        # Deliveries and timers need no handling here: the mailbox row is the
        # truth and react consults it before the first model call. The event
        # is only the poke that got us out of the park.

        await self._set_state("running")
        turn_id = uuid.uuid4().hex
        self._cancel_requested = False
        ctx = TurnCtx(
            emitter=self.emitter,
            config=self.deps.config,
            session=self.session,
            turn_id=turn_id,
            logger=self.log,
            hooks=self.deps.hooks,
        )
        deps = Deps(
            llm=self.deps.make_llm(self.session, self.log),
            tools=self.deps.tools,
            mcp_clients=self.deps.mcp_clients,
            state=self.deps.state,
            engine=self.deps.engine,
            max_turns=self.deps.max_turns,
            compactor=self.deps.compactor,
            compact_system_prompt=self.deps.compact_system_prompt,
            on_compact=self._on_compact,
            chunk_log_dir=self.deps.chunk_log_dir,
        )
        self._turn = asyncio.create_task(
            react(ctx, deps), name=f"crow-turn-{self.session_id}-{turn_id[:8]}"
        )
        try:
            done: Done = await self._turn
        except asyncio.CancelledError:
            if not self._cancel_requested:
                raise  # the driver itself is being stopped
            self.log.info("Turn cancelled for session %s", self.session_id)
            done = Done(stop_reason="cancelled")
        except Exception as exc:
            # react persists history as it goes, so a crash here loses the
            # turn, not the session. Report it and park rather than spinning.
            self.log.error("Turn failed: %s", exc, exc_info=True)
            mid = self.emitter.start_message()
            await self.emitter.agent_message(
                mid, [v2.TextContentBlock(text=f"agent error: {exc}")]
            )
            done = Done(stop_reason="error")
        finally:
            self._turn = None
            self._cancel_requested = False
        self._last_stop = done.stop_reason or "end_turn"
        self._last_usage = done.usage
        self._last_tools_used = done.tools_used
        self._last_tokens_spent = done.tokens_spent
        self.log.info("Turn %s ended: %s", turn_id[:8], self._last_stop)
        await self._settle_goal(done, time.monotonic() - started)

    async def _settle_goal(self, done: Done, elapsed: float) -> None:
        """Charge the finished turn to the goal, and stop the goal if the turn
        did.

        Runs before :meth:`_park`, so a turn that errored has already blocked
        the goal by the time the continuation is asked about it — otherwise the
        loop re-runs a repeating failure and spends tokens learning nothing
        new, which is the one thing a continuation must never do.

        Only a turn the GOAL caused is charged. A turn the user prompted is
        spend they asked for and watched happen; billing it to the goal makes
        the ceiling fire on conversation length rather than on autonomy, and a
        limit that stops you for talking to your own agent is a limit nobody
        will leave enabled.
        """
        engine = self.deps.engine
        if engine is None:
            return
        row = get_goal(engine, self.session_id)
        if row is None:
            return
        # Only a goal that is STILL RUNNING gets moved by how its turn ended.
        # A status that is not active was set by somebody else — the model
        # called goal_done, the user paused it, the budget CASE fired — and
        # overwriting it would mean a goal_done followed by an unrelated error
        # comes back as blocked. An exit that does not hold is not an exit.
        # The spend below is charged either way: those tokens were spent on
        # this goal whatever its status, and the row is that goal's account.
        running = row.status == GOAL_ACTIVE
        # STATE FIRST, and the state is the user's or the harness's, not the
        # arithmetic's: a cancel is the person stopping the work rather than the
        # work failing, so it pauses and `/goal resume` picks it back up. Both
        # writes carry the id they read, so a goal replaced mid-turn is left
        # alone rather than paused or blocked by a turn that was not about it.
        if running and done.stop_reason == "cancelled":
            update_goal_status(
                engine, self.session_id, GOAL_PAUSED, expected_goal_id=row.goal_id
            )
            self.log.info("Goal %s paused: the turn was cancelled", row.goal_id[:8])
            return
        if running and done.stop_reason == "error":
            update_goal_status(
                engine,
                self.session_id,
                GOAL_BLOCKED,
                expected_goal_id=row.goal_id,
                blocked_reason="the turn errored",
            )
            self.log.info("Goal %s blocked: the turn errored", row.goal_id[:8])
        if self._last_was_continuation:
            # tokens_spent, not usage: the turn's whole bill rather than its
            # last call's context size. Prompt tokens are included because
            # they are billed, and a budget that counted only completions
            # would understate a long-context goal by an order of magnitude
            # and look like a limit while never firing.
            account_goal_usage(
                engine,
                self.session_id,
                goal_id=row.goal_id,
                tokens=done.tokens_spent,
                seconds=int(elapsed),
            )

    async def _accept_prompt(self, prompt: Prompt) -> bool:
        """Echo, normalize and persist one prompt. False means "no turn".

        The echo is not optional and not redundant: v2 requires the agent to
        report where the user message landed in session history, as a
        ``user_message`` update carrying an agent-owned ``messageId``. The
        agent owns history, so it owns message identity — that id is what a
        later correction, a replay on resume, and a second client all key on.
        The blocks go back exactly as they arrived; only the persisted copy is
        normalized, because the wire shape and the provider shape differ.
        """
        content = await normalize_prompt(prompt.blocks, self.log)
        if not content:
            self.log.warning("Empty user content — skipping prompt")
            return False

        await self.emitter.user_message(prompt.message_id, prompt.blocks)
        await self.session.add_message({"role": "user", "content": content})
        # Running goes here rather than in _run_turn: the spec's order is
        # user_message then running, and a slash command is foreground work
        # too — it needs the same boundary a model turn gets.
        await self._set_state("running")
        # After the state change, not before it: the spec names user_message
        # then running as the turn's opening, and anything wedged between the
        # two is a deviation worth avoiding for a notification that is about
        # the session rather than the turn.
        await self._announce_title()

        if self.slash is not None and len(content) == 1 and content[0].get("type") == "text":
            text = content[0]["text"]
            if text.startswith("/"):
                reply = await self.slash(self.session, text)
                if reply is not None:
                    await self.emitter.agent_message(
                        self.emitter.start_message(),
                        [v2.TextContentBlock(text=reply)],
                    )
                    return False
                # Not a command after all — a path, or a "/" on its own. Fall
                # through and let the model answer it.
        return True

    async def _announce_title(self) -> None:
        """Tell the client what this session is called. Once.

        ``SessionInfo.title`` is the root agent's first user message, so it
        does not exist at ``session/new`` — and no response in the protocol
        carries a ``SessionInfo`` anyway, ``NewSessionResponse`` being a
        sessionId and config options. Without this a client holding a session
        list open shows an untitled session until it thinks to re-list, which
        is exactly the gap ``session_info_update`` is in the protocol to close.

        Read back out of the store rather than built from the prompt in hand,
        so the announcement and ``session/list`` cannot disagree about the
        name. The root's id is DERIVED rather than taken from ``self.session``:
        after a compaction the driver holds an agent whose first message is a
        summary, and titling from that would rename the session every time it
        grew — the same trap ``_session_title`` reads the root to avoid.

        Forks are skipped because ``session/list`` skips them: a branch is
        addressed by its own wire id and has no list entry to name.
        """
        if self._title_announced:
            return
        self._title_announced = True
        session = self.session
        if self.deps.engine is None or session.fork_idx != 1:
            return
        title = session_title(self.deps.engine, build_agent_id(session.session_id, 1, 1))
        if title:
            self.log.info("Session %s is titled %r", self.session_id, title)
            await self.emitter.session_info(title=title)

    def _on_compact(self, old_agent_id: str, new_session: AgentSession) -> None:
        """Compaction forked a new agent row inside the same wire session.

        The driver holds the current session, so this is the one place that
        has to swap it — every later turn, and every wake that lands after
        compaction, resolves through here. No scalar bookkeeping: the next
        turn re-reads from the object compaction just handed us.
        """
        self.log.info(
            "Compaction: %s -> %s", old_agent_id, new_session.agent_id
        )
        self.session = new_session

    # -- parking -----------------------------------------------------------

    async def _park(self) -> bool:
        """Announce ``idle`` and wait. True on wake, False on stop.

        The caller has already established there is nothing to do, so this
        only reports that and blocks. On timeout it returns to the loop rather
        than re-checking the mailbox itself: the loop's next iteration does
        that, and checking it here too would mean two places deciding what
        counts as work.

        There is no second resting state. A delegated task still running is
        background activity, which the spec says may continue while the agent
        reports ``idle`` without changing the state — and this session IS
        promptable, which is what ``idle`` means. What the driver is waiting
        on is not the client's business; the wake arrives as an event and the
        next turn announces itself with ``running``.

        The one thing checked before announcing idle is the goal, because a
        session that is about to start another turn on its own account is not
        idle and must not be reported as such.
        """
        if await self._goal_continuation():
            return True
        await self._set_state(
            "idle", stop_reason=self._last_stop, usage=self._last_usage
        )
        try:
            event = await asyncio.wait_for(self.inbox.get(), timeout=PARK_BACKSTOP_S)
        except TimeoutError:
            return not self._stopping
        self.submit(event)  # put it back; the loop drains it uniformly
        return True

    async def _goal_continuation(self) -> bool:
        """Decide whether this session should start another turn by itself.

        True when a continuation landed in the mailbox. The caller returns to
        the loop, ``_mailbox_pending()`` is now true, ``_run_turn([])`` runs,
        and react's prompt-start consult injects it — the existing path, with
        nothing new to wake and nobody to notify. This is ACP_V2.md §5.4, the
        state-triggered wake that was designed and never built: the transition
        into idle IS the trigger, the goal is the thing that defers, and by the
        time anything looks it is an ordinary pending delivery.

        No clock and no worker, which is §5.3's argument vindicated rather than
        sidestepped. A timer would fire mid-turn and interrupt at the next
        consult breakpoint — the opposite of the intent — and would need a
        celery worker running to make a transition that is entirely local to
        this process.

        The write is two commits (the delivery, then the turn counter) and the
        window between them is benign: a crash there leaves one continuation
        queued against a counter one low, which is a rounding error on a loop
        guard and not a way to loop forever.
        """
        engine = self.deps.engine
        if engine is None:
            # No store, no goals — the same guard _mailbox_pending uses. A
            # session with nowhere to persist a goal has nowhere to read one.
            return False
        row = active_goal(engine, self.session_id)
        if row is None:
            return False
        max_turns = self.deps.config.goal.max_turns
        verdict = eligible(
            row,
            tools_used=self._last_tools_used,
            was_continuation=self._last_was_continuation,
            max_goal_turns=max_turns,
        )
        if verdict is not None:
            if verdict.status is not None:
                update_goal_status(
                    engine,
                    self.session_id,
                    verdict.status,
                    expected_goal_id=row.goal_id,
                    blocked_reason=verdict.reason,
                )
            self.log.info("Goal %s not continued: %s", row.goal_id[:8], verdict.reason)
            return False
        queue_delivery(
            engine,
            self.session_id,
            task_id=row.goal_id,
            content=continuation_text(row, max_goal_turns=max_turns),
            priority="low",
        )
        account_goal_usage(engine, self.session_id, goal_id=row.goal_id, turns=1)
        self._continuation_in_flight = True
        self.log.info(
            "Goal %s continues: turn %d of %s",
            row.goal_id[:8],
            row.turns_used + 1,
            max_turns or "no ceiling",
        )
        return True

    def _mailbox_pending(self) -> bool:
        """Undelivered completions are waiting for this session."""
        return bool(self.deps.engine) and bool(
            pending_deliveries(self.deps.engine, self.session_id)
        )

    async def _set_state(self, state: str, **extra: Any) -> None:
        """Emit a state change, skipping no-op repeats.

        Re-parking after a backstop poll would otherwise emit the same
        ``idle`` every thirty seconds for the life of the session, and a
        client that logs state transitions would fill up with nothing.
        """
        if self._state == state:
            return
        self._state = state
        if state == "idle":
            await self.emitter.idle(
                stop_reason=extra.pop("stop_reason", "end_turn"),
                usage=extra.pop("usage", None),
            )
        elif state == "running":
            await self.emitter.running()
        else:
            await self.emitter.state(state, **extra)
