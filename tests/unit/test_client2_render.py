"""client2's human face: the config->wire tool translation and the renderer.

Both halves are pure enough to test without a child process, and both are
tested against REAL wire models — a renderer pinned against a hand-built stub
passes while the protocol moves underneath it.

The end-to-end dispatch (a real `crow-cli run -a NAME` against a real v2 child)
is tests/integration/test_cli_run_dispatch.py; the driver's own contract is
tests/integration/test_client2_subagent.py.
"""

from __future__ import annotations

import base64
import io
import json
import typing
from types import SimpleNamespace

import pytest
from acp.experimental.v2 import schema as vs
from rich.console import Console

from crow_cli.client2.main import (
    _RENDERS,
    CrowClientV2,
    TerminalClient,
    dump_update,
    texts,
)
from crow_cli.client2.subagent import (
    ChildExited,
    config_to_servers,
    mcp_servers_to_models,
)


# -- config mcpServers MAP -> wire LIST --------------------------------------


def test_a_stdio_server_keeps_its_name_and_gains_a_type():
    """Config keys a server by name and spells the transport `transport`; the
    wire puts the name inside the entry and spells it `type`."""
    out = config_to_servers(
        {"crow-mcp": {"transport": "stdio", "command": "crow-cli", "args": ["mcp"]}}
    )

    assert out == [
        {
            "type": "stdio",
            "name": "crow-mcp",
            "command": "crow-cli",
            "args": ["mcp"],
            "env": [],
        }
    ]


def test_a_stdio_env_mapping_becomes_a_name_value_list():
    out = config_to_servers(
        {"s": {"command": "c", "env": {"TOKEN": "abc", "N": 1}}}
    )

    assert out[0]["env"] == [
        {"name": "TOKEN", "value": "abc"},
        {"name": "N", "value": "1"},
    ]


def test_an_http_server_carries_url_and_headers():
    out = config_to_servers(
        {
            "remote": {
                "transport": "http",
                "url": "https://x.invalid/mcp",
                "headers": {"Authorization": "Bearer t"},
            }
        }
    )

    assert out == [
        {
            "type": "http",
            "name": "remote",
            "url": "https://x.invalid/mcp",
            "headers": [{"name": "Authorization", "value": "Bearer t"}],
        }
    ]


def test_the_transport_is_inferred_when_unwritten():
    """`url` means http, a command means stdio — the global mcpServers key is
    written by hand and nobody wants to spell the obvious."""
    out = config_to_servers(
        {
            "web": {"url": "https://x.invalid/mcp"},
            "local": {"command": "c"},
        }
    )

    assert [e["type"] for e in out] == ["http", "stdio"]


def test_a_type_key_is_accepted_as_well_as_transport():
    out = config_to_servers({"s": {"type": "stdio", "command": "c"}})
    assert out[0]["type"] == "stdio"


def test_sse_is_passed_through_for_the_model_layer_to_rewrite():
    """v2 deleted SseMcpServer; an SSE endpoint IS an HTTP endpoint, so the
    rewrite happens in mcp_servers_to_models, where that rule already lives."""
    out = config_to_servers({"s": {"transport": "sse", "url": "https://x.invalid/sse"}})

    assert out[0]["type"] == "sse"
    models = mcp_servers_to_models(out)
    assert models[0].type == "http"


def test_the_whole_translation_round_trips_into_wire_models():
    """The point of the list: it validates. A shape that only looks right is
    how a session comes up toolless with no error anywhere."""
    out = config_to_servers(
        {
            "crow-mcp": {
                "transport": "stdio",
                "command": "crow-cli",
                "args": ["mcp2"],
                "env": {"A": "b"},
            },
            "remote": {"transport": "http", "url": "https://x.invalid/mcp"},
        }
    )

    models = mcp_servers_to_models(out)

    assert [(m.type, m.name) for m in models] == [
        ("stdio", "crow-mcp"),
        ("http", "remote"),
    ]
    assert models[0].command == "crow-cli"
    assert models[0].args == ["mcp2"]
    assert [(e.name, e.value) for e in models[0].env] == [("A", "b")]


