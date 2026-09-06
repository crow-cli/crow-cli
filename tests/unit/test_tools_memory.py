"""memory — the agent's own history as polars frames: real result objects,
MemoryToolError raised on failure, register + write-through like every
subtool.

No mocks. A real crow.db built through the real write path
(create_database + create_agent + add_message), so the keyword index is the
one the product maintains — which matters, because add_message indexes
message_text() (content + reasoning) and NOT tool_calls, and two tests below
assert exactly that hole and the sql scan that sees through it. Reads go
through the real read-only engine, so the write refusal is sqlite's, not a
stub's.

Timestamps are stamped explicitly: "most recently active" is the sort the
list mode exists to do, and now_iso() would hand the ordering to the clock
(and to pytest-randomly).
"""

import importlib
import json
import sys

import polars as pl
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

import crow_cli.memory as cm
from crow_cli.memory.models import SubtoolCall
from crow_cli.tools import memory
from crow_cli.tools.register import begin_cell, clear, current_cell, db_uri, pending
from crow_cli.tools.results import MemoryResult, MemoryToolError, _compact

# from-import of internals IS safe; `import crow_cli.tools.memory as m` is
# not — the facade resolves that name to the FUNCTION.
from crow_cli.tools.memory import _cell, _excerpt

MOD = sys.modules["crow_cli.tools.memory"]

SESSION_COLS = [
    "session_id",
    "last_activity",
    "msgs",
    "agents",
    "cwd",
    "model",
    "last_role",
    "last_text",
]
MESSAGE_COLS = [
    "id",
    "agent_idx",
    "fork_idx",
    "role",
    "created_at",
    "chars",
    "calls",
    "text",
]
SEARCH_COLS = [
    "id",
    "session_id",
    "agent_idx",
    "fork_idx",
    "role",
    "created_at",
    "rank",
    "excerpt",
]

# The tool call whose arguments the FTS index cannot see. "setdefault" is the
# probe: it appears nowhere in any indexed text in this database.
EDIT_ARGS = json.dumps(
    {
        "file_path": "/proj/src/crow_cli/tools/register.py",
        "old_string": "_engine = None",
        "new_string": "_state = globals().setdefault('_state', {})",
    }
)
TOOL_CALLS = [
    {
        "id": "call_1",
        "type": "function",
        "function": {"name": "edit", "arguments": EDIT_ARGS},
    }
]
REASONED = "the pool was never disposed"
THINKING = "thinking about connection pools"
LONG = (
    "the polars repr elides the middle of a wide frame and the ends of a tall"
    " one, which is why printing a ten-thousand-row result cannot flood the"
    " context. " + "The rest of this message is padding. " * 20
)


