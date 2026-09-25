"""`crow-cli run` as the multi-protocol client: config picks the agent AND the wire.

Everything here is real. ``crow-cli`` is THIS tree's console script, spawned as
a subprocess; the agents on the other end are real ACP agents speaking real
JSON-RPC over real stdio pipes — one v1, one v2. A scripted peer is not a mock
of the code under test: the code under test is the client, and the peer is the
other end of the protocol.

What only a subprocess can show:

* which client an entry's ``protocol`` selects, end to end;
* that the entry's argv is honored exactly as written (no crow flag is added);
* that the entry's ``env`` reaches the child;
* that the tool supply the client chose is what the agent received;
* that ``-m`` arrives over ``session/set_config_option`` and not in an argv.

Each agent appends what it saw to a witness file named by an ``env`` the entry
carries, so "the client sent it" is proven by the agent receiving it rather than
by reading the client's mind.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Under `uv --project . run pytest` this is the project venv's console script,
# i.e. THIS tree's code. Not the installed one, not $PATH's.
CROW_CLI = Path(sys.executable).parent / "crow-cli"

TIMEOUT = 180.0

V1_AGENT = r'''"""A scripted ACP v1 agent: echoes one chunk and reports what it saw."""

import asyncio
import json
import os
from uuid import uuid4

from acp import (
    PROTOCOL_VERSION,
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
)
from acp.interfaces import Client
from acp.schema import AgentCapabilities, SetSessionConfigOptionResponse

from crow_cli.acp_helpers import text_block, update_agent_message

WITNESS = os.environ["DISPATCH_WITNESS"]


def saw(**event):
    with open(WITNESS, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


class Echo(Agent):
    _conn: Client

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(self, protocol_version, client_capabilities=None,
                         client_info=None, **kwargs):
        # Answer with the version THIS agent speaks, not the one asked for:
        # "An Agent that only supports v1 will answer with protocolVersion: 1".
        # Echoing the request back would claim v2 to a client that offered it
        # and get this agent driven by a stack it cannot answer.
        saw(event="initialize", asked=protocol_version, protocol=PROTOCOL_VERSION,
            probe=os.environ.get("DISPATCH_PROBE"),
            client_marker=os.environ.get("DISPATCH_CLIENT_MARKER"),
            client=client_info.name if client_info else None,
            terminal=client_capabilities.terminal if client_capabilities else None)
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(load_session=True),
        )

    async def new_session(self, cwd, additional_directories=None,
                          mcp_servers=None, **kwargs):
        saw(event="new_session", cwd=cwd,
            servers=[s.name for s in (mcp_servers or [])])
        return NewSessionResponse(session_id=uuid4().hex)

    async def load_session(self, cwd, session_id, additional_directories=None,
                           mcp_servers=None, **kwargs):
        saw(event="load_session", session_id=session_id,
            servers=[s.name for s in (mcp_servers or [])])
        return None

    async def set_config_option(self, config_id, session_id, value, **kwargs):
        saw(event="config_option", config_id=config_id, value=value)
        # configOptions is REQUIRED on the v1 reply: an agent that answers with
        # nothing makes the client raise a ValidationError it cannot attribute.
        return SetSessionConfigOptionResponse(config_options=[])

    async def prompt(self, session_id, prompt, **kwargs):
        text = "".join(getattr(b, "text", "") for b in prompt)
        saw(event="prompt", text=text)
        await self._conn.session_update(
            session_id=session_id,
            update=update_agent_message(text_block("V1-ECHO:" + text)),
        )
        return PromptResponse(stop_reason="end_turn")


asyncio.run(run_agent(Echo()))
'''

V2_AGENT = r'''"""A scripted ACP v2 agent: echoes one chunk, then reports idle the way v2
requires — the prompt response is empty, so the state update is the only
channel the outcome has."""

import asyncio
import json
import os

from acp.experimental import v2

s = v2.schema

WITNESS = os.environ["DISPATCH_WITNESS"]


def saw(**event):
    with open(WITNESS, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


class Echo:
    def __init__(self):
        self.conn = None
        self.sessions = 0

    def on_connect(self, conn):
        self.conn = conn

    # rc2's router hands a handler the request's FIELDS as keywords, with its
    # _meta spread in among them, so each signature names what it reads and
    # catches the rest.
    async def initialize(self, protocol_version, info, capabilities=None, **kw):
        saw(event="initialize", asked=protocol_version,
            protocol=v2.PROTOCOL_VERSION,
            probe=os.environ.get("DISPATCH_PROBE"),
            client_marker=os.environ.get("DISPATCH_CLIENT_MARKER"),
            client=info.name if info else None)
        return s.InitializeResponse(
            protocol_version=v2.PROTOCOL_VERSION,
            info=s.Implementation(name="v2-echo", version="0.0.1"),
            capabilities=s.AgentCapabilities(),
        )

    async def new_session(self, cwd, additional_directories=None,
                          mcp_servers=None, **kw):
        self.sessions += 1
        saw(event="new_session", cwd=cwd,
            servers=[m.name for m in (mcp_servers or [])])
        return s.NewSessionResponse(session_id="v2-%d" % self.sessions)

    async def resume_session(self, session_id, cwd, additional_directories=None,
                             mcp_servers=None, replay_from=None, **kw):
        saw(event="resume_session", session_id=session_id,
            replay=replay_from is not None,
            servers=[m.name for m in (mcp_servers or [])])
        return s.ResumeSessionResponse()

    async def fork_session(self, session_id, cwd, additional_directories=None,
                           mcp_servers=None, **kw):
        saw(event="fork_session", session_id=session_id,
            servers=[m.name for m in (mcp_servers or [])])
        return s.ForkSessionResponse(session_id="fork-of-" + session_id)

    async def set_config_option(self, config_id, session_id, value, **kw):
        saw(event="config_option", config_id=config_id, value=value)
        return s.SetSessionConfigOptionResponse(config_options=[])

    async def prompt(self, session_id, prompt, **kw):
        text = "".join(getattr(b, "text", "") for b in prompt)
        saw(event="prompt", text=text)
        asyncio.create_task(self._turn(session_id, text))
        return s.PromptResponse(message_id="u1")

    async def _turn(self, session_id, text):
        await self._send(session_id, s.RunningSessionStateUpdate())
        await self._send(
            session_id,
            s.AgentMessageChunk(
                message_id="m1",
                content=s.TextContentBlock(text="V2-ECHO:" + text),
            ),
        )
        await self._send(
            session_id, s.IdleSessionStateUpdate(stop_reason="end_turn")
        )

    async def _send(self, session_id, update):
        await self.conn.session_update(session_id=session_id, update=update)


asyncio.run(v2.run_agent(Echo()))
'''

#: An agent that dies at startup. The only place it can say why is stderr, so
#: this is the child whose error message has to carry the tail.
DEAD_AGENT = r"""import sys

