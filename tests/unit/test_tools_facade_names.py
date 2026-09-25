"""The facade's names: a submodule may never shadow the callable it ships.

``crow_cli.tools`` binds subtool CALLABLES as package attributes through a PEP
562 ``__getattr__``, and a module ``__getattr__`` is only consulted when
ordinary lookup fails. Importing a submodule makes the import machinery do
``setattr(package, child_name, module)`` — so while the modules were called
``fs.py`` and ``edit.py``, ``import crow_cli.tools.fs`` parked the MODULE on the
very attribute the facade binds ``fs`` to, and from then on
``crow_cli.tools.fs(...)`` was ``TypeError: 'module' object is not callable``.
Which of the two a caller got depended on whether anything had imported the
submodule first, so it was invisible in the kernel (whose prelude calls
``reload()``, which purged it) and showed up only in an in-process consumer.

The fix is the ``_tool`` suffix on every subtool module: no submodule name is a
binding name, so there is nothing left to shadow. These three tests are the
reason it stays fixed — the first two assert the invariant and the behaviour in
this process, the third reproduces the original failure in a fresh interpreter,
because in here another test may already have touched the facade and cached the
callable, which is exactly the accident that used to hide the bug.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import crow_cli.tools as T

SUBTOOLS = Path(T.__file__).parent


def _bindings() -> dict:
    """Both tables — the facade resolves either, whatever the kernel flavour."""
    return {**T._LAZY, **T._LAZY_V2}


def test_no_submodule_is_named_after_a_binding():
    """The invariant, stated once: the two namespaces do not overlap.

    A new subtool added as ``foo.py`` and bound as ``foo`` fails here, with the
    reason next to it, instead of failing whoever imports it first.
    """
    modules = {p.stem for p in SUBTOOLS.glob("*.py") if p.stem != "__init__"}
    overlap = modules & set(_bindings())
    assert not overlap, (
        f"{sorted(overlap)}: a subtool module may not share a name with the "
        "attribute the facade binds — importing the module would shadow the "
        "callable. Name the module <name>_tool.py."
    )


def test_importing_every_submodule_leaves_every_binding_callable():
    """The behaviour the invariant buys, checked over the whole facade."""
    for name in sorted({m for m, _ in _bindings().values()}):
        __import__(name)

    for binding, (module_name, attr) in sorted(_bindings().items()):
        value = getattr(T, binding)
        assert callable(value), f"{binding} resolved to {type(value).__name__}"
        assert not isinstance(value, type(sys)), f"{binding} is a MODULE"
        assert value.__module__ == module_name, binding
        assert value.__name__ == attr, binding


def test_a_fresh_process_that_imports_the_module_first_still_gets_the_callable():
    """The original failure, in the only state it can be reproduced in.

    Submodule imported BEFORE anything touches the facade attribute, in an
    interpreter where nothing else has run. Under the old names this printed
    ``module`` and the call raised TypeError.
    """
    code = (
        "import crow_cli.tools as T\n"
        "import crow_cli.tools.fs_tool\n"
        "import crow_cli.tools.task_tool\n"
        "print(type(T.fs).__name__, callable(T.fs))\n"
        "print(type(T.task).__name__, callable(T.task))\n"
        "print(type(T.goal_done).__name__, callable(T.goal_done))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.split("\n")[:3] == [
        "function True",
        "function True",
        "function True",
    ], out.stdout
