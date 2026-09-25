"""rlm, driving a real delegate over a real pipe.

The subject is :mod:`crow_cli.tools.rlm_tool`. The child is a scripted ACP v2 agent
in a subprocess — the peer end of the protocol, not a stand-in for the code
under test — and it does what a real crow fork does and a stub cannot: it mints
the fork's agent row off the trunk's head and writes the delegate's answer
under it, so ``_delegate_answer`` reads a real fork chain (the trunk prefix plus
the fork's own rows) out of the shared database instead of something arranged
behind its back.

What the unit tier cannot reach and this one can: a delegation that actually
spawns, a fork request that actually carries the depth budget, an answer that
actually comes back out of sqlite, and — the reason
:class:`crow_cli.client2.SubagentDriver` grew a ``wait`` — a wait that runs out
and hands the turn to the background instead of killing the delegate. The pure
refusals (no rail, no database, spent budget) live in
tests/unit/test_tools_rlm.py and are not repeated here.
"""

from __future__ import annotations

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

import crow_cli.tools.rlm_tool  # noqa: F401 — the module, not the lazy binding
from crow_cli.client2 import subagent as subagent_mod
from crow_cli.memory import (
    add_message,
    create_agent,
    create_database,
    get_agent,
    get_engine,
    last_assistant_text,
    load_agent_messages,
    set_agent_mcp_servers,
)
from crow_cli.tools.register import begin_cell, clear
from crow_cli.tools.results import RlmResult, RlmToolError
from crow_cli.tools.rlm_tool import _dispose, _state, rlm

#: ``from crow_cli.tools import rlm`` would hand back the FUNCTION, not the
#: module: the package's PEP-562 ``__getattr__`` serves the lazy table and
#: ``rlm`` is one of its bindings. One assertion below needs the module.
rlm_mod = sys.modules["crow_cli.tools.rlm_tool"]

#: A made-up session id. Nothing here touches the wake bus, but a name no
#: deployment has keeps a stray write attributable if that ever changes.
OWNER = "quiet-heron-of-delegation"
TRUNK = f"{OWNER}-1-1"
FORK = f"{OWNER}-1-2"

#: An interpreter start, a crow import and two sqlite writes, per delegate.
#: Every wait here is bounded, so a regression fails instead of hanging — and
#: that includes every blocking ``rlm()`` call, whose own default is 900s: a
#: delegate that never idles should cost a minute of suite time, not fifteen.
SETTLE_TIMEOUT = 60.0