sys.stderr.write("dead-agent: no LLM provider configured\n")
raise SystemExit(4)
"""


@pytest.fixture
def bench(tmp_path: Path) -> dict:
    """A hermetic config dir with one v2 entry, one v1 entry, and one v2 entry
    that carries its own tool supply."""
    v1_script = tmp_path / "v1_agent.py"
    v2_script = tmp_path / "v2_agent.py"
    v1_script.write_text(V1_AGENT)
    v2_script.write_text(V2_AGENT)

    witness = tmp_path / "witness.jsonl"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("API_KEY=dispatch-key\n")

    def entry(script: Path, protocol: str | None = None, **extra):
        spec = {
            "command": sys.executable,
            "args": [str(script)],
            "env": {
                "DISPATCH_WITNESS": str(witness),
                "DISPATCH_PROBE": "probe-" + script.stem,
            },
        }
        if protocol:
            spec["protocol"] = protocol
        spec.update(extra)
        return spec

    stdio = {
        "transport": "stdio",
        "command": str(sys.executable),
        "args": ["-c", "pass"],
    }
    models = {
        "dispatch-model": {
            "provider": "dispatch-provider",
            "model": "dispatch-model-id",
        },
        "other-model": {
            "provider": "dispatch-provider",
            "model": "other-model-id",
        },
    }
    providers = {
        "dispatch-provider": {
            "api_key": "${API_KEY}",
            "base_url": "https://dispatch.invalid/v1",
        }
    }
    db_uri = "sqlite:///%s" % (tmp_path / "dispatch.db")
    config = {
        "providers": providers,
        "models": models,
        "db_uri": db_uri,
        "mcpServers": {"global-supply": stdio},
        # ORDER IS MEANING: the top entry is what a bare `run` launches.
        "agent_servers": {
            "v2-echo": entry(v2_script, "acp2"),
            "v1-echo": entry(v1_script),
            "v2-private": entry(v2_script, "acp2", mcpServers={"private-supply": stdio}),
            # No `protocol`: `run` has to ask. This is the entry shape that
            # hung before discovery existed — the registry defaulted it to v1
            # and the v1 client spoke v1 to a v2 agent, so both sides waited.
            "v2-auto": entry(v2_script),
        },
    }
    (config_dir / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))

    empty_dir = tmp_path / "empty-config"
    empty_dir.mkdir()
    (empty_dir / ".env").write_text("API_KEY=dispatch-key\n")
    (empty_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {"providers": providers, "models": models, "db_uri": db_uri},
            sort_keys=False,
        )
    )

    return {
        "config_dir": config_dir,
        "empty_dir": empty_dir,
        "witness": witness,
        "cwd": tmp_path,
    }


def cli_env() -> dict[str, str]:
    """The environment a client subprocess runs in.

    ``CROW_CONFIG*`` is stripped so an ambient config cannot leak in, and
    ``NO_COLOR``/``COLUMNS`` pin rich: an assertion on a message is an
    assertion on ONE line, and a pipe-width console wraps it into three.
    ``TERM`` is left alone — rich reads ``dumb`` as "80 columns, always".
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("CROW_CONFIG")}
    env.update(
        NO_COLOR="1",
        COLUMNS="200",
        # A var the CLIENT has and no `agent_servers` entry declares, so an
        # agent can report whether the spawn overlaid the environment or
        # replaced it. See test_the_entrys_env_is_an_overlay_on_the_clients.
        DISPATCH_CLIENT_MARKER="from-the-client",
    )
    return env


