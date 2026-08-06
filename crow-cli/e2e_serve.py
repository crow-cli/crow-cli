#!/usr/bin/env python3
"""9.6 + 13.3 e2e: `crowctl serve <name>` / `crowctl acp --http` — ACP over HTTP.

Spawns the server, then drives the full v2 lifecycle over POST /acp + SSE:
initialize -> session/new -> session/prompt -> idle, then (13.3) drops the
connection, reconnects, session/resume, and checks the session remembers a
secret word — sessions must outlive connections.

    uv run python e2e_serve.py                # serves 'crow' on 8095
    uv run python e2e_serve.py acp-http 8096  # resident `crowctl acp --http`
    uv run python e2e_serve.py verifier 8096  # chain (single-turn only)

Needs: httpx in the venv, a built target/debug/crowctl, configured LLM.
"""
import json
import pathlib
import subprocess
import sys
import threading
import time

import httpx

TIMEOUT = 150.0
MARKER = "HTTP-BRIDGE-OK"
SECRET = "KUMQUAT"


def read_sse(base, headers, sink, stop):
    try:
        with httpx.stream("GET", base, headers=headers, timeout=None) as r:
            for line in r.iter_lines():
                if stop.is_set():
                    return
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data:
                        try:
                            sink.append(json.loads(data))
                        except json.JSONDecodeError:
                            sink.append({"_raw": data})
    except Exception as e:  # noqa: BLE001
        sink.append({"_sse_error": str(e)})


