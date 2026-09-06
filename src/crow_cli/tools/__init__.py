"""crow_cli.tools — the agent's Python standard library.

NOT MCP tools. Only ``execute`` is MCP-wired; everything here is plain async
Python called from code inside the execute kernel, observed through the
subtool register (crow_cli.tools.register) so the harness can emit proper
ACP tool calls and hydrate LLM images on drain — the three-fold split
described in crow_cli.tools.results.

Attributes resolve LAZILY (PEP 562), same pattern as crow_cli.mcp: the
package import stays cheap until a tool is actually used.

PRELUDE is the zero-day import line execute runs on kernel start/reset: it
calls :func:`reload`, which re-imports every tool module from source and
binds the names into the caller's namespace. So the tools are ambient —
part of Python's standard library as far as the agent is concerned — and no
cached module state survives a reset. help(tool) works out of the box:
ipykernel's pydoc falls to plain stdout, nothing pages.
"""

_LAZY = {
    "edit": ("crow_cli.tools.edit", "edit"),
    "fs": ("crow_cli.tools.fs", "fs"),
    "memory": ("crow_cli.tools.memory", "memory"),
    "vision": ("crow_cli.tools.vision", "vision"),
    "web": ("crow_cli.tools.web", "web"),
    "write": ("crow_cli.tools.write", "write"),
}

PRELUDE = "from crow_cli.tools import reload\nreload()"

__all__ = [*_LAZY, "PRELUDE", "reload"]


def reload() -> None:
    """Re-import every tool module from source, in THIS running kernel.

    The workflow for iterating on crow_cli.tools mid-session: edit a tool,
    call ``reload()``, and the next line runs the new code — no kernel
    reset, so variables, imports and cwd all survive. PRELUDE calls it on
    every kernel start and reset, so cached module state never carries over.

    Four things make this more than a loop of ``importlib.reload``:

    * the facade is LAZY, so a fresh kernel has imported nothing but this
      package — each submodule is imported if absent, reloaded if present;
    * reload re-executes a module in its EXISTING dict, so this package's
      cached facade functions would survive it, and a FIRST import of a
      submodule sets the parent attribute to the module object — both would
      shadow ``__getattr__``, so both are purged (after the binding below);
    * names are re-resolved from the fresh submodules and bound into the
      CALLER's globals (the kernel's user namespace), including ``reload``
      itself, so the next call runs the new one;
    * reloading ``register`` re-creates its identity contextvar and drops
      the sink/images_dir the per-cell prologue set, which would silently
      kill the subtool rail for the rest of the cell — the identity is
      captured first and re-applied after.

    Scope is ``crow_cli.tools.*`` only: the subtools, which is what runs in
    here. The MCP server (execute's prologue, output cap) and the agent
    (the drain, ACP emission) are separate long-lived processes — changes
    there need a restart, and changes to modules the tools import from
    (crow_cli.mcp.editor's engine, crow_cli.memory) need a kernel reset.
    """
    import importlib
    import sys

    caller = sys._getframe(1).f_globals

    register = sys.modules.get("crow_cli.tools.register")
    identity = None
    if register is not None:
        identity = (
            register.current_cell(),
            register._sink_uri,
            register._images_dir,
        )

    # Import-if-absent, reload-if-present: the facade is lazy, so a fresh
    # kernel has imported nothing but this package yet.
    for name in ("results", "register", *_LAZY):
        module_name = f"crow_cli.tools.{name}"
        module = sys.modules.get(module_name)
        if module is None:
            importlib.import_module(module_name)
        else:
            importlib.reload(module)

    package = importlib.reload(sys.modules[__name__])

    for name, (module_name, attr) in package._LAZY.items():
        caller[name] = getattr(importlib.import_module(module_name), attr)
    caller["reload"] = package.reload

    # Purge LAST. Two things put a stale value in this dict under a _LAZY
    # name: reload re-executes the package in its EXISTING dict, so a cached
    # facade function survives it; and importing a submodule for the FIRST
    # time makes the import machinery setattr(parent, child, module). The
    # second one is why this runs after the binding loop above — that loop
    # reads the FRESH _LAZY, while the import-if-absent loop at the top read
    # the running one, so a tool just added to _LAZY is first imported down
    # there. Purging before it left pkg.<new_tool> holding the MODULE, which
    # shadows __getattr__ and hands callers an uncallable object.
    for key in [k for k in list(package.__dict__) if k in package._LAZY]:
        del package.__dict__[key]

    cell, sink_uri, images_dir = identity or (None, None, None)
    if cell is not None:
        sys.modules["crow_cli.tools.register"].begin_cell(
            session_id=cell.session_id,
            parent_tool_call_id=cell.parent_tool_call_id,
            cell_seq=cell.cell_seq,
            agent_id=cell.agent_id,
            db_uri=sink_uri,
            images_dir=images_dir,
        )


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
    return sorted(set(globals()) | set(_LAZY) | {"reload"})