def run_cli(bench: dict, args: list[str], timeout: float = TIMEOUT):
    """`crow-cli` as a user runs it: a subprocess, its own process, real pipes."""
    return subprocess.run(
        [str(CROW_CLI), *args, "--config-dir", str(bench["config_dir"])],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(bench["cwd"]),
        env=cli_env(),
    )


def plain(text: str) -> str:
    """ANSI stripped, so an assertion reads like the message it pins."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def saw(bench: dict) -> list[dict]:
    """What the agents reported receiving, in order."""
    path = bench["witness"]
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def events(bench: dict, **match) -> list[dict]:
    return [e for e in saw(bench) if all(e.get(k) == v for k, v in match.items())]


# -- dispatch ----------------------------------------------------------------


def test_a_v2_entry_is_driven_by_the_v2_client(bench):
    proc = run_cli(bench, ["run", "-a", "v2-echo", "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "V2-ECHO:ping" in proc.stdout
    assert events(bench, event="initialize", probe="probe-v2_agent")


def test_a_v1_entry_is_driven_by_the_v1_client(bench):
    proc = run_cli(bench, ["run", "-a", "v1-echo", "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "V1-ECHO:ping" in proc.stdout
    assert events(bench, event="initialize", probe="probe-v1_agent")


def test_the_two_protocols_are_not_interchangeable(bench):
    """A v1 client handed a v2 agent (or the reverse) does not fail loudly, it
    hangs in a handshake that never completes. Both directions work here: one
    entry declared `acp2` and the other was asked."""
    first = run_cli(bench, ["run", "-a", "v2-echo", "a"])
    second = run_cli(bench, ["run", "-a", "v1-echo", "b"])

    assert "V2-ECHO:a" in first.stdout
    assert "V1-ECHO:b" in second.stdout
    assert "V1-ECHO" not in first.stdout
    assert "V2-ECHO" not in second.stdout


# -- discovery: an entry that did not say ------------------------------------


def test_an_undeclared_v2_entry_is_asked_and_driven_as_v2(bench):
    """The bug discovery exists for. `v2-auto` declares no protocol, so the
    registry used to default it to v1 and the v1 client spoke v1 to a v2 agent:
    a session that never initializes, no error on either side, and nothing in
    the config to tell you the field you forgot was load-bearing."""
    proc = run_cli(bench, ["run", "-a", "v2-auto", "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "V2-ECHO:ping" in proc.stdout
    assert "acp2" in plain(proc.stdout), "the banner names what the agent said"

    hit = events(bench, event="initialize", probe="probe-v2_agent")
    assert len(hit) == 1
    assert hit[0]["asked"] == 2 and hit[0]["protocol"] == 2


def test_an_undeclared_v1_entry_is_asked_and_gets_its_own_answer(bench):
    """The same question, the other answer. The client offers 2 to everybody;
    an agent that only speaks v1 says so, per the spec's "otherwise the Agent
    MUST respond with the latest version it supports"."""
    proc = run_cli(bench, ["run", "-a", "v1-echo", "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "V1-ECHO:ping" in proc.stdout

    hit = events(bench, event="initialize", probe="probe-v1_agent")
    assert len(hit) == 1
    assert hit[0]["asked"] == 2 and hit[0]["protocol"] == 1


def test_the_probe_is_the_connection_so_the_agent_handshakes_once(bench):
    """Discovery spawns once and hands the live, already-negotiated streams to
    the stack it selected. A probe that spawned its own child and let the stack
    spawn another would pay two cold starts for one agent — and v2 refuses a
    second `initialize` on a connection outright, so "let the stack handshake
    too" is not available as a shortcut."""
    proc = run_cli(bench, ["run", "-a", "v2-auto", "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert len(events(bench, event="initialize", probe="probe-v2_agent")) == 1
    assert len(events(bench, event="new_session")) == 1


def test_the_union_reaches_a_v1_agent_as_its_own_client_would(bench):
    """Each half of the union is what that version's own client sends, so a v1
    agent picked up by discovery is offered exactly what it was offered before
    discovery existed — `terminal: false` included, which is what routes its
    terminal tool to its own MCP supply instead of a client-side PTY."""
    run_cli(bench, ["run", "-a", "v1-echo", "ping"])

    hit = events(bench, event="initialize", probe="probe-v1_agent")
    assert hit[0]["terminal"] is False
    assert hit[0]["client"] == "crow-client"


def test_an_agent_that_cannot_be_asked_is_an_error_not_a_hang(bench, tmp_path):
    """The failure a declared `protocol` turns into a silent one. The child
    dies at startup and the only place it said why is its stderr, so the error
    has to carry that tail or the user is left with a closed pipe."""
    dead = tmp_path / "dead_agent.py"
    dead.write_text(DEAD_AGENT)
    override = tmp_path / "dead.yaml"
    override.write_text(
        yaml.safe_dump(
            {
                "agent_servers": {
                    "dead": {"command": sys.executable, "args": [str(dead)]}
                }
            },
            sort_keys=False,
        )
    )

    proc = run_cli(bench, ["run", "-a", "dead", "-o", str(override), "ping"])

    assert proc.returncode == 1
    text = plain(proc.stdout) + plain(proc.stderr)
    assert "no LLM provider configured" in text
    assert "child exited 4" in text


# -- the client owns tool supply ---------------------------------------------


def test_the_global_supply_is_handed_to_an_entry_with_no_own(bench):
    run_cli(bench, ["run", "-a", "v2-echo", "ping"])

    assert events(bench, event="new_session", servers=["global-supply"])


def test_an_entrys_own_supply_replaces_the_global_one(bench):
    """How a v2 agent gets crow-mcp2 without changing what the v1 sessions on
    the same box are handed."""
    run_cli(bench, ["run", "-a", "v2-private", "ping"])

    assert events(bench, event="new_session", servers=["private-supply"])


def test_the_v1_path_gets_the_same_global_supply(bench):
    run_cli(bench, ["run", "-a", "v1-echo", "ping"])

    assert events(bench, event="new_session", servers=["global-supply"])


@pytest.mark.parametrize(
    "entry,probe", [("v1-echo", "probe-v1_agent"), ("v2-echo", "probe-v2_agent")]
)
def test_the_entrys_env_is_an_overlay_on_the_clients_own(bench, entry, probe):
    """An entry's `env` is the only way it can configure an agent it does not
    own, and it is an OVERLAY on the client's environment, not a replacement.

    Both halves are asserted because the first half passes either way: an
    ``env=`` that substituted would still deliver the entry's own vars while
    leaving the child with no PATH and no HOME — a crow agent that cannot
    spawn `git` or `uv`, which no handshake reveals. Both protocols, because
    each client owns its own spawn site.
    """
    run_cli(bench, ["run", "-a", entry, "ping"])

    hit = events(bench, event="initialize", probe=probe)
    assert hit, saw(bench)
    assert hit[0]["client_marker"] == "from-the-client"


# -- the model travels over the wire -----------------------------------------


def test_the_model_arrives_as_a_config_option_not_an_argv_flag(bench):
    proc = run_cli(bench, ["run", "-a", "v2-echo", "-m", "other-model", "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert events(
        bench,
        event="config_option",
        config_id="model",
        value="dispatch-provider:other-model-id",
    )


def test_the_v1_path_moves_the_model_to_the_wire_too(bench):
    """`-m` used to ride crow's own argv, which is why it never reached a
    custom entry at all."""
    proc = run_cli(bench, ["run", "-a", "v1-echo", "-m", "other-model", "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert events(
        bench,
        event="config_option",
        config_id="model",
        value="dispatch-provider:other-model-id",
    )


def test_an_unknown_model_fails_before_anything_is_spawned(bench):
    proc = run_cli(bench, ["run", "-a", "v2-echo", "-m", "nope", "ping"])

    assert proc.returncode == 1
    assert "Unknown model 'nope'" in plain(proc.stdout)
    assert "dispatch-model" in plain(proc.stdout)
    assert saw(bench) == []


# -- sessions ----------------------------------------------------------------


def test_resume_reaches_the_v2_agent_without_replay_by_default(bench):
    proc = run_cli(bench, ["run", "-a", "v2-echo", "-s", "v2-1", "again"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert events(bench, event="resume_session", session_id="v2-1", replay=False)


def test_the_replay_flag_is_opt_in_and_reaches_the_wire(bench):
    proc = run_cli(bench, ["run", "-a", "v2-echo", "-s", "v2-1", "--replay", "again"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert events(bench, event="resume_session", session_id="v2-1", replay=True)


def test_fork_reaches_the_v2_agent(bench):
    proc = run_cli(bench, ["run", "-a", "v2-echo", "-s", "v2-1", "--fork", "again"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert events(bench, event="fork_session", session_id="v2-1")
    assert "fork-of-v2-1" in proc.stdout


def test_a_v1_session_is_loaded(bench):
    proc = run_cli(bench, ["run", "-a", "v1-echo", "-s", "abc", "again"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert events(bench, event="load_session", session_id="abc")


# -- machine output ----------------------------------------------------------


def test_json_mode_emits_the_agent_the_updates_and_the_stop_reason(bench):
    proc = run_cli(bench, ["run", "-a", "v2-echo", "-j", "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    kinds = [line["type"] for line in lines]

    session = next(line for line in lines if line["type"] == "session")
    assert session["agent"] == "v2-echo"
    assert session["protocol"] == "acp2"

    updates = [line["update"] for line in lines if line["type"] == "update"]
    assert [u["sessionUpdate"] for u in updates] == [
        "state_update",
        "agent_message_chunk",
        "state_update",
    ]
    assert updates[1]["content"]["text"] == "V2-ECHO:ping"

    result = next(line for line in lines if line["type"] == "result")
    assert result["stop_reason"] == "end_turn"
    assert kinds[-1] == "result"


def test_json_mode_carries_the_agent_on_the_v1_path_too(bench):
    proc = run_cli(bench, ["run", "-a", "v1-echo", "-j", "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    session = next(line for line in lines if line["type"] == "session")

    assert session["agent"] == "v1-echo"
    assert session["protocol"] == "acp"


# -- the listing -------------------------------------------------------------


def test_the_agents_command_lists_the_registry_in_config_order(bench):
    """`auto` is not a third protocol, it is the absence of a claim: the entry
    did not say, so `run` will ask the agent. Printing a guess here would be
    the same lie a `protocol` field that disagrees with the agent tells."""
    proc = run_cli(bench, ["agents", "-j"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)

    assert payload["fallback"] is False
    assert [(a["name"], a["protocol"]) for a in payload["agents"]] == [
        ("v2-echo", "acp2"),
        ("v1-echo", "auto"),
        ("v2-private", "acp2"),
        ("v2-auto", "auto"),
    ]
    assert [a["default"] for a in payload["agents"]] == [True, False, False, False]
    assert payload["agents"][0]["tools"] == "global"
    assert payload["agents"][2]["tools"] == "private-supply"


def test_the_agents_command_prints_the_launch_a_human_can_read(bench):
    proc = run_cli(bench, ["agents"])

    assert proc.returncode == 0, proc.stderr
    for needle in ("v2-echo", "v1-echo", "v2-private", "v2-auto", "acp2", "auto"):
        assert needle in proc.stdout


def test_the_listing_reads_the_same_override_run_does(bench, tmp_path):
    """`-o` exists so a user can list what `run` is about to launch.

    An override REPLACES `agent_servers` instead of merging into it, so the
    registry below has exactly one entry — and `run -a` finds it by that name.
    Discovery and launch disagreeing about which config they read would make
    the listing a lie.
    """
    override = tmp_path / "override.yaml"
    override.write_text(
        yaml.safe_dump(
            {
                "agent_servers": {
                    "only-entry": {
                        "protocol": "acp2",
                        "command": sys.executable,
                        "args": [str(tmp_path / "v2_agent.py")],
                        "env": {"DISPATCH_WITNESS": str(bench["witness"])},
                    }
                }
            },
            sort_keys=False,
        )
    )

    listing = run_cli(bench, ["agents", "-j", "-o", str(override)])

    assert listing.returncode == 0, listing.stderr
    payload = json.loads(listing.stdout)
    assert [a["name"] for a in payload["agents"]] == ["only-entry"]
    assert payload["agents"][0]["default"] is True
    assert payload["agents"][0]["protocol"] == "acp2"

    proc = run_cli(bench, ["run", "-a", "only-entry", "-o", str(override), "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "V2-ECHO:ping" in proc.stdout
    assert events(bench, event="initialize")


def test_an_empty_registry_falls_back_to_crows_own_v2_agent(bench):
    """`run` is the v2 client now; the TUI's fallback stays v1."""
    proc = subprocess.run(
        [str(CROW_CLI), "agents", "-j", "--config-dir", str(bench["empty_dir"])],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        cwd=str(bench["cwd"]),
        env=cli_env(),
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)

    assert payload["fallback"] is True
    assert len(payload["agents"]) == 1
    assert payload["agents"][0]["protocol"] == "acp2"
    assert payload["agents"][0]["builtin"] is True
    assert payload["agents"][0]["name"] == "crow-ai.dev"


def test_a_bare_run_with_no_registry_launches_crows_own_v2_agent(bench):
    """The default swap, end to end: `run` IS the v2 client now, so an empty
    registry falls back to crow's own v2 agent rather than its v1 one.

    The provider is `.invalid`, so the turn ends in a connection error — which
    is what makes this hermetic. Handshake, session, announcement and stop
    reason all happen with no LLM and no network to reach.
    """
    proc = subprocess.run(
        [str(CROW_CLI), "run", "--config-dir", str(bench["empty_dir"]), "ping"],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        cwd=str(bench["cwd"]),
        env=cli_env(),
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = plain(proc.stdout)
    assert "Agent: Crow (acp2)" in out
    assert '"agent": "crow-ai.dev", "protocol": "acp2"' in out
    # The turn ran to its end rather than dying at the announcement.
    assert '"type": "result"' in out
    assert '"stop_reason": "error"' in out
