"""crow_cli.mcp.memory.store + tools — include_forks filtering (schema v5).

Forks are invisible on the multi-identity surfaces by default: list_sessions
counts, session_records transcripts and query_memory hits all reflect the
trunk only unless include_forks=True.
"""

import gc
import tracemalloc

import pytest

import crow_cli.memory as cm
from crow_cli.mcp.memory import main, store


@pytest.fixture()
def mcp_store(tmp_path, monkeypatch):
    """One session: trunk s1-1-1 (3 msgs) + fork s1-1-2 (1 own msg)."""
    uri = f"sqlite:///{tmp_path / 'crow.db'}"
    cm.create_database(uri)
    engine = cm.get_engine(uri)
    cm.create_agent(
        engine, agent_id="s1-1-1", session_id="s1", agent_idx=1,
        cwd="/tmp", system_prompt="sp", tool_definitions=[],
        request_params={}, model_identifier="m",
    )
    for i in range(3):
        cm.add_message(engine, "s1-1-1", {"role": "user", "content": f"trunk msg {i} needlepoint"})
    anchor = cm.query_messages(engine, ["s1-1-1"])[1].id
    cm.create_agent(
        engine, agent_id="s1-1-2", session_id="s1", agent_idx=1, fork_idx=2,
        forked_at=str(anchor), tool_definitions=[], request_params={},
    )
    cm.add_message(engine, "s1-1-2", {"role": "user", "content": "fork only needlepoint"})
    engine.dispose()

    monkeypatch.setenv("CROW_DB_URI", uri)
    store._cached_engine.cache_clear()
    yield
    store._cached_engine.cache_clear()


# ---- store layer ----


def test_list_sessions_hides_forks_by_default(mcp_store):
    (s,) = store.list_sessions()
    assert s.session_id == "s1"
    assert s.agent_count == 1  # fork agent row not counted
    assert s.agent_idxs == [1]
    assert s.message_count == 3  # fork's own 2 rows not counted
    assert "fork only" not in (s.last_message.data.get("content", "") if s.last_message else "")


def test_list_sessions_include_forks(mcp_store):
    (s,) = store.list_sessions(include_forks=True)
    assert s.agent_count == 2
    assert s.message_count == 4


def test_session_records_hides_fork_rows(mcp_store):
    recs = store.session_records("s1")
    assert len(recs) == 3
    assert all(r.fork_idx == 1 for r in recs)

    recs = store.session_records("s1", include_forks=True)
    assert len(recs) == 4
    assert any(r.fork_idx == 2 for r in recs)


def test_search_hides_fork_hits(mcp_store):
    hits = store.search("needlepoint")
    assert len(hits) == 3
    assert all(h.fork_idx == 1 for h in hits)

    hits = store.search("needlepoint", include_forks=True)
    assert len(hits) == 4
    assert any(h.fork_idx == 2 for h in hits)


# ---- MCP tool layer (fastmcp keeps the functions directly callable) ----


async def test_tool_list_sessions_hides_forks(mcp_store):
    out = await main.list_sessions()
    assert "s1" in out
    assert "s1-1-2" not in out  # no fork id leaks into the summary
    out = await main.list_sessions(include_forks=True)
    assert "2 (a1–a1)" in out  # agents column folds the fork in


async def test_tool_query_session_hides_fork_messages(mcp_store):
    out = await main.query_session(session_id="s1", limit=10, order="asc")
    assert "trunk msg 0" in out
    assert "fork only" not in out

    out = await main.query_session(session_id="s1", limit=10, order="asc", include_forks=True)
    assert "fork only" in out


async def test_tool_query_memory_hides_fork_hits(mcp_store):
    out = await main.query_memory(query="needlepoint")
    assert "fork only" not in out
    out = await main.query_memory(query="needlepoint", include_forks=True)
    assert "fork only" in out


# ---- RAM regression: agent payloads must not be materialized ----
#
# Agent rows carry each agent's full system prompt and tool definitions.
# list_sessions / search used to load EVERY agent row in full just to map
# ids — a ~577 MB transient peak on a real db, ratcheting the long-lived
# MCP server's RSS up ~12 MB per call (glibc never returns the arenas).
# They only need the id/model/cwd columns.


@pytest.fixture()
def heavy_store(tmp_path, monkeypatch):
    """20 agents whose system prompt + tool definitions are 1 MiB each."""
    uri = f"sqlite:///{tmp_path / 'crow.db'}"
    cm.create_database(uri)
    engine = cm.get_engine(uri)
    payload = "x" * (1024 * 1024)
    for i in range(20):
        cm.create_agent(
            engine, agent_id=f"s{i}-1-1", session_id=f"s{i}", agent_idx=1,
            cwd="/tmp", system_prompt=payload,
            tool_definitions=[{"big": payload}], request_params={},
            model_identifier="m",
        )
        cm.add_message(engine, f"s{i}-1-1", {"role": "user", "content": f"needle {i}"})
    engine.dispose()

    monkeypatch.setenv("CROW_DB_URI", uri)
    store._cached_engine.cache_clear()
    yield
    store._cached_engine.cache_clear()


def _peak_mb(fn) -> float:
    """Traced allocation peak (MB) of fn, after a warmup call."""
    fn()  # engine creation + query compilation
    gc.collect()
    tracemalloc.start()
    try:
        fn()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak / 1024 / 1024


def test_list_sessions_does_not_materialize_agent_payloads(heavy_store):
    # Full-row load of the 20 agents would peak >40 MB; columns-only is ~kB.
    assert _peak_mb(lambda: store.list_sessions()) < 5


def test_search_does_not_materialize_agent_payloads(heavy_store):
    assert _peak_mb(lambda: store.search("needle")) < 5
