"""v1 ``session/load`` replay: persisted history -> ``session/update`` wire.

The point of these is fidelity to the LIVE emitters in
:mod:`crow_cli.agent.tools`. A replayed card that renders differently from the
same call watched live is a bug the client cannot work around, so the shapes
are asserted field by field rather than "something arrived".
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from crow_cli.agent.replay import replay
from crow_cli.memory import create_database, get_engine, subtool_calls_by_parent
from crow_cli.memory.models import SubtoolCall


class FakeConn:
    """Records every ``session_update`` in wire order."""

    def __init__(self) -> None:
        self.updates: list[Any] = []
        self.sessions: list[str] = []

    async def session_update(self, session_id: str, update: Any) -> None:
        self.sessions.append(session_id)
        self.updates.append(update)

    def kinds(self) -> list[str]:
        return [u.session_update for u in self.updates]

    def of(self, kind: str) -> list[Any]:
        return [u for u in self.updates if u.session_update == kind]

    def texts(self, kind: str) -> list[str]:
        return [u.content.text for u in self.of(kind)]


def call(name: str, args: dict, call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def tool_result(text: str, call_id: str = "call_1") -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": text}


async def test_a_user_turn_replays_as_user_message_chunks():
    conn = FakeConn()
    sent = await replay(conn, "s1", [{"role": "user", "content": "hello there"}])

    assert sent == 1
    assert conn.kinds() == ["user_message_chunk"]
    assert conn.texts("user_message_chunk") == ["hello there"]
    assert conn.sessions == ["s1"]


async def test_system_messages_are_not_transcript():
    conn = FakeConn()
    sent = await replay(
        conn,
        "s1",
        [{"role": "system", "content": "you are crow"}, {"role": "user", "content": "hi"}],
    )

    assert sent == 1
    assert conn.kinds() == ["user_message_chunk"]


async def test_an_assistant_turn_replays_thought_then_text():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "assistant",
                "reasoning_content": "  let me look  ",
                "content": "the answer",
            }
        ],
    )

    assert conn.kinds() == ["agent_thought_chunk", "agent_message_chunk"]
    # the persisted reasoning is one blob; it replays trimmed, not re-split
    assert conn.texts("agent_thought_chunk") == ["let me look"]
    assert conn.texts("agent_message_chunk") == ["the answer"]


async def test_a_blank_reasoning_blob_emits_nothing():
    conn = FakeConn()
    await replay(conn, "s1", [{"role": "assistant", "reasoning_content": "   ", "content": "x"}])

    assert conn.kinds() == ["agent_message_chunk"]


async def test_a_finished_tool_call_replays_as_start_then_one_update():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [call("search", {"pattern": "replay"})],
            },
            tool_result("3 hits"),
        ],
    )

    assert conn.kinds() == ["tool_call", "tool_call_update"]
    start, update = conn.updates
    # the id is minted, never the live <turn_id>/<llm id> — the turn id is gone
    assert start.tool_call_id == "replay/0/call_1"
    assert update.tool_call_id == start.tool_call_id
    assert start.title == "search"
    assert start.name == "search"
    assert start.kind == "search"
    assert start.status == "pending"
    # no in_progress theatre: the call is finished, so it ends where it lands
    assert update.status == "completed"
    assert update.content[0].type == "content"
    assert update.content[0].content.text == "3 hits"


async def test_edit_replays_its_real_diff_because_the_arguments_survived():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    call(
                        "edit",
                        {
                            "file_path": "/app/x.py",
                            "old_string": "before",
                            "new_string": "after",
                        }
                    )
                ],
            },
            tool_result("Edited /app/x.py"),
        ],
    )

    start, update = conn.updates
    assert start.title == "edit: /app/x.py"
    assert start.name == "edit"
    assert start.kind == "edit"
    assert [loc.path for loc in start.locations] == ["/app/x.py"]
    # exactly what the live emitter sends, so the client's diff viewer works
    assert start.raw_input == {"path": "/app/x.py", "content": "after"}
    diff = update.content[0]
    assert diff.type == "diff"
    assert (diff.path, diff.old_text, diff.new_text) == ("/app/x.py", "before", "after")


async def test_write_replays_a_new_file_diff_with_no_old_text():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [call("write", {"file_path": "/app/new.py", "content": "print(1)"})],
            },
            tool_result("Successfully wrote to /app/new.py"),
        ],
    )

    start, update = conn.updates
    assert start.title == "write: /app/new.py"
    assert start.name == "write"
    diff = update.content[0]
    assert diff.type == "diff"
    assert diff.new_text == "print(1)"
    assert diff.old_text is None


async def test_write_re_serialises_content_that_was_decoded_into_a_dict():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        # maximal_deserialize can hand back a dict, not a string
                        "function": {
                            "name": "write",
                            "arguments": {"file_path": "/app/c.json", "content": {"a": 1}},
                        },
                    }
                ],
            },
            tool_result("Successfully wrote to /app/c.json"),
        ],
    )

    diff = conn.updates[1].content[0]
    assert json.loads(diff.new_text) == {"a": 1}


async def test_execute_replays_the_fenced_cell_above_its_output():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [call("execute", {"code": "print(1)"})],
            },
            tool_result("1"),
        ],
    )

    start, update = conn.updates
    assert (start.title, start.name, start.kind) == ("execute", "execute", "execute")
    assert start.content[0].content.text == "```python\nprint(1)\n```"
    # the completion re-includes the code block: the client merges update
    # content over start content, so dropping it would erase the cell
    assert [c.content.text for c in update.content] == ["```python\nprint(1)\n```", "1"]


async def test_read_replays_the_file_content_it_returned():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [call("read", {"file_path": "/app/x.py"})],
            },
            tool_result("1  print(1)"),
        ],
    )

    start, update = conn.updates
    assert start.title == "read: /app/x.py"
    assert start.kind == "read"
    assert start.raw_input == {"path": "/app/x.py"}
    assert update.content[0].content.text == "1  print(1)"


async def test_terminal_replays_under_its_command():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [call("terminal", {"command": "ls -la"})],
            },
            tool_result("total 0"),
        ],
    )

    start = conn.updates[0]
    assert start.title == "ls -la"
    assert start.name == "terminal"
    assert start.kind == "execute"


async def test_a_call_the_turn_never_answered_replays_as_cancelled():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [{"role": "assistant", "content": "", "tool_calls": [call("search", {"pattern": "x"})]}],
    )

    start, update = conn.updates
    assert start.status == "pending"
    # v1 has no "cancelled" status; an interrupted call must still land on a
    # terminal one or the client spins on it forever
    assert update.status == "failed"
    assert update.content is None


async def test_answers_match_their_calls_by_id_within_the_run():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    call("search", {"pattern": "a"}, call_id="call_a"),
                    call("read", {"file_path": "/b"}, call_id="call_b"),
                ],
            },
            # persisted out of order — the id is what ties an answer to a call
            tool_result("B CONTENT", call_id="call_b"),
            tool_result("A HITS", call_id="call_a"),
        ],
    )

    starts = conn.of("tool_call")
    updates = conn.of("tool_call_update")
    # seq is the notification index, so a two-notification call advances it by 2
    assert [s.tool_call_id for s in starts] == ["replay/0/call_a", "replay/2/call_b"]
    by_id = {u.tool_call_id: u for u in updates}
    assert by_id["replay/0/call_a"].content[0].content.text == "A HITS"
    assert by_id["replay/2/call_b"].content[0].content.text == "B CONTENT"


async def test_an_orphaned_answer_still_replays_as_a_call_of_its_own():
    conn = FakeConn()
    sent = await replay(conn, "s1", [tool_result("stray output", call_id="call_z")])

    assert sent == 2  # start + final update
    start, update = conn.updates
    assert start.tool_call_id == "replay/0/call_z"
    assert update.status == "completed"
    assert update.content[0].content.text == "stray output"


async def test_a_malformed_arguments_payload_replays_as_no_args():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "type": "function",
                     "function": {"name": "search", "arguments": "{not json"}}
                ],
            },
            tool_result("ok"),
        ],
    )

    assert conn.of("tool_call")[0].title == "search"
    assert conn.of("tool_call_update")[0].status == "completed"


async def test_an_attachment_replays_as_an_image_block():
    conn = FakeConn()
    await replay(
        conn,
        "s1",
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is this"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}},
                ],
            }
        ],
    )

    chunks = conn.of("user_message_chunk")
    assert [c.content.type for c in chunks] == ["text", "image"]
    assert chunks[1].content.mime_type == "image/png"
    assert chunks[1].content.data == "aGVsbG8="


async def test_two_replays_of_one_history_mint_the_same_ids():
    history = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "", "tool_calls": [call("search", {"pattern": "q"})]},
        tool_result("hits"),
        {"role": "assistant", "content": "a"},
    ]
    first, second = FakeConn(), FakeConn()
    await replay(first, "s1", history)
    await replay(second, "s1", history)

    ids = lambda c: [u.tool_call_id for u in c.of("tool_call")]
    assert ids(first) == ids(second)
    assert first.kinds() == second.kinds()


async def test_a_whole_conversation_replays_in_order():
    conn = FakeConn()
    sent = await replay(
        conn,
        "s1",
        [
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": "alpha"},
            {"role": "assistant", "content": "", "tool_calls": [call("read", {"file_path": "/f"})]},
            tool_result("file body"),
            {"role": "assistant", "content": "beta"},
            {"role": "user", "content": "gamma"},
            {"role": "assistant", "content": "delta"},
        ],
    )

    assert conn.kinds() == [
        "user_message_chunk",
        "tool_call",
        "tool_call_update",
        "agent_message_chunk",
        "user_message_chunk",
        "agent_message_chunk",
    ]
    # one counted update per notification actually sent
    assert sent == len(conn.updates)


# ---- calls made INSIDE an execute cell ----
#
# crow does most of its file work in cells, so this is the half of replay that
# decides whether a reopened thread still shows its diffs.


@dataclass
class Row:
    """A ``subtool_calls`` row.

    The real one is ORM and replay only reads attributes off it, so a
    dataclass with the same field names is the honest double — and a field
    named wrong here fails a test instead of silently rendering an empty card.
    """

    id: int
    tool: str
    result_kind: str = "text"
    mode: str | None = None
    args: dict = field(default_factory=dict)
    status: str = "completed"
    acp_payload: dict | None = None
    llm_images: list = field(default_factory=list)
    error: str | None = None


class FakeStore:
    """An ImageStore: ``get(key) -> bytes | None``, and a call log."""

    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.asked: list[str] = []

    def get(self, key: str):
        self.asked.append(key)
        return self.blobs.get(key)


class FakeLog:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str, *args) -> None:
        self.warnings.append(msg % args if args else msg)

    def info(self, msg: str, *args) -> None:
        pass


EXEC_ID = "call_00_VOERVqhdTHwtqW1abTBI1514"


def cell_history(code: str = "r = await write('/f', 'x')", call_id: str = EXEC_ID) -> list[dict]:
    """One user turn, one execute call, its answer, one closing assistant."""
    return [
        {"role": "user", "content": "do it"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [call("execute", {"code": code}, call_id)],
        },
        tool_result("wrote /f", call_id),
        {"role": "assistant", "content": "done"},
    ]


def write_row(row_id: int = 7037, path: str = "/f", new: str = "x", old: str = "") -> Row:
    """The row the register writes for an in-cell ``write`` — payload shape
    copied from a real one (subtool_calls id 7037)."""
    return Row(
        id=row_id,
        tool="write",
        result_kind="diff",
        args={"file_path": path, "content": new},
        acp_payload={"content": "diff", "path": path, "old_text": old, "new_text": new},
    )


async def test_an_in_cell_write_replays_as_its_own_diff_call():
    conn = FakeConn()
    sent = await replay(
        conn, "s1", cell_history(), subtools={EXEC_ID: [write_row()]}
    )

    # between the parent's start and the parent's ending, as live
    assert conn.kinds() == [
        "user_message_chunk",
        "tool_call",
        "tool_call",
        "tool_call_update",
        "tool_call_update",
        "agent_message_chunk",
    ]
    assert sent == len(conn.updates) == 6

    parent, sub = conn.of("tool_call")
    assert parent.tool_call_id == f"replay/1/{EXEC_ID}"
    assert parent.name == "execute"
    assert sub.tool_call_id == "replay/2/call_sub7037"
    assert sub.name == "write"
    assert sub.title == "write: /f"
    assert sub.kind == "edit"
    assert sub.status == "pending"
    assert [loc.path for loc in sub.locations] == ["/f"]
    # the args the CODE passed, which is the only record of the call there is
    assert sub.raw_input == {"file_path": "/f", "content": "x"}

    sub_end, parent_end = conn.of("tool_call_update")
    assert sub_end.tool_call_id == "replay/2/call_sub7037"
    assert sub_end.status == "completed"
    diff = sub_end.content[0]
    assert diff.type == "diff"
    assert (diff.path, diff.new_text, diff.old_text) == ("/f", "x", "")
    # the parent still ends with its own cell + output
    assert parent_end.tool_call_id == f"replay/1/{EXEC_ID}"
    assert [c.type for c in parent_end.content] == ["content", "content"]


async def test_in_cell_calls_replay_in_row_order_each_with_its_own_id():
    conn = FakeConn()
    rows = [write_row(10, "/a", "one"), write_row(11, "/b", "two")]
    sent = await replay(conn, "s1", cell_history(), subtools={EXEC_ID: rows})

    subs = [u for u in conn.of("tool_call") if "call_sub" in u.tool_call_id]
    assert [s.tool_call_id for s in subs] == [
        "replay/2/call_sub10",
        "replay/4/call_sub11",
    ]
    assert [s.title for s in subs] == ["write: /a", "write: /b"]
    # 1 user + 2 parent + 4 in-cell + 1 assistant
    assert sent == len(conn.updates) == 8


async def test_a_read_row_carries_the_text_the_cell_read():
    conn = FakeConn()
    row = Row(
        id=5,
        tool="fs",
        mode="read",
        result_kind="read",
        args={"mode": "read", "path": "/f"},
        acp_payload={"content": "read", "path": "/f", "text": "file body"},
    )
    await replay(conn, "s1", cell_history(), subtools={EXEC_ID: [row]})

    sub = conn.of("tool_call")[1]
    assert sub.title == "fs/read: /f"
    assert sub.kind == "read"
    assert [loc.path for loc in sub.locations] == ["/f"]
    end = conn.of("tool_call_update")[0]
    assert end.content[0].content.text == "file body"


async def test_kind_follows_the_artifact_not_the_tool_name():
    """``get_tool_kind("sql")`` is "other"; the artifact is rows read out of a
    read-only connection, which is why the live drain consults a table first
    and replay consults the SAME table."""
    conn = FakeConn()
    row = Row(
        id=6,
        tool="memory",
        mode="sql",
        result_kind="memory",
        acp_payload={"text": "3 rows"},
    )
    await replay(conn, "s1", cell_history(), subtools={EXEC_ID: [row]})

    assert conn.of("tool_call")[1].kind == "read"
    assert conn.of("tool_call")[1].title == "memory/sql"


async def test_a_subject_rides_the_title_and_never_a_location():
    conn = FakeConn()
    row = Row(
        id=7,
        tool="web",
        mode="fetch",
        result_kind="web",
        acp_payload={"text": "the page", "subject": "https://crow-ai.dev"},
    )
    await replay(conn, "s1", cell_history(), subtools={EXEC_ID: [row]})

    sub = conn.of("tool_call")[1]
    assert sub.title == "web/fetch: https://crow-ai.dev"
    assert sub.kind == "fetch"
    assert sub.locations is None
    assert conn.of("tool_call_update")[0].content[0].content.text == "the page"


async def test_a_failed_row_replays_failed_with_its_error_as_the_content():
    conn = FakeConn()
    row = Row(
        id=8,
        tool="edit",
        result_kind="error",
        status="failed",
        error="EditError: old_string not found in file",
    )
    await replay(conn, "s1", cell_history(), subtools={EXEC_ID: [row]})

    assert conn.of("tool_call")[1].title == "edit"
    end = conn.of("tool_call_update")[0]
    assert end.status == "failed"
    assert end.content[0].content.text == "edit failed: EditError: old_string not found in file"


async def test_an_image_row_hydrates_through_the_store():
    conn = FakeConn()
    store = FakeStore({"k1": b"hello"})
    row = Row(
        id=9,
        tool="vision",
        result_kind="image",
        llm_images=[{"key": "k1", "mime": "image/png"}],
    )
    await replay(
        conn,
        "s1",
        cell_history(),
        subtools={EXEC_ID: [row]},
        resolve_store=lambda: store,
    )

    assert store.asked == ["k1"]
    block = conn.of("tool_call_update")[0].content[0].content
    assert block.type == "image"
    assert block.mime_type == "image/png"
    assert block.data == base64.b64encode(b"hello").decode()


async def test_the_store_is_probed_only_when_a_row_carries_images():
    """An S3 probe bought for a transcript with no images in it is a round
    trip for nothing, so the thunk is the contract, not a nicety."""
    probes: list[int] = []

    def resolve():
        probes.append(1)
        return FakeStore({})

    await replay(
        FakeConn(),
        "s1",
        cell_history(),
        subtools={EXEC_ID: [write_row()]},
        resolve_store=resolve,
    )
    assert probes == []

    rows = [
        Row(id=1, tool="vision", result_kind="image", llm_images=[{"key": "a"}]),
        Row(id=2, tool="vision", result_kind="image", llm_images=[{"key": "b"}]),
    ]
    await replay(
        FakeConn(),
        "s1",
        cell_history(),
        subtools={EXEC_ID: rows},
        resolve_store=resolve,
    )
    # once for the whole replay, not once per row
    assert probes == [1]


async def test_a_missing_blob_warns_and_still_emits_the_call():
    conn = FakeConn()
    log = FakeLog()
    row = Row(
        id=9,
        tool="vision",
        result_kind="image",
        llm_images=[{"key": "gone"}],
    )
    await replay(
        conn,
        "s1",
        cell_history(),
        log=log,
        subtools={EXEC_ID: [row]},
        resolve_store=lambda: FakeStore({}),
    )

    assert log.warnings == ["replay: image blob missing: gone"]
    assert conn.of("tool_call_update")[0].status == "completed"
    assert conn.of("tool_call_update")[0].content is None


async def test_image_rows_without_a_store_say_so_rather_than_rendering_nothing_silently():
    conn = FakeConn()
    log = FakeLog()
    row = Row(id=9, tool="vision", result_kind="image", llm_images=[{"key": "k"}])
    await replay(conn, "s1", cell_history(), log=log, subtools={EXEC_ID: [row]})

    assert log.warnings == [
        "replay: subtool row 9 carries 1 image ref(s) but no image store was supplied"
    ]
    assert len(conn.of("tool_call")) == 2


async def test_rows_keyed_on_another_call_do_not_leak_into_this_one():
    conn = FakeConn()
    sent = await replay(
        conn, "s1", cell_history(), subtools={"call_some_other_turn": [write_row()]}
    )

    assert conn.kinds() == [
        "user_message_chunk",
        "tool_call",
        "tool_call_update",
        "agent_message_chunk",
    ]
    assert sent == 4


async def test_an_orphaned_answer_still_replays_the_calls_its_cell_made():
    """The assistant message carrying the call was never written, but the cell
    ran and the register recorded what it touched — that is the part the user
    cares about, and it is keyed on the answer's own id."""
    conn = FakeConn()
    history = [
        {"role": "user", "content": "do it"},
        tool_result("wrote /f", EXEC_ID),
    ]
    await replay(conn, "s1", history, subtools={EXEC_ID: [write_row()]})

    assert conn.kinds() == [
        "user_message_chunk",
        "tool_call",
        "tool_call",
        "tool_call_update",
        "tool_call_update",
    ]
    assert conn.of("tool_call")[1].tool_call_id == "replay/2/call_sub7037"