class _DB(dict):
    """The fixture database: `db.uri` for the connection and `db["call"]` for
    a message id, because a test reads both kinds of thing constantly."""

    def __getattr__(self, name):
        return self[name]


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    """alpha-one (7 trunk messages over 2 agents + 1 fork message), beta-two
    (2 messages, one of them long), gamma-empty (an agent that never spoke —
    the coalesce branch of the sessions sort)."""
    root = tmp_path_factory.mktemp("memory")
    uri = f"sqlite:///{root / 'crow.db'}"
    cm.create_database(uri)
    engine = cm.get_engine(uri)

    def agent(agent_id, session_id, agent_idx, fork_idx=1, **fields):
        cm.create_agent(
            engine,
            agent_id=agent_id,
            session_id=session_id,
            agent_idx=agent_idx,
            fork_idx=fork_idx,
            tool_definitions=[],
            request_params={},
            **fields,
        )

    def msg(agent_id, message, when):
        mid = cm.add_message(engine, agent_id, message)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE messages SET created_at = :c WHERE id = :i"),
                {"c": when, "i": mid},
            )
        return mid

    agent("alpha-one-1-1", "alpha-one", 1, cwd="/proj", model_identifier="sonnet")
    # A second trunk agent with a DIFFERENT cwd/model: the sessions frame
    # reports the lowest agent_idx's, not the most recent one's.
    agent(
        "alpha-one-2-1", "alpha-one", 2, cwd="/later", model_identifier="haiku"
    )
    agent(
        "alpha-one-1-2",
        "alpha-one",
        1,
        fork_idx=2,
        forked_at="2",
        cwd="/fork",
        model_identifier="forked",
    )
    agent("beta-two-1-1", "beta-two", 1, cwd="/other", model_identifier="gpt")
    agent(
        "gamma-empty-1-1",
        "gamma-empty",
        1,
        cwd="/empty",
        model_identifier="",
        created_at="2026-07-01T00:00:00+00:00",
    )

    ids = {}
    a1 = "alpha-one-1-1"
    ids["system"] = msg(a1, {"role": "system", "content": "you are crow"},
                        "2026-09-01T01:00:00+00:00")
    ids["question"] = msg(
        a1,
        {"role": "user", "content": "why does the kernel leak file descriptors"},
        "2026-09-01T02:00:00+00:00",
    )
    # The row the index cannot see: tool calls, no content.
    ids["call"] = msg(
        a1,
        {"role": "assistant", "content": "", "tool_calls": TOOL_CALLS},
        "2026-09-01T03:00:00+00:00",
    )
    # ...while the RESULT of that call is indexed, path and all.
    ids["result"] = msg(
        a1,
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "edited /proj/src/crow_cli/tools/register.py",
        },
        "2026-09-01T04:00:00+00:00",
    )
    ids["reasoned"] = msg(
        a1,
        {
            "role": "assistant",
            "content": REASONED,
            "reasoning_content": THINKING,
        },
        "2026-09-01T05:00:00+00:00",
    )
    ids["compact"] = msg(
        "alpha-one-2-1",
        {"role": "user", "content": "compact the session"},
        "2026-09-01T06:00:00+00:00",
    )
    ids["compacted"] = msg(
        "alpha-one-2-1",
        {"role": "assistant", "content": "compacted the session down"},
        "2026-09-01T07:00:00+00:00",
    )
    ids["fork"] = msg(
        "alpha-one-1-2",
        {"role": "user", "content": "forked question about zebras"},
        "2026-09-01T08:00:00+00:00",
    )
    ids["polars"] = msg(
        "beta-two-1-1",
        {"role": "user", "content": "polars dataframe repr"},
        "2026-08-01T01:00:00+00:00",
    )
    ids["long"] = msg(
        "beta-two-1-1",
        {"role": "assistant", "content": LONG},
        "2026-08-01T02:00:00+00:00",
    )

    other = f"sqlite:///{root / 'empty.db'}"
    cm.create_database(other)
    engine.dispose()
    return _DB(uri=uri, other=other, root=root, **ids)


@pytest.fixture(autouse=True)
def _rail(db, request):
    """Every test starts on the identity rail execute's prologue would set,
    with an empty register and no engine cached from the last test — and with
    a parent tool-call id of its own, because the write-through rows land in
    the same module-scoped database and a shared id would have each test
    counting its neighbours' rows."""
    clear()
    MOD._dispose()
    begin_cell(
        session_id="s-under-test",
        parent_tool_call_id=f"turn-1/call_{request.node.name}",
        db_uri=db.uri,
    )
    yield
    clear()
    MOD._dispose()


def _written():
    """The subtool_calls rows THIS cell's write-through landed."""
    engine = create_engine(db_uri())
    try:
        with sessionmaker(engine)() as session:
            rows = (
                session.execute(
                    select(SubtoolCall).where(
                        SubtoolCall.parent_tool_call_id
                        == current_cell().parent_tool_call_id
                    )
                )
                .scalars()
                .all()
            )
            session.expunge_all()
        return rows
    finally:
        engine.dispose()


def _row(frame, **where):
    """The one row of `frame` matching every column=value, as a dict."""
    out = frame
    for column, value in where.items():
        out = out.filter(pl.col(column) == value)
    assert out.height == 1, f"expected 1 row for {where}, got {out.height}"
    return out.row(0, named=True)


# --- list: sessions --------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_is_most_recently_active_first(db):
    """The whole reason list exists: not "every session ever" but the ones
    that were just being worked on, with enough of each to recognize it."""
    r = await memory("list")
    assert isinstance(r, MemoryResult) and r
    assert r.df.columns == SESSION_COLS
    assert r.df["session_id"].to_list() == ["alpha-one", "beta-two", "gamma-empty"]
    assert r.rows == 3 == r.total
    assert r.subject == "sessions"
    assert "GROUP BY a.session_id" in r.sql

    row = _row(r.df, session_id="alpha-one")
    assert (row["msgs"], row["agents"]) == (7, 2)
    assert row["last_activity"] == "2026-09-01T07:00:00+00:00"
    assert (row["last_role"], row["last_text"]) == (
        "assistant",
        "compacted the session down",
    )
    # The lowest agent_idx's cwd/model, not the most recent agent's: a
    # session's identity is where it started.
    assert (row["cwd"], row["model"]) == ("/proj", "sonnet")