CHILD = r'''"""A scripted ACP v2 delegate: the peer end of the wire for the rlm tests.

Not a mock of anything under test — the subject is :mod:`crow_cli.tools.rlm_tool`.
What makes this one useful is that it does what a real crow fork does and a stub
cannot: ``session/fork`` mints the fork's agent row off the trunk's head, and
the turn writes the delegate's answer under that row, so the parent's
``_delegate_answer`` reads a real fork chain out of the shared database.

Directives are whole words on the CALLER'S line, which is the last one: rlm
wraps the request in a preamble, so there is no head left to partition on, and
a substring match would fire on the preamble itself — it says "change nothing",
and "change" contains "hang". ``hang`` never idles, ``die`` exits hard
mid-turn, ``slow:N`` sleeps.
"""

import asyncio
import os
import sys
import traceback

from acp.experimental import v2

from crow_cli.memory import (
    Message,
    Session,
    add_message,
    create_agent,
    get_engine,
    get_max_agent_idx,
    get_max_fork_idx,
)

s = v2.schema
DB = os.environ["CROW_RLM_TEST_DB"]
PROBE = os.environ.get("CROW_RLM_TEST_PROBE", "")


def say(line):
    """stderr AND a probe file, both flushed.

    The file is the channel that matters: the parent's driver is closed by the
    time most of these lines are interesting, and what a fork request carried
    is the one thing the parent cannot see from its side of the wire.
    """
    print(line, file=sys.stderr)
    sys.stderr.flush()
    if PROBE:
        with open(PROBE, "a") as fh:
            fh.write(line + "\n")


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


def mint_fork(session_id):
    """The fork's wire id, plus the row that makes it addressable.

    ``forked_at`` is the trunk's head message id, so the fork's history is the
    trunk PREFIX followed by its own rows — the chain ``load_agent_messages``
    walks, and the one a trunk scan reads wrong.
    """
    engine = get_engine(DB)
    try:
        idx = get_max_agent_idx(engine, session_id=session_id)
        trunk = "%s-%d-1" % (session_id, idx)
        with Session(engine) as db:
            head = (
                db.query(Message.id)
                .filter_by(agent_id=trunk)
                .order_by(Message.id.desc())
                .first()
            )
        fork_idx = get_max_fork_idx(engine, session_id, idx) + 1
        fork_id = "%s-%d-%d" % (session_id, idx, fork_idx)
        create_agent(
            engine, agent_id=fork_id, session_id=session_id, agent_idx=idx,
            fork_idx=fork_idx, forked_at=str(head[0]) if head else None,
            system_prompt="", cwd=os.getcwd(),
        )
        return fork_id
    finally:
        engine.dispose()


def remember(fork_id, text):
    """Persist the delegate's answer the way a real child does."""
    engine = get_engine(DB)
    try:
        add_message(
            engine, fork_id,
            {"role": "assistant", "content": [{"type": "text", "text": text}]},
        )
    finally:
        engine.dispose()


class ScriptedDelegate:
    def __init__(self):
        self.conn = None
        self.turn_task = None

    def on_connect(self, conn):
        self.conn = conn

    # rc2's router hands a handler the request's FIELDS as keywords, with its
    # _meta spread in among them — so ``**meta`` below IS the fork's _meta.
    async def initialize(self, protocol_version, info, capabilities=None, **kw):
        say("initialized")
        return s.InitializeResponse(
            protocol_version=v2.PROTOCOL_VERSION,
            info=s.Implementation(name="scripted-rlm-child", version="0.0.1"),
            capabilities=s.AgentCapabilities(),
        )

    async def fork_session(self, session_id, cwd, additional_directories=None,
                           mcp_servers=None, **meta):
        fork_id = mint_fork(session_id)
        say(
            "forked %s -> %s meta=%s servers=%d"
            % (session_id, fork_id, meta or None, len(mcp_servers or []))
        )
        return s.ForkSessionResponse(session_id=fork_id)

    async def prompt(self, session_id, prompt, **kw):
        text = "".join(getattr(b, "text", "") for b in prompt)
        say("prompt %s %r" % (session_id, text))
        self.turn_task = asyncio.create_task(self._turn(session_id, text))
        self.turn_task.add_done_callback(report)
        return s.PromptResponse(message_id="u1")

    async def _turn(self, session_id, text):
        body = text.strip().splitlines()[-1]
        words = body.split()
        # RunningSessionStateUpdate / IdleSessionStateUpdate are the wire
        # models. RunningStateUpdate and IdleStateUpdate are their payload
        # BASES and are not members of UpdateSessionNotification.update's
        # union, so sending one raises a ValidationError nobody retrieves.
        await self._send(session_id, s.RunningSessionStateUpdate())
        if "die" in words:
            say("dying")
            os._exit(3)
        if "hang" in words:
            say("hanging")
            await asyncio.Event().wait()
            return
        for word in words:
            if word.startswith("slow:"):
                await asyncio.sleep(float(word[5:]))
        reply = "the delegate answered: " + body
        await self._send(
            session_id,
            s.AgentMessageChunk(
                message_id="m-%s" % session_id,
                content=s.TextContentBlock(text=reply),
            ),
        )
        remember(session_id, reply)
        say("answered %s" % session_id)
        await self._send(session_id, s.IdleSessionStateUpdate(stop_reason="end_turn"))

    async def cancel_session(self, session_id, **kw):
        say("cancelled %s" % session_id)
        if self.turn_task is not None:
            self.turn_task.cancel()
        await self._send(session_id, s.IdleSessionStateUpdate(stop_reason="cancelled"))

    async def _send(self, session_id, update):
        await self.conn.session_update(session_id=session_id, update=update)


asyncio.run(v2.run_agent(ScriptedDelegate()))
'''



@pytest.fixture(autouse=True)
def _clean():
    """Both ends: ``_state`` is a module global that outlives a test, so a
    handle table left behind by one would make the next one's assertions about
    it pass or fail on ordering rather than on behaviour."""
    clear()
    _state.setdefault("live", {}).clear()
    yield
    clear()
    _dispose()
    _state.get("live", {}).clear()


