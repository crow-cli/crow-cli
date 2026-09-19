"""task — set work going in another process, and collect it later.

Four names, not one dispatcher. ``task`` launches, ``task_send`` steers,
``task_cancel`` stops, ``task_read`` looks. A ``mode="launch"|"send"|...``
argument would carry the same information and reach the model as one tool with
a four-way string switch on it, which is the shape that does not get used: the
signatures differ (launch takes a priority and a kind, send takes a ref, cancel
takes neither), the failure modes differ, and the docstring that has to explain
all four at once is the docstring the model skims. The house rule is that a
capability behind a mode-string dispatcher is a capability that does not get
reached.

A subtool, not an MCP tool. v1 served ``task`` from the agent process over MCP,
which meant one process holding every session's live children in a module-level
dict and attributing ownership from ``_meta`` because the caller was otherwise
anonymous. Here the launcher runs in the execute kernel, and there is exactly
one kernel per session, so the handle table is per-owner by construction and
attribution rides the identity rail the prologue already injects — a value the
model never derived and cannot forge. The child is still a separate process
driven over ACP v2 by :mod:`crow_cli.client2.subagent`; what moved is the state.

The mailbox is the truth and the poke is the courtesy. A completion is written
to ``task_deliveries`` in the SAME commit that flips the task row terminal
(:func:`crow_cli.memory.writes.finish_task` — state first, so a fast completion
can never outrun its own record), and only after that commit does
:func:`crow_cli.wake.publish_wake` tell the owner to go look. Every way the bus
can fail therefore costs latency and nothing else: the owner parks on its inbox
with a backstop poll behind it, and the row is still there.

Nobody is told twice. A launch with ``wait=True`` has a waiter, and a waiter is
holding the answer, so the finalize skips the delivery; a launch nobody waits on
delivers. The decision is read at commit time off a waiter count rather than
fixed at launch, because a wait can run out — and when it does the row is read
anyway, which is what makes the hand-off race-free: the watcher commits before
it signals, so a wait that times out inside that window finds a terminal row and
returns the answer instead of a snapshot.

There is no depth budget here, unlike :mod:`crow_cli.tools.rlm`. A delegate is a
copy of its caller and inherits its context, so an unbounded chain is an
infinity mirror; a task child is a fresh session with nothing in it, and the
cost of a chain is one visible process per link.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from dataclasses import dataclass, field

import crow_cli.memory as cm
from crow_cli.client2.subagent import SubagentDriver, child_config
from crow_cli.memory.messages import last_assistant_text
from crow_cli.memory.reads import (
    get_session_mcp_servers,
    get_task,
    list_agents,
    load_agent_messages,
    owner_tasks,
    task_by_sub_session,
)
from crow_cli.memory.writes import (
    cancel_task,
    finish_task,
    launch_next_task,
    reopen_task,
    set_task_sub_session,
)
from crow_cli.wake import Poke, publish_wake

from .register import CellContext, current_cell, db_uri, redis_url, subtool
from .results import TaskError, TaskListResult, TaskResult

#: How long a ``wait=True`` call blocks before it gives up and reports the task
#: as still running. Same figure as rlm's: both are "a whole agent turn", and
#: neither loses the work when it expires.
_TASK_TIMEOUT = 900.0

#: How long ``task_cancel`` waits for the watcher to finalize. Shorter than a
#: turn on purpose — a cancel that has to wait for the model to notice it is
#: already late, and the caller needs the ack to mean "re-promptable NOW".
_CANCEL_TIMEOUT = 15.0

# Same reason rlm.py and memory.py keep theirs in one: importlib.reload
# re-executes this source in the EXISTING module dict, so a module-level
# ``_engine = None`` would drop the handle on every reload() and leak its
# connection pool — and would drop the live-child table with it.
_state: dict = globals().setdefault("_state", {})


@dataclass
class LiveTask:
    """One child this kernel is driving right now.

    ``bus`` is captured at launch rather than read off the register at poke
    time: the watcher outlives the cell that armed it, and the next cell's
    prologue re-points the rail.

    ``waiters`` is how many calls are blocked on ``done``. The watcher reads it
    at commit time to decide whether the mailbox has to carry the answer. Both
    sides run on one event loop with no await between a read and its use, so it
    needs no lock.

    ``poked`` is the bus's answer, kept so a waiting caller can report whether
    the wake actually went out.
    """

    task_id: str
    owner: str
    sub: str
    priority: str
    kind: str
    bus: str
    driver: SubagentDriver
    prompt: str
    watcher: asyncio.Task | None = None
    poked: bool = False
    waiters: int = 0
    done: asyncio.Event = field(default_factory=asyncio.Event)


def _dispose() -> None:
    """Drop the cached engine (test hygiene, and a db_uri that changed)."""
    engine = _state.get("engine")
    if engine is not None:
        with contextlib.suppress(Exception):
            engine.dispose()
    _state["engine"] = None
    _state["uri"] = None


def _engine():
    """The WRITE engine for the injected crow.db, cached per uri.

    Not the read-only one rlm keeps: task registers state, and a mode=ro
    connection cannot. Same rail, same refusal — the kernel reads no config, so
    a caller outside one has to point the rail at a database itself.
    """
    uri = db_uri()
    if uri is None:
        raise TaskError(
            "no database — task() writes its state to the crow.db that"
            " execute's prologue injects on the identity rail; outside a"
            " kernel, point the rail at one with"
            " crow_cli.tools.register.begin_cell(db_uri=...)"
        )
    if _state.get("uri") != uri:
        _dispose()
        _state["engine"] = cm.get_engine(uri)
        _state["uri"] = uri
    return _state["engine"]


def _cell() -> CellContext:
    """This cell's identity, or a refusal.

    The owner is the session the delivery has to reach, and it comes off the
    rail the prologue injected — never off an argument, because a model that
    could name its own owner could deliver its work into somebody else's inbox.
    """
    cell = current_cell()
    if cell is None or not cell.session_id:
        raise TaskError(
            "no session identity — task() launches work ON BEHALF OF a session"
            " and has to know which mailbox to deliver it to, which only exists"
            " inside an execute cell (the prologue injects it)"
        )
    return cell


def _live() -> dict[str, LiveTask]:
    """The children THIS kernel drives, keyed by the child's wire session id.

    Process-local handle table; the durable truth is sqlite. v1 keyed the same
    table in the MCP server process, where it held every session's children at
    once — here one kernel serves one session, so the table is per-owner by
    construction and needs no attribution check on the way in.
    """
    return _state.setdefault("live", {})


def _child_answer(engine, sub_session: str) -> str:
    """The child's final answer, read out of the shared sqlite.

    The trunk's highest ``agent_idx`` is the child's own last turn — the same
    read ``memory("list", session_id=...)`` resolves, so the answer in the
    mailbox and the answer in the transcript cannot disagree. (rlm reads
    differently: a delegate IS a fork, and this trunk scan would miss it.)
    """
    trunks = [
        a for a in list_agents(engine, session_id=sub_session) if a.fork_idx == 1
    ]
    if not trunks:
        return "(the subagent produced no transcript)"
    agent = max(trunks, key=lambda a: a.agent_idx)
    return last_assistant_text(
        load_agent_messages(engine, agent),
        fallback="(the subagent produced no final answer)",
    )


def _register_task(
    engine, cell: CellContext, *, prompt: str, model, priority: str, kind: str
) -> str:
    """STATE FIRST: the running row exists before any ACP traffic, so a fast
    completion can never outrun the record.

    Allocating the id is :func:`crow_cli.memory.writes.launch_next_task` —
    global task-N, retried against the UNIQUE constraint — because a scheduled
    wake mints ids off the same counter and one of the two implementations
    would eventually drift. What stays here is the part only a subtool knows:
    which execute call this launch belongs to.
    """
    return launch_next_task(
        engine,
        owner_session=cell.session_id,
        kind=kind,
        tool_call_id=cell.parent_tool_call_id,
        prompt=prompt,
        model=model,
        priority=priority,
    )


def _arm(
    engine,
    *,
    task_id: str,
    owner: str,
    sub: str,
    priority: str,
    kind: str,
    driver: SubagentDriver,
    prompt: str,
) -> LiveTask:
    """Hand a started child to a background watcher and return its handle.

    Owner, priority and kind come from the task row's own values, so the poke
    that eventually goes out carries what the delivery row carries: a watcher
    routed on a priority the mailbox does not have would wake a session for a
    delivery it then declines to claim.
    """
    live = LiveTask(
        task_id=task_id,
        owner=owner,
        sub=sub,
        priority=priority or "low",
        kind=kind or "subagent",
        bus=redis_url(),
        driver=driver,
        prompt=prompt,
    )
    _live()[sub] = live
    live.watcher = asyncio.create_task(
        _watch(engine, live), name=f"crow-task-{task_id}"
    )
    return live


async def _watch(engine, live: LiveTask) -> None:
    """Drive the child's ONE turn, then finalize: row and delivery in one
    commit, poke second.

    Releasing the handle happens BEFORE the (slow) driver teardown, so a
    cancel-then-send does not bounce off a stale "mid-turn" guard.
    """
    try:
        status, result = "completed", None
        try:
            stop = await live.driver.prompt(live.sub, live.prompt)
            if stop == "cancelled":
                status = "cancelled"
        except Exception as e:  # driver/transport failure, or a dead child
            status, result = "failed", f"{type(e).__name__}: {e}"

        # A waiter is holding the answer already; a delivery would tell it the
        # same thing twice, once as a tool result and once as an injected user
        # message. Read at commit time rather than fixed at launch, because a
        # wait can run out — and then the mailbox is the only way home.
        deliver = live.waiters == 0
        if status == "cancelled":
            # The cancel was a synchronous call by the owner, who knows: no
            # delivery, and so no poke either. Waking a session to consult a
            # mailbox with nothing in it spends a turn for nothing.
            cancel_task(engine, live.task_id)
        else:
            if status == "failed":
                landed = finish_task(
                    engine,
                    live.task_id,
                    result=result,
                    status="failed",
                    content=f"[{live.task_id}: subagent {live.sub} failed: {result}]",
                    deliver=deliver,
                )
            else:
                result = _child_answer(engine, live.sub)
                landed = finish_task(
                    engine,
                    live.task_id,
                    result=result,
                    status="completed",
                    content=(
                        f"[{live.task_id}: subagent {live.sub} finished]\n{result}"
                    ),
                    deliver=deliver,
                )
            if landed and deliver:
                live.poked = await publish_wake(
                    live.bus,
                    Poke(
                        session_id=live.owner,
                        task_id=live.task_id,
                        priority=live.priority,
                        kind=live.kind,
                    ),
                )
    except Exception as e:
        # Nobody retrieves a bare create_task's exception, so a crash in here
        # looks exactly like a task that never finished. Be noisy.
        print(
            f"task: {live.task_id} watcher failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
    finally:
        _live().pop(live.sub, None)
        live.done.set()
        with contextlib.suppress(Exception):
            await live.driver.close()


def _from_row(row, *, waited: bool = False, poked: bool = False) -> TaskResult:
    return TaskResult(
        task_id=row.task_id,
        status=row.status,
        session_id=row.sub_session or "",
        prompt=row.prompt or "",
        result=row.result or "",
        waited=waited,
        poked=poked,
    )


def _snapshot(live: LiveTask) -> TaskResult:
    """The async launch's return: a handle and a promise, no result.

    Deliberately not a re-read of the row. A child that finished in the
    microseconds between launch and return would otherwise hand back an answer
    nobody waited for, while the mailbox is already on its way with the same
    text — the duplication ``waiters`` exists to prevent, arriving by the back
    door.
    """
    return TaskResult(
        task_id=live.task_id,
        status="running",
        session_id=live.sub,
        prompt=live.prompt,
    )


async def _outcome(engine, live: LiveTask, timeout: float | None) -> TaskResult:
    """Block for the turn, then report the row.

    A timeout is not a failure and does not raise. The task is still running,
    the child is alive, and its completion will still land in the mailbox;
    raising would make the register record this call as ``failed`` — a lie
    written to the database — and would tell the model its launch broke when
    what broke was its patience.

    The row is read whether or not the wait ran out, which is also what closes
    the hand-off race: ``_watch`` commits before it sets ``done``, so a wait
    that expires inside that window finds a terminal row and returns the answer
    instead of a snapshot.
    """
    live.waiters += 1
    try:
        await asyncio.wait_for(live.done.wait(), timeout)
    except TimeoutError:
        pass
    finally:
        live.waiters -= 1
    row = get_task(engine, live.task_id)
    if row is None:
        raise TaskError(f"{live.task_id} vanished from the database mid-wait")
    return _from_row(row, waited=True, poked=live.poked)


def _resolve(engine, ref: str):
    """A task by its ``task_id`` OR by its subagent's wire session id.

    Both are handles the model legitimately holds — the task_id from the launch,
    the session id from a transcript read — and refusing one of them teaches it
    that the other is the wrong thing to say.
    """
    row = get_task(engine, ref)
    if row is None:
        row = task_by_sub_session(engine, ref)
    if row is None:
        raise TaskError(
            f"no task matches {ref!r} — it is neither a task_id in this database"
            " nor the session id of a subagent one owns. task_read() with no"
            " argument lists yours."
        )
    return row


@subtool(tool="task")
async def task(
    prompt: str,
    *,
    wait: bool = False,
    model: str | None = None,
    priority: str = "low",
    tools: bool = True,
    kind: str = "subagent",
    timeout: float | None = _TASK_TIMEOUT,
) -> TaskResult:
    """Launch a subagent in its own process and get on with your turn.

    The child is a fresh crow session — its own context, its own tool supply,
    its own transcript in the shared database — so the work it does and the
    reading it takes to do it never enter yours. What comes back is the answer,
    and only the answer.

    By default this does NOT block. You get a handle (``r.task_id``, plus
    ``r.session_id`` for the child's transcript) and the child runs on. When it
    finishes, the answer lands in your mailbox and wakes you: it arrives as a
    message at the top of your next turn, or mid-turn if you launched it
    ``priority="high"``. Do not poll. ``task_read`` is for "something looks
    wrong and I want to look", not for waiting.

    Args:
        prompt: the whole job. The child sees none of your conversation — it is
          not a fork — so anything it needs that is not on disk goes in here.
        wait: True blocks this cell until the child's turn ends and returns its
          answer in ``r.result``. Use it when the next line depends on the
          answer; otherwise leave it False and let the mailbox bring it. A wait
          that runs out is not a failure: you get the running snapshot, and the
          answer still arrives.
        model: the child's model (default: inherit yours).
        priority: "high" makes the completion interrupt your current turn
          instead of holding to the end of it. Reserve it for work you are
          blocked on.
        tools: False gives the child no tools at all — an interrogation, or a
          job that must not touch anything.
        kind: a label stored on the row and carried on the wake. Free text;
          other wake sources (a timer, a queued job) use their own.
        timeout: seconds a ``wait=True`` call blocks (default 900). None waits
          forever.

    Returns:
        TaskResult — ``.task_id`` the durable handle, ``.status`` the row's,
        ``.session_id`` the child's wire id (so
        ``memory("list", session_id=r.session_id)`` reads what it actually did
        rather than the summary of it), ``.result`` the answer when you waited
        for one, ``.poked`` whether the wake reached the bus. ``print(r.text)``
        is the display channel.

    Raises:
        TaskError: the child could not be started, or there is no identity rail
          or database to register it against. A failed launch closes its own row
          first, so nothing is left marked running that you cannot account for.

    Example:
        r = await task("read every file under src/ and list the ones that"
                       " import redis", priority="high")
        print(r.task_id, r.session_id)   # task-4 cool-otter-of-judgment
    """
    cell = _cell()
    engine = _engine()
    cwd = os.getcwd()
    servers = get_session_mcp_servers(engine, cell.session_id) if tools else []
    task_id = _register_task(
        engine, cell, prompt=prompt, model=model, priority=priority, kind=kind
    )
    driver = SubagentDriver()
    try:
        await driver.start(cwd, model=model, **child_config())
        sub = await driver.new_session(cwd, mcp_servers=servers)
    except Exception as e:
        # deliver=False: the caller is right here and about to be told by the
        # exception. The row still has to go terminal — a task left "running" is
        # a task its owner parks on forever.
        finish_task(
            engine,
            task_id,
            result=str(e),
            status="failed",
            content=f"[{task_id}: launch failed: {e}]",
            deliver=False,
        )
        with contextlib.suppress(Exception):
            await driver.close()
        raise TaskError(f"{task_id}: launch failed: {type(e).__name__}: {e}") from e
    set_task_sub_session(engine, task_id, sub)
    live = _arm(
        engine,
        task_id=task_id,
        owner=cell.session_id,
        sub=sub,
        priority=priority,
        kind=kind,
        driver=driver,
        prompt=prompt,
    )
    if not wait:
        return _snapshot(live)
    return await _outcome(engine, live, timeout)


@subtool(tool="task_send")
async def task_send(
    ref: str,
    prompt: str,
    *,
    wait: bool = False,
    model: str | None = None,
    timeout: float | None = _TASK_TIMEOUT,
) -> TaskResult:
    """Send another prompt to a subagent whose turn has ended.

    Same child, same session id, whole history preserved — a redirect or a
    follow-up rather than a new task, so the row keeps its ``task_id`` and its
    priority and the answer lands in the same mailbox.

    The task must NOT be mid-turn, and that is enforced rather than documented
    and hoped for: a second prompt queued behind a running turn is a redirect
    nobody sees, because the child is busy with the thing you were trying to
    stop. ``task_cancel`` first, then send — that ordering IS the redirect
    workflow.

    There is no ``priority`` argument. The row's priority is what the delivery
    is claimed under and what the wake is routed on, and a knob that changed one
    without the other would wake a session for a delivery it then declines.

    Args:
        ref: the ``task_id`` or the child's session id.
        prompt: the next instruction. The child remembers everything before it.
        wait: as ``task`` — True blocks for the answer.
        model: override for this turn (default: the one it was launched with).
        timeout: seconds a ``wait=True`` call blocks (default 900).

    Returns:
        TaskResult, as ``task``.

    Raises:
        TaskError: the task is mid-turn, or is marked running with no child of
          this kernel driving it (an orphan — cancel it first), or re-attaching
          to the child's session failed.
    """
    cell = _cell()
    engine = _engine()
    row = _resolve(engine, ref)
    sub = row.sub_session or ""
    if sub in _live():
        raise TaskError(
            f"{row.task_id} is mid-turn — subagent {sub} is live in this kernel."
            f' task_cancel("{row.task_id}") first, then send again: a prompt'
            " queued behind a running turn is a redirect nobody sees."
        )
    if row.status == "running":
        raise TaskError(
            f"{row.task_id} is marked running but no child of this kernel is"
            " driving it — whatever launched it is gone and the row was"
            f' orphaned. task_cancel("{row.task_id}") closes it, then send.'
        )
    if not sub:
        raise TaskError(
            f"{row.task_id} never got a subagent session, so there is nothing to"
            " re-attach to — launch a new task instead"
        )
    if not reopen_task(engine, row.task_id):
        raise TaskError(
            f"{row.task_id} went running again between the check and the write,"
            " so it was not reopened — nothing was sent"
        )
    cwd = os.getcwd()
    servers = get_session_mcp_servers(engine, cell.session_id)
    driver = SubagentDriver()
    try:
        await driver.start(cwd, model=model or row.model, **child_config())
        await driver.resume_session(sub, cwd, mcp_servers=servers)
    except Exception as e:
        finish_task(
            engine,
            row.task_id,
            result=str(e),
            status="failed",
            content=f"[{row.task_id}: re-attach to {sub} failed: {e}]",
            deliver=False,
        )
        with contextlib.suppress(Exception):
            await driver.close()
        raise TaskError(
            f"{row.task_id}: re-attach to {sub} failed: {type(e).__name__}: {e}"
        ) from e
    live = _arm(
        engine,
        task_id=row.task_id,
        owner=row.owner_session,
        sub=sub,
        priority=row.priority,
        kind=row.kind,
        driver=driver,
        prompt=prompt,
    )
    if not wait:
        return _snapshot(live)
    return await _outcome(engine, live, timeout)


def _cancel_orphan(engine, row) -> TaskResult:
    """Close out a task this kernel is not driving.

    A terminal row is nothing to do, and is reported as itself — if it
    completed, that hands back the answer, which beats a refusal. A RUNNING row
    with no live child is an orphan: the kernel that launched it was reset,
    which killed the kernel process, which closed the child's stdin, which ended
    the child. Nobody will ever finalize that row, and a task left running
    forever is a session that parks on it forever, so close it here.
    """
    if row.status != "running":
        return _from_row(row)
    cancel_task(engine, row.task_id)
    return TaskResult(
        task_id=row.task_id,
        status="cancelled",
        session_id=row.sub_session or "",
        prompt=row.prompt or "",
        result=(
            "no child of this kernel was driving it — the row had been orphaned"
            " and has been closed."
        ),
    )


@subtool(tool="task_cancel")
async def task_cancel(
    ref: str, *, timeout: float | None = _CANCEL_TIMEOUT
) -> TaskResult:
    """Stop a subagent mid-turn.

    Synchronous: when this returns the turn is dead and the row is terminal, so
    a ``task_send`` on the same task works immediately. A cancel whose ack lied
    — "sent", but still mid-turn — is how the redirect workflow dies.

    A cancel produces NO delivery. You called it, so you know; a "was cancelled"
    message in your own mailbox would tell you what you did.

    Cancelling a task this kernel is not driving is not an error either, and
    neither is cancelling one that already finished — see ``_cancel_orphan``.

    Args:
        ref: the ``task_id`` or the child's session id.
        timeout: seconds to wait for teardown (default 15). On expiry the result
          still says ``running`` and says why: the cancel went out, the row is
          just not terminal yet.

    Returns:
        TaskResult carrying the row's TRUE status. ``.waited`` is True — this
        call blocked, whether or not the block ran out.

    Raises:
        TaskError: no task matches ``ref``, or there is no database.
    """
    engine = _engine()
    row = _resolve(engine, ref)
    live = _live().get(row.sub_session or "")
    if live is None:
        return _cancel_orphan(engine, row)
    # The turn can end naturally between that lookup and this call, and a dead
    # transport must not surface as a tool error — the row read below reports
    # what actually happened.
    with contextlib.suppress(Exception):
        await live.driver.cancel(live.sub)
    try:
        await asyncio.wait_for(live.done.wait(), timeout)
    except TimeoutError:
        return TaskResult(
            task_id=live.task_id,
            status="running",
            session_id=live.sub,
            prompt=live.prompt,
            waited=True,
            result=(
                f"cancel sent to {live.sub} but teardown was still in progress"
                f" after {timeout}s — the row is not terminal yet, so a"
                " task_send would bounce off it. Retry in a few seconds."
            ),
        )
    row = get_task(engine, live.task_id) or row
    return _from_row(row, waited=True, poked=live.poked)


@subtool(tool="task_read")
async def task_read(ref: str | None = None) -> TaskResult | TaskListResult:
    """Look at a task without waiting on it.

    With ``ref``, one task in full: its status, and its result if it has one.
    Without, the table of every task this session has launched — handles and
    states and no results, because a list that carried every answer would cost
    exactly the context the task system exists to protect.

    This is a look, not a wait. It does not block, it does not claim a delivery,
    and calling it in a loop will not make the child finish sooner.

    Args:
        ref: a ``task_id`` or a child's session id. None lists yours.

    Returns:
        TaskResult for one task; TaskListResult for the table — ``len(r)``,
        ``r.tasks``, and ``print(r.text)`` for the aligned rendering.

    Raises:
        TaskError: no task matches ``ref``, or there is no identity rail or
          database.
    """
    engine = _engine()
    if ref is None:
        # Only the listing needs an owner: a named task carries its own, and
        # demanding identity to look at one would refuse a plain-Python caller
        # that pointed the rail at a database and nothing else.
        rows = owner_tasks(engine, _cell().session_id)
        return TaskListResult(tasks=[_from_row(row) for row in rows])
    return _from_row(_resolve(engine, ref))
