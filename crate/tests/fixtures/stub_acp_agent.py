#!/usr/bin/env python3
"""Stub ACP agent for the startup end-to-end tests.

Answers the bare minimum, logs every request it receives as JSONL, and takes
its behavior from the environment:

  STUB_LOG          path of the JSONL wire log (required)
  STUB_PROTOCOL     1 | 2 — which protocolVersion to answer `initialize` with.
                    The client sends one union request and the answer picks the
                    stack, so this is the only switch the two shapes need. A v1
                    agent answers 1 even though the request asked for 2; that
                    is the spec, and it is what the negotiation exists for.
  STUB_CAPS         load | resume | both | none — which re-attach methods exist
  STUB_LOAD_FAIL=1  the implemented re-attach methods refuse the id (-32602)
  STUB_HOLD=1       a v2 prompt acknowledges and goes running, then stops
                    talking. The turn stays open until something settles it,
                    which is what a cancel test needs: an agent that answers in
                    the same breath is already idle before the client can
                    interrupt it.
  STUB_ASK_PERMISSION=1
                    a v2 prompt asks `session/request_permission` and holds the
                    turn until the client answers. The reply is printed, so a
                    test can read the user's decision off the pane as well as
                    off the wire.
"""
import json
import os
import sys
import time

LOG = os.environ["STUB_LOG"]
CAPS = os.environ.get("STUB_CAPS", "load")
HAS_LOAD = CAPS in ("load", "both")
HAS_RESUME = CAPS in ("resume", "both")
REFUSE = os.environ.get("STUB_LOAD_FAIL") == "1"
HOLD = os.environ.get("STUB_HOLD") == "1"
ASK_PERMISSION = os.environ.get("STUB_ASK_PERMISSION") == "1"
V2 = os.environ.get("STUB_PROTOCOL", "1") == "2"

# The request id of the permission ask in flight, and the session holding it.
# A stub that answered its own permission request would only ever test the
# client's ability to talk to itself.
PERMISSION_RID = "perm-1"
AWAITING_PERMISSION = {}

log = open(LOG, "a", buffering=1)
MODES = {
    "currentModeId": "default",
    "availableModes": [{"id": "default", "name": "Default", "description": ""}],
}
MODEL_OPTIONS = [
    {"value": "stub-default", "name": "stub-default"},
    {"value": "qwen3.8-max", "name": "qwen3.8-max"},
]


LAST_PROMPT = ""


def note(msg):
    log.write(json.dumps({"t": round(time.time(), 3), "msg": msg}) + "\n")


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def update(sid, kind, **extra):
    send({
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"sessionId": sid, "update": {"sessionUpdate": kind, **extra}},
    })


def config_options(current):
    # v2 renamed the identifier `configId` and dropped the old key rather than
    # aliasing it. Everything else about the option is the same shape.
    key = "configId" if V2 else "id"
    return [{
        "type": "select",
        key: "model",
        "name": "Model",
        "currentValue": current,
        "options": MODEL_OPTIONS,
    }]


def session_setup(sid):
    if V2:
        # v2 has no session modes and no `models` block: the config options are
        # the whole snapshot.
        return {"sessionId": sid, "configOptions": config_options("stub-default")}
    return {
        "sessionId": sid,
        "modes": MODES,
        "models": {
            "currentModelId": "stub-default",
            "availableModels": MODEL_OPTIONS,
        },
        "configOptions": config_options("stub-default"),
    }


def state(sid, name, **extra):
    """A v2 `state_update`. The turn ends here, not in the prompt response."""
    update(sid, "state_update", state=name, **extra)


def turn(sid, text="stub reply ok"):
    """One v2 turn, in the order the real agent sends it.

    `session/prompt` answers `{}` first: that is an acknowledgement, not a
    result, and a client that treats it as the end of the turn stops listening
    before the agent has said anything.
    """
    # The echo of the prompt the client already drew. Forwarded to the
    # transcript it would print the line twice; dropped outright it would take
    # the replayed copy of an old prompt with it.
    send({"jsonrpc": "2.0", "method": "session/update", "params": {
        "sessionId": sid,
        "update": {"sessionUpdate": "user_message", "messageId": "u1",
                   "content": [{"type": "text", "text": LAST_PROMPT}]},
    }})
    state(sid, "running")
    update(sid, "agent_message_chunk", messageId="m2",
           content={"type": "text", "text": text})
    update(sid, "usage_update", used=1200, size=180000)
    state(sid, "idle", stopReason="end_turn",
          usage={"totalTokens": 1200, "inputTokens": 1180, "outputTokens": 20})


