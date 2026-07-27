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

        # prompt lookup-or-create (content-addressed by template, coolname id)
        pr = c.post("/prompts", json={"name": "sys", "template": "You are {{ name }}"}).json()
        check("prompt created", pr["created"] is True)
        check("prompt got a coolname id", bool(pr["id"]))
        pr2 = c.post("/prompts", json={"name": "sys", "template": "You are {{ name }}"}).json()
        check("same template -> same id, not recreated", pr2["id"] == pr["id"] and pr2["created"] is False)
        ag = c.post("/agents", json={
            "agent_id": "http-agent-1", "session_id": "http-sess", "agent_idx": 1,
            "cwd": "/tmp", "prompt_id": pr["id"], "system_prompt": "You are crow",
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

        # ---- new endpoints for the crow-cli/query_memory integration ----
        # GET /prompts/{id}
        gp = c.get(f"/prompts/{pr['id']}").json()
        check("get_prompt by id", gp["id"] == pr["id"] and "You are" in gp["template"])

        # GET /agents (list) + session filter
        agents = c.get("/agents").json()
        check("list_agents returns our agent", any(a["agent_id"] == "http-agent-1" for a in agents))
        agents_filt = c.get("/agents", params={"session_id": "http-sess"}).json()
        check("list_agents session filter", len(agents_filt) == 1 and agents_filt[0]["session_id"] == "http-sess")

        # POST /messages/query — the browse primitive query_memory rides on
        mq = c.post("/messages/query", json={"session_id": "http-sess"}).json()
        check("query_messages by session returns the message", len(mq) == 1 and mq[0]["role"] == "user")
        check("query_messages attaches session/agent meta", mq[0]["session_id"] == "http-sess" and mq[0]["agent_idx"] == 1)
        mq_role = c.post("/messages/query", json={"session_id": "http-sess", "roles": ["assistant"]}).json()
        check("query_messages role filter (no assistant -> empty)", len(mq_role) == 0)
        mq_desc = c.post("/messages/query", json={"session_id": "http-sess", "order": "desc"}).json()
        check("query_messages desc order works", len(mq_desc) == 1)

    print("\nALL HTTP CHECKS PASSED ✔")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