@asynccontextmanager
async def in_kernel(tmp_path, monkeypatch, *, servers=None):
    """The identity rail execute's prologue would inject, plus a delegate.

    ``agent_argv`` points at the scripted delegate so its behaviour is
    controllable; the argv itself is tested in
    tests/integration/test_client2_subagent.py, and tests/e2e spawns the real
    one. The database and probe paths ride the ENVIRONMENT, which is only
    reachable because :meth:`SubagentDriver.start` passes the whole of
    ``os.environ`` down — the trimmed MCP default would leave the child with no
    database to write its fork row into.
    """
    script = tmp_path / "delegate.py"
    script.write_text(CHILD)
    monkeypatch.setattr(
        subagent_mod, "agent_argv", lambda **_: [sys.executable, str(script)]
    )
    uri = f"sqlite:///{tmp_path}/crow.db"
    probe = tmp_path / "probe.log"
    monkeypatch.setenv("CROW_RLM_TEST_DB", uri)
    monkeypatch.setenv("CROW_RLM_TEST_PROBE", str(probe))
    create_database(uri)
    engine = get_engine(uri)
    try:
        # The trunk the delegation forks FROM. Two rows, so the fork's prefix
        # is a real chain for ``_delegate_answer`` to walk.
        create_agent(
            engine, agent_id=TRUNK, session_id=OWNER, agent_idx=1, fork_idx=1,
            system_prompt="you are crow", cwd=str(tmp_path),
        )
        add_message(engine, TRUNK, {"role": "system", "content": "you are crow"})
        add_message(engine, TRUNK, {"role": "user", "content": "is x.py relevant?"})
        if servers is not None:
            set_agent_mcp_servers(engine, TRUNK, servers)
        begin_cell(
            session_id=OWNER, db_uri=uri, parent_tool_call_id="call-abc"
        )
        yield engine, uri, probe
    finally:
        # Nothing may outlive the test: a live delegate is a live process, and
        # cancelling the task runs ``_drive``'s finally, which reaps it.
        live = list(_state.get("live", {}).values())
        for item in live:
            item.task.cancel()
        if live:
            await asyncio.gather(
                *(item.task for item in live), return_exceptions=True
            )
        _state.get("live", {}).clear()
        engine.dispose()
        clear()
        _dispose()


async def settled(timeout: float = SETTLE_TIMEOUT) -> None:
    """Wait for every background delegation to finish AND reap its driver.

    Awaits the tasks rather than polling the handle table: ``_drive`` pops its
    entry BEFORE the slow teardown, so an empty table means "no longer driving"
    and not yet "the child is gone". Awaiting also surfaces anything the task
    raised, which reading the table cannot.
    """
    live = list(_state.get("live", {}).values())
    if live:
        await asyncio.wait_for(
            asyncio.gather(*(item.task for item in live), return_exceptions=True),
            timeout,
        )
    assert not _state.get("live"), f"still driving {sorted(_state.get('live', {}))}"


async def said(probe: Path, needle: str, timeout: float = SETTLE_TIMEOUT) -> str:
    """The probe file, once it contains ``needle``.

    The child appends as it goes, so "the child wrote it" and "the parent can
    read it" are two moments; asserting on the file without waiting is a race
    that passes most of the time.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = probe.read_text() if probe.exists() else ""
        if needle in text:
            return text
        await asyncio.sleep(0.05)
    raise AssertionError(f"{needle!r} never reached the probe")


def answer_in(engine, fork_id: str) -> str:
    """What the delegate persisted, read the way rlm reads it."""
    agent = get_agent(engine, fork_id)
    assert agent is not None, f"no agent row for {fork_id}"
    return last_assistant_text(load_agent_messages(engine, agent))


# -- the port itself --------------------------------------------------------


def test_rlm_drives_the_v2_client_and_not_the_frozen_v1_one():
    """Stated as a fact rather than implied by a green run.

    ``crow_cli.client.subagent`` speaks ACP v1 at import time and agent1 is
    frozen, so a v2 kernel that reaches for it drags the old protocol — and a
    ``PromptResponse`` that still carries a stop reason — into every process
    that delegates. Nothing else in the suite would notice: both drivers are
    called ``SubagentDriver``, and both have a ``prompt``.
    """
    assert rlm_mod.SubagentDriver is subagent_mod.SubagentDriver
    assert rlm_mod.child_config is subagent_mod.child_config
    assert rlm_mod.ChildExited is subagent_mod.ChildExited


# -- a delegation, end to end ----------------------------------------------


async def test_a_blocking_delegation_returns_the_delegates_answer(
    tmp_path, monkeypatch
):
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri, probe):
        r = await rlm("is x.py relevant? answer yes or no", timeout=SETTLE_TIMEOUT)
        assert isinstance(r, RlmResult)
        assert r.waited is True
        assert r.depth == 1
        assert r.stop_reason == "end_turn"
        assert r.session_id == FORK, "a fork's wire id IS its agent_id"
        assert r.answer == "the delegate answered: is x.py relevant? answer yes or no"
        # The answer came out of the fork CHAIN, not off the wire: the trunk
        # prefix plus the fork's own rows, which is the read task's trunk scan
        # gets wrong for a delegate.
        assert answer_in(engine, FORK) == r.answer
        assert get_agent(engine, FORK).fork_idx == 2
        await said(probe, "answered")
    assert not _state.get("live"), "a waited-for delegate is reaped, not kept"


async def test_the_fork_carries_the_offset_and_the_depth_budget(
    tmp_path, monkeypatch
):
    """Neither number is in the v2 schema — ``ForkSessionRequest`` carries the
    environment and nothing else — so both ride ``_meta``, and both come off
    the rail rather than off an argument a model could forge."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri, probe):
        r = await rlm("is x.py relevant?", offset=3, timeout=SETTLE_TIMEOUT)
        text = await said(probe, "meta=")
    assert r.depth == 1
    assert "meta={'messageOffset': 3, 'rlmDepth': 1}" in text