def test_no_servers_is_an_empty_list_not_an_error():
    """Zero tools is a session, not a failure — the client owns supply."""
    assert config_to_servers(None) == []
    assert config_to_servers({}) == []


def test_a_stdio_server_with_no_command_is_refused():
    with pytest.raises(ValueError, match="a stdio server needs a command"):
        config_to_servers({"s": {"transport": "stdio", "args": ["x"]}})


def test_a_url_server_with_no_url_is_refused():
    with pytest.raises(ValueError, match="a http server needs a url"):
        config_to_servers({"s": {"transport": "http"}})


def test_a_non_mapping_entry_is_refused_by_name():
    with pytest.raises(ValueError, match=r"mcpServers\.'s' must be a mapping, not str"):
        config_to_servers({"s": "crow-cli mcp"})


def test_config_order_is_preserved():
    out = config_to_servers({"b": {"command": "b"}, "a": {"command": "a"}})
    assert [e["name"] for e in out] == ["b", "a"]


# -- content -> text ---------------------------------------------------------


def test_texts_handles_nothing_a_string_and_a_block():
    assert texts(None) == ""
    assert texts("hi") == "hi"
    assert texts(vs.TextContentBlock(text="hi")) == "hi"


def test_texts_joins_a_list_which_is_what_a_whole_message_update_carries():
    """Chunks carry ONE block, whole-message updates carry a LIST."""
    blocks = [vs.TextContentBlock(text="a"), vs.TextContentBlock(text="b")]
    assert texts(blocks) == "ab"


def test_a_non_text_block_says_it_was_there():
    """An image is not text, and rendering it as nothing loses the fact."""
    block = vs.ImageContentBlock(data="AAAA", mime_type="image/png")
    assert texts(block) == "<image>"


# -- the wire shape -j emits -------------------------------------------------


def test_dump_update_is_the_notification_a_client_would_have_received():
    update = vs.AgentMessageChunk(
        message_id="m1", content=vs.TextContentBlock(text="hi")
    )

    assert dump_update(update) == {
        "sessionUpdate": "agent_message_chunk",
        "messageId": "m1",
        "content": {"type": "text", "text": "hi"},
    }


def test_dump_update_drops_what_was_never_set():
    """exclude_unset, not exclude_none: a field the agent explicitly set to
    None is a statement, and one it never set is not."""
    assert dump_update(vs.RunningSessionStateUpdate()) == {
        "sessionUpdate": "state_update",
        "state": "running",
    }


# -- the renderer ------------------------------------------------------------


class Harness:
    """A TerminalClient with its two output channels separated.

    Rich output goes to a StringIO (``.text``); everything the client writes
    to the real stdout — base64 PTY bytes via ``sys.stdout.buffer`` and the
    JSONL a ``-j`` run prints — is caught at the file-descriptor level by
    ``capfd`` (``.fd``). Patching ``sys.stdout`` from a fixture does NOT work:
    pytest re-activates its capture for the call phase and silently undoes it.
    """

    def __init__(self, capfd, json_out: bool = False) -> None:
        self.capfd = capfd
        self.rich = io.StringIO()
        self.console = Console(
            file=self.rich, width=200, force_terminal=False, no_color=True
        )
        self.client = TerminalClient(self.console, json_out=json_out)
        self._fd = ""

    def sync(self) -> "Harness":
        self._fd += self.capfd.readouterr().out
        return self

    @property
    def text(self) -> str:
        return self.rich.getvalue()

    @property
    def fd(self) -> str:
        return self.sync()._fd

    @property
    def events(self) -> list[dict]:
        return [json.loads(line) for line in self.fd.splitlines() if line.strip()]


@pytest.fixture
def harness(capfd):
    return Harness(capfd)


@pytest.fixture
def json_harness(capfd):
    return Harness(capfd, json_out=True)


