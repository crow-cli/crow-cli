"""End-to-end wire contract: real crow-memory binary + real HTTP + this SDK.

Replaces the old rust-side tests (http_api.rs / images_api.rs) — the
contract is now enforced from the client side, because python IS the SDK.
No mocks anywhere: spawns `target/release/crow-memory` on a temp store.

Requires: cargo build --release -p crow-memory  (skips if absent).
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from crow_memory_sdk import MemoryApiError, SyncMemoryClient

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
BIN = WORKTREE_ROOT / "target" / "release" / "crow-memory"

# Minimal valid 1x1 RGBA PNG (68 bytes, len % 3 == 2 → padded base64 path).
PNG_1X1 = bytes(
    [
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
        0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
        0x0B, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x60, 0x00, 0x02, 0x00,
        0x00, 0x05, 0x00, 0x01, 0x7A, 0x5E, 0xAB, 0x3F, 0x00, 0x00, 0x00, 0x00,
        0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
    ]
)
PNG_2X2 = bytes(
    [
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
        0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x02,
        0x08, 0x02, 0x00, 0x00, 0x00, 0xFD, 0xD4, 0x9A, 0x73, 0x00, 0x00, 0x00,
        0x14, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0xF8, 0xCF, 0xC0, 0xC0,
        0x00, 0xC2, 0x0C, 0xFF, 0xFF, 0xFF, 0x67, 0x00, 0x00, 0x1E, 0xEF, 0x04,
        0xFC, 0xA3, 0xC8, 0xB4, 0xF7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
        0x44, 0xAE, 0x42, 0x60, 0x82,
    ]
)
PNG_1X1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII="
)
PNG_1X1_ID = "sha256:43739c566e26fd7cb88f69d3864ea34740372f5ee99acac169e090beffbce5c6"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def client():
    if not BIN.exists():
        pytest.skip(f"{BIN} missing — cargo build --release -p crow-memory")
    tmp = Path(tempfile.mkdtemp(prefix="crow-memory-e2e-"))
    config = tmp / "config.yaml"
    config.write_text(f"memory_path: {tmp / 'store.lance'}\n")
    port = _free_port()
    proc = subprocess.Popen(
        [str(BIN), "--config", str(config), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    c = SyncMemoryClient(base_url=f"http://127.0.0.1:{port}", timeout=15.0)
    deadline = time.time() + 60
    try:
        while time.time() < deadline:
            try:
                c.health()
                break
            except MemoryApiError:
                if proc.poll() is not None:
                    pytest.fail("crow-memory exited during startup")
                time.sleep(0.2)
        else:
            pytest.fail("crow-memory never became healthy")
        yield c
    finally:
        c.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def _mk_agent(client: SyncMemoryClient, agent_id: str, sess: str, idx: int, pid: str):
    client.create_agent(
        agent_id=agent_id,
        session_id=sess,
        agent_idx=idx,
        cwd="/tmp/w",
        prompt_id=pid,
        prompt_args={},
        system_prompt="you are crow",
        tool_definitions=[],
        request_params={},
        model_identifier="test-model",
    )


def test_full_api_round_trip(client: SyncMemoryClient):
    # prompts: create, hash-dedupe, fetch, 404 → None
    pid = client.lookup_or_create_prompt("hello {{name}}", "test-prompt")
    again = client.lookup_or_create_prompt("hello {{name}}", "test-prompt")
    assert pid == again, "same template must dedupe by hash"
    pr = client.get_prompt(pid)
    assert pr is not None
    assert pr.template == "hello {{name}}"
    assert pr.name == "test-prompt"
    assert client.get_prompt("nope-nope-nope") is None

    # agents: create, get, list, max idx
    _mk_agent(client, "a-1", "s-1", 0, pid)
    _mk_agent(client, "a-2", "s-1", 1, pid)
    a = client.get_agent("a-1")
    assert a is not None
    assert a.session_id == "s-1"
    assert a.prompt_args == {}
    assert client.get_agent("ghost") is None
    assert client.get_max_agent_idx("s-1") == 1
    assert len(client.list_agents(session_id="s-1")) == 2
    assert len(client.list_agents()) == 2

    # messages: append-only, ids increase, load in order
    id1 = client.add_message("a-1", {"role": "user", "content": "the sky is blue"})
    id2 = client.add_message(
        "a-1",
        {"role": "assistant", "content": "yes it is"},
        usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    )
    assert id2 > id1
    msgs = client.load_messages("a-1")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["content"] == "yes it is"

    # query by agent with role filter
    users = client.query_messages_by_agent("a-1", order_asc=True, limit=10, role="user")
    assert len(users) == 1
    assert users[0].role == "user"
    all_ = client.query_messages_by_agent("a-1", order_asc=False, limit=10)
    assert len(all_) == 2
    assert all_[0].id > all_[1].id, "order_asc=False → newest first"

    # semantic search (embedding server may be down → recent fallback;
    # either path must return the messages)
    hits = client.search_messages("sky", limit=10)
    assert hits
    user_hits = client.search_messages("sky", limit=10, role="user")
    assert all(m.role == "user" for m in user_hits)

    # sessions: aggregated from agents + messages
    sessions = client.list_sessions(limit=50)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.session_id == "s-1"
    assert s.message_count == 2
    assert s.agent_count == 2
    assert s.model_identifier == "test-model"
    # pagination
    assert client.list_sessions(limit=50, offset=1) == []


def test_concurrent_add_message_unique_ids(client: SyncMemoryClient):
    pid = client.lookup_or_create_prompt("test", "race")
    _mk_agent(client, "race-agent-1", "race-sess", 0, pid)

    # Before the id-allocation mutex, concurrent requests computed the same
    # id → duplicate message ids.
    n = 20

    def add(i: int) -> int:
        return client.add_message(
            "race-agent-1", {"role": "user", "content": f"concurrent message {i}"}
        )

    with ThreadPoolExecutor(max_workers=n) as pool:
        ids = list(pool.map(add, range(n)))
    assert len(set(ids)) == n, "concurrent add_message handed out duplicate ids"
    assert len(client.load_messages("race-agent-1")) == n


def test_list_sessions_stats_across_sessions(client: SyncMemoryClient):
    pid = client.lookup_or_create_prompt("test", "sessions")
    for agent_id, sess, idx in [
        ("ls-a-1", "ls-sess-a", 0),
        ("ls-b-1", "ls-sess-b", 0),
        ("ls-b-2", "ls-sess-b", 1),
        ("ls-c-1", "ls-sess-c", 0),
    ]:
        _mk_agent(client, agent_id, sess, idx, pid)

    # 3 messages to A, then 1 (newest) to B, none to C.
    for content in ["a one", "a two", "a three"]:
        client.add_message("ls-a-1", {"role": "user", "content": content})
    client.add_message("ls-b-1", {"role": "assistant", "content": "b last"})

    sessions = client.list_sessions(limit=50)
    assert len(sessions) == 3

    # Ordered by most-recent message activity: B (newest msg), A, then C.
    assert sessions[0].session_id == "ls-sess-b"
    assert sessions[0].message_count == 1
    assert sessions[0].agent_count == 2
    assert sessions[0].agent_idxs == [0, 1]
    assert sessions[0].last_role == "assistant"
    assert sessions[0].last_message is not None
    assert sessions[0].last_message.data["content"] == "b last"
    assert sessions[0].last_message.agent_id == "ls-b-1"

    assert sessions[1].session_id == "ls-sess-a"
    assert sessions[1].message_count == 3
    assert sessions[1].agent_count == 1
    assert sessions[1].last_role == "user"
    assert sessions[1].last_message.data["content"] == "a three"

    # Session with agents but no messages.
    assert sessions[2].session_id == "ls-sess-c"
    assert sessions[2].message_count == 0
    assert sessions[2].last_message is None


def test_image_round_trip(client: SyncMemoryClient):
    client.add_image("img-1", "image/png", PNG_1X1, 1, 1)
    img = client.get_image("img-1")
    assert img is not None
    assert img.image_id == "img-1"
    assert img.mime == "image/png"
    assert (img.w, img.h) == (1, 1)
    assert img.data == PNG_1X1, "bytes must survive the round trip exactly"
    assert img.created_at

    # A second image with different dims; both coexist.
    client.add_image("img-2", "image/jpeg", PNG_2X2, 2, 2)
    img2 = client.get_image("img-2")
    assert img2 is not None
    assert img2.mime == "image/jpeg"
    assert (img2.w, img2.h) == (2, 2)
    assert img2.data == PNG_2X2
    assert client.get_image("img-1").data == PNG_1X1  # first image untouched


def test_image_missing_is_none(client: SyncMemoryClient):
    assert client.get_image("ghost-image") is None


def test_message_image_extract_dedupe_hydrate(client: SyncMemoryClient):
    """Inline base64 goes in, image_ref comes out of the store, the images
    row is keyed sha256:<hex>, and a hydrated load hands back the exact
    data URL."""
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "what is this?"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{PNG_1X1_B64}"},
            },
        ],
    }
    client.add_message("img-agent-1", msg)

    # Stored data carries an image_ref, not the base64 blob.
    raw = client.load_messages("img-agent-1")
    assert len(raw) == 1
    content = raw[0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_ref"
    assert content[1]["image_id"] == PNG_1X1_ID
    assert content[1]["mime"] == "image/png"
    assert "iVBORw0KGgo" not in str(raw[0]), (
        "base64 payload must not be persisted in message data"
    )

    # Images row keyed by sha256:, bytes exact.
    img = client.get_image(PNG_1X1_ID)
    assert img is not None
    assert img.mime == "image/png"
    assert img.data == PNG_1X1

    # Same bytes again, ACP-style block this time.
    client.add_message(
        "img-agent-1",
        {"role": "user", "content": [
            {"type": "image", "data": PNG_1X1_B64, "mimeType": "image/png"}
        ]},
    )
    # (row-count dedupe check lived in lancedb directly in the old rust test;
    # observable contract here: same id still resolves to the exact bytes)
    assert client.get_image(PNG_1X1_ID).data == PNG_1X1

    # Hydrated load: image_ref → inline data URL, bytes identical.
    hydrated = client.load_messages("img-agent-1", hydrate=True)
    assert len(hydrated) == 2
    want_url = f"data:image/png;base64,{PNG_1X1_B64}"
    assert hydrated[0]["content"][1]["type"] == "image_url"
    assert hydrated[0]["content"][1]["image_url"]["url"] == want_url
    assert hydrated[1]["content"][0]["type"] == "image_url"
    assert hydrated[1]["content"][0]["image_url"]["url"] == want_url

    # Non-hydrated load still shows the refs.
    raw_again = client.load_messages("img-agent-1")
    assert raw_again[1]["content"][0]["type"] == "image_ref"


def test_fails_fast_on_4xx(client: SyncMemoryClient):
    """4xx must NOT retry with backoff (the v1 retry-storm lesson)."""
    start = time.time()
    resp = client._request("GET", "/v1/definitely-not-a-route")
    with pytest.raises(MemoryApiError) as ei:
        client._raise_for_status(resp)
    assert ei.value.status == 404
    assert time.time() - start < 2


def test_wedged_server_times_out():
    """A server that accepts TCP but never answers must error, not hang —
    the exact wedge that used to hang every persist/memory call forever."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    port = srv.getsockname()[1]
    # Hold connections open, never write a byte.
    import threading

    def hold():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=conn.recv, args=(1,), daemon=True).start()

    threading.Thread(target=hold, daemon=True).start()

    c = SyncMemoryClient(
        base_url=f"http://127.0.0.1:{port}", timeout=0.25, max_retries=2
    )
    start = time.time()
    with pytest.raises(MemoryApiError) as ei:
        c.health()
    assert time.time() - start < 15, "silent server must error, not hang"
    assert ei.value.status == 0
    c.close()
    srv.close()
