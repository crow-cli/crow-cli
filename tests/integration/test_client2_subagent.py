"""The headless ACP v2 client, tested against real children over real pipes.

Two kinds of child, and neither is a mock of the code under test. The code
under test is :class:`crow_cli.client2.SubagentDriver`; a child agent is the
*other end of the protocol*, so standing one up is not stubbing anything:

* a **scripted child** — a small v2 agent written to ``tmp_path`` and spawned
  as a subprocess. It exists because the behaviours worth testing have to be
  provoked on demand: a turn that hangs so cancellation has something to
  cancel, a quarter-megabyte stderr flood so the drain has something to drain.
* a **real ``crow_cli.agent2.main`` child** — one test, because every other
  test points ``agent_argv`` at the scripted child. An argv that no test ever
  executes is how a subagent ends up dead in production and green in CI.

``agent_argv`` is patched in the scripted tests rather than exercised, because
it is a pure function of the environment with its own tests below. Everything
else — spawn, stderr drain, handshake, sessions, turns, cancel, teardown — is
real in every test here, including the pipes.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import yaml
from acp.experimental import v2
from pydantic import ValidationError

from crow_cli.client2 import (
    ChildExited,
    HeadlessClient,
    SubagentDriver,
    child_config,
)
from crow_cli.client2 import subagent as subagent_mod
from crow_cli.client2.subagent import (
    STDERR_LINES,
    agent_argv,
    mcp_servers_to_models,
)

#: An interpreter start plus a crow import, and the flood test also pushes a
#: quarter megabyte through a pipe. Generous on purpose — but every wait here
#: is bounded, so a regression fails instead of hanging the suite.
START_TIMEOUT = 60.0
TURN_TIMEOUT = 30.0

#: Well past the 64KB a Linux pipe buffers. A parent that does not read the
#: child's stderr blocks the child on this many lines and never hears back.
FLOOD_LINES = 3000

SCRIPTED_CHILD = r'''"""A scripted ACP v2 agent: the peer end of the wire for the client2 tests.

