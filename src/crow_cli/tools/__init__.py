"""crow_cli.tools — the agent's Python standard library.

NOT MCP tools. Only ``execute`` is MCP-wired; everything here is plain async
Python called from code inside the execute kernel, observed through the
subtool register (crow_cli.tools.register) so the harness can emit proper
ACP tool calls and hydrate LLM images on drain — the three-fold split
described in crow_cli.tools.results.

Attributes resolve LAZILY (PEP 562), same pattern as crow_cli.mcp: the
package import stays cheap until a tool is actually used.

**Every subtool module is named ``<name>_tool.py``, and that suffix is
load-bearing.** Importing a submodule makes the import machinery do
``setattr(package, child_name, module)``, and a module ``__getattr__`` is only
consulted when ordinary lookup FAILS — so a submodule called ``fs.py`` parks
itself on ``crow_cli.tools.fs`` and shadows the ``fs`` the facade binds, and
``crow_cli.tools.fs(...)`` becomes ``TypeError: 'module' object is not
callable``. Which of the two you got depended on whether anything had imported
the submodule yet. The suffix means no submodule name is a binding name, so
there is nothing to shadow: ``crow_cli.tools.fs`` is the function by exactly
one route, and ``crow_cli.tools.fs_tool`` is the module by exactly one route.
``tests/unit/test_tools_facade_names.py`` pins the invariant, so a new subtool
added as ``foo.py`` with a binding ``foo`` fails a test instead of failing
whoever imports it first. ``register.py`` and ``results.py`` keep their plain
names because nothing binds them.

PRELUDE is the zero-day import line execute runs on kernel start/reset: it
calls :func:`reload`, which re-imports every tool module from source and
binds the names into the caller's namespace. So the tools are ambient —
part of Python's standard library as far as the agent is concerned — and no
cached module state survives a reset. help(tool) works out of the box:
ipykernel's pydoc falls to plain stdout, nothing pages.

There are two preludes, one per protocol generation: PRELUDE binds _LAZY,
PRELUDE_V2 binds _LAZY plus _LAZY_V2. The split exists because a name is not
free — see _LAZY_V2 for why `task` is not ambient in every kernel.
"""

_LAZY = {
    "edit": ("crow_cli.tools.edit_tool", "edit"),
    "fs": ("crow_cli.tools.fs_tool", "fs"),
    "memory": ("crow_cli.tools.memory_tool", "memory"),
    "rlm": ("crow_cli.tools.rlm_tool", "rlm"),
    "sg": ("crow_cli.tools.sg_tool", "sg"),
    "vision": ("crow_cli.tools.vision_tool", "vision"),
    "web": ("crow_cli.tools.web_tool", "web"),
    "write": ("crow_cli.tools.write_tool", "write"),
}

#: Bound in a v2 kernel ONLY, on top of _LAZY.
#:
#: For `task` the reason is a collision, not a protocol. v1 already ships it
#: as an MCP tool served from the agent process, so a v1 kernel that also had
#: a `task` subtool would have two launchers minting ids off the same global
#: counter and writing the same two tables.
#:
#: For `goal_done`/`goal_blocked` it IS the protocol: they are the exits from
#: a continuation loop, and only the agent2 driver runs one (v1 has no idle
#: transition to hook). Binding them in a v1 kernel would offer the model a
#: way out of a loop it is not in — a call that succeeds, changes a row, and
#: means nothing.
#:
#: Either way, v1 is frozen: it does not get new ambient surface just because
#: v2 needs it.
_LAZY_V2 = {
    "goal_blocked": ("crow_cli.tools.goal_tool", "goal_blocked"),
    "goal_done": ("crow_cli.tools.goal_tool", "goal_done"),
    "task": ("crow_cli.tools.task_tool", "task"),
    "task_cancel": ("crow_cli.tools.task_tool", "task_cancel"),
    "task_read": ("crow_cli.tools.task_tool", "task_read"),
    "task_send": ("crow_cli.tools.task_tool", "task_send"),
}

#: Which flavour THIS module instance is. Remembered rather than inferred so
#: an interactive reload() re-binds the set the kernel started with instead of
#: silently dropping the task tools mid-session. setdefault, because reload
#: re-executes this source in the existing module dict.
_IS_V2: bool = globals().setdefault("_IS_V2", False)

PRELUDE = "from crow_cli.tools import reload\nreload()"
PRELUDE_V2 = "from crow_cli.tools import reload\nreload(v2=True)"

__all__ = [*_LAZY, *_LAZY_V2, "PRELUDE", "PRELUDE_V2", "reload"]


