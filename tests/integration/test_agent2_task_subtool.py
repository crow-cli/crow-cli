"""The task subtool, driving real children over real pipes.

The subject is :mod:`crow_cli.tools.task`: its rows, its mailbox, its watcher,
its wake. The child is a scripted ACP v2 agent in a subprocess — the peer end of
the protocol, not a stand-in for the code under test — and it writes its own
transcript into the shared sqlite as it goes, so ``_child_answer`` reads a real
trunk chain instead of something arranged behind its back.

What the unit tier cannot reach and this one can: a launch that actually
spawns, a completion that actually lands in the mailbox, a cancel that actually
reaps a process, a poke that actually crosses a redis socket. The pure refusals
— no rail, no database, a mid-turn send — live in tests/unit/test_tools_task.py
and are not repeated here.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time
from contextlib import asynccontextmanager

import pytest
import redis
import redis.asyncio as aioredis

from crow_cli.client2 import subagent as subagent_mod
from crow_cli.memory import (
    create_agent,
    create_database,
    get_engine,
    list_agents,
    set_agent_mcp_servers,
)
from crow_cli.memory.reads import get_task, owner_tasks, pending_deliveries
from crow_cli.tools.register import begin_cell, clear, pending
from crow_cli.tools.results import TaskError, TaskResult
from crow_cli.tools.task import (
    _dispose,
    _live,
    task,
    task_cancel,
    task_read,
    task_send,
)
from crow_cli.wake import CHANNEL, Poke

CHILD = r'''
"""A scripted ACP v2 subagent: the peer end of the wire for the task tests.

Not a mock of anything under test. The subject is :mod:`crow_cli.tools.task` —
its rows, its mailbox, its watcher — and a child agent is the other side of the
protocol. What makes this one useful is that it does what a real crow child does
and a stub cannot: it writes its own transcript into the shared database as the
turn progresses, so ``_child_answer`` reads a real trunk chain rather than
something the test arranged behind its back.

Directives ride the prompt, before a ``|``: ``slow:N`` sleeps, ``hang`` never
idles, ``die`` exits hard mid-turn.
"""

import asyncio
import os
import sys
import traceback

from acp.experimental import v2

from crow_cli.memory import add_message, create_agent, get_engine, list_agents

s = v2.schema
DB = os.environ["CROW_TASK_TEST_DB"]


def say(line):
    """stderr, flushed: the parent asserts on these, so they must arrive."""
    print(line, file=sys.stderr)
    sys.stderr.flush()


def report(task):
    """A turn that raises has to be NOISY. Nobody retrieves a bare
    ``create_task``'s exception, so a crash in the turn looks exactly like a
    hang from the parent's side of the pipe."""
    if task.cancelled():
        return
    if exc := task.exception():
        say("turn failed: %r" % (exc,))
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()


def remember(session_id, text):
    """Persist the turn the way a real crow child does, and return its index.

    The next trunk ``agent_idx`` is computed rather than counted in-process:
    ``task_send`` resumes this session in a FRESH child, whose own counter
    would start at one again and collide with the row already there.
    """
    engine = get_engine(DB)
    try:
        seen = [a.agent_idx for a in list_agents(engine, session_id=session_id)]
        idx = max(seen, default=0) + 1
        agent_id = "%s-%d-1" % (session_id, idx)
        create_agent(
            engine, agent_id=agent_id, session_id=session_id, agent_idx=idx,
            fork_idx=1, system_prompt="", cwd=os.getcwd(),
        )
        add_message(engine, agent_id, {"role": "user", "content": text})
        add_message(
            engine, agent_id,
            {"role": "assistant",
             "content": [{"type": "text", "text": "pong: " + text}]},
        )
        return idx
    finally:
        engine.dispose()