@pytest.mark.asyncio
async def test_list_sessions_a_session_that_never_spoke(db):
    """coalesce(max(m.created_at), max(a.created_at)): a session with no
    messages still has an age, and NULLs sort differently on the two
    backends."""
    r = await memory("list")
    row = _row(r.df, session_id="gamma-empty")
    assert (row["msgs"], row["agents"]) == (0, 1)
    assert row["last_activity"] == "2026-07-01T00:00:00+00:00"
    assert (row["last_role"], row["last_text"]) == ("", "")
    assert row["cwd"] == "/empty"


@pytest.mark.asyncio
async def test_list_sessions_limit_keeps_total(db):
    r = await memory("list", limit=1)
    assert r.rows == 1 and r.total == 3
    assert r.df["session_id"].to_list() == ["alpha-one"]
    # "1 of 3" is what tells the model to raise the limit; "1" is not.
    assert r.text.startswith("sessions — 1 row(s) of 3 matching")


@pytest.mark.asyncio
async def test_list_sessions_include_forks_counts_them(db):
    """A fork reads the trunk's prefix, it does not copy it — so folding
    forks in adds exactly what the fork itself said, and changes which
    message is last."""
    trunk = await memory("list")
    forks = await memory("list", include_forks=True)
    assert _row(trunk.df, session_id="alpha-one")["msgs"] == 7
    row = _row(forks.df, session_id="alpha-one")
    assert (row["msgs"], row["agents"]) == (8, 3)
    assert (row["last_role"], row["last_text"]) == (
        "user",
        "forked question about zebras",
    )
    assert row["last_activity"] == "2026-09-01T08:00:00+00:00"
    # Sessions are counted, not agents: the fork does not add one.
    assert forks.total == 3


@pytest.mark.asyncio
async def test_text_cuts_the_stamp_but_the_frame_keeps_it(db):
    """.df is the artifact and stays lossless — its ISO strings still compare
    lexicographically, which is how a date filter works. .text is a rendering,
    and the rendering trims. The table width is pinned because polars wraps a
    cell to the width its column got, and at the default budget a 19-char
    stamp is two wrapped lines."""
    r = await memory("list")
    assert r.df["last_activity"][0] == "2026-09-01T07:00:00+00:00"
    with pl.Config(tbl_width_chars=200):
        assert "2026-09-01T07:00:00" in r.text
        assert "+00:00" not in r.text


# --- list: one session's messages -----------------------------------------


@pytest.mark.asyncio
async def test_list_messages_are_the_tail_in_chronological_order(db):
    """DESC + LIMIT is how you ask for the LAST n, and the frame is reversed
    back: a transcript that arrives newest-first is wrong everywhere it is
    used."""
    r = await memory("list", session_id="alpha-one")
    assert r.df.columns == MESSAGE_COLS
    assert r.subject == "alpha-one"
    assert r.rows == 7 == r.total
    assert "ORDER BY m.id DESC" in r.sql
    assert r.df["id"].to_list() == sorted(r.df["id"].to_list())
    assert r.df["role"].to_list() == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
        "assistant",
    ]
    assert r.df["agent_idx"].to_list() == [1, 1, 1, 1, 1, 2, 2]
    assert r.df["fork_idx"].to_list() == [1] * 7
    first = r.df.row(0, named=True)
    assert first["created_at"] == "2026-09-01T01:00:00+00:00"
    assert (first["chars"], first["text"]) == (12, "you are crow")


@pytest.mark.asyncio
async def test_list_messages_limit_is_the_last_n_not_the_first_n(db):
    r = await memory("list", session_id="alpha-one", limit=3)
    assert r.rows == 3 and r.total == 7
    assert r.df["id"].to_list() == [db["reasoned"], db["compact"], db["compacted"]]
    assert r.text.startswith("alpha-one — 3 row(s) of 7 matching")


@pytest.mark.asyncio
async def test_list_messages_roles_are_pushed_into_the_query(db):
    """Filtering the frame afterwards would leave fewer rows than the limit
    asked for; total has to respect the filter too, or it lies."""
    users = await memory("list", session_id="alpha-one", roles=("user",))
    assert users.df["id"].to_list() == [db["question"], db["compact"]]
    assert users.rows == 2 == users.total

    # A string is a sequence of characters, not of roles.
    assistants = await memory("list", session_id="alpha-one", roles="assistant")
    assert assistants.df["id"].to_list() == [db["call"], db["reasoned"], db["compacted"]]
    assert assistants.total == 3

    both = await memory(
        "list", session_id="alpha-one", roles=["system", "tool"], limit=10
    )
    assert both.df["role"].to_list() == ["system", "tool"]
    assert both.total == 2


