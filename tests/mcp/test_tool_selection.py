"""``--include-tools``: the allowlist that splits one codebase into many servers.

In-process. Two halves of ``register_tools`` are observable without a
subprocess, and this file covers both:

* ``resolve_tool_selection`` — flag parsing and validation. Pure.
* ``register_tools`` — which modules it imports, and what fastmcp serves after.

Import PRUNING is observed by recording ``import_module`` calls rather than
replacing them: the real import still runs, but "which modules did we ask for"
is otherwise unobservable in a process where an earlier test already imported
all ten. That the code path under test executes for real is the justification
for the patch. The end-to-end proof that a pruned tool is genuinely unreachable
lives in ``tests/integration/test_mcp_tool_selection.py``, over a real wire.
"""

import importlib
import importlib.util

import pytest
from fastmcp.exceptions import NotFoundError

from crow_cli.mcp import tool_modules, tool_names
from crow_cli.mcp.server import main as server_main
from crow_cli.mcp.server.main import (
    ToolSelectionError,
    register_tools,
    resolve_tool_selection,
)

ALL = set(tool_names())


@pytest.fixture
def recorded_imports(monkeypatch):
    """The module names ``register_tools`` asks importlib for, in order.

    Wraps rather than replaces, so the real import still happens.
    """
    seen: list[str] = []
    real = importlib.import_module

    def recording(name, *args, **kwargs):
        seen.append(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(server_main.importlib, "import_module", recording)
    return seen


class TestToolRegistry:
    def test_every_owning_module_exists(self):
        # find_spec resolves without executing, so this stays fast and cannot
        # be satisfied by a module that imports but crashes.
        for name, module in tool_modules().items():
            assert importlib.util.find_spec(module) is not None, (
                f"{name} claims {module}, which does not exist"
            )

    def test_several_tools_can_share_a_module(self):
        # The reason enable(only=True) is still needed after import pruning.
        owners: dict[str, list[str]] = {}
        for name, module in tool_modules().items():
            owners.setdefault(module, []).append(name)
        shared = {m: sorted(ns) for m, ns in owners.items() if len(ns) > 1}
        assert shared["crow_cli.mcp.memory.main"] == [
            "list_sessions",
            "query_memory",
            "query_session",
        ]
        assert shared["crow_cli.mcp.vision.main"] == [
            "capture_webcam",
            "read_image_file",
        ]


class TestResolveToolSelection:
    """``None`` (not given -> ALL) is deliberately distinct from ``[]``
    (-> nothing, always a mistake)."""

    def test_not_given_means_all(self):
        assert resolve_tool_selection(None) is None

    def test_empty_list_means_all(self):
        # argparse with action="append" and no flag yields None, but a caller
        # passing [] means the same thing: nobody asked for a slice.
        assert resolve_tool_selection([]) is None

    def test_comma_separated(self):
        assert resolve_tool_selection(["read,write,edit"]) == [
            "read",
            "write",
            "edit",
        ]

    def test_repeated_flags(self):
        assert resolve_tool_selection(["read", "write"]) == ["read", "write"]

    def test_both_spellings_at_once(self):
        # config.yaml wants one string, a shell wants repeated flags; mixing
        # them is not an error.
        assert resolve_tool_selection(["read,write", "edit"]) == [
            "read",
            "write",
            "edit",
        ]

    def test_whitespace_is_stripped(self):
        assert resolve_tool_selection([" read , write "]) == ["read", "write"]

    def test_duplicates_collapse_keeping_order(self):
        assert resolve_tool_selection(["write", "read", "write"]) == [
            "write",
            "read",
        ]

    def test_empty_fragments_are_dropped(self):
        assert resolve_tool_selection(["read", ""]) == ["read"]
        assert resolve_tool_selection(["read,,write"]) == ["read", "write"]

    def test_single_tool(self):
        assert resolve_tool_selection(["execute"]) == ["execute"]

    def test_every_tool_is_selectable(self):
        # The registry is the contract: --list-tools prints it, so anything it
        # prints must be accepted back.
        assert resolve_tool_selection(tool_names()) == tool_names()

    def test_unknown_tool_is_refused(self):
        with pytest.raises(ToolSelectionError) as exc:
            resolve_tool_selection(["bogus"])
        msg = str(exc.value)
        assert "bogus" in msg
        # The fix is in the message: the user does not have to go find
        # --list-tools, the valid names are already in front of them.
        for name in ALL:
            assert name in msg

    def test_unknown_alongside_known_blames_only_the_unknown(self):
        with pytest.raises(ToolSelectionError) as exc:
            resolve_tool_selection(["read", "nope"])
        # "read" is valid and must not be reported as the problem.
        blamed = str(exc.value).split("available:")[0]
        assert "nope" in blamed
        assert "read" not in blamed

    @pytest.mark.parametrize(
        "blank", [[""], [" "], [","], [" , "], [" , , "], ["", ""]]
    )
    def test_a_server_with_nothing_on_it_is_refused(self, blank):
        # An empty allowlist is legal fastmcp and serves zero tools — a server
        # that answers every call with NotFoundError. Always a typo, so refuse
        # it at the door instead of spawning it.
        with pytest.raises(ToolSelectionError) as exc:
            resolve_tool_selection(blank)
        assert "resolved to no tool names" in str(exc.value)

    def test_error_is_a_value_error(self):
        # So a caller that only catches ValueError still catches this.
        assert issubclass(ToolSelectionError, ValueError)


class TestRegisterTools:
    async def test_default_registers_everything(self, all_tools):
        assert {t.name for t in await all_tools.list_tools()} == ALL

    async def test_default_returns_the_names_it_serves(self, all_tools):
        assert set(register_tools(None)) == ALL

    async def test_one_tool(self, narrow):
        assert await narrow(["read"]) == ["read"]

    async def test_narrows_inside_a_shared_module(self, narrow):
        # memory.main owns three tools; importing it registers all three, so
        # the enable(only=True) half is what trims it back to the one asked for.
        assert await narrow(["query_memory"]) == ["query_memory"]

    async def test_both_tools_of_a_shared_module(self, narrow):
        assert await narrow(["list_sessions", "query_session"]) == [
            "list_sessions",
            "query_session",
        ]

    async def test_a_selection_of_everything_is_everything(self, narrow):
        assert set(await narrow(tool_names())) == ALL

    def test_imports_only_the_owning_modules(self, recorded_imports):
        assert register_tools(["query_memory", "read"]) == [
            "query_memory",
            "read",
        ]
        assert recorded_imports == [
            "crow_cli.mcp.memory.main",
            "crow_cli.mcp.read.main",
        ]

    def test_two_tools_one_module_imports_it_once(self, recorded_imports):
        register_tools(["capture_webcam", "read_image_file"])
        assert recorded_imports == ["crow_cli.mcp.vision.main"]

    def test_default_imports_every_owning_module(self, recorded_imports):
        register_tools(None)
        assert set(recorded_imports) == set(tool_modules().values())

    async def test_a_deselected_tool_is_refused_not_just_hidden(self, narrow):
        # The security property. list_tools() omitting it would be cosmetic; a
        # client that guesses the name must still be refused.
        await narrow(["read"])
        with pytest.raises(NotFoundError, match="terminal"):
            await server_main.mcp.call_tool(
                "terminal", {"command": "echo pwned"}
            )

    async def test_a_selected_tool_still_works(self, narrow, tmp_path):
        # Narrowing must not break the tools it keeps.
        await narrow(["read"])
        target = tmp_path / "hello.txt"
        target.write_text("hi from crow\n")
        result = await server_main.mcp.call_tool(
            "read", {"file_path": str(target)}
        )
        assert not result.is_error
        assert "hi from crow" in result.content[0].text

    async def test_narrowing_is_reversible(self, narrow):
        # A server process narrows once at startup and never looks back, but
        # this singleton is shared with the rest of the tier — if it could not
        # be widened again, no test could narrow it safely. Note the order:
        # register_tools(None) adds no transform, so it cannot on its own undo
        # an earlier enable(only=True).
        await narrow(["read"])
        register_tools(None)
        server_main.mcp.enable(names=ALL, only=True, components={"tool"})
        assert {t.name for t in await server_main.mcp.list_tools()} == ALL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
