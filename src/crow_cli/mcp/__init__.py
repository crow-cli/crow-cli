"""crow_cli.mcp — MCP tools facade.

Attributes resolve LAZILY (PEP 562): importing the package stays cheap, and
a single tool facade (e.g. memory telemetry, also surfaced on the CLI) can
be pulled without registering — and paying the import cost of — every other
tool group. Accessing any name below loads its module on demand.
"""

_LAZY = {
    "capture_webcam": ("crow_cli.mcp.vision.main", "capture_webcam"),
    "edit": ("crow_cli.mcp.editor.main", "edit"),
    "execute": ("crow_cli.mcp.execute.main", "execute"),
    "list_sessions": ("crow_cli.mcp.memory.main", "list_sessions"),
    "mcp": ("crow_cli.mcp.server.app", "mcp"),
    "query_memory": ("crow_cli.mcp.memory.main", "query_memory"),
    "query_session": ("crow_cli.mcp.memory.main", "query_session"),
    "read": ("crow_cli.mcp.read.main", "read"),
    "read_image_file": ("crow_cli.mcp.vision.main", "read_image_file"),
    "task": ("crow_cli.mcp.task.main", "task"),
    "terminal": ("crow_cli.mcp.terminal", "terminal"),
    "web_fetch": ("crow_cli.mcp.web_fetch", "web_fetch"),
    "web_search": ("crow_cli.mcp.web_search", "web_search"),
    "write": ("crow_cli.mcp.write.main", "write"),
}

__all__ = [*list(_LAZY), "tool_modules", "tool_names"]


def tool_modules() -> dict[str, str]:
    """Tool name -> the module whose IMPORT registers that tool.

    ``_LAZY`` above already is that registry — it exists so one facade can be
    pulled without paying for every other tool group — so this is it minus the
    server instance, which is not a tool. Importing the named module runs its
    ``@mcp.tool`` decorators; that is the whole registration mechanism.

    One source of truth for "which tools exist". ``crow-cli mcp --list-tools``,
    ``--include-tools`` validation, the selective import in
    ``server.main.register_tools`` and the registration smoke test all read
    this, so adding a tool here is what makes it selectable.
    """
    return {name: module for name, (module, _attr) in _LAZY.items() if name != "mcp"}


def tool_names() -> list[str]:
    """Every servable tool name, sorted. Reads the registry, imports nothing."""
    return sorted(tool_modules())


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
