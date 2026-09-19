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
        saw(event="initialize", protocol=protocol_version,
            probe=os.environ.get("DISPATCH_PROBE"),
            client_marker=os.environ.get("DISPATCH_CLIENT_MARKER"))
        return InitializeResponse(
            protocol_version=protocol_version,
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

    async def initialize(self, request):
        saw(event="initialize", protocol=request.protocol_version,
            probe=os.environ.get("DISPATCH_PROBE"),
            client_marker=os.environ.get("DISPATCH_CLIENT_MARKER"),
            client=request.info.name if request.info else None)
        return s.InitializeResponse(
            protocol_version=v2.PROTOCOL_VERSION,
            info=s.Implementation(name="v2-echo", version="0.0.1"),
            capabilities=s.AgentCapabilities(),
        )

    async def new_session(self, request):
        self.sessions += 1
        saw(event="new_session", cwd=request.cwd,
            servers=[m.name for m in (request.mcp_servers or [])])
        return s.NewSessionResponse(session_id="v2-%d" % self.sessions)

    async def resume_session(self, request):
        saw(event="resume_session", session_id=request.session_id,
            replay=request.replay_from is not None,
            servers=[m.name for m in (request.mcp_servers or [])])
        return s.ResumeSessionResponse()

    async def fork_session(self, request):
        saw(event="fork_session", session_id=request.session_id,
            servers=[m.name for m in (request.mcp_servers or [])])
        return s.ForkSessionResponse(session_id="fork-of-" + request.session_id)

    async def set_config_option(self, request):
        saw(event="config_option", config_id=request.config_id,
            value=request.value)
        return s.SetSessionConfigOptionResponse(config_options=[])

    async def prompt(self, request):
        text = "".join(getattr(b, "text", "") for b in request.prompt)
        saw(event="prompt", text=text)
        asyncio.create_task(self._turn(request.session_id, text))
        return s.PromptResponse()

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
        await self.conn.session_update(
            s.UpdateSessionNotification(session_id=session_id, update=update)
        )


asyncio.run(v2.run_agent(Echo()))
'''


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
    """The point of declaring `protocol`: a v1 client handed a v2 agent (or the
    reverse) does not fail loudly, it hangs in a handshake that never
    completes. Both directions work here because each entry named its own."""
    first = run_cli(bench, ["run", "-a", "v2-echo", "a"])
    second = run_cli(bench, ["run", "-a", "v1-echo", "b"])

    assert "V2-ECHO:a" in first.stdout
    assert "V1-ECHO:b" in second.stdout
    assert "V1-ECHO" not in first.stdout
    assert "V2-ECHO" not in second.stdout


def test_the_top_entry_is_what_a_bare_run_launches(bench):
    proc = run_cli(bench, ["run", "ping"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "V2-ECHO:ping" in proc.stdout


def test_the_agent_it_picked_is_announced(bench):
    """A surprise must never be silent: `run` with no -a launches whatever
    config put on top, and the header says which."""
    proc = run_cli(bench, ["run", "ping"])

    assert "v2-echo" in proc.stdout
    assert "acp2" in proc.stdout


def test_an_unknown_name_is_an_error_not_a_fallback(bench):
    proc = run_cli(bench, ["run", "-a", "nope", "ping"])

    assert proc.returncode == 1
    assert "No agent_servers entry named 'nope'" in plain(proc.stdout)
    assert "v2-echo, v1-echo, v2-private" in plain(proc.stdout)
    assert saw(bench) == [], "nothing may be spawned for a name that does not exist"


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
    proc = run_cli(bench, ["agents", "-j"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)

    assert payload["fallback"] is False
    assert [(a["name"], a["protocol"]) for a in payload["agents"]] == [
        ("v2-echo", "acp2"),
        ("v1-echo", "acp"),
        ("v2-private", "acp2"),
    ]
    assert [a["default"] for a in payload["agents"]] == [True, False, False]
    assert payload["agents"][0]["tools"] == "global"
    assert payload["agents"][2]["tools"] == "private-supply"


def test_the_agents_command_prints_the_launch_a_human_can_read(bench):
    proc = run_cli(bench, ["agents"])

    assert proc.returncode == 0, proc.stderr
    for needle in ("v2-echo", "v1-echo", "v2-private", "acp2", "acp"):
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