Speaks real JSON-RPC over real stdio. Answers the handshake, mints session
ids, and reports turn outcomes as ``state_update`` notifications the way v2
requires — the prompt response is empty, so this is the only channel the
outcome has. Hangs on a prompt containing ``hang`` so cancellation has
something to cancel, and floods stderr on demand so the parent's drain has
something to drain.
"""

import asyncio
import os
import sys
import traceback

from acp.experimental import v2

s = v2.schema

FLOOD = __FLOOD__
HANG_ON = "hang"


def say(line):
    """stderr, flushed: the parent asserts on these, so they must arrive."""
    print(line, file=sys.stderr)
    sys.stderr.flush()


def report(task):
    """A turn that raises has to be NOISY.

    Nobody retrieves a bare ``create_task``'s exception, so a crash in the
    turn looks exactly like a hang from the parent's side of the pipe.
    """
    if task.cancelled():
        return
    if exc := task.exception():
        say("turn failed: %r" % (exc,))
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()


class ScriptedChild:
    def __init__(self):
        self.conn = None
        self.sessions = 0
        self.turn_task = None

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, request):
        say("initialized protocol=%s" % request.protocol_version)
        return s.InitializeResponse(
            protocol_version=v2.PROTOCOL_VERSION,
            info=s.Implementation(name="scripted-child", version="0.0.1"),
            capabilities=s.AgentCapabilities(),
        )

    async def new_session(self, request):
        self.sessions += 1
        say(
            "new-session cwd=%s servers=%d"
            % (request.cwd, len(request.mcp_servers or []))
        )
        return s.NewSessionResponse(session_id="child-%d" % self.sessions)

    async def resume_session(self, request):
        say("resumed %s replay_from=%s" % (request.session_id, request.replay_from))
        return s.ResumeSessionResponse()

    async def fork_session(self, request):
        say("forked %s meta=%s" % (request.session_id, request.field_meta))
        return s.ForkSessionResponse(session_id="fork-of-%s" % request.session_id)

    async def prompt(self, request):
        text = "".join(getattr(b, "text", "") for b in request.prompt)
        say("prompt %s %r" % (request.session_id, text))
        self.turn_task = asyncio.create_task(self._turn(request.session_id, text))
        self.turn_task.add_done_callback(report)
        return s.PromptResponse()

    async def _turn(self, session_id, text):
        # The wire models are Running/Idle/RequiresActionSessionStateUpdate.
        # RunningStateUpdate and IdleStateUpdate are their payload BASES and
        # are not members of UpdateSessionNotification.update's union, so
        # sending one raises a ValidationError that nobody retrieves.
        await self._send(session_id, s.RunningSessionStateUpdate())
        if "die" in text:
            say("dying on %r" % text)
            os._exit(3)
        if HANG_ON in text:
            say("hanging on %r" % text)
            await asyncio.Event().wait()
            return
        await self._send(
            session_id,
            s.AgentMessageChunk(
                message_id="m1", content=s.TextContentBlock(text="pong: " + text)
            ),
        )
        await self._send(session_id, s.IdleSessionStateUpdate(stop_reason="end_turn"))

    async def cancel_session(self, notification):
        say("cancelled %s" % notification.session_id)
        if self.turn_task is not None:
            self.turn_task.cancel()
        await self._send(
            notification.session_id,
            s.IdleSessionStateUpdate(stop_reason="cancelled"),
        )

    async def _send(self, session_id, update):
        await self.conn.session_update(
            s.UpdateSessionNotification(session_id=session_id, update=update)
        )


for _i in range(FLOOD):
    say("stderr-flood-line-%06d %s" % (_i, "x" * 60))
if FLOOD:
    say("stderr-flood-done")

_probe = os.environ.get("CROW_CLIENT2_PROBE")
if _probe:
    say("env-probe=%s" % _probe)

asyncio.run(v2.run_agent(ScriptedChild()))
'''


def child_source(flood: int = 0) -> str:
    return SCRIPTED_CHILD.replace("__FLOOD__", str(flood))


@asynccontextmanager
async def scripted(tmp_path, monkeypatch, *, flood: int = 0, name: str = "child.py"):
    """A started :class:`SubagentDriver` talking to the scripted child.

    ``agent_argv`` is pointed at the script instead of ``crow_cli.agent2.main``
    so the child's behaviour is controllable; the argv itself is tested
    directly below and end to end in the real-child test.
    """
    script = tmp_path / name
    script.write_text(child_source(flood))
    argv = [sys.executable, str(script)]
    monkeypatch.setattr(subagent_mod, "agent_argv", lambda **_: argv)
    driver = SubagentDriver()
    try:
        await asyncio.wait_for(driver.start(str(tmp_path)), START_TIMEOUT)
        yield driver
    finally:
        await driver.close()


async def wait_for_update(driver, pred, timeout: float = TURN_TIMEOUT):
    """The first recorded update matching ``pred``.

    Polls the record rather than sleeping a fixed amount: the child is a
    separate process, so there is no in-process event to await.
    """

    async def poll():
        while True:
            for update in list(driver.client.updates):
                if pred(update):
                    return update
            await asyncio.sleep(0.02)

    return await asyncio.wait_for(poll(), timeout)


async def wait_for_stderr(driver, needle: str, timeout: float = TURN_TIMEOUT) -> str:
    """The child's stderr tail, once it contains ``needle``.

    The drainer is its own task reading a pipe from its own process, so "the
    child printed it" and "the parent has read it" are two moments. Asserting
    on the tail without waiting for it is a race that passes most of the time.
    """

    async def poll():
        while needle not in driver.stderr_tail:
            await asyncio.sleep(0.02)

    await asyncio.wait_for(poll(), timeout)
    return driver.stderr_tail


def is_running(update) -> bool:
    return getattr(update, "session_update", None) == "state_update" and getattr(
        update, "state", None
    ) == "running"


def make_child_config(tmp_path: Path) -> Path:
    """A hermetic config dir for a real agent2 child.

    A provider and a model must exist for ``config.is_configured``; neither is
    contacted, because nothing here sends a prompt. ``db_uri`` points at a
    throwaway sqlite so the child's ``session/new`` writes rows nowhere else
    can see.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / ".env").write_text("API_KEY=child-key\n")
    (config_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "child-provider": {
                        "api_key": "${API_KEY}",
                        "base_url": "https://child.invalid/v1",
                    }
                },
                "models": {
                    "child-model": {
                        "provider": "child-provider",
                        "model": "child-model-id",
                    }
                },
                "db_uri": "sqlite:///%s" % (tmp_path / "child.db"),
            }
        )
    )
    return config_dir