class ScriptedChild:
    def __init__(self):
        self.conn = None
        self.sessions = 0
        self.turn_task = None

    def on_connect(self, conn):
        self.conn = conn

    # rc2's router hands a handler the request's FIELDS as keywords, with its
    # _meta spread in among them, so each signature names what it reads and
    # catches the rest.
    async def initialize(self, protocol_version, info, capabilities=None, **kw):
        say("initialized")
        return s.InitializeResponse(
            protocol_version=v2.PROTOCOL_VERSION,
            info=s.Implementation(name="scripted-task-child", version="0.0.1"),
            capabilities=s.AgentCapabilities(),
        )

    async def new_session(self, cwd, additional_directories=None,
                          mcp_servers=None, **kw):
        self.sessions += 1
        say("new-session cwd=%s servers=%d" % (cwd, len(mcp_servers or [])))
        return s.NewSessionResponse(session_id="child-%d" % self.sessions)

    async def resume_session(self, session_id, cwd, additional_directories=None,
                             mcp_servers=None, replay_from=None, **kw):
        say("resumed %s servers=%d" % (session_id, len(mcp_servers or [])))
        return s.ResumeSessionResponse()

    async def prompt(self, session_id, prompt, **kw):
        text = "".join(getattr(b, "text", "") for b in prompt)
        say("prompt %s %r" % (session_id, text))
        self.turn_task = asyncio.create_task(self._turn(session_id, text))
        self.turn_task.add_done_callback(report)
        return s.PromptResponse(message_id="u1")

    async def _turn(self, session_id, text):
        head, sep, body = text.partition("|")
        directives, body = (head.split(), body) if sep else ([], text)
        # RunningSessionStateUpdate / IdleSessionStateUpdate are the wire
        # models. RunningStateUpdate and IdleStateUpdate are their payload
        # BASES and are not members of UpdateSessionNotification.update's
        # union, so sending one raises a ValidationError nobody retrieves.
        await self._send(session_id, s.RunningSessionStateUpdate())
        for directive in directives:
            if directive == "die":
                say("dying")
                os._exit(3)
            if directive == "hang":
                say("hanging")
                await asyncio.Event().wait()
                return
            if directive.startswith("slow:"):
                await asyncio.sleep(float(directive[5:]))
        await self._send(
            session_id,
            s.AgentMessageChunk(
                message_id="m-%s" % session_id,
                content=s.TextContentBlock(text="pong: " + body),
            ),
        )
        idx = remember(session_id, body)
        say("turn %d done for %s" % (idx, session_id))
        await self._send(session_id, s.IdleSessionStateUpdate(stop_reason="end_turn"))

    async def cancel_session(self, session_id, **kw):
        say("cancelled %s" % session_id)
        if self.turn_task is not None:
            self.turn_task.cancel()
        await self._send(session_id, s.IdleSessionStateUpdate(stop_reason="cancelled"))

    async def _send(self, session_id, update):
        await self.conn.session_update(session_id=session_id, update=update)