@pytest.mark.asyncio
async def test_list_messages_include_forks_adds_only_what_the_fork_said(db):
    r = await memory("list", session_id="alpha-one", include_forks=True)
    assert r.rows == 8 == r.total
    last = r.df.row(-1, named=True)
    assert last["id"] == db["fork"]
    assert (last["agent_idx"], last["fork_idx"]) == (1, 2)
    assert last["text"] == "forked question about zebras"


@pytest.mark.asyncio
async def test_list_messages_calls_column_carries_the_unindexed_row(db):
    """An assistant message that only calls tools has no content: without a
    calls column, 21% of the live database prints as blank rows."""
    r = await memory("list", session_id="alpha-one")
    row = _row(r.df, id=db["call"])
    assert (row["chars"], row["text"], row["role"]) == (0, "", "assistant")
    assert row["calls"].startswith(
        'edit({"file_path": "/proj/src/crow_cli/tools/register.py"'
    )
    # Arguments are cut: the frame is a view, sql is the whole JSON.
    assert row["calls"].endswith(")")
    assert len(row["calls"]) == len("edit(") + MOD._CALL_ARGS + 1
    # And the row that produced it carries no calls at all.
    assert _row(r.df, id=db["result"])["calls"] == ""


@pytest.mark.asyncio
async def test_list_messages_fold_reasoning_into_text(db):
    """message_text() is content + reasoning, and `chars` counts what `text`
    holds — the same extraction the FTS index is built from."""
    r = await memory("list", session_id="alpha-one")
    row = _row(r.df, id=db["reasoned"])
    assert row["text"] == f"{REASONED}\n{THINKING}"
    assert row["chars"] == len(REASONED) + 1 + len(THINKING)


@pytest.mark.asyncio
async def test_a_long_message_is_whole_in_the_frame_and_cut_in_the_snippet(db):
    """The frame keeps the message — it is the artifact. The sessions frame's
    last_text is a recognition snippet, because a list of sessions that
    printed whole messages would be unreadable."""
    messages = await memory("list", session_id="beta-two")
    assert _row(messages.df, id=db["long"])["chars"] == len(LONG)

    snippet = _row((await memory("list")).df, session_id="beta-two")["last_text"]
    assert snippet == " ".join(LONG.split())[:200] + "…"
    assert len(snippet) == 201


@pytest.mark.asyncio
async def test_list_messages_unknown_session_raises(db):
    """A typo'd session id and a session that said nothing look identical in
    an empty frame, and the first one is a caller bug."""
    with pytest.raises(MemoryToolError) as exc:
        await memory("list", session_id="alpha-1")
    assert "no session or fork 'alpha-1'" in str(exc.value)
    # ...and the way out is named in the same breath.
    assert "memory('list')" in str(exc.value)


@pytest.mark.asyncio
async def test_list_messages_resolves_a_wire_agent_id(db):
    """A fork's wire id IS its agent_id, and rlm hands that back as
    RlmResult.session_id — so memory("list", session_id=…) resolves it and
    scopes to exactly that fork. This is the documented async-delegation
    collection path; before the dual-identity fix it raised "no session …"."""
    r = await memory("list", session_id="alpha-one-1-2")
    assert r.total == 1 and r.rows == 1
    row = r.df.row(0, named=True)
    assert row["fork_idx"] == 2
    assert "forked question about zebras" in row["text"]


@pytest.mark.asyncio
async def test_list_messages_blank_session_id_raises(db):
    with pytest.raises(MemoryToolError, match="session_id= is blank"):
        await memory("list", session_id="   ")


@pytest.mark.asyncio
async def test_limit_zero_is_an_empty_frame_with_its_total(db):
    """How many are there, without paying to fetch any."""
    sessions = await memory("list", limit=0)
    assert sessions.rows == 0 and sessions.total == 3
    assert sessions.df.columns == SESSION_COLS

    messages = await memory("list", session_id="alpha-one", limit=0)
    assert messages.rows == 0 and messages.total == 7
    assert messages.df.columns == MESSAGE_COLS


# --- search ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_is_best_first_and_rank_ascends(db):
    r = await memory("search", "session")
    assert r.df.columns == SEARCH_COLS
    assert set(r.df["id"].to_list()) == {db["compact"], db["compacted"]}
    ranks = r.df["rank"].to_list()
    # bm25's own sign: lower is better, and the rows arrive that way. Not
    # negated into a "score" that invites a descending sort.
    assert ranks == sorted(ranks)
    assert all(isinstance(x, float) for x in ranks)
    assert r.subject == "session"