def notif(update, session_id: str = "s1"):
    return vs.UpdateSessionNotification(session_id=session_id, update=update)


def test_an_agent_message_chunk_renders_its_text(harness):
    harness.client.render(
        vs.AgentMessageChunk(message_id="m1", content=vs.TextContentBlock(text="hello"))
    )
    assert "hello" in harness.text


def test_a_thought_and_an_answer_are_visibly_different_transitions(harness):
    """The rule between them is the only thing separating a model's muttering
    from its answer in a scrolling terminal."""
    harness.client.render(
        vs.AgentThoughtChunk(message_id="t1", content=vs.TextContentBlock(text="hmm"))
    )
    harness.client.render(
        vs.AgentMessageChunk(message_id="m1", content=vs.TextContentBlock(text="answer"))
    )

    assert "Thinking" in harness.text
    assert "Assistant" in harness.text
    assert harness.text.index("Thinking") < harness.text.index("answer")


def test_the_same_transition_twice_draws_one_rule(harness):
    for _ in range(3):
        harness.client.render(
            vs.AgentMessageChunk(
                message_id="m1", content=vs.TextContentBlock(text="x")
            )
        )
    assert harness.text.count("Assistant") == 1


def test_a_replayed_user_message_is_rendered_as_the_users(harness):
    harness.client.render(
        vs.UserMessageChunk(message_id="u1", content=vs.TextContentBlock(text="do it"))
    )
    assert "You" in harness.text
    assert "do it" in harness.text


def test_a_whole_message_user_update_renders_when_we_did_not_send_it(harness):
    """The replay shape: `user_message` carries a LIST of blocks, not one."""
    harness.client.render(
        vs.UserMessageUpdate(
            message_id="u1", content=[vs.TextContentBlock(text="stored")]
        )
    )
    assert "You" in harness.text
    assert "stored" in harness.text


def test_the_agent_echo_of_our_own_prompt_is_not_rendered_twice(harness):
    """v2 REQUIRES the agent to echo a prompt back as a `user_message` with an
    agent-owned messageId — that is how a replay and a second client learn where
    it landed. This client already printed what the human typed."""
    update = vs.UserMessageUpdate(
        message_id="u1", content=[vs.TextContentBlock(text="do it")]
    )

    with harness.client.own_echo():
        harness.client.render(update)
    assert harness.text == ""

    harness.client.render(update)
    assert "do it" in harness.text


def test_a_delivery_still_renders_mid_turn(harness):
    """A mailbox delivery is a `user_message_chunk`, not the prompt echo: the
    model is about to answer something nobody typed here, and hiding it hides
    an input the transcript will later contain."""
    with harness.client.own_echo():
        harness.client.render(
            vs.UserMessageChunk(
                message_id="d1", content=vs.TextContentBlock(text="task finished")
            )
        )
    assert "task finished" in harness.text


def test_own_echo_releases_even_when_the_turn_raises(harness):
    """A dead child must not leave the next session's replay muted."""
    with pytest.raises(RuntimeError):
        with harness.client.own_echo():
            raise RuntimeError("child died")

    harness.client.render(
        vs.UserMessageUpdate(message_id="u1", content=[vs.TextContentBlock(text="x")])
    )
    assert "x" in harness.text


async def test_suppressing_the_echo_does_not_suppress_the_record(harness):
    """The record is what a later resume replays; the render is what a human
    reads now. Only the second one is the duplicate."""
    with harness.client.own_echo():
        await harness.client.session_update(
            notif(
                vs.UserMessageUpdate(
                    message_id="u1", content=[vs.TextContentBlock(text="do it")]
                )
            )
        )

    assert len(harness.client.updates) == 1
    assert harness.text == ""