def notif(session_id: str, update):
    return v2.schema.UpdateSessionNotification(session_id=session_id, update=update)


# -- the driver, over a real pipe ------------------------------------------


async def test_the_handshake_yields_a_child_that_mints_session_ids(tmp_path, monkeypatch):
    async with scripted(tmp_path, monkeypatch) as driver:
        first = await asyncio.wait_for(driver.new_session(str(tmp_path)), TURN_TIMEOUT)
        second = await asyncio.wait_for(driver.new_session(str(tmp_path)), TURN_TIMEOUT)
        tail = await wait_for_stderr(driver, "initialized protocol=")
    assert first == "child-1"
    assert second == "child-2", "a second session/new must mint a second id"
    assert "initialized protocol=2" in tail


async def test_prompt_returns_the_stop_reason_the_idle_update_carried(
    tmp_path, monkeypatch
):
    """The v2 inversion: ``PromptResponse`` is empty, so the outcome arrives
    as a notification and somebody has to watch for it."""
    async with scripted(tmp_path, monkeypatch) as driver:
        sid = await asyncio.wait_for(driver.new_session(str(tmp_path)), TURN_TIMEOUT)
        stop = await asyncio.wait_for(driver.prompt(sid, "ping"), TURN_TIMEOUT)
        updates = list(driver.client.updates)

    assert stop == "end_turn"
    assert is_running(updates[0]), "running must precede the chunks"
    text = "".join(
        getattr(u.content, "text", "")
        for u in updates
        if getattr(u, "session_update", None) == "agent_message_chunk"
    )
    assert text == "pong: ping"


async def test_a_prompt_that_never_idles_times_out_rather_than_hanging(
    tmp_path, monkeypatch
):
    async with scripted(tmp_path, monkeypatch) as driver:
        sid = await asyncio.wait_for(driver.new_session(str(tmp_path)), TURN_TIMEOUT)
        with pytest.raises(TimeoutError):
            await driver.prompt(sid, "please hang", timeout=0.5)
        await driver.cancel(sid)
        await wait_for_stderr(driver, "cancelled")


async def test_wait_picks_up_a_turn_a_timed_out_prompt_left_in_flight(
    tmp_path, monkeypatch
):
    """The seam a hand-off rides: ``prompt`` is ``wait`` plus the send.

    A timeout cancels the getter but leaves the queue, so a second wait finds
    the reason that arrives afterwards instead of waiting for a notification
    that already came. Without this, the only way to stop waiting on a slow
    delegate is to kill it — which is what rlm used to do while its own error
    message promised the delegate was "not lost".
    """
    async with scripted(tmp_path, monkeypatch) as driver:
        sid = await asyncio.wait_for(driver.new_session(str(tmp_path)), TURN_TIMEOUT)
        with pytest.raises(TimeoutError):
            await driver.prompt(sid, "please hang", timeout=0.5)
        handed_off = asyncio.create_task(driver.wait(sid))
        await driver.cancel(sid)
        assert await asyncio.wait_for(handed_off, TURN_TIMEOUT) == "cancelled"
        await wait_for_stderr(driver, "cancelled")


async def test_a_child_that_dies_mid_turn_raises_instead_of_hanging(
    tmp_path, monkeypatch
):
    """The queue the idle would have landed in is never going to fill, so
    waiting on it is waiting for nothing. A task watcher that waits forever
    leaves its row "running" forever, with its owner parked behind it — which
    is the one failure the whole mailbox design exists to prevent.
    """
    async with scripted(tmp_path, monkeypatch) as driver:
        sid = await asyncio.wait_for(driver.new_session(str(tmp_path)), TURN_TIMEOUT)
        with pytest.raises(ChildExited) as exc:
            await asyncio.wait_for(driver.prompt(sid, "die please"), TURN_TIMEOUT)
        assert driver.proc.returncode == 3
    assert "child process exited with code 3" in str(exc.value)