async def test_the_delegate_is_told_its_budget_is_spent(tmp_path, monkeypatch):
    """Enforced twice: on the rail, which refuses a delegate that tries to
    delegate, and in the delegate's own prompt, because a delegate that does
    not KNOW it is one deep is a delegate that tries."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri, probe):
        await rlm("is x.py relevant?", timeout=SETTLE_TIMEOUT)
        text = await said(probe, "prompt ")
    assert "delegation 1 of a maximum 1" in text
    assert "rlm() will refuse you" in text


async def test_the_tool_supply_is_the_callers_decision(tmp_path, monkeypatch):
    """``mcp_servers=[]`` means ZERO tools, which is what an interrogation
    fork wants — and the client owns that decision exactly as for a new
    session, because the agent cannot know what "ask a copy of me" meant."""
    servers = [{"type": "stdio", "name": "gate", "command": "/bin/true"}]
    inherited = tmp_path / "inherited"
    stripped = tmp_path / "stripped"
    inherited.mkdir()
    stripped.mkdir()
    async with in_kernel(inherited, monkeypatch, servers=servers) as (e1, u1, p1):
        await rlm("with the tools", timeout=SETTLE_TIMEOUT)
        first = await said(p1, "servers=")
    async with in_kernel(stripped, monkeypatch, servers=servers) as (e2, u2, p2):
        await rlm("without the tools", tools=False, timeout=SETTLE_TIMEOUT)
        second = await said(p2, "servers=")
    assert "servers=1" in first
    assert "servers=0" in second


# -- not blocking -----------------------------------------------------------


async def test_an_async_delegation_returns_a_handle_and_finishes_alone(
    tmp_path, monkeypatch
):
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri, probe):
        r = await rlm("slow:1 then answer: is x.py relevant?", wait=False)
        assert r.waited is False
        assert r.answer == ""
        assert r.session_id == FORK
        assert 'memory("list"' in r.text, "the handle says how to collect it"
        live = _state["live"][FORK]
        assert live.driver.proc is not None
        assert live.driver.proc.returncode is None
        await settled()
        # The transcript IS the mailbox: nobody waited, and the answer is there.
        assert answer_in(engine, FORK) == (
            "the delegate answered: slow:1 then answer: is x.py relevant?"
        )
    assert live.driver.proc is None, "settled means the driver was closed"


async def test_a_wait_that_runs_out_hands_off_instead_of_killing(
    tmp_path, monkeypatch
):
    """The behaviour the port changed, and the reason the driver grew ``wait``.

    v1 raised ``RlmToolError`` here and closed the driver in the same
    ``finally`` — which terminates the child — while its own message promised
    the delegate "is not lost: its transcript keeps growing under that id".
    What ran out is the caller's patience, not the delegate's turn, and
    ``task``'s ``_outcome`` already had the honest version: a wait that expires
    is not a failure.
    """
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri, probe):
        r = await rlm("hang in there, then answer", timeout=0.5)
        assert r.waited is False, "an expired wait is a handle, not an error"
        assert r.answer == ""
        live = _state["live"][FORK]
        proc = live.driver.proc
        await said(probe, "hanging")
        assert proc is not None and proc.returncode is None, (
            "the delegate is still alive — that is the whole claim"
        )
        # Still REACHABLE, which is what turns "not lost" from a promise into
        # something a caller can act on: the handle holds the only reference
        # to the child process there is.
        await live.driver.cancel(FORK)
        await settled()
        assert proc.returncode is not None, "handed off, then reaped — not orphaned"


async def test_a_delegate_that_dies_is_reported_and_not_hung(tmp_path, monkeypatch):
    """A dead child will never send another notification, so waiting on the
    queue anyway is how a delegation burns its whole timeout and then reports
    a slowness that never happened."""
    async with in_kernel(tmp_path, monkeypatch) as (engine, uri, probe):
        with pytest.raises(RlmToolError) as exc:
            await rlm("die on the spot", timeout=SETTLE_TIMEOUT)
        assert not _state.get("live"), "a dead delegate is nobody's to keep"
    assert "died before it answered" in str(exc.value)
    assert "child process exited with code 3" in str(exc.value)
