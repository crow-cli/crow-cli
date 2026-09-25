"""The subtool drain: rows in, one ACP upsert per artifact out.

Real sqlite, real ``SubtoolCall`` rows shaped the way ``tools/results.py``
actually writes them, real v2 pydantic models serialized to wire JSON. The
only stand-in is the connection, which records notifications instead of
sending them — there is no client in a unit test, and the wire JSON is
exactly what a client would receive.
"""

import base64
import logging

import pytest
from acp.experimental.v2 import schema as vs

from crow_cli.agent2.ctx import TurnCtx
from crow_cli.agent2.emitter import Emitter
from crow_cli.agent2.tools import drain_subtool_calls
from crow_cli.config import Config
from crow_cli.memory.db import get_engine
from crow_cli.memory.image_store import resolve_image_store
from crow_cli.memory.models import Base, SubtoolCall

SESSION_ID = "drain-session"
AGENT_ID = f"{SESSION_ID}-1-1"
PARENT = "turn-0001/call_execute_1"
IMAGE_KEY = "deadbeef.png"
IMAGE_BYTES = b"\x89PNG\r\n\x1a\nFAKEPIXELS"


class RecordingConn:
    """Stands in for AgentSideConnection; keeps the wire JSON."""

    def __init__(self):
        self.wire: list[dict] = []

    async def session_update(self, session_id, update, **kwargs):
        # Rebuilds the notification and dumps it the way the connection does:
        # ``exclude_unset``, and — since python-sdk 1.0.0rc2 dropped
        # ``exclude_none`` from ``_dump`` — nothing else. A field the emitter
        # set to ``None`` on purpose is a ``null`` a client receives, so this
        # fake has to keep it rather than tidy it away.
        self.wire.append(
            vs.UpdateSessionNotification(
                session_id=session_id, update=update
            ).model_dump(mode="json", by_alias=True, exclude_unset=True)
        )

    @property
    def updates(self) -> list[dict]:
        return [w["update"] for w in self.wire]


# (tool, mode, args, status, result_kind, acp_payload, llm_images, error)
ROWS = [
    ("fs", "write", {"path": "target.py", "content": "x = 2\n"}, "completed", "diff",
     {"path": "target.py", "old_text": "x = 1\n", "new_text": "x = 2\n"}, [], None),
    ("fs", "read", {"path": "target.py"}, "completed", "read",
     {"path": "target.py", "text": "x = 2\n"}, [], None),
    ("vision", None, {"prompt": "what is this"}, "completed", "image", {},
     [{"key": IMAGE_KEY, "mime": "image/png"}], None),
    ("web", "fetch", {"url": "https://example.com"}, "completed", "web",
     {"content": "text", "text": "https://example.com — 200", "subject": "https://example.com"},
     [], None),
    ("rlm", None, {"prompt": "prove it"}, "completed", "rlm",
     {"content": "text", "text": "delegate sub-7 — depth 1", "subject": "sub-7"}, [], None),
    ("memory", "search", {"query": "acp v2"}, "completed", "memory",
     {"content": "text", "text": "3 sessions", "subject": "acp v2"}, [], None),
    ("fs", "rewrite", {"pattern": "TODO"}, "completed", "rewrite",
     {"content": "text", "text": "rewrote 2 files"}, [], None),
    ("sg", None, {"pattern": "drain"}, "completed", "search",
     {"content": "text", "text": "tools.py:412: drain", "subject": "drain"}, [], None),
    ("fs", "glob", {"pattern": "**/*.rs"}, "failed", "error", None, [], "permission denied"),
]


@pytest.fixture
async def drained(tmp_path):
    """A TurnCtx over a real db holding ROWS, plus the drain's output."""
    (tmp_path / "target.py").write_text("x = 1\n")
    config = Config(config_dir=tmp_path)
    config.db_uri = f"sqlite:///{tmp_path / 'crow.db'}"
    engine = get_engine(config.db_uri)
    Base.metadata.create_all(engine)
    resolve_image_store(config.image_store.get("s3"), tmp_path / "images").put(
        IMAGE_KEY, IMAGE_BYTES
    )
    with engine.begin() as conn:
        for tool, mode, args, status, kind, payload, images, error in ROWS:
            conn.execute(
                SubtoolCall.__table__.insert().values(
                    session_id=SESSION_ID, agent_id=AGENT_ID,
                    parent_tool_call_id=PARENT, tool=tool, mode=mode, args=args,
                    status=status, result_kind=kind, acp_payload=payload,
                    llm_images=images, error=error, emitted=0,
                )
            )
        # noise that must NOT be drained
        conn.execute(
            SubtoolCall.__table__.insert().values(
                session_id=SESSION_ID, agent_id=AGENT_ID, parent_tool_call_id=PARENT,
                tool="fs", mode="read", args={}, status="completed", result_kind="read",
                acp_payload={"path": "old.py", "text": "stale"}, llm_images=[],
                error=None, emitted=1,
            )
        )
        conn.execute(
            SubtoolCall.__table__.insert().values(
                session_id=SESSION_ID, agent_id=AGENT_ID,
                parent_tool_call_id="turn-9999/call_other",
                tool="fs", mode="read", args={}, status="completed", result_kind="read",
                acp_payload={"path": "other.py", "text": "other"}, llm_images=[],
                error=None, emitted=0,
            )
        )
    engine.dispose()

    conn = RecordingConn()
    ctx = TurnCtx(
        emitter=Emitter(conn, SESSION_ID),
        config=config,
        session=_Session(AGENT_ID, str(tmp_path)),
        turn_id="turn-0001",
        logger=logging.getLogger(__name__),
    )
    llm_blocks = await drain_subtool_calls(ctx, PARENT)
    return ctx, conn, llm_blocks


