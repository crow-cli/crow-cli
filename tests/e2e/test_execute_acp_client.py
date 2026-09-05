"""E2E over the wire: what the ACP CLIENT sees when code inside an execute
cell edits files.

A real crow agent subprocess — spawned with THIS interpreter, so the agent,
its MCP server and the kernel are all live code from this tree — is driven
by a real ACP client (crow_cli.client.subagent.SubagentDriver, the same
machinery the task system uses). The client's session_update stream is the
assertion surface: the model calls `execute` ONCE, the cell calls `write()`
and `fs('read')` in-kernel, and the client must see an honest ACP tool call
for each — the write as kind="edit" with a file location, the code's own
arguments as rawInput and diff content the frontend renders as a diff view;
the read as kind="read", located at the same file, carrying the numbered
text.

This is the tier the in-process tests cannot cover. They drive the react
loop directly, so a stale MCP server (started before the identity-rail
prologue existed) or a database missing subtool_calls silently produces NO
diffs while every assertion still passes. Here the whole stack is spawned
fresh, exactly as it is in production.

Live: needs a configured provider; skips otherwise.
"""

import asyncio
import re
from pathlib import Path

import pytest
import yaml

from crow_cli.agent.mcp_client import fastmcp_config_to_acp_servers
from crow_cli.client.subagent import SubagentDriver
from crow_cli.config import Config

pytestmark = pytest.mark.asyncio

PREFERRED_MODEL = "qwen3.8-max-preview"
PROMPT_TIMEOUT = 240


def _live_config_or_skip():
    config = Config.load()
    if not config.is_configured:
        pytest.skip("No LLM provider configured")
    if not config.llm.models:
        pytest.skip("No models configured")
    return config


def _model_name(config) -> str:
    return (
        PREFERRED_MODEL
        if PREFERRED_MODEL in config.llm.models
        else next(iter(config.llm.models))
    )


def _updates_by_id(updates, tool_call_id):
    return [
        u
        for u in updates
        if getattr(u, "tool_call_id", None) == tool_call_id
        and getattr(u, "session_update", None) in ("tool_call", "tool_call_update")
    ]


async def test_client_sees_in_cell_write_and_read_as_their_own_calls(tmp_path):
    config = _live_config_or_skip()
    model = _model_name(config)

    # Keep the real config dir (.env, providers, mcpServers -> this tree's
    # crow-cli mcp) and isolate ONLY the database, so the run never touches
    # the live crow.db.
    override = tmp_path / "override.yaml"
    override.write_text(
        yaml.safe_dump({"db_uri": f"sqlite:///{tmp_path / 'client-e2e.db'}"})
    )

    target = tmp_path / "hello.txt"
    content = "hello from the kernel\n"
    code = (
        f"r = await write({str(target)!r}, {content!r})\n"
        f"back = await fs('read', {str(target)!r})\n"
        "print(r.path, r.added)\n"
        "print(back.text)"
    )
    prompt = (
        "Call the `execute` tool EXACTLY ONCE, with this code verbatim:\n\n"
        f"{code}\n\n"
        "Do not call any other tool. Then reply with the single word DONE."
    )

    driver = SubagentDriver()
    try:
        await driver.start(cwd=str(tmp_path), model=model, config_file=override)
        # The child comes up with ZERO tools unless the client hands it the
        # MCP servers (the CLI does exactly this) — config's crow-mcp is this
        # tree's server, so execute and the identity rail are live code.
        session_id = await driver.new_session(
            cwd=str(tmp_path),
            mcp_servers=fastmcp_config_to_acp_servers(config.mcp_servers),
        )
        response = await asyncio.wait_for(
            driver.prompt(session_id, prompt), timeout=PROMPT_TIMEOUT
        )
        updates = list(driver.client.updates)
    finally:
        await driver.close()

    assert response.stop_reason in ("end_turn", "max_tokens", "max_turn_requests"), (
        response.stop_reason
    )

    # The code really ran: the file is on disk with the content written.
    assert Path(target).read_text() == content

    tool_calls = [
        u
        for u in updates
        if getattr(u, "session_update", None) in ("tool_call", "tool_call_update")
    ]
    ids = []
    for u in tool_calls:
        if u.tool_call_id not in ids:
            ids.append(u.tool_call_id)

    # The model's own call: execute.
    exec_ids = [
        i for i in ids if _updates_by_id(updates, i)[0].kind == "execute"
    ]
    assert exec_ids, f"no execute tool call on the wire: {ids}"

    # The in-cell write and read: each its OWN tool call, synthetic id shaped
    # like a real one (<turn>/call_sub<row>), in call-record order.
    sub_ids = [i for i in ids if re.search(r"/call_sub\d+", i)]
    assert len(sub_ids) == 2, f"the in-cell calls never reached the client: {ids}"
    sub_id = sub_ids[0]

    start, progress, final = _updates_by_id(updates, sub_id)
    assert start.session_update == "tool_call"
    assert start.kind == "edit"
    assert start.status == "pending"
    assert str(target) in start.title
    assert [loc.path for loc in (start.locations or [])] == [str(target)]

    # rawInput is the call the CODE made — the args write() was given.
    assert start.raw_input["file_path"] == str(target)
    assert start.raw_input["content"] == content

    # The artifact: a real ACP diff block, which is what the frontend turns
    # into a diff view.
    diffs = [c for c in (progress.content or []) if c.type == "diff"]
    assert len(diffs) == 1, progress.content
    assert diffs[0].path == str(target)
    assert diffs[0].old_text in (None, "")  # a new file
    assert diffs[0].new_text == content

    assert final.status == "completed"

    # The in-cell read: kind follows the artifact ("read", not the "other"
    # that get_tool_kind("fs") would give), located at the file, carrying the
    # numbered text — the same shape execute_acp_read sends.
    read_start, read_progress, read_final = _updates_by_id(updates, sub_ids[1])
    assert read_start.kind == "read"
    assert read_start.title == f"fs/read: {target}"
    assert [loc.path for loc in (read_start.locations or [])] == [str(target)]
    assert read_start.raw_input["mode"] == "read"
    assert read_start.raw_input["path"] == str(target)
    read_texts = [
        c.content.text
        for c in (read_progress.content or [])
        if c.type == "content" and c.content.type == "text"
    ]
    assert read_texts == ["1→hello from the kernel"]
    assert read_final.status == "completed"

    # The LLM's view is untouched by any of this: execute's own completion
    # carries only what the cell printed.
    exec_done = _updates_by_id(updates, exec_ids[0])[-1]
    assert exec_done.status == "completed"
    texts = [
        c.content.text
        for c in (exec_done.content or [])
        if c.type == "content" and c.content.type == "text"
    ]
    assert any(str(target) in t for t in texts), texts
    # The read reached the MODEL too, but only because the cell printed it —
    # the artifact on the sibling call is the client's channel, not the LLM's.
    assert any("1→hello from the kernel" in t for t in texts), texts
    assert not [c for c in (exec_done.content or []) if c.type == "diff"]
