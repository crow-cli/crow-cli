#!/usr/bin/env python
"""Live e2e: memory layer against a REAL PostgreSQL container.

Boots an ephemeral postgres:17-alpine container, then drives the real
memory package through the postgres path of every dialect seam:
  1. create_database   -> tables + messages_fts tsvector table + GIN index
  2. add_message/search_messages -> tsvector FTS round trip, lower=better
  3. JSON column round trip (Message.data) byte-identical
  4. claim_deliveries with 2 concurrent claimers -> exactly one wins
     (row-level atomicity on postgres — the multi-machine mailbox story)
  5. get_ro_engine     -> SELECT ok, INSERT refused by the server

Usage:
  uv --project . run python scripts/e2e_postgres_live.py
"""

import subprocess
import threading
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from crow_cli.memory import (
    add_message,
    claim_deliveries,
    create_agent,
    create_database,
    finish_task,
    get_engine,
    get_ro_engine,
    launch_task,
    load_messages,
    search_messages,
)

PORT = 15432
CONTAINER = "crow-pg-e2e"
USER = PASSWORD = DB = "crowe2e"
URI = f"postgresql+psycopg://{USER}:{PASSWORD}@127.0.0.1:{PORT}/{DB}"


def docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def start_postgres() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    docker(
        "run", "-d", "--name", CONTAINER,
        "-p", f"{PORT}:5432",
        "-e", f"POSTGRES_USER={USER}",
        "-e", f"POSTGRES_PASSWORD={PASSWORD}",
        "-e", f"POSTGRES_DB={DB}",
        "postgres:17-alpine",
    )
    # Probe with a REAL connection: pg_isready can succeed against the
    # throwaway server the image runs during initdb, before the restart.
    for _ in range(60):
        try:
            probe = get_engine(URI)
            with probe.connect() as conn:
                conn.execute(text("SELECT 1"))
            probe.dispose()
            print(f"[ok] postgres accepting connections at 127.0.0.1:{PORT}")
            return
        except SQLAlchemyError:
            time.sleep(1)
    raise SystemExit("[FAIL] postgres never became ready")


def stop_postgres() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    print("[ok] container removed")


def run() -> None:
    # ---- 1: schema + FTS objects on postgres ----
    create_database(URI)
    engine = get_engine(URI)
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        }
        indexes = {
            r[0]
            for r in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            )
        }
    for t in ("agents", "messages", "tasks", "task_deliveries", "prompts", "messages_fts"):
        assert t in tables, f"missing table {t}: {tables}"
    assert "idx_messages_fts_tsv" in indexes, f"missing GIN index: {indexes}"
    print("[ok] create_database: tables + messages_fts + GIN index")

    # ---- 2: FTS write/search round trip, lower=better contract ----
    create_agent(
        engine,
        agent_id="e2e-pg-1-1",
        session_id="e2e-pg",
        agent_idx=1,
        cwd="/tmp",
        system_prompt="sp",
        tool_definitions=[],
        request_params={},
        model_identifier="m",
    )
    add_message(
        engine, "e2e-pg-1-1",
        {"role": "user", "content": "the quick brown fox jumps over the lazy dog"},
    )
    add_message(
        engine, "e2e-pg-1-1",
        {"role": "user", "content": "postgres full text search drill"},
    )
    hits = search_messages(engine, "postgres search", limit=10)
    assert len(hits) == 1, f"expected 1 hit, got {len(hits)}"
    assert hits[0]["session_id"] == "e2e-pg"
    assert hits[0]["score"] < 0, f"ts_rank must be negated (lower=better): {hits[0]['score']}"
    hits2 = search_messages(engine, "fox dog", limit=10)
    assert len(hits2) == 1 and "fox" in hits2[0]["data"]["content"]
    assert search_messages(engine, "   ", limit=10) == []
    print("[ok] search_messages: tsvector round trip, lower=better, empty-safe")

    # ---- 3: JSON column round trip ----
    rich_msg = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "json round trip"},
            {"type": "tool_call", "name": "terminal", "arguments": {"command": "ls -la"}},
        ],
        "reasoning_content": "nested dicts survive",
    }
    add_message(engine, "e2e-pg-1-1", rich_msg)
    rows = load_messages(engine, "e2e-pg-1-1")
    stored = [r for r in rows if r.get("reasoning_content")]
    assert len(stored) == 1 and stored[0] == rich_msg, f"round trip mismatch: {stored}"
    print("[ok] Message.data JSON round trip: identical dict")

    # ---- 4: mailbox exactly-once under concurrent claimers ----
    launch_task(
        engine,
        task_id="e2e-t1",
        owner_session="e2e-pg",
        tool_call_id="tc1",
        prompt="drill",
    )
    assert finish_task(engine, "e2e-t1", result="done", content="completion payload")

    barrier = threading.Barrier(2)
    results: list[list] = [[], []]

    def claim(i: int) -> None:
        barrier.wait()
        results[i] = claim_deliveries(engine, "e2e-pg")

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = [d for r in results for d in r]
    assert len(total) == 1, f"delivery claimed {len(total)} times: {results}"
    assert total[0]["content"] == "completion payload"
    print("[ok] claim_deliveries: 2 concurrent claimers, exactly one won")

    # ---- 5: read-only engine enforced by the server ----
    ro = get_ro_engine(URI)
    with ro.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM messages")).scalar() == 3
    try:
        with ro.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO prompts(id, name, template, created_at) "
                    "VALUES ('x', 'x', 'x', 'x')"
                )
            )
        raise AssertionError("read-only engine accepted a write")
    except SQLAlchemyError as e:
        assert "read-only" in str(e).lower(), f"unexpected error: {e}"
    print("[ok] get_ro_engine: SELECT ok, INSERT refused by postgres")

    engine.dispose()
    ro.dispose()
    print("\nE2E-POSTGRES-OK")


if __name__ == "__main__":
    if subprocess.run(["docker", "pull", "postgres:17-alpine"], capture_output=True).returncode != 0:
        print("[..] pull failed — trying cached image")
    start_postgres()
    try:
        run()
    finally:
        stop_postgres()