def _names() -> dict:
    """The facade table for this kernel: _LAZY, plus the v2 set if v2."""
    return {**_LAZY, **_LAZY_V2} if _IS_V2 else dict(_LAZY)


def reload(v2: bool | None = None) -> None:
    """Re-import every tool module from source, in THIS running kernel.

    The workflow for iterating on crow_cli.tools mid-session: edit a tool,
    call ``reload()``, and the next line runs the new code — no kernel
    reset, so variables, imports and cwd all survive. PRELUDE calls it on
    every kernel start and reset, so cached module state never carries over.

    ``v2`` adds the v2-only names (``task`` and friends) to the binding. It
    defaults to None, meaning "whatever this kernel already is", so the
    interactive ``reload()`` a session calls to pick up an edit re-binds the
    set the kernel started with. PRELUDE_V2 passes True once, at kernel start.

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
      the sink/images_dir/redis_url the per-cell prologue set, which would
      silently kill the subtool rail for the rest of the cell — the identity
      is captured first and re-applied after.

    Scope is ``crow_cli.tools.*`` only: the subtools, which is what runs in
    here. The MCP server (execute's prologue, output cap) and the agent
    (the drain, ACP emission) are separate long-lived processes — changes
    there need a restart, and changes to modules the tools import from
    (crow_cli.mcp.editor's engine, crow_cli.memory) need a kernel reset.
    """
    import importlib
    import sys

    global _IS_V2
    if v2 is not None:
        _IS_V2 = bool(v2)

    caller = sys._getframe(1).f_globals
    names = _names()

    register = sys.modules.get("crow_cli.tools.register")
    identity = None
    if register is not None:
        identity = (
            register.current_cell(),
            register._sink_uri,
            register._images_dir,
            register._redis_url,
        )

    # Import-if-absent, reload-if-present: the facade is lazy, so a fresh
    # kernel has imported nothing but this package yet.
    #
    # MODULE names, read off the table's values — not binding names with
    # "crow_cli.tools." glued in front. Several bindings share one module (task,
    # task_cancel, task_read and task_send all live in crow_cli.tools.task_tool),
    # and the _tool suffix means the glued derivation is now wrong for EVERY
    # binding rather than accidentally right for most of it. That is the point:
    # it used to look safe right up until PRELUDE_V2 ran for real and went
    # looking for a module called crow_cli.tools.task_cancel. Deduped because
    # reloading one module four times would re-execute it four times.
    for module_name in dict.fromkeys(
        ("crow_cli.tools.results", "crow_cli.tools.register")
        + tuple(module for module, _attr in names.values())
    ):
        module = sys.modules.get(module_name)
        if module is None:
            importlib.import_module(module_name)
        else:
            importlib.reload(module)

    package = importlib.reload(sys.modules[__name__])

    for name, (module_name, attr) in package._names().items():
        caller[name] = getattr(importlib.import_module(module_name), attr)
    caller["reload"] = package.reload

    # Purge LAST, so a cached facade function does not survive the reload:
    # __getattr__ caches into this dict, and reload re-executes the package in
    # its EXISTING dict, so without this `crow_cli.tools.fs` keeps handing back
    # the pre-edit function even though the caller's binding below is fresh.
    #
    # Membership is read off `package._names()` and not the `names` captured
    # before the reload, so a table the reload changed — a tool added, one
    # removed — purges by the new membership.
    #
    # This used to have a second job: undoing the MODULE that the import
    # machinery parked on the package attribute when a submodule was first
    # imported, which shadowed __getattr__ and handed callers an uncallable
    # object. The _tool suffix removed that failure mode at the source (see the
    # module docstring), so all that is left here is the stale-function case.
    for key in [k for k in list(package.__dict__) if k in package._names()]:
        del package.__dict__[key]

    cell, sink_uri, images_dir, bus_url = identity or (None, None, None, None)
    if cell is not None:
        sys.modules["crow_cli.tools.register"].begin_cell(
            session_id=cell.session_id,
            parent_tool_call_id=cell.parent_tool_call_id,
            cell_seq=cell.cell_seq,
            agent_id=cell.agent_id,
            db_uri=sink_uri,
            images_dir=images_dir,
            redis_url=bus_url,
            rlm_depth=cell.rlm_depth,
        )


def __getattr__(name):
    # Both tables, whatever this kernel's flavour: attribute access is a
    # library import, not a kernel binding, and tests read the v2 tools
    # without standing up a v2 kernel to do it.
    try:
        module_name, attr = {**_LAZY, **_LAZY_V2}[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module_name), attr)
    globals()[name] = value  # cache so the lookup happens once
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY) | set(_LAZY_V2) | {"reload"})