async def test_cancel_ends_a_hung_turn_and_the_session_survives_it(tmp_path, monkeypatch):
    async with scripted(tmp_path, monkeypatch) as driver:
        sid = await asyncio.wait_for(driver.new_session(str(tmp_path)), TURN_TIMEOUT)
        hung = asyncio.create_task(driver.prompt(sid, "hang please"))
        await wait_for_update(driver, is_running)
        await driver.cancel(sid)
        assert await asyncio.wait_for(hung, TURN_TIMEOUT) == "cancelled"

        # The redirect story: cancellation is per-turn, so the same session id
        # is still promptable and still reports its own outcome.
        again = await asyncio.wait_for(driver.prompt(sid, "again"), TURN_TIMEOUT)
    assert again == "end_turn"


async def test_a_child_that_floods_stderr_does_not_deadlock_its_parent(
    tmp_path, monkeypatch
):
    """v1 opened the child's stderr pipe and never read it. A child that logs
    more than the pipe buffers then blocks on the write and hangs with no
    error on either side — so the drain is load-bearing, not tidy."""
    async with scripted(tmp_path, monkeypatch, flood=FLOOD_LINES) as driver:
        sid = await asyncio.wait_for(driver.new_session(str(tmp_path)), TURN_TIMEOUT)
        stop = await asyncio.wait_for(driver.prompt(sid, "ping"), TURN_TIMEOUT)
        tail = await wait_for_stderr(driver, "stderr-flood-done")

    assert stop == "end_turn", "the turn completed, so the pipe never filled"
    assert len(tail.splitlines()) <= STDERR_LINES, "the tail is bounded"
    assert "stderr-flood-line-000000" not in tail, "it keeps the END, not the start"


async def test_the_child_inherits_the_parents_environment(tmp_path, monkeypatch):
    """``spawn_stdio_transport`` defaults to a trimmed MCP-style environment.
    A crow child needs the parent's, or shell-exported keys and service URLs
    vanish between the two processes."""
    monkeypatch.setenv("CROW_CLIENT2_PROBE", "inherited")
    async with scripted(tmp_path, monkeypatch) as driver:
        tail = await wait_for_stderr(driver, "env-probe=")
    assert "env-probe=inherited" in tail


async def test_resume_asks_for_no_replay_and_fork_returns_a_new_id(tmp_path, monkeypatch):
    async with scripted(tmp_path, monkeypatch) as driver:
        sid = await asyncio.wait_for(driver.new_session(str(tmp_path)), TURN_TIMEOUT)
        await asyncio.wait_for(driver.resume_session(sid, str(tmp_path)), TURN_TIMEOUT)
        forked = await asyncio.wait_for(
            driver.fork_session(sid, str(tmp_path)), TURN_TIMEOUT
        )
        tail = await wait_for_stderr(driver, "forked child-1")

    assert forked == "fork-of-child-1"
    assert "resumed child-1 replay_from=None" in tail, (
        "the transcript is in sqlite; replaying it over the wire is pure cost"
    )
    assert "meta=None" in tail, "a fork with nothing to anchor sends no _meta"


async def test_fork_anchors_ride_the_request_meta(tmp_path, monkeypatch):
    """``messageOffset``/``rlmDepth`` are the delegation half of the fork
    contract, and they are not in the schema — v2's ``ForkSessionRequest``
    carries the environment and nothing else — so they ride ``_meta``.

    The offset steps the fork's history back over the call that made it, and
    the depth is persisted on the fork's agent row so the budget survives a
    resume in a different process. A delegate that forgets either is the
    infinity mirror, and neither is observable from this side of the wire
    except by asking the child what it received.
    """
    async with scripted(tmp_path, monkeypatch) as driver:
        sid = await asyncio.wait_for(driver.new_session(str(tmp_path)), TURN_TIMEOUT)
        forked = await asyncio.wait_for(
            driver.fork_session(
                sid, str(tmp_path), message_offset=2, rlm_depth=1
            ),
            TURN_TIMEOUT,
        )
        tail = await wait_for_stderr(driver, "meta=")

    assert forked == "fork-of-child-1"
    assert "meta={'messageOffset': 2, 'rlmDepth': 1}" in tail