async def test_two_replays_mint_the_same_in_cell_ids():
    history = cell_history()
    subtools = {EXEC_ID: [write_row(10), write_row(11)]}
    first, second = FakeConn(), FakeConn()
    await replay(first, "s1", history, subtools=subtools)
    await replay(second, "s1", history, subtools=subtools)

    ids = lambda c: [u.tool_call_id for u in c.updates if hasattr(u, "tool_call_id")]
    assert ids(first) == ids(second)
    assert "replay/2/call_sub10" in ids(first)


# ---- the reader that supplies the mapping ----


@pytest.fixture
def register_db(tmp_path):
    """A real sqlite db with real register rows, written the way the kernel's
    write-through writes them: ``parent_tool_call_id`` is TurnCtx.tcid's
    ``<turn_id>/<llm id>``, and the message history carries only the bare id.
    """
    db = f"sqlite:///{tmp_path / 'register.db'}"
    create_database(db)
    engine = get_engine(db)
    with engine.begin() as conn:
        for row in (
            # two calls in one cell, ids out of insertion order on purpose
            dict(id=21, session_id="s1", parent_tool_call_id="turn-1/call_A",
                 tool="edit", result_kind="diff", status="completed", emitted=1),
            dict(id=20, session_id="s1", parent_tool_call_id="turn-1/call_A",
                 tool="write", result_kind="diff", status="completed", emitted=1),
            dict(id=22, session_id="s1", parent_tool_call_id="turn-2/call_B",
                 tool="fs", mode="read", result_kind="read", status="completed", emitted=0),
            # no parent: a row nobody can attribute, skipped not crashed on
            dict(id=23, session_id="s1", parent_tool_call_id=None,
                 tool="write", result_kind="diff", status="completed", emitted=0),
            dict(id=24, session_id="other", parent_tool_call_id="turn-9/call_A",
                 tool="write", result_kind="diff", status="completed", emitted=0),
        ):
            conn.execute(SubtoolCall.__table__.insert().values(args={}, **row))
    engine.dispose()
    return db


