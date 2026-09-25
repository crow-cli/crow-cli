"""``crow-cli acp2`` — the console command, tested from the argv that spawns it.

``client2.subagent.agent_argv`` names ``acp2`` and ``cli.main.run_agent2``
implements it, and nothing else in the tree ties the two together: a packaged
crow spawns a v2 subagent as ``[sys.executable, "acp2", ...]``, where
``sys.executable`` IS the binary. So every test here builds its argv the way a
frozen build would, stands this venv's console script in for the binary, and
completes a real v2 handshake over a real stdio pipe. A rename on either side,
or a flag ``agent_argv`` sends that ``acp2`` does not accept, fails as a spawn
that never handshakes rather than as a diff someone has to notice.

Nothing reaches a network. ``SessionRegistry.make_llm`` is lazy — a session is
provisioned long before a model is dialled — so ``initialize`` and
``session/new`` only need the model to *resolve*. The turn-shaped half of the
wire is ``tests/integration/test_agent2_gate.py`` (scripted model, in-memory
transport) and ``tests/e2e/test_agent2_live.py`` (real provider, ``-m``).
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from acp.connection import StreamDirection
from acp.experimental import v2
from acp.stdio import spawn_stdio_transport

from crow_cli.client2.subagent import agent_argv
from crow_cli.memory import Agent, get_engine, normalize_db_uri

#: This venv's console script — the same argv a frozen build runs against
#: ``sys.executable``. Not ``$PATH``'s ``crow-cli``, not the installed one.
CROW_CLI = Path(sys.executable).parent / "crow-cli"

#: A spawn is ~1.6s, most of it ``crow_cli.cli.main``'s import. Comfortably
#: inside this means something hung rather than something was slow.
TIMEOUT = 60.0

PROVIDER = "acp2-provider"

# The model ``-m`` selects, and the one the config falls back to when there is
# no override — ``SessionRegistry.default_model_value`` takes
# ``next(iter(config.llm.models.values()))``. FIRST goes first in config.yaml
# on purpose: were MODEL the default too, a ``-m`` that silently stopped
# reaching the agent would leave the picker showing MODEL anyway, and the
# assertion in the first test would prove nothing.
MODEL = "acp2-model"
MODEL_ID = "acp2-model-id"
FIRST = "acp2-first"
FIRST_ID = "acp2-first-id"
MARKER = "You are ACP2-PROMPT-MARKER. Workspace: "


class _Client:
    """The client half. Assertions read the wire tap, not this queue."""

    def __init__(self) -> None:
        self.updates: asyncio.Queue = asyncio.Queue()

    async def session_update(self, session_id, update, **kwargs) -> None:
        await self.updates.put((session_id, update))


def config_root(tmp_path: Path) -> Path:
    """A hermetic ``--config-dir``: one provider, two models, no ``db_uri``.

    ``db_uri`` is left out on purpose. ``Config.load`` would default it to
    ``<config_dir>/crow.db``; the tests send a ``--config-file`` that sets it,
    so the session landing in the override's database and NOT in the default
    one is what proves ``apply_config_overrides`` ran.

    Model order is load-bearing, hence ``sort_keys=False``: see FIRST.
    """
    root = tmp_path / "crow"
    root.mkdir(parents=True)
    (root / ".env").write_text("API_KEY=not-a-real-key\n")
    (root / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "providers": {
                    PROVIDER: {
                        "api_key": "${API_KEY}",
                        "base_url": "https://acp2.invalid/v1",
                    }
                },
                "models": {
                    FIRST: {"provider": PROVIDER, "model": FIRST_ID},
                    MODEL: {"provider": PROVIDER, "model": MODEL_ID},
                },
            },
            sort_keys=False,
        )
    )
    return root


def db_uri(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'acp2.db'}"


def db_override(tmp_path: Path) -> Path:
    """The ``--config-file`` every test sends: only the database moves."""
    override = tmp_path / "override.yaml"
    override.write_text(yaml.safe_dump({"db_uri": db_uri(tmp_path)}))
    return override


def agents(tmp_path: Path) -> list[Agent]:
    """The agent rows the child wrote, read back through the real schema."""
    engine = get_engine(normalize_db_uri(db_uri(tmp_path)))
    try:
        with Session(engine) as session:
            return session.query(Agent).all()
    finally:
        engine.dispose()


def frozen_argv(monkeypatch, **kwargs) -> list[str]:
    """``agent_argv`` as a packaged crow builds it.

    ``sys.frozen`` is the whole branch: set, and the answer is
    ``[sys.executable, "acp2", ...]`` rather than the source checkout's
    ``[sys.executable, "-m", "crow_cli.agent2.main", ...]``.
    """
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    argv = agent_argv(**kwargs)
    assert argv[0] == sys.executable
    assert argv[1] == "acp2"
    return argv


@asynccontextmanager
async def acp2(tmp_path: Path, *args: str):
    """Spawn ``crow-cli acp2`` and yield ``(conn, wire, stderr, process)``.

    ``wire`` is the observer tap: the JSON-RPC dicts that actually crossed the
    pipe, in order, both directions. ``stderr`` is drained into a list rather
    than left on the pipe — an undrained 64KB buffer deadlocks the child, and
    when a spawn test fails the child's traceback is the only evidence there
    is. Shutdown is left to ``spawn_stdio_transport``, which closes stdin and
    waits before it escalates, so ``process.returncode`` read after the block
    says whether the agent exited on EOF or had to be terminated.
    """
    stderr: list[str] = []
    wire: list = []
    async with spawn_stdio_transport(
        str(CROW_CLI), "acp2", *args, cwd=str(tmp_path)
    ) as (reader, writer, process):

        async def drain() -> None:
            assert process.stderr is not None
            while True:
                line = await process.stderr.readline()
                if not line:
                    return
                stderr.append(line.decode(errors="replace"))

        drainer = asyncio.create_task(drain())
        conn = v2.ClientSideConnection(
            _Client(), writer, reader, observers=[wire.append]
        )
        try:
            yield conn, wire, stderr, process
        finally:
            await conn.close()
            drainer.cancel()
            if stderr:
                # A child that dies mid-handshake leaves its traceback here and
                # nowhere else: all the client sees is ConnectionError. pytest
                # shows captured stdout on failure, so this costs nothing when
                # the spawn worked.
                print("agent stderr:\n" + "".join(stderr))


async def handshake(conn) -> v2.schema.InitializeResponse:
    return await asyncio.wait_for(
        conn.initialize(
            protocol_version=v2.PROTOCOL_VERSION,
            info=v2.schema.Implementation(name="acp2-cli", version="2.0.0"),
        ),
        TIMEOUT,
    )


async def new_session(conn, cwd: Path) -> v2.schema.NewSessionResponse:
    return await asyncio.wait_for(
        conn.new_session(cwd=str(cwd), mcp_servers=[]),
        TIMEOUT,
    )


def kinds(wire: list) -> list[str]:
    """Every ``session/update`` the client received, in wire order."""
    return [
        event.message["params"]["update"]["sessionUpdate"]
        for event in wire
        if event.direction is StreamDirection.INCOMING
        and event.message.get("method") == "session/update"
    ]


async def test_the_argv_a_frozen_build_spawns_reaches_a_live_v2_agent(
    tmp_path, monkeypatch
):
    """``agent_argv``'s frozen shape, run for real, answers a v2 handshake.

    All three flags ``agent_argv`` can send ride this argv, so each gets an
    assertion: ``--config-dir`` is where the providers come from, ``-m`` is the
    picker's current value, and ``--config-file`` is why the row is in the
    override's database.
    """
    root = config_root(tmp_path)
    override = db_override(tmp_path)
    argv = frozen_argv(
        monkeypatch,
        model=MODEL,
        config_dir=str(root),
        config_file=str(override),
    )

    # argv[0] is the interpreter this venv's console script stands in for and
    # argv[1] is the subcommand ``acp2()`` already supplies. What is left is
    # the flag surface under test, unmodified.
    async with acp2(tmp_path, *argv[2:]) as (conn, wire, stderr, process):
        init = await handshake(conn)
        assert init.protocol_version == v2.PROTOCOL_VERSION
        assert init.info.name == "crow-cli"
        caps = init.capabilities.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        assert caps["session"]["mcp"] == {"stdio": {}, "http": {}}
        assert caps["session"]["fork"] == {}

        new = await new_session(conn, tmp_path)
        sid = new.session_id
        picker = {o.config_id: o for o in (new.config_options or [])}["model"]
        assert picker.current_value == f"{PROVIDER}:{MODEL_ID}"
        assert {o.name for o in picker.options} == {MODEL, FIRST}

        # A fresh session advertises its commands and reports idle before any
        # turn; closing it is the last thing a client does.
        assert kinds(wire)[:2] == ["available_commands_update", "state_update"]
        await asyncio.wait_for(
            conn.close_session(session_id=sid),
            TIMEOUT,
        )

    assert process.returncode == 0, "".join(stderr)
    assert not stderr, "".join(stderr)

    rows = agents(tmp_path)
    assert [a.agent_id for a in rows] == [f"{sid}-1-1"]
    assert rows[0].model_identifier == MODEL_ID
    # The override moved the database; the config dir's own default was never
    # created, which is the only way to tell the two apart after the fact.
    assert not (root / "crow.db").exists()


async def test_the_system_prompt_flag_is_the_prompt_the_session_is_born_with(
    tmp_path,
):
    """``-p`` reaches ``config.system_prompt_path``, and the row shows it.

    The flag is v1's, carried over verbatim, and the persisted system prompt is
    the only evidence it survived the port: ``default_system_prompt`` reads the
    file instead of crow's built-in template when the path is set, and
    ``session/new`` renders it once and stores it on the agent row.
    """
    root = config_root(tmp_path)
    override = db_override(tmp_path)
    template = tmp_path / "prompt.jinja2"
    template.write_text(MARKER + "{{ workspace }}")

    async with acp2(
        tmp_path,
        "--config-dir",
        str(root),
        "--config-file",
        str(override),
        "-p",
        str(template),
    ) as (conn, _wire, stderr, process):
        await handshake(conn)
        await new_session(conn, tmp_path)

    assert process.returncode == 0, "".join(stderr)
    rows = agents(tmp_path)
    assert len(rows) == 1
    assert rows[0].system_prompt == MARKER + str(tmp_path)


async def test_debug_is_what_opens_the_chunk_log_directory(tmp_path):
    """``--debug`` sets ``config.chunk_log``, and the directory is the proof.

    ``SessionRegistry.driver_for`` mkdirs ``<config_dir>/logs/<session_id>``
    when ``chunk_log`` is on and does not when it is off, so the flag is the
    only difference between the two spawns below. The chunk files themselves
    need a model turn — the e2e tier's business; that the directory exists at
    all means the flag reached the registry through the command.
    """
    root = config_root(tmp_path)
    override = db_override(tmp_path)
    base = ["--config-dir", str(root), "--config-file", str(override)]

    sids: list[str] = []
    for extra in ([], ["--debug"]):
        async with acp2(tmp_path, *base, *extra) as (conn, _wire, stderr, process):
            await handshake(conn)
            new = await new_session(conn, tmp_path)
            sids.append(new.session_id)
        assert process.returncode == 0, "".join(stderr)

    quiet, logged = sids
    assert not (root / "logs" / quiet).exists()
    assert (root / "logs" / logged).is_dir()