def replay_v2(sid):
    """A v2 `session/resume` replay: whole messages, not chunks.

    Every update here arrives BEFORE the resume response, and that ordering is
    the only thing separating a replayed prompt from a live echo. The client
    keeps a user_message that lands inside the window and drops one that lands
    after it, which is how the same notification is history in one case and a
    duplicate of a line the pane already drew in the other.
    """
    send({"jsonrpc": "2.0", "method": "session/update", "params": {
        "sessionId": sid,
        "update": {"sessionUpdate": "user_message", "messageId": "ru1",
                   "content": [{"type": "text", "text": "an older prompt"}]},
    }})
    send({"jsonrpc": "2.0", "method": "session/update", "params": {
        "sessionId": sid,
        "update": {"sessionUpdate": "agent_thought", "messageId": "rt1",
                   "content": [{"type": "text",
                                "text": "the stub thinks in italics"}]},
    }})
    # The real v2 agent sent no `tool_call` at all: the first thing it said
    # about the call was an in_progress `tool_call_update`. A patch for an id
    # nobody announced has to create the cell.
    send({"jsonrpc": "2.0", "method": "session/update", "params": {
        "sessionId": sid,
        "update": {"sessionUpdate": "tool_call_update", "toolCallId": "t1",
                   "title": "execute", "kind": "execute",
                   "status": "in_progress",
                   "rawInput": {"code": "print(6 * 7)"}},
    }})
    send({"jsonrpc": "2.0", "method": "session/update", "params": {
        "sessionId": sid,
        "update": {"sessionUpdate": "tool_call_update", "toolCallId": "t1",
                   "status": "completed",
                   "content": [{"terminalId": "term_t1", "type": "terminal"}],
                   "rawOutput": {"output": "42", "exit_code": None}},
    }})
    send({"jsonrpc": "2.0", "method": "session/update", "params": {
        "sessionId": sid,
        "update": {"sessionUpdate": "agent_message", "messageId": "rm1",
                   "content": [{"type": "text", "text": "replayed history line"}]},
    }})