async def test_json_mode_carries_the_echo_even_mid_turn(json_harness):
    """`-j` is a transcript, not a terminal: it gets every update."""
    with json_harness.client.own_echo():
        await json_harness.client.session_update(
            notif(
                vs.UserMessageUpdate(
                    message_id="u1", content=[vs.TextContentBlock(text="do it")]
                )
            )
        )

    assert [e["update"]["sessionUpdate"] for e in json_harness.events] == [
        "user_message"
    ]


def test_rich_markup_in_model_output_is_not_interpreted(harness):
    """A model that prints `[red]` is printing text, not styling this client."""
    harness.client.render(
        vs.AgentMessageChunk(
            message_id="m1", content=vs.TextContentBlock(text="[red]not a style[/red]")
        )
    )
    assert "[red]not a style[/red]" in harness.text


# -- tool calls --------------------------------------------------------------


def test_tool_call_patches_accumulate(harness):
    """Updates are PATCHES: the title set on the first is not on the last, and
    a renderer that reads only the last one prints an id instead of a name."""
    harness.client.render(
        vs.SessionToolCallUpdate(
            tool_call_id="t1", name="execute", title="ls -la", kind="execute",
            status="in_progress",
        )
    )
    harness.client.render(vs.SessionToolCallUpdate(tool_call_id="t1", status="completed"))

    assert "ls -la" in harness.text
    assert harness.text.count("ls -la") == 2


def test_a_tool_call_with_no_title_falls_back_to_its_name(harness):
    harness.client.render(vs.SessionToolCallUpdate(tool_call_id="t1", name="read"))
    assert "read" in harness.text


def test_a_tool_call_with_neither_falls_back_to_its_id(harness):
    harness.client.render(vs.SessionToolCallUpdate(tool_call_id="call-9"))
    assert "call-9" in harness.text


def test_a_failed_tool_call_shows_why(harness):
    harness.client.render(
        vs.SessionToolCallUpdate(
            tool_call_id="t1",
            title="boom",
            status="failed",
            raw_output=[vs.TextContentBlock(text="Traceback: no such file")],
        )
    )
    assert "boom" in harness.text
    assert "Traceback: no such file" in harness.text


def test_a_long_failure_is_truncated(harness):
    harness.client.render(
        vs.SessionToolCallUpdate(
            tool_call_id="t1", status="failed", raw_output="x" * 5000
        )
    )
    assert harness.text.count("x") <= 2100


def test_a_completed_tool_call_does_not_dump_its_raw_output(harness):
    """The model's copy of the terminal bytes is ANSI-stripped and the human
    already got the real ones; showing both is showing one thing twice."""
    harness.client.render(
        vs.SessionToolCallUpdate(
            tool_call_id="t1", title="ls", status="completed", raw_output="total 8"
        )
    )
    assert "total 8" not in harness.text


def test_tool_call_content_chunks_are_rendered(harness):
    """The wrapper is the trap: `ContentToolCallContent.type` is `"content"`,
    so a renderer that stops at the first non-text block prints `<content>`
    and the tool's output never reaches the screen."""
    harness.client.render(
        vs.ToolCallContentChunkUpdate(
            tool_call_id="t1", content=vs.ContentToolCallContent(
                content=vs.TextContentBlock(text="partial")
            ),
        )
    )
    assert "partial" in harness.text
    assert "<content>" not in harness.text


def test_a_diff_content_lists_its_changes_not_its_patch(harness):
    harness.client.render(
        vs.ToolCallContentChunkUpdate(
            tool_call_id="t1",
            content=vs.DiffToolCallContent(
                changes=[
                    vs.ModifyDiffChange(path="/tmp/a.py"),
                    vs.MoveDiffChange(old_path="/tmp/b.py", path="/tmp/c.py"),
                ],
                patch=vs.DiffPatch(format="unified", text="--- a\n+++ b\n@@ -1 @@"),
            ),
        )
    )
    assert "modify /tmp/a.py" in harness.text
    assert "move /tmp/b.py -> /tmp/c.py" in harness.text
    assert "@@ -1 @@" not in harness.text


