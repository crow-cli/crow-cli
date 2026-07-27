"""HTTP-layer smoke test via FastAPI TestClient (in-process, real routing)."""

import base64
import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from crow_memory.server import build_app

TEST_IMG = Path("/home/thomas/src/crow-team/crow-cli/sandbox/lancedb-testing/test_images/img_003.png")


def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    assert cond, label


def main():
    tmp = tempfile.mkdtemp(prefix="crowmem_http_")
    app = build_app(store_path=tmp)
    print("starting TestClient (loads both models)...\n")
    with TestClient(app) as c:
        check("health", c.get("/health").json()["status"] == "ok")

        # prompt + agent
        pr = c.post("/prompts", json={"id": "p1", "name": "sys", "template": "You are {{ name }}"}).json()
        check("prompt created", pr["created"] is True)
        ag = c.post("/agents", json={
            "agent_id": "http-agent-1", "session_id": "http-sess", "agent_idx": 1,
            "cwd": "/tmp", "prompt_id": "p1", "system_prompt": "You are crow",
            "tool_definitions": [{"name": "read"}], "model_identifier": "test-model",
        }).json()
        check("agent created", ag["agent_id"] == "http-agent-1")
        check("max_idx reflects agent", c.get("/sessions/http-sess/max-idx").json()["max_agent_idx"] == 1)

        # message with inline image
        raw = TEST_IMG.read_bytes()
        b64 = base64.b64encode(raw).decode()
        msg = {"role": "user", "content": [
            {"type": "text", "text": "screenshot of the terminal output"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}
        ar = c.post("/agents/http-agent-1/messages", json={"message": msg,
                                                           "usage": {"total_tokens": 42}}).json()
        check("message added, image extracted", len(ar["image_ids"]) == 1)
        image_id = ar["image_ids"][0]

        # load back (image-free) and hydrated
        loaded = c.get("/agents/http-agent-1").json()
        check("load returns agent + 1 message", loaded["agent"]["agent_id"] == "http-agent-1" and len(loaded["messages"]) == 1)
        check("stored message is image-free", "base64," not in str(loaded["messages"][0]))
        hydrated = c.get("/agents/http-agent-1", params={"hydrate": True}).json()
        check("hydrated message has data URL", "data:image/png;base64," in str(hydrated["messages"][0]))

        # image bytes endpoint
        img_resp = c.get(f"/images/{image_id}")
        check("image bytes endpoint round-trips", img_resp.status_code == 200 and img_resp.content == raw)
        check("image content-type", img_resp.headers["content-type"] == "image/png")

        # search: text -> messages
        s_text = c.post("/search", json={"query": "screenshot of the terminal", "modality": "text", "limit": 3}).json()
        check("text search hits the message", len(s_text["messages"]) >= 1 and s_text["messages"][0]["agent_id"] == "http-agent-1")

        # search: text -> images
        s_img = c.post("/search", json={"query": "a screenshot of code", "modality": "image", "limit": 3}).json()
        check("image search hits the image", len(s_img["images"]) >= 1 and s_img["images"][0]["image_id"] == image_id)

        # search: both
        s_both = c.post("/search", json={"query": "terminal screenshot", "modality": "both", "limit": 3}).json()
        check("both-modality returns messages AND images", len(s_both["messages"]) >= 1 and len(s_both["images"]) >= 1)

        # search: image -> image
        s_i2i = c.post("/search", json={"modality": "image", "query_image_b64": b64, "limit": 3}).json()
        check("image->image search hits itself", len(s_i2i["images"]) >= 1 and s_i2i["images"][0]["image_id"] == image_id)

    print("\nALL HTTP CHECKS PASSED ✔")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