def test_the_reader_groups_on_the_persisted_llm_id(register_db):
    engine = get_engine(register_db)
    try:
        grouped = subtool_calls_by_parent(engine, "s1")
        assert set(grouped) == {"call_A", "call_B"}
        # id order, which is the order the cell made the calls in
        assert [r.id for r in grouped["call_A"]] == [20, 21]
        assert [r.tool for r in grouped["call_A"]] == ["write", "edit"]
        assert [r.id for r in grouped["call_B"]] == [22]
        # a fork's wire id is its agent_id, and the rows carry the trunk's
        # bare session id — both have to resolve to the same grouping
        assert set(subtool_calls_by_parent(engine, "s1-2-2")) == {"call_A", "call_B"}
        assert subtool_calls_by_parent(engine, "nope") == {}
    finally:
        engine.dispose()


def test_the_reader_does_not_consume_the_queue(register_db):
    """``emitted`` is the LIVE drain's claim marker. A replay that flipped it
    would delete those calls from every future turn's wire, which is the one
    way this read could do real damage."""
    engine = get_engine(register_db)
    try:
        subtool_calls_by_parent(engine, "s1")
        subtool_calls_by_parent(engine, "s1")
        with engine.connect() as conn:
            rows = conn.execute(
                SubtoolCall.__table__.select().order_by(SubtoolCall.id)
            ).all()
        assert [(r.id, r.emitted) for r in rows] == [
            (20, 1), (21, 1), (22, 0), (23, 0), (24, 0)
        ]
    finally:
        engine.dispose()