def test_a_terminal_content_reference_is_named_not_dumped(harness):
    """The bytes it points at arrive over the terminal channel; printing them
    here too would be printing one thing twice."""
    harness.client.render(
        vs.ToolCallContentChunkUpdate(
            tool_call_id="t1",
            content=vs.TerminalToolCallContent(terminal_id="term-7"),
        )
    )
    assert "<terminal>" in harness.text


# -- terminals ---------------------------------------------------------------


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def test_a_terminal_update_prints_the_command_then_the_snapshot(harness):
    harness.client.render(
        vs.SessionTerminalUpdate(
            terminal_id="term-1",
            command="ls -la",
            output=vs.TerminalOutput(data=b64("total 8\n")),
        )
    )
    assert "$ ls -la" in harness.text
    assert harness.fd == "total 8\n"


def test_raw_bytes_bypass_rich(harness):
    """An ANSI escape is data from the child's PTY, not markup for this
    console; rich would reinterpret it."""
    harness.client.render(
        vs.SessionTerminalOutputChunk(terminal_id="t", data=b64("\x1b[31mred\x1b[0m"))
    )
    assert harness.fd == "\x1b[31mred\x1b[0m"
    assert "red" not in harness.text


def test_a_snapshot_is_skipped_for_a_terminal_that_already_streamed(harness):
    """The snapshot exists for a client that was NOT watching. This one was."""
    harness.client.render(
        vs.SessionTerminalOutputChunk(terminal_id="t", data=b64("line1\n"))
    )
    harness.client.render(
        vs.SessionTerminalUpdate(
            terminal_id="t", output=vs.TerminalOutput(data=b64("line1\nline2\n"))
        )
    )

    assert harness.fd == "line1\n"


def test_a_snapshot_is_kept_for_a_terminal_that_never_streamed(harness):
    harness.client.render(
        vs.SessionTerminalUpdate(
            terminal_id="other", output=vs.TerminalOutput(data=b64("all of it\n"))
        )
    )
    assert harness.fd == "all of it\n"


def test_a_nonzero_exit_is_reported_and_a_zero_one_is_not(harness):
    harness.client.render(
        vs.SessionTerminalUpdate(
            terminal_id="a", exit_status=vs.TerminalExitStatus(exit_code=0)
        )
    )
    harness.client.render(
        vs.SessionTerminalUpdate(
            terminal_id="b", exit_status=vs.TerminalExitStatus(exit_code=2)
        )
    )
    assert "exit 2" in harness.text
    assert "exit 0" not in harness.text


def test_a_signalled_exit_with_no_code_prints_nothing(harness):
    harness.client.render(
        vs.SessionTerminalUpdate(
            terminal_id="a", exit_status=vs.TerminalExitStatus(signal="SIGKILL")
        )
    )
    assert "exit" not in harness.text


# -- state, usage, session ---------------------------------------------------


def test_an_idle_state_prints_its_stop_reason(harness):
    harness.client.render(vs.IdleSessionStateUpdate(stop_reason="end_turn"))
    assert "idle (end_turn)" in harness.text


def test_a_running_state_prints_nothing_but_resets_the_transition(harness):
    harness.client.render(
        vs.AgentMessageChunk(message_id="m", content=vs.TextContentBlock(text="a"))
    )
    harness.client.render(vs.RunningSessionStateUpdate())
    harness.client.render(
        vs.AgentMessageChunk(message_id="m", content=vs.TextContentBlock(text="b"))
    )

    assert harness.text.count("Assistant") == 2


def test_a_state_this_client_does_not_know_is_named_not_hidden(harness):
    """v2's state enum is extensible, so an agent is allowed to invent one.
    Folding it into `idle` would tell a human the turn was over; dropping it
    would tell them nothing at all."""
    harness.client.render(vs.OtherSessionStateUpdate(state="_some_agents_idea"))
    assert "state: _some_agents_idea" in harness.text