async def test_new_session_carries_the_mcp_servers_it_was_given(tmp_path, monkeypatch):
    servers = [{"type": "stdio", "name": "gate", "command": "/bin/true"}]
    async with scripted(tmp_path, monkeypatch) as driver:
        await asyncio.wait_for(
            driver.new_session(str(tmp_path), mcp_servers=servers), TURN_TIMEOUT
        )
        tail = await wait_for_stderr(driver, "servers=1")
    assert "new-session cwd=%s servers=1" % tmp_path in tail


async def test_close_reaps_the_child_process(tmp_path, monkeypatch):
    async with scripted(tmp_path, monkeypatch) as driver:
        proc = driver.proc
        assert proc is not None and proc.returncode is None
    assert driver.conn is None and driver.proc is None
    assert proc.returncode is not None, "close() must not leave a zombie"


async def test_close_on_a_driver_that_never_started_is_a_no_op():
    driver = SubagentDriver()
    await driver.close()
    assert driver.conn is None
    assert driver.proc is None
    assert driver.stderr_tail == ""


async def test_agent_argv_really_starts_a_v2_agent_that_can_open_a_session(tmp_path):
    """The one test that does not patch ``agent_argv``.

    Everything above proves the driver speaks v2 correctly to *a* child; this
    proves the argv it builds starts *our* child. No model is needed —
    ``make_llm`` runs per turn and nothing here prompts.
    """
    config_dir = make_child_config(tmp_path)
    driver = SubagentDriver()
    try:
        await asyncio.wait_for(
            driver.start(str(tmp_path), config_dir=config_dir), START_TIMEOUT
        )
        proc = driver.proc
        sid = await asyncio.wait_for(driver.new_session(str(tmp_path)), START_TIMEOUT)
        tail = driver.stderr_tail
    finally:
        await driver.close()

    assert isinstance(sid, str) and sid
    assert sid.count("-") >= 2, "expected a coolname session id, got %r" % sid
    assert proc.returncode is not None
    assert "Traceback" not in tail, tail


# -- the pure pieces --------------------------------------------------------


def test_agent_argv_names_the_v2_entry_point():
    assert agent_argv() == [sys.executable, "-m", "crow_cli.agent2.main"]


def test_agent_argv_threads_the_config_pointers_and_the_model():
    assert agent_argv(model="m", config_dir=Path("/cd"), config_file=Path("/cf.yaml")) == [
        sys.executable,
        "-m",
        "crow_cli.agent2.main",
        "--config-dir",
        "/cd",
        "--config-file",
        "/cf.yaml",
        "--model",
        "m",
    ]


def test_agent_argv_names_the_acp2_subcommand_in_a_frozen_build(monkeypatch):
    """A packaged crow's ``sys.executable`` IS the ``crow-cli`` binary, so the
    v2 agent is a subcommand of it.

    Not ``-m crow_cli.agent2.main`` — a frozen interpreter has no crow_cli on
    its path — and not ``acp``, which would produce a child that answers a v2
    handshake with a v1 one. The flags are the same in both shapes, because
    ``cli.main.run_agent2`` declares the ones ``agent.main`` does.
    """
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert agent_argv() == [sys.executable, "acp2"]
    assert agent_argv(model="m", config_dir=Path("/cd"), config_file=Path("/cf.yaml")) == [
        sys.executable,
        "acp2",
        "--config-dir",
        "/cd",
        "--config-file",
        "/cf.yaml",
        "--model",
        "m",
    ]


def test_child_config_forwards_the_env_pointers(monkeypatch, tmp_path):
    monkeypatch.setenv("CROW_CONFIG_FILE", str(tmp_path / "c.yaml"))
    monkeypatch.setenv("CROW_CONFIG_DIR", str(tmp_path / "cd"))
    assert child_config() == {
        "config_file": tmp_path / "c.yaml",
        "config_dir": tmp_path / "cd",
    }


def test_child_config_is_empty_when_the_parent_used_the_defaults(monkeypatch):
    monkeypatch.delenv("CROW_CONFIG_FILE", raising=False)
    monkeypatch.delenv("CROW_CONFIG_DIR", raising=False)
    assert child_config() == {}


