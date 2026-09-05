"""crow_cli.tools — the agent's Python standard library.

NOT MCP tools. Only ``execute`` is MCP-wired; everything here is plain async
Python called from code inside the execute kernel, observed through the
subtool register (crow_cli.tools.register) so the harness can emit proper
ACP tool calls and hydrate LLM images on drain — the three-fold split
described in crow_cli.tools.results.

Attributes resolve LAZILY (PEP 562), same pattern as crow_cli.mcp: the
package import stays cheap until a tool is actually used.

PRELUDE is the zero-day import line execute runs on kernel start/reset so
these names are ambient — part of Python's standard library as far as the
agent is concerned. help(tool) works out of the box: ipykernel's pydoc
falls to plain stdout, nothing pages.
"""

_LAZY = {
    "edit": ("crow_cli.tools.edit", "edit"),
    "vision": ("crow_cli.tools.vision", "vision"),
}

PRELUDE = "from crow_cli.tools import edit, vision"

__all__ = [*_LAZY, "PRELUDE"]


def __getattr__(name):
    try:
        module_name, attr = _LAZY[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module_name), attr)
    globals()[name] = value  # cache so the lookup happens once
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