def ask_permission(sid):
    """A v2 `session/request_permission`, in the shape the spec requires.

    The copy the user reads is the top-level `title`; v1 put it on the tool
    call, and a client still reading it there draws an empty box. The call it
    describes rides in `subject`. The turn then waits for the answer, because
    that is what an agent does.
    """
    AWAITING_PERMISSION[PERMISSION_RID] = sid
    state(sid, "running")
    send({"jsonrpc": "2.0", "id": PERMISSION_RID,
          "method": "session/request_permission",
          "params": {
              "sessionId": sid,
              "title": "Run this script?",
              "description": "wants to execute scripts/setup.sh",
              "subject": {"type": "command", "command": "cargo test",
                          "cwd": "/workspace"},
              "options": [
                  {"optionId": "allow", "name": "Allow once",
                   "kind": "allow_once"},
                  {"optionId": "deny", "name": "Reject once",
                   "kind": "reject_once"},
              ],
          }})


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    note(msg)
    method = msg.get("method")
    if method is None:
        # A response to the one request the stub makes. The turn it was holding
        # completes here, saying which option the user actually picked.
        sid = AWAITING_PERMISSION.pop(msg.get("id"), None)
        if sid is not None:
            outcome = (msg.get("result") or {}).get("outcome") or {}
            picked = outcome.get("optionId") or outcome.get("outcome") or "none"
            update(sid, "agent_message_chunk", messageId="m3",
                   content={"type": "text",
                            "text": "permission answer: " + str(picked)})
            state(sid, "idle", stopReason="end_turn")
        continue
    rid = msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        if V2:
            # v2 spells the agent's identity `info`, not `agentInfo`, and its
            # capabilities are presence markers nested under `session`.
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": 2,
                "info": {"name": "stub-agent", "title": "Stub", "version": "0.0.1"},
                "capabilities": {"session": {
                    "prompt": {"image": {}, "embeddedContext": {}},
                    "mcp": {"stdio": {}, "http": {}},
                    "fork": {},
                    **({"list": {}} if HAS_LOAD or HAS_RESUME else {}),
                }},
                "authMethods": [],
            }})
            continue
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": 1,
            "agentCapabilities": {
                "loadSession": HAS_LOAD,
                "sessionCapabilities": {"list": {}, **({"resume": {}} if HAS_RESUME else {})},
            },
            "agentInfo": {"name": "stub-agent", "title": "Stub", "version": "0.0.1"},
            "authMethods": [],
        }})
    elif method == "session/new":
        send({"jsonrpc": "2.0", "id": rid, "result": session_setup("stub-new-0001")})
    elif method in ("session/load", "session/resume"):
        # v2 has no `session/load` at all: resume + `replayFrom` replaced it.
        implemented = (HAS_LOAD and not V2) if method == "session/load" else HAS_RESUME
        if not implemented:
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32601, "message": "Method not found: " + method}})
            continue
        sid = params.get("sessionId") or "stub-loaded"
        if REFUSE:
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32602, "message": "no such session: " + sid}})
            continue
        if V2:
            replay_v2(sid)
            send({"jsonrpc": "2.0", "id": rid, "result": session_setup(sid)})
            continue
        # A replayed thought: the pane should open it without a click.
        update(sid, "agent_thought_chunk", messageId="th1",
               content={"type": "text", "text": "the stub thinks in italics"})
        # A replayed tool call: the pane should frame the command and keep it
        # on screen after the result lands.
        send({"jsonrpc": "2.0", "method": "session/update", "params": {
            "sessionId": sid,
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "t1",
                "title": "execute",
                "kind": "execute",
                "status": "in_progress",
                "rawInput": {"code": "print(6 * 7)"},
            },
        }})
        send({"jsonrpc": "2.0", "method": "session/update", "params": {
            "sessionId": sid,
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "t1",
                "status": "completed",
                "rawOutput": {"output": "42"},
            },
        }})
        # crow-cli's shape: no rawInput at all. The cell rides the call's
        # `content`, already fenced, and the completion repeats it ahead of
        # the output because clients merge update fields over the start.
        fence = {"type": "content",
                 "content": {"type": "text", "text": "```python\nprint(6 * 9)\n```"}}
        send({"jsonrpc": "2.0", "method": "session/update", "params": {
            "sessionId": sid,
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "t2",
                "title": "execute",
                "kind": "execute",
                "status": "pending",
                "content": [fence],
            },
        }})
        send({"jsonrpc": "2.0", "method": "session/update", "params": {
            "sessionId": sid,
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "t2",
                "status": "completed",
                "content": [fence, {"type": "content",
                                    "content": {"type": "text", "text": "54"}}],
            },
        }})
        update(sid, "agent_message_chunk", messageId="m1",
               content={"type": "text", "text": "replayed history line"})
        send({"jsonrpc": "2.0", "id": rid, "result": session_setup(sid)})
    elif method == "session/set_config_option":
        value = params.get("value")
        current = value.get("value") if isinstance(value, dict) else value
        send({"jsonrpc": "2.0", "id": rid,
              "result": {"configOptions": config_options(current or "stub-default")}})
    elif method == "session/prompt":
        sid = params.get("sessionId") or "stub-new-0001"
        blocks = params.get("prompt") or []
        LAST_PROMPT = "".join(
            b.get("text", "") for b in blocks if isinstance(b, dict)
        )
        if V2:
            # The acknowledgement goes out first, exactly as the real agent
            # does. Everything the turn actually produced follows it.
            send({"jsonrpc": "2.0", "id": rid, "result": {}})
            if ASK_PERMISSION:
                ask_permission(sid)
                continue
            if HOLD:
                state(sid, "running")
                continue
            turn(sid)
            continue
        update(sid, "agent_message_chunk", messageId="m2",
               content={"type": "text", "text": "stub reply ok"})
        send({"jsonrpc": "2.0", "id": rid, "result": {"stopReason": "end_turn"}})
    elif method == "session/cancel":
        # A notification: no id, no response. v2 cancellation is per-turn, so
        # the child is still promptable afterwards.
        if V2:
            state(params.get("sessionId") or "stub-new-0001", "idle",
                  stopReason="cancelled")
    elif method == "exit":
        break
    elif rid is not None:
        send({"jsonrpc": "2.0", "id": rid, "result": {}})
