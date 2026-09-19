"""crow-mcp2: registration, the runner, and the v2 prelude.

The v2 surface is one tool, so the registration smoke test that guards v1's
thirteen is mostly a drift guard here — the registry in ``crow_cli.mcp2`` is
what ``--list-tools`` prints and what ``register_tools`` imports, and both have
to agree with what fastmcp actually ends up serving.

The prelude half is the reason this file exists. ``PRELUDE_V2`` had never been
executed by anything until crow-mcp2 got a runner: v1's kernels run
``PRELUDE``, whose eight bindings each happen to be named after their own
module, so ``reload()`` deriving a module name from a binding name went
unnoticed. ``_LAZY_V2`` binds four names out of ``crow_cli.tools.task``, and
the derivation went looking for ``crow_cli.tools.task_cancel``. The prelude
raised, ``_run_prelude`` logged one truncated warning, and every v2 kernel came
up with no subtools at all — no ``fs``, no ``memory``, no ``task``.
"""

import importlib.util
import json
import logging

import pytest
from fastmcp import Client

from crow_cli.mcp.server.app import mcp as v1_mcp
from crow_cli.mcp.server.main import DEFAULT_PORT as v1_DEFAULT_PORT
from crow_cli.mcp2 import TOOL_MODULES, tool_names
from crow_cli.mcp2 import main as runner
from crow_cli.mcp2.execute.main import _kernels, shutdown_all
from crow_cli.mcp2.server import mcp

ALL = set(tool_names())


@pytest.fixture(autouse=True)
def _reap_kernels():
    """``_kernels`` is module state and each entry is a live child process."""
    yield
    shutdown_all()


@pytest.fixture
def server():
    assert set(runner.register_tools()) == ALL
    return mcp