@pytest.mark.asyncio
async def test_search_has_no_sql_and_no_total(db):
    """search goes through the memory package's FTS seam (dialect SQL lives
    there), and counting every match to report a total is a second expensive
    query nobody asked for."""
    r = await memory("search", "session")
    assert r.sql == ""
    assert r.total == 0


@pytest.mark.asyncio
async def test_search_excerpt_windows_the_match(db):
    """polars shows ~30 chars of a cell: a frame of whole messages would
    print their openings and never the part that matched."""
    r = await memory("search", "elides")
    row = _row(r.df, id=db["long"])
    assert row["excerpt"].startswith("the polars repr elides")
    assert row["excerpt"].endswith("…")
    assert len(row["excerpt"]) < 300 < len(LONG)
    assert row["role"] == "assistant"
    assert row["session_id"] == "beta-two"


@pytest.mark.asyncio
async def test_search_excerpt_falls_back_token_by_token(db):
    """bm25 ANDs tokens, so the whole query is often not a substring."""
    r = await memory("search", "middle polars")
    row = _row(r.df, id=db["long"])
    assert "middle polars" not in row["excerpt"]
    assert "middle" in row["excerpt"]


@pytest.mark.asyncio
async def test_search_sees_reasoning(db):
    r = await memory("search", "pools")
    assert r.rows == 1
    row = r.df.row(0, named=True)
    assert row["id"] == db["reasoned"] and row["role"] == "assistant"
    assert THINKING in row["excerpt"]


@pytest.mark.asyncio
async def test_search_cannot_see_tool_calls_but_sql_can(db):
    """THE INDEX HOLE, pinned from both sides: message_text() is content +
    reasoning, so a call-only assistant message is invisible to bm25 (17,208
    rows, 21% of the live database) while the RESULT it produced is indexed
    normally — and a LIKE scan sees everything, which is the documented
    workaround."""
    assert (await memory("search", "register")).df["id"].to_list() == [db["result"]]
    assert (await memory("search", "setdefault")).rows == 0

    scan = await memory(
        "sql", "select id, role from messages where data like '%setdefault%'"
    )
    assert scan.df["id"].to_list() == [db["call"]]
    assert scan.df["role"].to_list() == ["assistant"]


@pytest.mark.asyncio
async def test_search_scopes_to_a_session(db):
    """Pushed into the WHERE, not filtered after the LIMIT: the old path
    returned the intersection of "best 20 globally" with "in this session",
    which for a common term is usually empty."""
    inside = await memory("search", "session", session_id="alpha-one")
    assert inside.rows == 2
    assert inside.subject == "session in alpha-one"
    assert inside.df["session_id"].unique().to_list() == ["alpha-one"]

    outside = await memory("search", "session", session_id="beta-two")
    assert outside.rows == 0
    assert outside.df.columns == SEARCH_COLS  # an empty frame keeps its shape
    assert outside.subject == "session in beta-two"


@pytest.mark.asyncio
async def test_search_roles_are_pushed_down(db):
    r = await memory("search", "session", roles=("user",))
    assert r.df["id"].to_list() == [db["compact"]]
    assert r.df["role"].to_list() == ["user"]


@pytest.mark.asyncio
async def test_search_include_forks(db):
    assert (await memory("search", "zebras")).rows == 0
    r = await memory("search", "zebras", include_forks=True)
    assert r.rows == 1
    row = r.df.row(0, named=True)
    assert (row["id"], row["fork_idx"], row["agent_idx"]) == (db["fork"], 2, 1)


@pytest.mark.asyncio
async def test_search_limit_is_the_number_of_matches(db):
    r = await memory("search", "the", limit=2)
    assert r.rows == 2


# --- sql -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sql_runs_the_statement_verbatim(db):
    stmt = "select role, count(*) n from messages group by role order by role"
    r = await memory("sql", stmt)
    assert r.subject == stmt and r.sql == stmt
    assert r.df.columns == ["role", "n"]
    assert dict(zip(r.df["role"], r.df["n"])) == {
        "assistant": 4,
        "system": 1,
        "tool": 1,
        "user": 4,
    }
    assert r.total == 0  # nothing to count: the statement is the whole answer


