"""v1 ``session/load`` replay: persisted history -> ``session/update`` wire.

The point of these is fidelity to the LIVE emitters in
:mod:`crow_cli.agent.tools`. A replayed card that renders differently from the
same call watched live is a bug the client cannot work around, so the shapes
are asserted field by field rather than "something arrived".
"""

from __future__ import annotations

import json
from typing import Any

from crow_cli.agent.replay import replay


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