asyncio.run(v2.run_agent(ScriptedChild()))
'''

OWNER = "brave-otter-of-judgment"

#: An interpreter start, a crow import and a sqlite write, per child. Every
#: wait here is bounded, so a regression fails instead of hanging the suite.
START_TIMEOUT = 60.0
SETTLE_TIMEOUT = 60.0

REDIS_URL = os.getenv("CROW_REDIS_URL", "redis://localhost:6379/0")
#: A port nothing listens on. The dead-bus test needs a real refusal, not a
#: mocked one: ECONNREFUSED and "the client raised what we told it to" are
#: different claims.
DEAD_URL = "redis://localhost:6399/0"


def _bus_available() -> bool:
    try:
        client = redis.from_url(
            REDIS_URL, socket_connect_timeout=1.0, socket_timeout=1.0
        )
        client.ping()
        client.close()
        return True
    except Exception:
        return False


requires_bus = pytest.mark.skipif(
    not _bus_available(), reason=f"no redis at {REDIS_URL} (compose up -d redis)"
)


@pytest.fixture(autouse=True)
def _clean():
    clear()
    yield
    clear()
    _dispose()
    _live().clear()


@asynccontextmanager
async def in_kernel(tmp_path, monkeypatch, *, bus: str = ""):
    """The identity rail execute's prologue would inject, plus a child.

    ``agent_argv`` points at the scripted child so its behaviour is
    controllable; the argv itself has its own tests, and
    tests/e2e/test_agent2_live.py spawns the real one. ``CROW_TASK_TEST_DB``
    rides the environment, which is only reachable because
    :meth:`SubagentDriver.start` passes the whole of ``os.environ`` down — the
    trimmed default would leave the child with no database to write to.
    """
    script = tmp_path / "child.py"
    script.write_text(CHILD)
    monkeypatch.setattr(
        subagent_mod, "agent_argv", lambda **_: [sys.executable, str(script)]
    )
    uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(uri)
    monkeypatch.setenv("CROW_TASK_TEST_DB", uri)
    begin_cell(
        session_id=OWNER, db_uri=uri, redis_url=bus, parent_tool_call_id="call-abc"
    )
    engine = get_engine(uri)
    try:
        yield engine, uri
    finally:
        # Nothing may outlive the test: a live task is a live process.
        for live in list(_live().values()):
            with contextlib.suppress(Exception):
                await live.driver.cancel(live.sub)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(live.watcher, SETTLE_TIMEOUT)
            with contextlib.suppress(Exception):
                await live.driver.close()
        _live().clear()
        engine.dispose()
        clear()
        _dispose()


async def settled(engine, task_id: str, timeout: float = SETTLE_TIMEOUT):
    """The row, once it is terminal.

    Polls rather than sleeping a fixed amount: the watcher is a task in this
    loop, but the child is a separate process and there is no in-process event
    standing for "the answer has been read out of sqlite".
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = get_task(engine, task_id)
        if row is not None and row.status != "running":
            return row
        await asyncio.sleep(0.05)
    raise AssertionError(f"{task_id} was still running after {timeout}s")


async def reaped(live, timeout: float = SETTLE_TIMEOUT) -> None:
    """Wait for the watcher to finish tearing down.

    ``done`` is set before the driver is closed, so a test that asserts on the
    child process has to wait for the watcher itself. Awaiting the task also
    surfaces anything it raised, which a bare ``done.wait()`` would swallow.
    """
    await asyncio.wait_for(live.watcher, timeout)


async def wait_for_stderr(driver, needle: str, timeout: float = START_TIMEOUT) -> str:
    """The child's stderr tail, once it contains ``needle``.

    The drainer is its own task reading a pipe from its own process, so "the
    child printed it" and "the parent has read it" are two moments.
    """

    async def poll():
        while needle not in driver.stderr_tail:
            await asyncio.sleep(0.02)

    await asyncio.wait_for(poll(), timeout)
    return driver.stderr_tail


def give_owner_tools(engine, servers: list[dict]) -> None:
    """Provision the owner's row with a tool supply, the way ``sessions.create``
    does — ``get_session_mcp_servers`` reads it back off the agents table."""
    agent_id = f"{OWNER}-1-1"
    create_agent(
        engine, agent_id=agent_id, session_id=OWNER, agent_idx=1, fork_idx=1,
        system_prompt="", cwd="/tmp",
    )
    set_agent_mcp_servers(engine, agent_id, servers)


async def _await_subscriber(timeout: float = 10.0) -> None:
    """Block until the server has registered a subscription on the channel.

    ``subscribe`` returning is not the same as the server having recorded it,
    and a publish issued into that gap goes nowhere. Asking the server is the
    only honest readiness signal — it is the party that decides whether a
    message has anywhere to go.
    """
    client = aioredis.from_url(REDIS_URL)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pairs = await client.pubsub_numsub(CHANNEL)
            if pairs and pairs[0][1] >= 1:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"nothing subscribed to {CHANNEL} within {timeout}s")
    finally:
        await client.aclose()


async def _next_poke(pubsub, session_id: str, timeout: float = SETTLE_TIMEOUT) -> Poke:
    """The next poke for ``session_id``, skipping anybody else's.

    One channel serves the whole deployment, so a subscriber has to expect
    traffic it does not own — which is the point of the design and a thing the
    test had better not trip over.
    """

    async def poll():
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=0.5
            )
            if message is not None and message.get("type") == "message":
                poke = Poke.decode(message["data"])
                if poke is not None and poke.session_id == session_id:
                    return poke
            await asyncio.sleep(0.02)

    return await asyncio.wait_for(poll(), timeout)


# -- launch ----------------------------------------------------------------


async def test_an_async_launch_registers_a_running_row_and_returns_a_handle(
    tmp_path, monkeypatch
):
    """STATE FIRST, and the handle is the point: the row exists, attributed to
    the rail's owner and to the execute call that launched it, before the child
    has said a word."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri):
        r = await task("slow:1|count the files")
        assert isinstance(r, TaskResult)
        assert r.task_id == "task-1"
        assert r.session_id == "child-1"
        assert r.status == "running"
        assert r.result == ""
        assert r.waited is False and r.poked is False

        row = get_task(engine, "task-1")
        assert row.status == "running"
        assert row.owner_session == OWNER
        assert row.sub_session == "child-1"
        assert row.tool_call_id == "call-abc"
        assert row.prompt == "slow:1|count the files"
        assert pending_deliveries(engine, OWNER) == []

        # One register entry, on the execute call that made it — the ACP half
        # of the three-fold split, and what the client renders.
        entries = pending()
        assert [e.tool for e in entries] == ["task"]
        assert entries[0].status == "completed"
        assert entries[0].result_kind == "task"
        assert entries[0].acp_payload["subject"] == "task-1"
        assert entries[0].parent_tool_call_id == "call-abc"

        row = await settled(engine, "task-1")
        assert row.status == "completed"
        assert row.result == "pong: count the files"
        mail = pending_deliveries(engine, OWNER)
        assert len(mail) == 1
        assert mail[0].task_id == "task-1"
        assert mail[0].priority == "low"
        assert "pong: count the files" in mail[0].content
        assert _live() == {}, "the watcher released the child"


async def test_a_wait_returns_the_answer_and_tells_nobody_twice(tmp_path, monkeypatch):
    """The waiter is holding the answer, so the mailbox stays empty. A delivery
    would inject the same text again as a user message at the top of the next
    turn — the duplication the whole design exists to avoid."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri):
        r = await task("count the files", wait=True)
        assert r.status == "completed"
        assert r.waited is True
        assert r.result == "pong: count the files"
        assert "pong: count the files" in r.text
        assert r.poked is False, "no delivery landed, so there was nothing to poke"
        assert pending_deliveries(engine, OWNER) == []
        assert _live() == {}


async def test_a_wait_that_runs_out_is_a_snapshot_not_a_failure(tmp_path, monkeypatch):
    """The hand-off. The wait expires, the caller is told it is still going, and
    the completion STILL reaches the mailbox — because the waiter count dropped
    to zero before the watcher committed. Raising here instead would record a
    failed subtool call for a task that did not fail, and would tell the model
    its launch broke when what broke was its patience."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri):
        r = await task("slow:2|count the files", wait=True, timeout=0.5)
        live = _live()["child-1"]
        assert r.status == "running"
        assert r.waited is True
        assert "you waited for it and it is still going" in r.text
        assert live.waiters == 0, "the waiter left, so the mailbox is the way home"

        await reaped(live)
        row = await settled(engine, "task-1")
        assert row.status == "completed"
        assert row.result == "pong: count the files"
        assert len(pending_deliveries(engine, OWNER)) == 1


# -- cancel ----------------------------------------------------------------


async def test_cancel_makes_the_row_terminal_with_no_delivery(tmp_path, monkeypatch):
    """Synchronous, and the ack means it: when task_cancel returns the row is
    terminal and the child is reaped, so a task_send works immediately."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri):
        r = await task("hang|count the files")
        live = _live()[r.session_id]
        proc = live.driver.proc
        await wait_for_stderr(live.driver, "hanging")

        c = await task_cancel(r.task_id)
        assert c.status == "cancelled"
        assert c.waited is True
        assert "no delivery to collect" in c.text
        await reaped(live)

        row = get_task(engine, "task-1")
        assert row.status == "cancelled"
        assert row.finished_at is not None
        assert pending_deliveries(engine, OWNER) == []
        assert _live() == {}
        # Taken before the cancel: the watcher's teardown closes the driver,
        # and close() drops its handle on the process it just reaped.
        assert proc.returncode is not None, "the child was reaped"


async def test_a_child_that_dies_mid_turn_marks_the_task_failed(
    tmp_path, monkeypatch
):
    """A dead child will never send another notification, so waiting on the
    queue is waiting for nothing. Without ChildExited this row stays "running"
    forever and its owner parks forever behind it."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri):
        r = await task("die|count the files")
        live = _live()[r.session_id]
        await reaped(live)

        row = await settled(engine, "task-1")
        assert row.status == "failed"
        assert "exited with code 3" in row.result
        mail = pending_deliveries(engine, OWNER)
        assert len(mail) == 1
        assert "failed" in mail[0].content
        assert _live() == {}


# -- steer -----------------------------------------------------------------


async def test_send_runs_a_second_turn_on_the_same_row(tmp_path, monkeypatch):
    """A redirect is not a new task: same task_id, same child session, whole
    history preserved, and the row's answer is the LATEST turn's."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri):
        first = await task("one", wait=True)
        assert first.status == "completed"
        assert first.result == "pong: one"

        second = await task_send(first.task_id, "two", wait=True)
        assert second.task_id == "task-1"
        assert second.session_id == first.session_id
        assert second.status == "completed"
        assert second.result == "pong: two"

        rows = owner_tasks(engine, OWNER)
        assert [t.task_id for t in rows] == ["task-1"]
        assert rows[0].result == "pong: two"
        # Two turns, one row, one session: the second is a new trunk agent_idx
        # under the SAME wire id, which is what makes the history continuous.
        assert len(list_agents(engine, session_id=first.session_id)) == 2
        assert pending_deliveries(engine, OWNER) == []


async def test_send_refuses_while_the_child_is_mid_turn(tmp_path, monkeypatch):
    """The unit test drives this with a table entry; here the child is real and
    the refusal still leaves the row exactly as it was."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri):
        r = await task("hang|one")
        live = _live()[r.session_id]
        await wait_for_stderr(live.driver, "hanging")

        with pytest.raises(TaskError, match="mid-turn"):
            await task_send(r.task_id, "two")
        assert get_task(engine, "task-1").status == "running"

        c = await task_cancel(r.task_id)
        assert c.status == "cancelled"


# -- read ------------------------------------------------------------------


async def test_read_sees_a_live_task_and_then_its_answer(tmp_path, monkeypatch):
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri):
        r = await task("slow:1|count the files")
        listing = await task_read()
        assert len(listing) == 1
        assert listing.tasks[0].status == "running"
        assert listing.tasks[0].result == ""

        await settled(engine, "task-1")
        one = await task_read(r.task_id)
        assert one.status == "completed"
        assert one.result == "pong: count the files"
        # A look is not a claim: the delivery is still there for the owner.
        assert len(pending_deliveries(engine, OWNER)) == 1


# -- tool supply -----------------------------------------------------------


async def test_the_child_inherits_the_owners_tool_supply(tmp_path, monkeypatch):
    """The [] cascade regression: a subagent that comes up toolless cannot do
    the work it was launched for, and nothing on the parent's side looks
    wrong."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri):
        give_owner_tools(
            engine,
            [{"name": "crow-mcp", "type": "stdio", "command": "/bin/true",
              "args": [], "env": []}],
        )
        r = await task("slow:1|count the files")
        tail = await wait_for_stderr(_live()[r.session_id].driver, "new-session")
        assert "servers=1" in tail
        await settled(engine, "task-1")


async def test_a_toolless_launch_gives_the_child_nothing(tmp_path, monkeypatch):
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri):
        give_owner_tools(
            engine,
            [{"name": "crow-mcp", "type": "stdio", "command": "/bin/true",
              "args": [], "env": []}],
        )
        r = await task("slow:1|answer from what you know", tools=False)
        tail = await wait_for_stderr(_live()[r.session_id].driver, "new-session")
        assert "servers=0" in tail
        await settled(engine, "task-1")


# -- the bus ---------------------------------------------------------------


@requires_bus
async def test_the_poke_goes_out_after_the_row_is_committed(tmp_path, monkeypatch):
    """The ordering the whole bus rests on: row first, poke second, and the
    poke says "go look" — a session, a task, the priority the delivery row
    carries and the kind. Nothing on the wire that could disagree with the
    row, because there is nothing on the wire but a pointer to it."""
    client = aioredis.from_url(REDIS_URL)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(CHANNEL)
        await _await_subscriber()
        async with in_kernel(tmp_path, monkeypatch, bus=REDIS_URL) as (engine, uri):
            r = await task("count the files", priority="high", kind="research")
            live = _live()[r.session_id]
            poke = await _next_poke(pubsub, OWNER)
            assert poke.task_id == r.task_id
            assert poke.priority == "high"
            assert poke.kind == "research"

            # Observable after the commit, therefore: already terminal, and the
            # delivery already claimable by whoever this poke just woke.
            row = get_task(engine, r.task_id)
            assert row.status == "completed"
            mail = pending_deliveries(engine, OWNER)
            assert [d.task_id for d in mail] == [r.task_id]
            assert mail[0].priority == "high"

            # The subscriber can be handed the message before the publisher's
            # own await resumes, so the flag is only guaranteed once the
            # watcher has finished — which is also the point by which the
            # child is down and the handle table is empty.
            await reaped(live)
            assert live.poked is True
            assert _live() == {}
    finally:
        await pubsub.aclose()
        await client.aclose()


@requires_bus
async def test_a_cancel_publishes_nothing(tmp_path, monkeypatch):
    """No delivery, so no poke. Waking a session to consult a mailbox with
    nothing in it spends a turn — and a model call — for nothing."""
    client = aioredis.from_url(REDIS_URL)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(CHANNEL)
        await _await_subscriber()
        async with in_kernel(tmp_path, monkeypatch, bus=REDIS_URL) as (engine, uri):
            r = await task("hang|count the files")
            live = _live()[r.session_id]
            await wait_for_stderr(live.driver, "hanging")

            c = await task_cancel(r.task_id)
            await reaped(live)
            assert c.status == "cancelled"
            assert live.poked is False
            assert pending_deliveries(engine, OWNER) == []
            with pytest.raises(TimeoutError):
                await _next_poke(pubsub, OWNER, timeout=2.0)
    finally:
        await pubsub.aclose()
        await client.aclose()


async def test_a_dead_bus_costs_latency_and_nothing_else(tmp_path, monkeypatch):
    """The row is the truth. A bus that refuses the connection must not lose a
    completion, must not raise into the watcher, and must not leave the mailbox
    wrong — the owner's backstop poll delivers it either way."""
    async with in_kernel(tmp_path, monkeypatch, bus=DEAD_URL) as (engine, uri):
        r = await task("count the files")
        live = _live()[r.session_id]
        await reaped(live)
        assert live.poked is False

        row = await settled(engine, "task-1")
        assert row.status == "completed"
        assert row.result == "pong: count the files"
        assert len(pending_deliveries(engine, OWNER)) == 1