def test_usage_is_rendered_with_its_cost(harness):
    harness.client.render(
        vs.UsageUpdate(used=1200, size=180000, cost=vs.Cost(amount=0.5, currency="USD"))
    )
    assert "context 1,200/180,000" in harness.text
    assert "0.5 USD" in harness.text


def test_usage_without_a_cost_still_reports_the_window(harness):
    harness.client.render(vs.UsageUpdate(used=7, size=1000))
    assert "context 7/1,000" in harness.text


def test_a_session_title_is_kept(harness):
    harness.client.render(vs.SessionInfoUpdate(title="Fix the parser"))
    assert harness.client.title == "Fix the parser"
    assert "Fix the parser" in harness.text


def test_available_commands_are_listed(harness):
    harness.client.render(
        vs.AvailableCommandsUpdate(
            available_commands=[
                vs.AvailableCommand(name="compact", description="Compact now"),
                vs.AvailableCommand(name="clear", description="Clear"),
            ]
        )
    )
    assert "commands: compact, clear" in harness.text


def test_no_available_commands_says_none(harness):
    harness.client.render(vs.AvailableCommandsUpdate(available_commands=[]))
    assert "commands: none" in harness.text


def test_config_options_show_their_current_values(harness):
    harness.client.render(
        vs.ConfigOptionUpdate(
            config_options=[
                vs.SelectSessionConfigOption(
                    config_id="model",
                    name="Model",
                    category="model",
                    current_value="alibaba:qwen3.8-max",
                    options=[
                        vs.SessionConfigSelectOption(
                            value="alibaba:qwen3.8-max", name="qwen3.8-max"
                        )
                    ],
                )
            ]
        )
    )
    assert "model=alibaba:qwen3.8-max" in harness.text


def test_compaction_status_and_error_are_rendered(harness):
    harness.client.render(
        vs.SessionCompactionUpdate(compaction_id="c1", status="failed", error="boom")
    )
    assert "compaction failed: boom" in harness.text


def test_a_compaction_summary_chunk_is_rendered(harness):
    harness.client.render(
        vs.SessionCompactionSummaryChunk(
            compaction_id="c1", content=vs.TextContentBlock(text="so far...")
        )
    )
    assert "so far..." in harness.text


# -- the dispatch table itself ----------------------------------------------


def test_an_unknown_update_kind_prints_its_kind(harness):
    """The protocol's union is longer than any client's switch. A variant this
    renderer has never seen must print its name: rendering nothing is
    indistinguishable from an agent that stopped talking."""
    harness.client.render(vs.OtherSessionUpdate(session_update="brand_new_thing"))
    assert "brand_new_thing" in harness.text


def test_an_update_with_no_discriminator_at_all_prints_its_class(harness):
    harness.client.render(SimpleNamespace())
    assert "SimpleNamespace" in harness.text


def _discriminators() -> set[str]:
    """Every `sessionUpdate` value the protocol defines."""
    union = vs.UpdateSessionNotification.model_fields["update"].annotation
    out: set[str] = set()
    for member in typing.get_args(union):
        field = member.model_fields["session_update"]
        out.update(typing.get_args(field.annotation) or [str])
    return out


#: crow's agent emits neither, so this client has nothing to render for them.
#: A NEW protocol variant that lands here unrendered is the point: it fails
#: this test instead of failing silently in a terminal.
UNRENDERED = {"plan_update", "plan_removed"}


def test_every_protocol_update_kind_is_rendered_or_deliberately_not():
    kinds = _discriminators()
    assert "plan_update" in kinds, "the union moved; re-read it"
    assert set(_RENDERS) | UNRENDERED == kinds - {str}


def test_every_renderer_is_a_real_method():
    for kind, handler in _RENDERS.items():
        assert callable(handler), kind
        assert getattr(handler, "__name__", "").startswith("_"), kind