class _Session:
    """The three TurnCtx properties read; no agent row needed for a drain."""

    def __init__(self, agent_id, cwd):
        self.agent_id = agent_id
        self.cwd = cwd
        self.rlm_depth = 0


def test_one_upsert_per_row(drained):
    _, conn, _ = drained
    assert len(conn.wire) == len(ROWS)
    for w in conn.wire:
        assert w["sessionId"] == SESSION_ID
        assert w["update"]["sessionUpdate"] == "tool_call_update"
    # the synthetic ids are deterministic and turn-scoped
    assert [u["toolCallId"] for u in conn.updates] == [
        f"turn-0001/call_sub{i}" for i in range(1, len(ROWS) + 1)
    ]


def test_kind_follows_the_artifact_not_the_name(drained):
    _, conn, _ = drained
    kinds = {u["toolCallId"]: u["kind"] for u in conn.updates}
    assert kinds["turn-0001/call_sub1"] == "edit"      # fs/write -> diff
    assert kinds["turn-0001/call_sub2"] == "read"      # fs/read
    assert kinds["turn-0001/call_sub4"] == "fetch"     # web, though mode "run" would be "other"
    assert kinds["turn-0001/call_sub5"] == "think"     # rlm, which matches no name rule
    assert kinds["turn-0001/call_sub6"] == "read"      # memory, though mode "search" is "search"
    assert kinds["turn-0001/call_sub7"] == "edit"      # rewrite
    assert kinds["turn-0001/call_sub8"] == "search"    # sg


def test_diff_carries_absolute_changes_and_a_git_patch(drained):
    ctx, conn, _ = drained
    diff = conn.updates[0]["content"][0]
    assert diff["type"] == "diff"
    assert diff["changes"] == [
        {"path": f"{ctx.cwd}/target.py", "fileType": "text", "operation": "modify"}
    ]
    assert diff["patch"]["format"] == "git_patch"
    text = diff["patch"]["text"]
    # git convention: absolute path minus the leading slash, never "a//tmp/..."
    assert text.startswith(f"--- a{ctx.cwd}/target.py\n")
    assert "-x = 1\n" in text and "+x = 2\n" in text
    assert conn.updates[0]["locations"] == [{"path": f"{ctx.cwd}/target.py"}]


def test_a_subject_is_displayed_never_claimed_as_a_location(drained):
    _, conn, _ = drained
    web, rlm = conn.updates[3], conn.updates[4]
    assert web["title"] == "web/fetch: https://example.com"
    assert rlm["title"] == "rlm: sub-7"
    assert "locations" not in web and "locations" not in rlm


def test_failed_row_says_what_failed(drained):
    _, conn, _ = drained
    last = conn.updates[-1]
    assert last["status"] == "failed"
    assert last["content"][0]["content"]["text"] == "fs/glob failed: permission denied"


def test_images_reach_both_channels(drained):
    _, conn, llm_blocks = drained
    image = conn.updates[2]["content"][0]["content"]
    assert image["type"] == "image" and image["mimeType"] == "image/png"
    assert len(llm_blocks) == 1
    url = llm_blocks[0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == IMAGE_BYTES


def test_the_llm_gets_nothing_but_images(drained):
    """Subtools are code, not conversation: no text rides the LLM channel."""
    _, _, llm_blocks = drained
    assert all(b["type"] == "image_url" for b in llm_blocks)


async def test_rows_are_claimed(drained):
    """A second drain of the same parent emits nothing — the table is a queue."""
    ctx, _, _ = drained
    engine = get_engine(ctx.config.db_uri)
    with engine.begin() as c:
        left = c.execute(
            SubtoolCall.__table__.select().where(SubtoolCall.emitted == 0)
        ).fetchall()
    engine.dispose()
    # every drained row flipped; the other parent's row is untouched
    assert [r.parent_tool_call_id for r in left] == ["turn-9999/call_other"]

    again = RecordingConn()
    ctx2 = TurnCtx(emitter=Emitter(again, SESSION_ID), config=ctx.config,
                   session=ctx.session, turn_id="turn-0001", logger=ctx.logger)
    assert await drain_subtool_calls(ctx2, PARENT) == []
    assert again.wire == []


async def test_no_db_uri_is_a_no_op(drained):
    ctx, _, _ = drained
    ctx.config.db_uri = ""
    assert await drain_subtool_calls(ctx, PARENT) == []
