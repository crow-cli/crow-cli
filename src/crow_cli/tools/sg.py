"""Structural code search — ast-grep as a first-class subtool.

``fs(mode="ast")`` already did this, buried as one of six modes behind a
dispatcher; this is the same engine with its own name in the kernel, because
a capability that needs a mode string to reach is a capability that does not
get reached. Reach for it instead of ``search()``/rg whenever the question is
about CODE SHAPE rather than text.

The engine, the language table and the walk all live in ``crow_cli.tools.fs``
and are imported at CALL time: ``reload()`` refreshes modules in ``_LAZY``
order, so a module-level ``from .fs import ...`` would keep a stale function
across a reload (the same reason ``fs._finish`` imports ``write`` late).
"""

from __future__ import annotations

from .register import subtool
from .results import FsError, SearchResult


@subtool(tool="sg")
async def sg(
    pattern: str,
    path: str | None = None,
    *,
    lang: str | None = None,
    file_pattern: str | None = None,
    limit: int | None = None,
) -> SearchResult:
    """Search a tree for a SYNTAX-TREE shape, not a substring.

    Matches whole AST nodes, so it never hits inside a string literal or a
    comment unless the pattern targets one, and it never substring-matches an
    identifier: the pattern ``db_uri`` will not match ``my_db_uri``. That is
    the difference from ``search()``/rg, and the reason to prefer it for
    renames, signature changes, call-site hunts, and "where is this code
    shape" questions.

    Args:
        pattern: an ast-grep pattern. ``$NAME`` captures exactly one node,
            ``$$$NAME`` captures zero or more (so ``$$$`` alone is "any
            arguments at all"). Literals must match the grammar: punctuation,
            keywords and parameter syntax are part of the pattern, which is
            why ``def $F($$$)`` finds definitions but ``def $F(...)`` does
            not. A pattern the grammar cannot match raises rather than
            silently returning nothing — but grammatical is not matching.
            Verified live: ``def $F($$$):`` (trailing colon) parses fine and
            returns ZERO hits, while ``def $F($$$)`` finds every def — the
            colon you would write in source is exactly the punctuation the
            pattern must not have. Likewise ``$F = $$$`` matches
            assignments: holes sit wherever a node can. When a "sensible"
            pattern comes back empty, strip its tail before doubting the
            code.
        path: a directory to walk (default: the kernel's cwd), or a single
            file to search on its own — one known module is the common case
            and should not cost a walk. Absolute, or relative to cwd. A
            directory walk is gitignore-aware and skips .git, .venv,
            __pycache__ and node_modules.
        lang: one grammar instead of every mapped extension. Omit it to
            search the whole tree across languages. Unsupported languages
            raise — the native binding PANICS on them (a pyo3
            PanicException, which is a BaseException and would sail through
            an ``except Exception``), so they are refused up front.
        file_pattern: restrict the walk to files matching a glob (rg -g,
            e.g. "*.py"). Applied before parsing, so it is the cheap way to
            narrow a big tree.
        limit: max matches (default 200). A COUNT, not a slice end; negative
            raises. ``.truncated`` says whether the cap was hit.

    Returns:
        SearchResult — ``.matches`` of SearchMatch(path, line, text) in walk
        order, ``.paths`` deduplicated, ``.text`` rendered one
        ``path:line: text`` per match, ``.truncated``. A structural match can
        span lines (a whole function); ``.text`` collapses its whitespace and
        caps it, so one match is always one line of output.

    Raises:
        FsError: no pattern, unsupported lang, a path that is not a
            directory, an unmatchable pattern, negative limit, ripgrep
            absent, or a walk that failed or timed out.

    Note:
        The model sees only what the cell PRINTS — ``print(r.text)``, or
        iterate ``r.matches`` for structured use. The client gets the same
        text as a search-kind call. This tool only READS: the structural
        rewrite lives at ``fs(mode="rewrite")``, which plans the whole tree
        before writing any of it and diffs per file.
    """
    import asyncio
    from pathlib import Path

    from .fs import _LANGS, _ast, _ast_scan, _cap, _lang_of, _resolve_path

    if not pattern:
        raise FsError("sg() requires a pattern")
    if lang is not None and lang not in _LANGS:
        raise FsError(
            "unsupported ast language " + repr(lang) + " — expected one of: " + ", ".join(_LANGS)
        )
    try:
        root = _resolve_path(path or ".")
    except ValueError as e:
        raise FsError(str(e)) from None

    cap = _cap(limit, "search")
    if root.is_dir():
        return await _ast(root, pattern, lang, file_pattern, cap)

    # A single file skips the walk entirely — the common case is "this
    # module", and making the caller pass its directory plus a file_pattern
    # to search one known file is a mode string's worth of friction.
    if not root.exists():
        raise FsError(f"no such file or directory: {root}")
    grammar = lang or _lang_of(root)
    if grammar is None:
        raise FsError(
            f"cannot infer a grammar for {root.name} — pass lang= "
            f"(one of: {', '.join(_LANGS)})"
        )
    matches, truncated = await asyncio.to_thread(
        _ast_scan, [Path(root)], pattern, grammar, cap
    )
    return SearchResult(
        pattern=pattern, root=str(root), matches=matches, truncated=truncated
    )
