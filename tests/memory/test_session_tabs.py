"""session_tabs — the TUI's tab state lives in the shared store now.

Real sqlite via create_database (same schema the agent writes); verifies
CRUD, recency ordering, and the tui DB facade against an explicit db_uri
(so Config.load() is never touched in tests).
"""

from crow_cli.memory import session_tabs
from crow_cli.memory.db import create_database
from crow_cli.tui.db import DB


def make_uri(tmp_path) -> str:
    uri = f"sqlite:///{tmp_path / 'crow.db'}"
    create_database(uri)
    return uri


def test_new_get_roundtrip(tmp_path):
    uri = make_uri(tmp_path)
    pk = session_tabs.tab_new(
        uri,
        title="sess-one",
        agent="Crow",
        agent_identity="crowai.dev",
        agent_session_id="sess-one",
        meta_json='{"agent_data": {"identity": "crowai.dev"}}',
    )
    row = session_tabs.tab_get(uri, pk)
    assert row["title"] == "sess-one"
    assert row["agent_identity"] == "crowai.dev"
    assert row["protocol"] == "acp"
    assert session_tabs.tab_get(uri, pk + 1) is None


def test_rename_and_touch(tmp_path):
    uri = make_uri(tmp_path)
    a = session_tabs.tab_new(uri, title="a", agent="Crow", agent_identity="i", agent_session_id="a")
    b = session_tabs.tab_new(uri, title="b", agent="Crow", agent_identity="i", agent_session_id="b")

    assert session_tabs.tab_rename(uri, a, "a-renamed")
    assert session_tabs.tab_get(uri, a)["title"] == "a-renamed"

    # b was created later; touching a must put it first in recency order
    assert session_tabs.tab_touch(uri, a)
    recent = session_tabs.tab_recent(uri)
    assert [r["id"] for r in recent] == [a, b]

    assert not session_tabs.tab_touch(uri, a + b + 99)
    assert not session_tabs.tab_rename(uri, a + b + 99, "nope")


async def test_tui_facade_against_explicit_uri(tmp_path):
    uri = make_uri(tmp_path)
    db = DB(db_uri=uri)
    pk = await db.session_new(
        title="t",
        agent="Crow",
        agent_identity="crowai.dev",
        agent_session_id="wire-1",
        meta={"k": "v"},
    )
    assert await db.session_update_last_used(pk)
    assert await db.session_update_title(pk, "t2")
    session = await db.session_get(pk)
    assert session["title"] == "t2"
    assert session["meta_json"] == '{"k": "v"}'
    recent = await db.session_get_recent()
    assert [s["id"] for s in recent] == [pk]
