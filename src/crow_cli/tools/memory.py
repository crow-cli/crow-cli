"""memory — the agent's own history, as DataFrames.

Modes:
- ``list``   — the database's entries: sessions, most-recently-active first.
  With ``session_id=``, that session's entries instead: its messages, oldest
  first. ``ls`` semantics — one mode, and how much you name decides the level.
- ``search`` — BM25 keyword search across every session, or within one when
  ``session_id=`` is given. Best match first.
- ``sql``    — your own statement, over a READ-ONLY connection.

Python objects, not markdown. The three MCP tools this replaces
(list_sessions, query_memory, query_session) each returned ONE markdown
table, because an MCP tool returns one string, and each therefore grew a set
of parameters whose only job was to control that string. Every one of them is
a Python expression here, so every one of them is gone:

- ``mode=conversation|with_thinking|with_tools|full`` — a display filter for
  a transcript. The frame has a ``role`` column; ``.filter()`` is the filter.
- ``order=asc|desc`` — ``.reverse()``, ``.head()``, ``.tail()``.
- ``offset`` — pagination, which dies wherever it appears. ``limit`` is
  top-N by recency or relevance (a property of the QUERY), and slicing the
  frame you got is Python.
- ``context=N`` — the neighbours of a match. The frame carries the message
  ``id``; ``list(session_id=…)`` carries the messages around it.
- ``after``/``before`` — ``created_at`` is a column of ISO strings, which
  compare lexicographically: ``.filter(pl.col("created_at") > "2026-09")``.
- ``search_type=semantic|keyword|both`` — "semantic" was bm25 all along (the
  ColBERT backend is gone) and "keyword" was a substring scan in Python.
  ``sql`` does substring scans in sqlite's C, over columns FTS cannot see.

What survives is what cannot be done after the fact: ``limit``, and the
filters that have to be INSIDE a ranked query for ``limit`` to mean "this
many matches" rather than "this many rows scanned" — ``roles``,
``include_forks``, ``session_id``. Pushing them down is a bug fix, not a
feature: the old path fetched the global top-N and filtered in Python, so a
session-scoped search for a common term returned the intersection of "best
80 in the database" with "in this session", which is usually empty.

Read-only at the CONNECTION level (crow_cli.memory.get_ro_engine: sqlite's
``mode=ro`` URI so the OS refuses, postgres READ ONLY transaction
characteristics so the server refuses). Verified: insert, update, delete,
create and drop all raise "attempt to write a readonly database". It is not a
sandbox and does not claim to be — ``ATTACH`` a fresh file and writing to it
works, and the kernel has ``write()`` and the whole filesystem anyway. The
guarantee is that memory cannot be edited by accident while being read.

The database is the one execute's prologue injected on the identity rail
(``register.db_uri()``) — the same rail that carries the subtool sink, so the
kernel still reads no config and cannot point itself at someone else's
history by guessing a path.

THE INDEX HAS A HOLE, and ``search`` inherits it: messages_fts indexes
``message_text()`` — content plus reasoning_content — and NOT tool_calls.
Measured on the live database: 17,208 assistant messages (21% of it) carry
tool calls and no content, so bm25 cannot see them at all; a file path
mentioned in 70 assistant messages is found in 1, because the other 69 mention
it only inside an edit's arguments. Tool RESULTS are indexed (a tool
message's content is the result). For the hole, ``sql`` with
``data LIKE '%…%'`` — a full scan, 0.5s over 499MB, and it sees everything.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

import crow_cli.memory as cm

from .register import db_uri as _rail_db_uri
from .register import subtool
from .results import _MEMORY_BYTES, MemoryResult, MemoryToolError

_MODES = ("list", "search", "sql")
_ROLES = ("system", "user", "assistant", "tool")

_SESSIONS_LIMIT = 50
_MESSAGES_LIMIT = 1000
_SEARCH_LIMIT = 20
# The byte cap is the real guard, but it only streams for the queries this
# module composes — search goes through the memory package's FTS seam, which
# materializes its hits. 10k rows at the live db's 6KB average is 60MB, which
# is the biggest hole a limit= can dig.
_MAX_LIMIT = 10_000

_SNIPPET = 200  # last_text on the sessions frame
_CALL_ARGS = 80  # chars of a tool call's arguments
_EXCERPT = 200  # chars either side of a search match

# Eight columns each, which is not a coincidence: polars' repr elides the
# middle of a frame wider than eight (first four, last four), and print(r.df)
# is the LLM's whole view of the result.
_SESSION_COLS = (
    "session_id",
    "last_activity",
    "msgs",
    "agents",
    "cwd",
    "model",
    "last_role",
    "last_text",
)
_MESSAGE_COLS = (
    "id",
    "agent_idx",
    "fork_idx",
    "role",
    "created_at",
    "chars",
    "calls",
    "text",
)
_SEARCH_COLS = (
    "id",
    "session_id",
    "agent_idx",
    "fork_idx",
    "role",
    "created_at",
    "rank",
    "excerpt",
)

# The engine lives in a mutable CELL, not a module global, for the reason
# web.py keeps its browser in one: importlib.reload re-executes this source in
# the EXISTING module dict, so `_engine = None` at module level would drop the
# handle on every reload() and leak its connection pool — file descriptors on
# sqlite, a server session each on postgres.
_state: dict = globals().setdefault("_state", {})


def _dispose() -> None:
    """Drop the cached engine (test hygiene, and a db_uri that changed)."""
    engine = _state.get("engine")
    if engine is not None:
        with suppress(Exception):
            engine.dispose()
    _state["engine"] = None
    _state["uri"] = None


def _engine():
    """The read-only engine for the injected crow.db, cached per uri."""
    uri = _rail_db_uri()
    if uri is None:
        raise MemoryToolError(
            "no database — memory() reads the crow.db that execute's prologue"
            " injects on the identity rail; outside a kernel, point the rail"
            " at one with crow_cli.tools.register.begin_cell(db_uri=…)"
        )
    if _state.get("uri") != uri:
        _dispose()
        if uri.startswith("sqlite:///"):
            # mode=ro cannot CREATE, so a missing file is "unable to open
            # database file" — true, and useless. Name the path instead.
            path = Path(uri.removeprefix("sqlite:///"))
            if not path.exists():
                raise MemoryToolError(
                    f"no database at {path} — nothing has been remembered yet"
                )
        _state["engine"] = cm.get_ro_engine(uri)
        _state["uri"] = uri
    return _state["engine"]


def _stmt(sql: str, params: dict | None = None, expanding: tuple[str, ...] = ()):
    return text(sql).bindparams(
        *(bindparam(name, expanding=True) for name in expanding),
        **(params or {}),
    )


def _fetch(engine, stmt) -> tuple[list[tuple], list[str], bool]:
    """(rows, column names, truncated) for one statement, streamed.

    Iterated, not fetchall()'d, and breaking out of the loop stops sqlite
    stepping the query — measured on the live db: a 1MB cap on
    ``select id, data from messages`` returns 316 rows in 1ms where the same
    query aggregated to completion takes 511ms. That is what makes the cap a
    guard rather than a decoration: 499MB of message JSON never has to fit in
    the kernel to be refused.

    The first row is always kept, whatever it costs — one 12.8MB message (the
    live db's largest) must produce a frame with one row in it, not an empty
    one that looks like "no matches".

    ``stmt`` is a TextClause for the queries composed here and a plain string
    for mode="sql", which goes through exec_driver_sql: the model's statement
    verbatim, with no bindparam parser between it and the database. text() is
    careful about quoted literals and comments, but it does scan for
    ``:name``, and a statement that trips the scan fails with a complaint
    about SQLAlchemy's parameters ("A value is required for bind parameter
    'role'") where the same statement through the driver fails with the
    database's own ("Incorrect number of bindings supplied") — this mode's
    contract is that what you wrote is what runs, so the database should be
    the one to say what is wrong with it.
    """
    rows: list[tuple] = []
    size = 0
    truncated = False
    with engine.connect() as conn:
        conn = conn.execution_options(stream_results=True)
        result = conn.exec_driver_sql(stmt) if isinstance(stmt, str) else conn.execute(stmt)
        names = list(result.keys())
        for row in result:
            cost = sum(len(v) if isinstance(v, str) else 8 for v in row)
            if rows and size + cost > _MEMORY_BYTES:
                truncated = True
                break
            rows.append(tuple(row))
            size += cost
    return rows, names, truncated


def _scalar(engine, stmt) -> int:
    with engine.connect() as conn:
        return conn.execute(stmt).scalar() or 0


def _frame(columns: dict[str, list]) -> Any:
    import polars as pl

    return pl.DataFrame(columns)


def _empty(cols: tuple[str, ...]) -> Any:
    return _frame({c: [] for c in cols})


def _cell(value: Any) -> Any:
    """A value polars can hold: scalars as themselves, everything else JSON.

    Polars infers a Struct from the FIRST row of dicts, and a real messages
    table breaks that two ways (both measured on 1.44.1): ``content`` is a str
    in a user row and a list of blocks in an assistant one, which RAISES
    (``TypeError: unexpected value while building Series of type String``);
    and a row carrying a key the first row lacked — ``tool_calls`` — does not
    raise, the key is silently DROPPED from the inferred Struct. A JSON string
    column builds every time and loses nothing, is searchable as text, answers
    ``.str.json_path_match("$.content")``, and ``json.loads`` gets the object
    back out of ``.to_dicts()``.
    """
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    return json.dumps(value, default=str, ensure_ascii=False)


def _data(raw: Any) -> dict:
    """The message dict, whichever way the dialect handed it over: raw SQL
    bypasses the ORM's JSON type, so sqlite returns text and postgres jsonb."""
    if isinstance(raw, str):
        with suppress(ValueError):
            raw = json.loads(raw)
    return raw if isinstance(raw, dict) else {"content": str(raw or "")}


def _calls(data: dict) -> str:
    """``edit({"file_path": "/home/…"), terminal({"command": "pytest …")``.

    Without this column a transcript frame is 40% blank rows: an assistant
    message that only calls tools has no content, and its tool calls are the
    interesting part of it — which file, which command. Arguments are cut at
    80 chars because the frame is a view, and ``sql`` is the whole JSON.
    """
    out = []
    for call in data.get("tool_calls") or []:
        fn = (call or {}).get("function") or {}
        name = fn.get("name") or "?"
        args = fn.get("arguments") or ""
        out.append(f"{name}({args[:_CALL_ARGS]})" if args else name)
    return ", ".join(out)


def _snippet(raw: Any) -> str:
    text = " ".join(cm.message_text(_data(raw)).split())
    return text[:_SNIPPET] + ("…" if len(text) > _SNIPPET else "")


def _excerpt(text: str, query: str) -> str:
    """The window around the match — what makes a hit legible.

    polars' repr shows ~30 chars of a cell, so a frame of whole messages
    would print their openings and never the part that matched. Falls back
    token by token (bm25 ANDs tokens; they need not be adjacent, so the whole
    query is often not a substring) and then to the head of the message.
    """
    low = text.lower()
    for needle in (query, *query.split()):
        needle = needle.strip().lower()
        if not needle:
            continue
        idx = low.find(needle)
        if idx < 0:
            continue
        start = max(0, idx - _EXCERPT)
        end = min(len(text), idx + len(needle) + _EXCERPT)
        return (
            ("…" if start else "")
            + text[start:end]
            + ("…" if end < len(text) else "")
        )
    head = text[: _EXCERPT * 2]
    return head + ("…" if len(text) > len(head) else "")


def _q_sessions(limit: int, include_forks: bool) -> MemoryResult:
    engine = _engine()
    where = "" if include_forks else "WHERE a.fork_idx = 1"
    and_where = "" if include_forks else "AND a.fork_idx = 1"
    agg = (
        "SELECT a.session_id AS session_id, "
        # coalesce, not a bare max: a session with no messages would sort
        # NULL, and NULLs come FIRST on a postgres DESC and LAST on a sqlite
        # one — the same query, two different answers.
        "coalesce(max(m.created_at), max(a.created_at)) AS last_activity, "
        "count(DISTINCT m.id) AS msgs, count(DISTINCT a.agent_id) AS agents "
        "FROM agents a LEFT JOIN messages m ON m.agent_id = a.agent_id "
        f"{where} GROUP BY a.session_id ORDER BY last_activity DESC LIMIT :lim"
    )
    rows, _, truncated = _fetch(engine, _stmt(agg, {"lim": limit}))
    total = _scalar(
        engine,
        _stmt(
            "SELECT count(DISTINCT session_id) FROM agents"
            + ("" if include_forks else " WHERE fork_idx = 1")
        ),
    )
    cols = {c: [] for c in _SESSION_COLS}
    if not rows:
        return MemoryResult(
            df=_empty(_SESSION_COLS), subject="sessions", sql=agg, total=total
        )

    sids = [r[0] for r in rows]
    # Two more queries for the page, not one per session: the shape this
    # replaces asked each session for its own last message (N+1).
    detail, _, _ = _fetch(
        engine,
        _stmt(
            "SELECT a.session_id, a.cwd, a.model_identifier FROM agents a "
            f"WHERE a.session_id IN :sids {and_where} ORDER BY a.agent_idx",
            {"sids": sids},
            ("sids",),
        ),
    )
    first: dict[str, tuple[str, str]] = {}
    for sid, cwd, model in detail:
        first.setdefault(sid, (cwd or "", model or ""))
    last, _, last_cut = _fetch(
        engine,
        _stmt(
            "SELECT session_id, role, data FROM ("
            " SELECT a.session_id AS session_id, m.role AS role, m.data AS data,"
            " row_number() OVER (PARTITION BY a.session_id ORDER BY m.id DESC)"
            " AS rn FROM messages m JOIN agents a ON a.agent_id = m.agent_id"
            f" WHERE a.session_id IN :sids {and_where}) t WHERE rn = 1",
            {"sids": sids},
            ("sids",),
        ),
    )
    tail = {sid: (role, _snippet(data)) for sid, role, data in last}
    for sid, last_activity, msgs, agents in rows:
        cwd, model = first.get(sid, ("", ""))
        role, snippet = tail.get(sid, ("", ""))
        cols["session_id"].append(sid)
        cols["last_activity"].append(last_activity or "")
        cols["msgs"].append(msgs)
        cols["agents"].append(agents)
        cols["cwd"].append(cwd)
        cols["model"].append(model)
        cols["last_role"].append(role or "")
        cols["last_text"].append(snippet)
    return MemoryResult(
        df=_frame(cols),
        subject="sessions",
        sql=agg,
        total=total,
        truncated=truncated or last_cut,
    )


def _q_messages(
    session_id: str, roles: tuple[str, ...] | None, limit: int, include_forks: bool
) -> MemoryResult:
    engine = _engine()
    # A typo'd session id and a session that said nothing look identical in an
    # empty frame, and the first one is a caller bug — so it is an error, the
    # same ruling as a blank web query.
    if not _scalar(
        engine, _stmt("SELECT count(*) FROM agents WHERE session_id = :sid", {"sid": session_id})
    ):
        raise MemoryToolError(
            f"no session {session_id!r} in the database — memory('list')"
            " lists the ones there are"
        )
    clauses = ["a.session_id = :sid"]
    params: dict[str, Any] = {"sid": session_id}
    expanding: tuple[str, ...] = ()
    if not include_forks:
        clauses.append("a.fork_idx = 1")
    if roles:
        clauses.append("m.role IN :roles")
        params["roles"] = roles
        expanding = ("roles",)
    where = " AND ".join(clauses)
    join = "FROM messages m JOIN agents a ON a.agent_id = m.agent_id "
    total = _scalar(
        engine,
        _stmt(f"SELECT count(*) {join}WHERE {where}", params, expanding),
    )
    sql = (
        "SELECT m.id, a.agent_idx, a.fork_idx, m.role, m.created_at, m.data "
        f"{join}WHERE {where} ORDER BY m.id DESC LIMIT :lim"
    )
    rows, _, truncated = _fetch(
        engine, _stmt(sql, {**params, "lim": limit}, expanding)
    )
    # The tail, read forwards: DESC + LIMIT is how you ask for the LAST n, and
    # a transcript that arrives newest-first is one .reverse() away from being
    # wrong everywhere it is used.
    rows.reverse()
    cols = {c: [] for c in _MESSAGE_COLS}
    for mid, agent_idx, fork_idx, role, created_at, raw in rows:
        data = _data(raw)
        body = cm.message_text(data)
        cols["id"].append(mid)
        cols["agent_idx"].append(agent_idx)
        cols["fork_idx"].append(fork_idx)
        cols["role"].append(role)
        cols["created_at"].append(created_at or "")
        cols["chars"].append(len(body))
        cols["calls"].append(_calls(data))
        cols["text"].append(body)
    return MemoryResult(
        df=_frame(cols),
        subject=session_id,
        sql=sql,
        total=total,
        truncated=truncated,
    )


def _q_search(
    query: str,
    session_id: str | None,
    roles: tuple[str, ...] | None,
    limit: int,
    include_forks: bool,
) -> MemoryResult:
    engine = _engine()
    hits = cm.search_messages(
        engine,
        query,
        limit=limit,
        session_id=session_id,
        roles=list(roles) if roles else None,
        include_forks=include_forks,
    )
    cols = {c: [] for c in _SEARCH_COLS}
    for hit in hits:
        body = cm.message_text(hit["data"])
        cols["id"].append(hit["id"])
        cols["session_id"].append(hit["session_id"])
        cols["agent_idx"].append(hit["agent_idx"])
        cols["fork_idx"].append(hit["fork_idx"])
        cols["role"].append(hit["role"])
        cols["created_at"].append(hit["created_at"] or "")
        # bm25's own sign: lower is better, and the rows arrive that way. Not
        # negated into a "score" — a column that invites a descending sort and
        # then returns the worst hits first is worse than one with an
        # unfamiliar convention and an honest name.
        cols["rank"].append(hit["score"])
        cols["excerpt"].append(_excerpt(body, query))
    subject = query if session_id is None else f"{query} in {session_id}"
    return MemoryResult(df=_frame(cols), subject=subject)


def _q_sql(statement: str) -> MemoryResult:
    engine = _engine()
    rows, names, truncated = _fetch(engine, statement)
    cols: dict[str, list] = {name: [] for name in names}
    for row in rows:
        for name, value in zip(names, row):
            cols[name].append(_cell(value))
    return MemoryResult(
        df=_frame(cols), subject=statement, sql=statement, truncated=truncated
    )


def _limit(value: int | None, default: int) -> int:
    if value is None:
        return default
    if value < 0:
        raise MemoryToolError(f"limit must be >= 0, got {value}")
    if value > _MAX_LIMIT:
        raise MemoryToolError(
            f"limit must be <= {_MAX_LIMIT}, got {value} — the frame is not"
            " the constraint, kernel RAM is; mode='sql' with your own LIMIT"
            " and fewer columns goes further"
        )
    return int(value)


def _roles(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = (value,)  # a string is a sequence of characters, not of roles
    roles = tuple(str(r) for r in value)
    for role in roles:
        if role not in _ROLES:
            raise MemoryToolError(
                f"unknown role {role!r} — expected one of: {', '.join(_ROLES)}"
            )
    return roles


@subtool(tool="memory")
async def memory(
    mode: str,
    target: str | None = None,
    session_id: str | None = None,
    roles: tuple[str, ...] | list[str] | str | None = None,
    limit: int | None = None,
    include_forks: bool | None = None,
):
    """Read your own memory: past sessions, what they said, what you did.

    Args:
        mode: "list", "search" or "sql".
        target: search — the words to look for. sql — the statement. list
            takes none.
        session_id: list/search — scope to one session. For list this changes
            WHAT is listed: sessions are the database's entries, and a
            session's entries are its messages.
        roles: list/search — keep only these message roles: "system", "user",
            "assistant", "tool". Default all four. Pushed into the query, so
            ``limit`` still means this many rows (filtering the frame
            afterwards would leave you with fewer than you asked for).
        limit: list/search — top N (sessions 50, messages 1000, hits 20;
            max 10000). Messages come back as the LAST N in chronological
            order; ``.total`` says how many there were.
        include_forks: list/search — default False, which reads the trunk
            only. True folds in fork agents' own messages (a fork reads the
            trunk's prefix, it does not copy it, so this adds only what the
            fork itself said) and counts them in the session totals.

    Returns:
        MemoryResult — ``.df`` is a polars DataFrame, ``.sql`` the statement
        that ran (empty for search, which goes through the memory package's
        FTS seam), ``.total`` the rows matching before the limit when that is
        cheap to know, ``.truncated`` whether the 64MB cap cut it, ``.rows``
        the height, ``.text`` the printable rendering.

        list of sessions -> session_id, last_activity, msgs, agents, cwd,
        model, last_role, last_text (a 200-char snippet).
        list of a session -> id, agent_idx, fork_idx, role, created_at,
        chars, calls (its tool calls, arguments cut at 80 chars), text.
        search -> id, session_id, agent_idx, fork_idx, role, created_at,
        rank (bm25, LOWER is better; rows arrive best-first), excerpt (±200
        chars around the match — the frame is a view, the whole message is
        the id away).

    Raises:
        MemoryToolError: unknown mode, a missing or blank target, an argument
            on the wrong mode, an unknown role, a negative or absurd limit, a
            session_id that does not exist, SQL the database rejected —
            including any write, which the connection refuses at the OS level.

    Note:
        The model sees only what the cell PRINTS, and polars' repr is bounded
        by construction — 5 rows from each end, 4 columns from each end, ~30
        chars per cell — so ``print(r.df)`` is a legible table of a 10,000-row
        result and cannot flood the context. For more than the repr shows:
        ``print(r.df["text"][3])``, ``for row in r.df.iter_rows(named=True)``,
        ``print(r.df.select("id", "role", "calls"))``.

        Schema (v5), for mode="sql":
          agents    agent_id PK = "{session_id}-{agent_idx}-{fork_idx}", all
                    1-based, trunk fork_idx=1; session_id, agent_idx,
                    fork_idx, forked_at (the message id a fork branched
                    from), cwd, model_identifier, status, created_at,
                    system_prompt, prompt_id, prompt_args, tool_definitions,
                    mcp_servers, request_params.
          messages  id PK, agent_id, fork_idx, role, created_at (ISO), data
                    (the whole message as JSON: content, tool_calls,
                    tool_call_id, reasoning_content), prompt_tokens,
                    completion_tokens, total_tokens.
          messages_fts  the keyword index: rowid = messages.id, UNINDEXED
                    agent_id/role/fork_idx, indexed text. MATCH it with
                    quoted tokens — `where messages_fts match '"crow.db"'` —
                    and rank with bm25(messages_fts), lower = better.
          prompts   id PK, name, template, created_at — versioned system
                    prompts, so character has a history.
          tasks     task_id PK, kind, owner_session, tool_call_id,
                    sub_session, prompt, model, priority, status, result,
                    created_at, finished_at.
          task_deliveries  id PK, session_id, task_id, priority, content,
                    status, created_at, delivered_at.
          subtool_calls  every tool call made inside an execute cell:
                    session_id, agent_id, parent_tool_call_id, cell_seq,
                    tool, mode, args, status, result_kind, acp_payload,
                    llm_images, error, emitted, created_at.
          session_tabs  TUI tab state (title, resume meta).

        Examples (mode="sql"):
          "select a.session_id, count(*) n, sum(m.total_tokens) tok from
           messages m join agents a on a.agent_id=m.agent_id group by 1
           order by tok desc limit 10"
          "select tool, mode, count(*) n from subtool_calls group by 1,2
           order by n desc"
          "select id, role, json_extract(data,'$.content') from messages
           where id = 2018783"   (postgres: data->>'content')
          "select m.id, m.role from messages m where m.data like
           '%EXECUTE_TODO%' and m.role='assistant' limit 20"  — the scan that
           sees what the FTS index cannot: tool call arguments.

        The connection is read-only: memory cannot be written from here. That
        is a guarantee about crow.db, not a sandbox — the kernel has write(),
        fs() and the filesystem.
    """
    if mode not in _MODES:
        raise MemoryToolError(
            f"unknown memory mode {mode!r} — expected one of: {', '.join(_MODES)}"
        )
    forks = bool(include_forks)
    target = (target or "").strip()

    if mode == "sql":
        for name, value in (
            ("session_id", session_id),
            ("roles", roles),
            ("limit", limit),
            ("include_forks", include_forks),
        ):
            if value is not None:
                raise MemoryToolError(
                    f"{name}= is for mode='list' and 'search', not 'sql' —"
                    " write it into the statement"
                )
        if not target:
            raise MemoryToolError("mode='sql' requires target= — the statement to run")
        return await _run(_q_sql, target)

    if target and mode == "list":
        raise MemoryToolError(
            "mode='list' takes no target= — it lists sessions, or the messages"
            " of one when session_id= is given"
        )
    if mode == "search" and not target:
        raise MemoryToolError(
            "mode='search' requires target= — the words to look for"
        )
    if session_id is not None:
        session_id = session_id.strip()
        if not session_id:
            raise MemoryToolError("session_id= is blank")
    kept = _roles(roles)
    # A sessions list has no role column to filter, so accepting roles= here
    # would be an argument quietly ignored — the caller asked for something
    # and got something else with no signal.
    if kept is not None and mode == "list" and session_id is None:
        raise MemoryToolError(
            "roles= filters MESSAGES, and mode='list' without session_id="
            " lists sessions — pass session_id= to list a session's messages"
        )

    if mode == "search":
        return await _run(
            _q_search,
            target,
            session_id,
            kept,
            _limit(limit, _SEARCH_LIMIT),
            forks,
        )
    if session_id is not None:
        return await _run(
            _q_messages, session_id, kept, _limit(limit, _MESSAGES_LIMIT), forks
        )
    return await _run(_q_sessions, _limit(limit, _SESSIONS_LIMIT), forks)


async def _run(fn, *args) -> MemoryResult:
    """Blocking SQLAlchemy off the kernel's event loop, and the database's own
    errors in the tool's own vocabulary.

    to_thread for the reason vision runs cv2 in one: a cell is already inside
    ipykernel's running loop, and a 500ms full scan on it stalls the
    kernel's heartbeats with it.
    """
    try:
        return await asyncio.to_thread(fn, *args)
    except MemoryToolError:
        raise
    except SQLAlchemyError as exc:
        # SQLAlchemy renders "(sqlite3.OperationalError) <the actual problem>"
        # on the first line and then the statement, the parameters and a link
        # to its own docs — the model wrote the statement, it wants the
        # problem.
        raise MemoryToolError(str(exc).splitlines()[0]) from None