def test_the_state_variants_share_one_discriminator_and_one_renderer():
    """Running/Idle/RequiresAction/Other are four models under `state_update`,
    so the dispatch cannot be isinstance-based without losing three of them."""
    for update in (
        vs.RunningSessionStateUpdate(),
        vs.IdleSessionStateUpdate(),
        vs.RequiresActionSessionStateUpdate(),
        vs.OtherSessionStateUpdate(state="weird"),
    ):
        assert update.session_update == "state_update"
    assert _RENDERS["state_update"] is TerminalClient._state


# -- recording, and the json mode -------------------------------------------


async def test_rendering_cannot_break_the_record(json_harness):
    """`super().session_update` runs FIRST: the record and the idle queue are
    what makes a prompt return, and the face is the second job."""
    client = json_harness.client
    client.watch("s1")
    await client.session_update(notif(vs.RunningSessionStateUpdate()))
    await client.session_update(notif(vs.IdleSessionStateUpdate(stop_reason="end_turn")))

    assert len(client.updates) == 2
    assert client.stops["s1"].get_nowait() == "end_turn"


async def test_json_mode_emits_the_wire_and_renders_nothing(json_harness):
    await json_harness.client.session_update(
        notif(vs.AgentMessageChunk(message_id="m1", content=vs.TextContentBlock(text="hi")))
    )

    assert json_harness.events == [
        {
            "type": "update",
            "session_id": "s1",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "messageId": "m1",
                "content": {"type": "text", "text": "hi"},
            },
        }
    ]
    assert json_harness.text == ""


async def test_rich_mode_emits_no_jsonl(harness):
    await harness.client.session_update(
        notif(vs.AgentMessageChunk(message_id="m1", content=vs.TextContentBlock(text="hi")))
    )
    assert harness.events == []
    assert "hi" in harness.text


async def test_an_unrenderable_update_still_lands_in_the_record(harness):
    await harness.client.session_update(
        notif(vs.OtherSessionUpdate(session_update="brand_new_thing"))
    )
    assert len(harness.client.updates) == 1
    assert "brand_new_thing" in harness.text
# -- the turn, and who echoes it ---------------------------------------------


async def test_send_prompt_holds_the_echo_for_the_length_of_the_turn(capfd):
    """The wiring. `agent2.driver._accept_prompt` echoes every prompt back as a
    `user_message` because v2 requires it, so the client that sent the prompt
    has to be the one that holds it — and `send_prompt` is the only thing that
    knows the length of a turn.
    """
    h = Harness(capfd)
    wrapper = CrowClientV2(h.console)
    wrapper.client = h.client
    wrapper.session_id = "s1"

    async def fake_prompt(session_id, text, timeout=None):
        await h.client.session_update(
            notif(
                vs.UserMessageUpdate(
                    message_id="u1", content=[vs.TextContentBlock(text=text)]
                )
            )
        )
        await h.client.session_update(
            notif(
                vs.AgentMessageChunk(
                    message_id="m1", content=vs.TextContentBlock(text="done")
                )
            )
        )
        return "end_turn"

    wrapper.driver = SimpleNamespace(prompt=fake_prompt)

    assert await wrapper.send_prompt("do it") == "end_turn"
    assert h.text.count("do it") == 1, h.text
    assert "done" in h.text


async def test_the_next_turn_after_a_raise_still_holds_its_echo(capfd):
    h = Harness(capfd)
    wrapper = CrowClientV2(h.console)
    wrapper.client = h.client
    wrapper.session_id = "s1"

    async def boom(session_id, text, timeout=None):
        raise ChildExited("child exited")

    async def echo(session_id, text, timeout=None):
        await h.client.session_update(
            notif(
                vs.UserMessageUpdate(
                    message_id="u2", content=[vs.TextContentBlock(text=text)]
                )
            )
        )
        return "end_turn"

    wrapper.driver = SimpleNamespace(prompt=boom)
    with pytest.raises(ChildExited):
        await wrapper.send_prompt("first")

    wrapper.driver = SimpleNamespace(prompt=echo)
    await wrapper.send_prompt("second")

    assert h.text.count("second") == 1, h.text