@pytest.mark.asyncio
async def test_sql_json_column_is_text_and_path_matchable(db):
    """Raw SQL bypasses the ORM's JSON type, so sqlite hands back text —
    which polars can search, and json_path_match can address."""
    r = await memory("sql", "select id, data from messages order by id")
    assert isinstance(r.df["data"][0], str)
    matched = r.df.with_columns(
        pl.col("data").str.json_path_match("$.role").alias("role")
    )
    assert matched["role"].to_list() == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
        "assistant",
        "user",
        "user",
        "assistant",
    ]
    assert json.loads(r.df["data"][db["call"] - 1])["tool_calls"] == TOOL_CALLS


@pytest.mark.asyncio
async def test_sql_write_is_refused_by_the_connection(db):
    """Read-only at the OS level (sqlite's mode=ro), not by inspection of the
    statement — so this is the database refusing, and the message says so."""
    with pytest.raises(MemoryToolError, match="readonly"):
        await memory(
            "sql",
            "insert into prompts(id, name, template, created_at)"
            " values ('p', 'n', 't', 'now')",
        )
    for stmt in (
        "update messages set role = 'user'",
        "delete from messages",
        "drop table messages",
    ):
        with pytest.raises(MemoryToolError, match="readonly"):
            await memory("sql", stmt)


@pytest.mark.asyncio
async def test_sql_syntax_error_names_the_problem(db):
    """SQLAlchemy renders the statement, the parameters and a link to its own
    docs under the actual complaint; the model wrote the statement, it wants
    the complaint."""
    with pytest.raises(MemoryToolError) as exc:
        await memory("sql", "selct 1")
    assert 'near "selct": syntax error' in str(exc.value)
    assert "\n" not in str(exc.value)


@pytest.mark.asyncio
async def test_sql_bind_error_comes_from_the_database_not_sqlalchemy(db):
    """The mode's contract is verbatim, so it goes through exec_driver_sql
    with no bindparam parser in front of it: text() would blame SQLAlchemy
    ("A value is required for bind parameter 'role'") for a statement the
    database is perfectly capable of complaining about itself."""
    with pytest.raises(MemoryToolError) as exc:
        await memory("sql", "select * from messages where role = :role")
    assert "Incorrect number of bindings supplied" in str(exc.value)
    assert "bind parameter" not in str(exc.value)


@pytest.mark.asyncio
async def test_sql_a_string_literal_with_a_colon_is_not_a_parameter(db):
    r = await memory("sql", "select count(*) n from messages where data like '%a:b%'")
    assert r.df["n"].to_list() == [0]


@pytest.mark.asyncio
async def test_sql_empty_result_keeps_its_columns(db):
    r = await memory("sql", "select id, role from messages where id = -1")
    assert r.rows == 0
    assert r.df.columns == ["id", "role"]


@pytest.mark.asyncio
async def test_sql_missing_table_names_it(db):
    with pytest.raises(MemoryToolError, match="no such table: nosuchtable"):
        await memory("sql", "select * from nosuchtable")


@pytest.mark.asyncio
async def test_sql_rejects_the_other_modes_arguments(db):
    """Each of these would be an argument quietly ignored — write it into the
    statement instead, where it is visible."""
    stmt = "select 1"
    for kwargs in (
        {"session_id": "alpha-one"},
        {"roles": ("user",)},
        {"limit": 5},
        {"include_forks": True},
    ):
        with pytest.raises(MemoryToolError, match="write it into the statement"):
            await memory("sql", stmt, **kwargs)


@pytest.mark.asyncio
async def test_sql_requires_a_target(db):
    with pytest.raises(MemoryToolError, match="requires target="):
        await memory("sql")
    with pytest.raises(MemoryToolError, match="requires target="):
        await memory("sql", "   ")


@pytest.mark.asyncio
async def test_subject_is_truncated_in_the_acp_payload_only(db):
    stmt = "select '" + "x" * 300 + "' as s"
    r = await memory("sql", stmt)
    assert r.subject == stmt  # the Python object keeps the truth
    assert len(r.acp_payload()["subject"]) == 100
    assert r.acp_payload()["content"] == "text"
    assert r.acp_payload()["text"] == r.text


# --- guards ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_mode_raises(db):
    with pytest.raises(MemoryToolError, match="unknown memory mode 'lst'"):
        await memory("lst")
    with pytest.raises(MemoryToolError, match="list, search, sql"):
        await memory("conversation")


@pytest.mark.asyncio
async def test_list_takes_no_target(db):
    with pytest.raises(MemoryToolError, match="takes no target="):
        await memory("list", "alpha-one")


@pytest.mark.asyncio
async def test_search_requires_a_target(db):
    with pytest.raises(MemoryToolError, match="requires target="):
        await memory("search")
    with pytest.raises(MemoryToolError, match="requires target="):
        await memory("search", "  ")


