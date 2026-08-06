#!/usr/bin/env python3
"""E2E test for the crow-verifier conductor proxy (FAIL path).

Chain: this script (ACP client) → conductor → crow-verifier (proxy) → crowctl acp (worker)
                                          ↕ HTTP
                                    verifier daemon (crow-server on :8081)

The worker is told to refuse a file-write task. Expected flow:
  worker refuses → idle (held by proxy) → verifier reads history, checks disk,
  verdict(pass=false) → proxy re-prompts worker with feedback → worker writes
  the file → idle → verifier verdict(pass=true) → idle forwarded to us.

Prereqs:
  - conductor built with v2:  cd ../rust-sdk && PROTOC=~/.local/bin/protoc \
      cargo build -p agent-client-protocol-conductor --features unstable_protocol_v2 -j 2
  - crow-verifier + crowctl built:  PROTOC=~/.local/bin/protoc cargo build -j 2
  - verifier daemon running:  crow-server --port 8081 -d /tmp/verifier-config

Pass = /tmp/verifier-test.txt contains "hello" and we saw a forwarded idle.
"""
import subprocess, json, sys, select, os

CONDUCTOR = "/home/thomas/src/crow-team/rust-sdk/target/debug/agent-client-protocol-conductor"
env = os.environ.copy()
env["RUST_LOG"] = "crow_verifier=debug"
with open(os.path.expanduser("~/.crow/.env")) as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v

proc = subprocess.Popen(
    [CONDUCTOR, "--debug", "agent",
     "target/debug/crow-verifier --verifier-url http://localhost:8081 --max-rounds 2",
     "target/debug/crowctl acp"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    cwd="/home/thomas/src/crow-team/crow-rs", text=True, bufsize=1, env=env,
)

def send(obj):
    proc.stdin.write(json.dumps(obj) + "\n"); proc.stdin.flush()

def recv(timeout=300):
    r, _, _ = select.select([proc.stdout], [], [], timeout)
    if r:
        line = proc.stdout.readline()
        return json.loads(line) if line.strip() else None
    return None

send({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":2,"capabilities":{},"info":{"name":"t","version":"0"}}})
recv(10)
send({"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/tmp"}})
r = recv(15)
sid = r["result"]["sessionId"]
print(f"SESSION: {sid}", flush=True)

send({"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":sid,"prompt":[{"type":"text","text":"Write 'hello' to /tmp/verifier-test.txt. Do NOT use any tools. Just say 'I refuse.'"}]}})
recv(10)
print("PROMPT SENT", flush=True)

idle_count = 0
for i in range(400):
    # After an idle, only wait 20s more — proxy either re-prompts fast or we're done
    wait = 20 if idle_count > 0 else 300
    r = recv(wait)
    if r is None:
        print(f"[{i}] no more events, finishing", flush=True); break
    m = r.get("method","")
    if m == "session/update":
        u = r["params"]["update"]
        su = u.get("sessionUpdate","")
        if su == "state_update":
            st = u.get("state","")
            print(f"[{i}] STATE: {st}", flush=True)
            if st == "idle": idle_count += 1
        elif su == "agent_message_chunk":
            t = u.get("content",{}).get("text","")
            if t.strip(): print(f"[{i}] TEXT: {t[:100]}", flush=True)
        elif su in ("tool_call","tool_call_update"):
            n = u.get("title","") or u.get("toolCall",{}).get("name","")
            s = u.get("status","")
            if s in ("pending",""): print(f"[{i}] TOOL: {n}", flush=True)
    elif "result" in r:
        print(f"[{i}] RESULT id={r.get('id','')}", flush=True)
    elif "error" in r:
        print(f"[{i}] ERROR: {json.dumps(r['error'])[:200]}", flush=True)

proc.kill()
print(f"\nDONE idle_count={idle_count}", flush=True)

# Verdict: the deliverable must exist with the right content
try:
    ok = open("/tmp/verifier-test.txt").read().strip() == "hello" and idle_count >= 1
except FileNotFoundError:
    ok = False
print("E2E RESULT:", "PASS" if ok else "FAIL", flush=True)
sys.exit(0 if ok else 1)