def test_mcp_servers_to_models_round_trips_what_the_registry_stored():
    stored = [
        {
            "type": "stdio",
            "name": "crow",
            "command": "/bin/crow-cli",
            "args": ["mcp"],
            "env": [{"name": "K", "value": "V"}],
        },
        {
            "type": "http",
            "name": "h",
            "url": "https://h.invalid/mcp",
            "headers": [{"name": "A", "value": "B"}],
        },
        {"type": "acp", "name": "a", "server_id": "srv"},
    ]
    models = mcp_servers_to_models(stored)
    assert [type(m).__name__ for m in models] == [
        "StdioMcpServer",
        "HttpMcpServer",
        "AcpMcpServer",
    ]
    assert models[0].command == "/bin/crow-cli"
    assert models[0].env[0].name == "K"
    assert models[1].headers[0].value == "B"
    assert models[2].server_id == "srv"


def test_sse_is_rewritten_to_http_rather_than_dropped():
    """v2 deleted ``SseMcpServer``. An SSE endpoint is an HTTP endpoint, so an
    old stored server keeps working instead of silently disappearing and
    leaving the child toolless."""
    (model,) = mcp_servers_to_models(
        [{"type": "sse", "name": "old", "url": "https://old.invalid/sse"}]
    )
    assert type(model).__name__ == "HttpMcpServer"
    assert model.type == "http"
    assert str(model.url) == "https://old.invalid/sse"


def test_a_stdio_server_stored_without_args_or_env_still_validates():
    (model,) = mcp_servers_to_models([{"name": "bare", "command": "/bin/true"}])
    assert model.type == "stdio"
    assert model.args == []
    assert model.env == []


def test_an_unknown_type_is_kept_as_an_other_server():
    (model,) = mcp_servers_to_models([{"type": "carrier-pigeon", "name": "p"}])
    assert type(model).__name__ == "OtherMcpServer"
    assert model.type == "carrier-pigeon"


def test_a_server_that_is_already_a_model_passes_through():
    original = v2.schema.StdioMcpServer(name="m", command="/bin/true")
    assert mcp_servers_to_models([original]) == [original]


def test_none_and_empty_both_mean_no_servers():
    assert mcp_servers_to_models(None) == []
    assert mcp_servers_to_models([]) == []


def test_a_malformed_server_raises_instead_of_vanishing():
    """v1 validated the whole list at once and pydantic dropped the bad item,
    so the child came up toolless with no error anywhere."""
    with pytest.raises(ValidationError):
        mcp_servers_to_models([{"type": "stdio", "name": "no-command"}])


def test_the_stop_queue_is_per_session_and_stable_across_calls():
    client = HeadlessClient()
    queue = client.watch("s1")
    assert client.watch("s1") is queue, "watching twice must not lose a stop"
    assert client.watch("s2") is not queue


async def test_only_an_idle_for_a_watched_session_ends_the_wait():
    client = HeadlessClient()
    queue = client.watch("s1")
    await client.session_update(notif("s1", v2.schema.RunningSessionStateUpdate()))
    assert queue.empty(), "running is not a stop"
    await client.session_update(
        notif("s2", v2.schema.IdleSessionStateUpdate(stop_reason="end_turn"))
    )
    assert queue.empty(), "another session's idle must not wake ours"
    await client.session_update(
        notif("s1", v2.schema.IdleSessionStateUpdate(stop_reason="cancelled"))
    )
    assert queue.get_nowait() == "cancelled"


async def test_an_idle_with_no_stop_reason_still_ends_the_wait():
    """``stop_reason`` is optional in v2; omitting it means "not reporting",
    not "still running". A driver that waited for a value would hang."""
    client = HeadlessClient()
    queue = client.watch("s1")
    await client.session_update(notif("s1", v2.schema.IdleSessionStateUpdate()))
    assert queue.get_nowait() is None


async def test_updates_are_recorded_even_for_sessions_nobody_watches():
    client = HeadlessClient()
    await client.session_update(
        notif("ghost", v2.schema.IdleSessionStateUpdate(stop_reason="end_turn"))
    )
    assert len(client.updates) == 1