async def _call(code, session_id="mcp2-test", **meta):
    """One cell in a real kernel subprocess; execute answers JSON."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "execute", {"code": code}, meta={"session_id": session_id, **meta}
        )
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


class TestRegistration:
    def test_server_name(self, server):
        assert server.name == "crow-mcp2"

    def test_it_is_not_the_v1_instance(self, server):
        # The whole point of a second FastMCP: v1's client-execution tools
        # (read/write/edit/terminal) drive capabilities ACP v2 deleted, and
        # putting both shapes on one schema list lets the model pick either.
        assert server is not v1_mcp
        assert v1_mcp.name == "crow-mcp"

    async def test_the_registry_matches_what_registers(self, server):
        assert ALL == {"execute"}
        assert {t.name for t in await server.list_tools()} == ALL

    def test_every_owning_module_exists(self):
        # find_spec resolves without executing, so a registry entry pointing at
        # a renamed or deleted module fails here rather than at spawn time.
        for name, module in TOOL_MODULES.items():
            assert importlib.util.find_spec(module) is not None, (
                f"{name} claims {module}, which does not exist"
            )

    def test_tool_names_is_sorted(self):
        # --list-tools prints it verbatim; sorted is diffable and stable.
        assert tool_names() == sorted(tool_names())

    def test_register_tools_is_idempotent(self, server):
        # A server registers once at startup, but nothing enforces that, and
        # re-importing a module that owns a @mcp.tool must not double-register.
        assert runner.register_tools() == tool_names()
        assert runner.register_tools() == tool_names()

    async def test_execute_keeps_its_docstring(self, server):
        # The docstring IS the product: it is what the model reads.
        (tool,) = await server.list_tools()
        assert "persistent IPython kernel" in tool.description


class TestPreludeV2:
    async def test_rerunning_the_prelude_raises_nothing(self, server):
        # The regression, stated as narrowly as it can be. Before the fix this
        # cell died with "No module named 'crow_cli.tools.task_cancel'".
        out = await _call(
            "from crow_cli.tools import reload\nreload(v2=True)\nprint('ok')"
        )
        assert out["exit_code"] == 0
        assert out["output"].strip() == "ok"

    async def test_the_prelude_binds_the_whole_v2_facade(self, server):
        # Read the table out of the running kernel rather than restating it
        # here: the claim is "every name THIS kernel's flavour declares is
        # bound", so a tool added to _LAZY_V2 is covered without an edit.
        # _IS_V2 is what proves PRELUDE_V2 ran and not PRELUDE.
        # `have = dir()` is its own statement on purpose: dir() evaluated
        # inside a generator's condition runs in the generator's frame and
        # sees only the loop variable, so every name looks unbound.
        out = await _call(
            "import crow_cli.tools as T\n"
            "have = dir()\n"
            "print(sorted(n for n in T._names() if n not in have), T._IS_V2)"
        )
        assert out["output"].strip() == "[] True"

    async def test_the_four_task_bindings_share_one_module(self, server):
        # The shape that broke the derivation: four names, one module. Asserted
        # through the bindings a cell actually sees, not through the table.
        out = await _call(
            "print(task.__module__, task_read.__module__,"
            " task_send.__module__, task_cancel.__module__)"
        )
        assert out["output"].split() == ["crow_cli.tools.task"] * 4

    async def test_a_bound_subtool_runs(self, server, tmp_path):
        # Binding is not enough — the object has to be the callable, not the
        # module the import machinery left on the package attribute.
        target = tmp_path / "f.txt"
        target.write_text("hello\n")
        out = await _call(
            f"r = await fs('read', {str(target)!r})\nprint('hello' in r.text)"
        )
        assert out["output"].strip() == "True"


class TestServe:
    """``mcp.run`` blocks forever, so it is recorded rather than run — there is
    no other way to observe which transport ``serve`` picked. Everything else
    on the path is real: ``register_tools``, the file logger, and the kernels
    ``shutdown_all`` reaps, which are actual child ipykernel processes."""

    @pytest.fixture(autouse=True)
    def _hermetic_log(self, monkeypatch, tmp_path):
        # serve() logs to a rotating file under the real config dir. Redirect
        # it, and clear the handlers on the way in AND out: setup_logger only
        # attaches when the named logger has none, so a handler left over from
        # an earlier test would keep writing to that test's tmp_path.
        monkeypatch.setattr(runner, "LOG_PATH", tmp_path / "crow-mcp2.log")
        logging.getLogger("crow_cli.mcp2_logger").handlers.clear()
        yield
        logging.getLogger("crow_cli.mcp2_logger").handlers.clear()

    @pytest.fixture
    def runs(self, monkeypatch, server):
        seen = []

        def record(**kwargs):
            seen.append(kwargs)

        monkeypatch.setattr(mcp, "run", record)
        return seen

    async def test_stdio_runs_bare_and_reaps_the_kernels(self, runs):
        await _call("print(1)", session_id="serve-stdio")
        assert _kernels, "expected a live kernel for serve() to reap"
        runner.serve("stdio", "127.0.0.1", 2770)
        assert runs == [{"show_banner": False}]
        # The claim the finally block exists for: a kernel is a child process,
        # and a server whose run() returned must not leave it behind.
        assert _kernels == {}

    async def test_http_is_renamed_to_what_fastmcp_calls_it(self, runs):
        runner.serve("http", "127.0.0.1", 2770)
        assert runs == [
            {
                "transport": "streamable-http",
                "host": "127.0.0.1",
                "port": 2770,
                "show_banner": False,
            }
        ]

    async def test_streamable_http_passes_through_unchanged(self, runs):
        runner.serve("streamable-http", "0.0.0.0", 9999)
        assert runs[0]["transport"] == "streamable-http"
        assert runs[0]["host"] == "0.0.0.0" and runs[0]["port"] == 9999

    async def test_kernels_are_reaped_even_when_run_raises(self, monkeypatch, server):
        # A client that drops mid-cell is the normal way a stdio server ends,
        # and it does not end politely.
        await _call("print(1)", session_id="serve-boom")
        assert _kernels

        def boom(**kwargs):
            raise RuntimeError("client went away")

        monkeypatch.setattr(mcp, "run", boom)
        with pytest.raises(RuntimeError, match="went away"):
            runner.serve("stdio", "127.0.0.1", 2770)
        assert _kernels == {}

    def test_an_unknown_transport_is_refused_before_anything_is_announced(
        self, server, capsys
    ):
        with pytest.raises(ValueError, match="carrier-pigeon"):
            runner.serve("carrier-pigeon", "127.0.0.1", 2770)
        assert capsys.readouterr().out == ""

    def test_the_default_port_is_not_v1s(self):
        # Both servers are meant to run at once — agent1 is frozen and still
        # talks to crow-mcp — so they cannot share a port.
        assert runner.DEFAULT_PORT != v1_DEFAULT_PORT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