@pytest.mark.asyncio
async def test_unknown_role_raises(db):
    with pytest.raises(MemoryToolError, match="unknown role 'human'"):
        await memory("list", session_id="alpha-one", roles=("human",))


@pytest.mark.asyncio
async def test_roles_on_a_sessions_list_raises(db):
    """A sessions list has no role column: accepting roles= would be an
    argument the caller cared about, quietly dropped."""
    with pytest.raises(MemoryToolError, match="filters MESSAGES"):
        await memory("list", roles=("user",))


@pytest.mark.asyncio
async def test_absurd_limits_raise(db):
    with pytest.raises(MemoryToolError, match="limit must be >= 0"):
        await memory("list", limit=-1)
    with pytest.raises(MemoryToolError, match="limit must be <= 10000"):
        await memory("list", limit=99_999)


# --- the cap ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_byte_cap_truncates_and_says_so(db, monkeypatch):
    """Iterated, not fetchall()'d: breaking out of the loop stops sqlite
    stepping the query, so 499MB of message JSON never has to fit in the
    kernel to be refused."""
    monkeypatch.setattr(MOD, "_MEMORY_BYTES", 400)
    r = await memory("sql", "select id, data from messages order by id")
    assert r.truncated is True
    assert 0 < r.rows < 10
    assert "TRUNCATED" in r.text
    assert "prefix of the answer" in r.text


@pytest.mark.asyncio
async def test_the_first_row_survives_the_cap(db, monkeypatch):
    """One 12.8MB message (the live db's largest) must make a frame with one
    row in it, not an empty one that reads as "no matches"."""
    monkeypatch.setattr(MOD, "_MEMORY_BYTES", 1)
    r = await memory("sql", "select id, data from messages order by id")
    assert r.rows == 1 and r.truncated is True
    assert r.df["id"].to_list() == [db["system"]]


@pytest.mark.asyncio
async def test_an_uncapped_query_is_not_truncated(db):
    r = await memory("sql", "select id, data from messages")
    assert r.truncated is False and r.rows == 10


# --- the rail and the engine ----------------------------------------------


@pytest.mark.asyncio
async def test_no_rail_raises_naming_begin_cell(db):
    """The kernel reads NO config: the database arrives on the identity rail
    execute's prologue sets, and without it the tool says how to set one."""
    clear()
    with pytest.raises(MemoryToolError, match="begin_cell"):
        await memory("list")


@pytest.mark.asyncio
async def test_a_missing_database_names_its_path(db, tmp_path):
    """mode=ro cannot CREATE, so sqlite's own complaint is "unable to open
    database file" — true, and useless."""
    missing = tmp_path / "never-existed.db"
    begin_cell(session_id="s", parent_tool_call_id="t/c", db_uri=f"sqlite:///{missing}")
    with pytest.raises(MemoryToolError) as exc:
        await memory("list")
    assert str(missing) in str(exc.value)
    assert "nothing has been remembered yet" in str(exc.value)


@pytest.mark.asyncio
async def test_the_engine_is_cached(db):
    assert MOD._engine() is MOD._engine()
    assert MOD._state["uri"] == db.uri


@pytest.mark.asyncio
async def test_the_engine_is_rebuilt_when_the_uri_changes(db):
    first = MOD._engine()
    begin_cell(session_id="s", parent_tool_call_id="t/c", db_uri=db.other)
    second = MOD._engine()
    assert second is not first
    r = await memory("list")
    assert r.rows == 0 and r.total == 0


@pytest.mark.asyncio
async def test_reload_keeps_the_cached_engine(db):
    """importlib.reload re-executes the source in the EXISTING module dict,
    so a module-level `_engine = None` would drop the handle on every
    reload() and leak its pool — fds on sqlite, a server session each on
    postgres. globals().setdefault is the fix, and this is what pins it."""
    before = MOD._engine()
    importlib.reload(MOD)
    assert MOD._state["uri"] == db.uri
    assert MOD._engine() is before
    r = await MOD.memory("list")
    assert r.rows == 3


# --- register + write-through ---------------------------------------------


@pytest.mark.asyncio
async def test_a_call_records_one_row(db):
    r = await memory("search", "kernel")
    entries = pending()
    assert len(entries) == 1
    e = entries[0]
    assert (e.tool, e.mode, e.status) == ("memory", "search", "completed")
    assert e.args["target"] == "kernel" and e.args["mode"] == "search"
    assert e.result_kind == "memory"
    assert e.llm_images == []  # rows are never pictures
    assert e.acp_payload == {
        "content": "text",
        "text": r.text,
        "subject": "kernel",
    }
    assert (e.session_id, e.parent_tool_call_id) == (
        "s-under-test",
        current_cell().parent_tool_call_id,
    )