def wait_for(events, pred, desc, timeout=TIMEOUT):
    """events: list object (polled live) or callable returning one."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        src = events() if callable(events) else events
        for ev in src:
            if pred(ev):
                return ev
        time.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {desc}")


def is_idle(sess):
    def pred(e):
        p = e.get("params", {})
        u = p.get("update", {}) if isinstance(p, dict) else {}
        return (
            p.get("sessionId") == sess
            and u.get("sessionUpdate") == "state_update"
            and u.get("state") == "idle"
        )
    return pred


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "crow"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8095
    ctl = pathlib.Path(__file__).parent / ".." / "target" / "debug" / "crowctl"
    base = f"http://127.0.0.1:{port}/acp"

    if target == "acp-http":
        cmd = [str(ctl.resolve()), "acp", "--http", "--port", str(port)]
    else:
        cmd = [str(ctl.resolve()), "serve", target, "--port", str(port)]
    server = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        # health gate
        t0 = time.time()
        while time.time() - t0 < 15:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).text == "ok":
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        else:
            raise RuntimeError("server never became healthy")

        stop = threading.Event()
        conn_events, sess_events = [], []

        # ---- connection A: initialize (spawns/attaches the agent) ----
        r = httpx.post(
            base,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": 2,
                    "info": {"name": "e2e-serve", "version": "0"},
                },
            },
            timeout=60,
        )
        conn_id = r.headers.get("acp-connection-id")
        assert r.status_code == 200 and conn_id and "result" in r.json(), (
            r.status_code,
            r.text[:300],
        )
        print(f"PASS initialize (agent info: {r.json()['result'].get('info')})")

        threading.Thread(
            target=read_sse,
            args=(base, {"Accept": "text/event-stream", "Acp-Connection-Id": conn_id},
                  conn_events, stop),
            daemon=True,
        ).start()

        # session/new (response rides the connection SSE stream)
        r = httpx.post(
            base,
            headers={"Acp-Connection-Id": conn_id},
            json={"jsonrpc": "2.0", "id": 2, "method": "session/new",
                  "params": {"cwd": "/tmp", "mcpServers": []}},
            timeout=30,
        )
        assert r.status_code in (200, 202), (r.status_code, r.text[:300])
        ev = wait_for(conn_events, lambda e: e.get("id") == 2 and "result" in e,
                      "session/new response")
        sess = ev["result"]["sessionId"]
        print(f"PASS session/new -> {sess}")

        threading.Thread(
            target=read_sse,
            args=(base, {"Accept": "text/event-stream", "Acp-Connection-Id": conn_id,
                         "Acp-Session-Id": sess}, sess_events, stop),
            daemon=True,
        ).start()
        time.sleep(0.3)

        # session/prompt: store a secret word AND emit the marker
        r = httpx.post(
            base,
            headers={"Acp-Connection-Id": conn_id, "Acp-Session-Id": sess},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session/prompt",
                "params": {
                    "sessionId": sess,
                    "prompt": [{"type": "text",
                                "text": f"Remember the secret word: {SECRET}. "
                                        f"Then reply with exactly: {MARKER}"}],
                },
            },
            timeout=30,
        )
        assert r.status_code in (200, 202), (r.status_code, r.text[:300])
        wait_for(lambda: sess_events + conn_events, lambda e: e.get("id") == 3, "prompt ack")
        print("PASS prompt acked")

        idle = wait_for(sess_events, is_idle(sess), "state_update idle")
        ok = MARKER in json.dumps(sess_events)
        print(
            f"PASS turn completed (stop_reason={idle['params']['update'].get('stopReason')}, "
            f"marker={'seen' if ok else 'NOT seen'})"
        )
        if not ok:
            raise RuntimeError("model output marker missing from session stream")

        # Chains (e.g. verifier) are out of scope for reconnect-resume (13.3):
        # single-turn bridge coverage only.
        if target not in ("crow", "acp-http"):
            stop.set()
            httpx.delete(base, headers={"Acp-Connection-Id": conn_id}, timeout=10)
            print(f"PASS e2e complete (single-turn): crowctl serve {target}")
            return

        # ---- 13.3: drop connection A, reconnect, resume, recall ----
        stop.set()
        r = httpx.delete(base, headers={"Acp-Connection-Id": conn_id}, timeout=10)
        assert r.status_code in (200, 202), (r.status_code, r.text[:300])
        print(f"PASS connection dropped ({r.status_code}); reconnecting")
        time.sleep(1)

        stop_b = threading.Event()
        conn_b, sess_b = [], []
        r = httpx.post(
            base,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": 2,
                    "info": {"name": "e2e-serve-reconnect", "version": "0"},
                },
            },
            timeout=60,
        )
        conn_b_id = r.headers.get("acp-connection-id")
        assert r.status_code == 200 and conn_b_id, (r.status_code, r.text[:300])
        threading.Thread(
            target=read_sse,
            args=(base, {"Accept": "text/event-stream", "Acp-Connection-Id": conn_b_id},
                  conn_b, stop_b),
            daemon=True,
        ).start()

        # session/resume needs the Acp-Session-Id header; its response and the
        # replay ride the SESSION-level stream (params carry sessionId).
        r = httpx.post(
            base,
            headers={"Acp-Connection-Id": conn_b_id, "Acp-Session-Id": sess},
            json={"jsonrpc": "2.0", "id": 2, "method": "session/resume",
                  "params": {"sessionId": sess, "cwd": "/tmp",
                             "replayFrom": {"type": "start"}}},
            timeout=60,
        )
        assert r.status_code in (200, 202), (r.status_code, r.text[:300])
        threading.Thread(
            target=read_sse,
            args=(base, {"Accept": "text/event-stream", "Acp-Connection-Id": conn_b_id,
                         "Acp-Session-Id": sess}, sess_b, stop_b),
            daemon=True,
        ).start()
        ev = wait_for(lambda: sess_b + conn_b,
                      lambda e: e.get("id") == 2 and "result" in e, "resume response")
        assert "error" not in ev, f"resume errored: {ev}"
        print("PASS session/resume on fresh connection")

        # recall the secret word
        r = httpx.post(
            base,
            headers={"Acp-Connection-Id": conn_b_id, "Acp-Session-Id": sess},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session/prompt",
                "params": {
                    "sessionId": sess,
                    "prompt": [{"type": "text",
                                "text": "What was the secret word I told you? "
                                        "Answer with just the word."}],
                },
            },
            timeout=30,
        )
        assert r.status_code in (200, 202), (r.status_code, r.text[:300])
        wait_for(lambda: sess_b + conn_b, lambda e: e.get("id") == 3, "recall ack")
        wait_for(sess_b, is_idle(sess), "recall idle")
        if SECRET not in json.dumps(sess_b):
            raise RuntimeError(
                f"secret '{SECRET}' not recalled after reconnect — "
                f"session did not outlive the connection"
            )
        print(f"PASS reconnect-resume: secret '{SECRET}' recalled after connection drop")

        stop_b.set()
        httpx.delete(base, headers={"Acp-Connection-Id": conn_b_id}, timeout=10)
        mode = "acp --http (resident)" if target == "acp-http" else f"serve {target}"
        print(f"PASS e2e complete: {mode}")
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
