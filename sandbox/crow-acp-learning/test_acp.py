#!/usr/bin/env python3
"""Simple synchronous test script for crow-cli ACP protocol."""

import json
import subprocess
import sys
import threading
import time


def main():
    workspace = sys.argv[1] if len(sys.argv) > 1 else "/home/thomas/src/crow-ai"

    print("=== Spawning crow-cli acp ===")
    proc = subprocess.Popen(
        ["crow-cli", "acp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=workspace,
    )

    # Reader thread
    responses = []
    def reader():
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if not line.startswith("{"):
                print(f"[NON-JSON] {line[:120]}")
                continue
            try:
                msg = json.loads(line)
                responses.append(msg)
                print(f"[RESPONSE] id={msg.get('id', 'N/A')} method={msg.get('method', 'N/A')}")
                if "error" in msg:
                    print(f"  ERROR: {json.dumps(msg['error'], indent=2)}")
                else:
                    print(f"  RESULT: {json.dumps(msg.get('result', {}), indent=2)[:500]}")
            except json.JSONDecodeError:
                print(f"[PARSE-ERR] {line[:200]}")
        print("[READER] stdout closed")

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    def send(method, params, msg_id):
        req = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        line = json.dumps(req) + "\n"
        print(f"\n[SEND] {method}")
        proc.stdin.write(line)
        proc.stdin.flush()

    # Wait for startup
    time.sleep(1)

    # 1. Initialize
    send("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test-script", "version": "0.1.0"}}, 1)
    time.sleep(2)

    # 2. List sessions
    send("session/list", {"cwd": workspace}, 2)
    time.sleep(2)

    # 3. Create new session
    send("session/new", {"cwd": workspace}, 3)
    time.sleep(2)

    print("\n=== Shutting down ===")
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    stderr = proc.stderr.read()
    if stderr:
        print(f"\n[STDERR]\n{stderr[:2000]}")

    print(f"\n=== Summary: received {len(responses)} responses ===")
    for r in responses:
        print(f"  id={r.get('id')}: {'error' if 'error' in r else 'ok'}")


if __name__ == "__main__":
    main()