@pytest.mark.asyncio
async def test_the_row_is_written_through(db):
    """The table is the queue: rows land at call time and survive a wedged
    kernel, keyed by the parent tool-call id the model cannot forge."""
    await memory("list", session_id="alpha-one", limit=2)
    rows = _written()
    assert len(rows) == 1
    row = rows[0]
    assert (row.tool, row.mode, row.status) == ("memory", "list", "completed")
    assert row.result_kind == "memory"
    assert row.emitted == 0
    assert row.acp_payload["subject"] == "alpha-one"
    assert "2 row(s) of 7 matching" in row.acp_payload["text"]
    assert row.args["limit"] == 2


@pytest.mark.asyncio
async def test_a_failed_call_records_the_failure(db):
    """A cell that died halfway still made real calls, and the client
    deserves to see the one that failed. Zero hits is NOT a failure — an
    empty frame is an answer."""
    await memory("search", "nonexistent-token-xyz")
    assert pending()[0].status == "completed"

    with pytest.raises(MemoryToolError):
        await memory("list", session_id="no-such-session")
    entries = pending()
    assert len(entries) == 2
    e = entries[-1]
    assert (e.status, e.result_kind) == ("failed", "error")
    assert e.acp_payload is None and e.llm_images == []
    assert e.error.startswith("MemoryToolError: no session")
    rows = _written()
    assert len(rows) == 2
    failed = [r for r in rows if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].mode == "list" and failed[0].acp_payload is None
    assert failed[0].error.startswith("MemoryToolError:")


# --- internals -------------------------------------------------------------


def test_compact_trims_stamps_and_nothing_else():
    """Noise reduction: a full stamp spends its column's width on microseconds
    and an offset nobody can use. The height that saves depends on the width
    budget and on whether the stamp is the tallest cell in its row, so what is
    pinned here is the trim itself, the losslessness of .df, and that a frame
    with no stamp column comes back untouched."""
    df = pl.DataFrame(
        {
            "id": [1, 2],
            "created_at": [
                "2026-09-06T10:17:44.233789+00:00",
                "2026-09-06T10:17:45.000001+00:00",
            ],
            "text": ["a", "b"],
        }
    )
    out = _compact(df)
    assert out["created_at"].to_list() == [
        "2026-09-06T10:17:44",
        "2026-09-06T10:17:45",
    ]
    assert df["created_at"][0].endswith("+00:00")  # the artifact is lossless
    assert (out.columns, out.height) == (df.columns, df.height)

    plain = pl.DataFrame({"role": ["user"], "n": [1]})
    assert _compact(plain) is plain


def test_cell_json_encodes_non_scalars():
    """Why the JSON column exists, on the two shapes a real messages table
    has: content is a str in a user row and a list of blocks in an assistant
    one (polars infers the field type from the first row and RAISES on the
    second), and a row with a key the first row lacked does not raise at all —
    the key is silently DROPPED from the inferred Struct."""
    user = {"role": "user", "content": "hi"}
    assistant = {"role": "assistant", "content": [{"type": "text", "text": "yo"}]}
    with pytest.raises(TypeError):
        pl.DataFrame({"data": [user, assistant]})

    called = {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]}
    lost = pl.DataFrame({"data": [user, called]})
    assert "tool_calls" not in lost["data"].to_list()[1]

    # The encoding builds every time and loses nothing.
    encoded = [_cell(v) for v in [assistant, called, "plain", None]]
    assert encoded[0] == json.dumps(assistant, ensure_ascii=False)
    assert json.loads(encoded[1])["tool_calls"] == [{"id": "c1"}]
    assert encoded[2:] == ["plain", None]
    assert pl.DataFrame({"v": encoded})["v"].to_list() == encoded
    # Scalars pass through, so a column of ints stays a column of ints.
    assert _cell(3) == 3 and _cell(True) is True


def test_excerpt_windows_and_falls_back():
    body = "x" * 500 + " NEEDLE " + "y" * 500
    out = _excerpt(body, "needle")
    assert "NEEDLE" in out and out.startswith("…") and out.endswith("…")
    assert len(out) <= 2 * MOD._EXCERPT + len(" NEEDLE ") + 2
    # No token in the text at all: the head, so the cell is never blank.
    head = _excerpt("a" * 900, "zzz")
    assert head == "a" * 400 + "…"
    assert _excerpt("short", "zzz") == "short"
