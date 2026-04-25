#!/usr/bin/env python3
"""
Tool call persistence integrity test.

Stores messages with tool_calls through the actual session.py code path,
loads them back, and compares byte-for-byte — specifically targeting
the tool_call arguments where drift would hide.

Run:
  cd crow-cli/sandbox/async-react && uv --project . run tool_call_integrity_test.py
"""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

# crow-cli is a dependency in pyproject.toml
from crow_cli.agent.db import Base, Message, Session as SessionModel, create_database
from crow_cli.agent.session import Session, get_coolname
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SQLAlchemySession


def sha256(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def byte_diff(s1: str, s2: str) -> str:
    """Human-readable diff between two strings."""
    if s1 == s2:
        return "identical"
    b1 = s1.encode("utf-8")
    b2 = s2.encode("utf-8")
    parts = []
    parts.append(f"len: {len(b1)} vs {len(b2)} (delta={len(b2) - len(b1)})")
    # Find first difference
    for i in range(min(len(b1), len(b2))):
        if b1[i] != b2[i]:
            start = max(0, i - 20)
            end = min(len(b1), len(b2), i + 40)
            parts.append(
                f"diff at byte {i}: ...{b1[start:end]}... vs ...{b2[start:end]}..."
            )
            break
    if len(b1) != len(b2):
        longer = b1 if len(b1) > len(b2) else b2
        shorter = b2 if len(b1) > len(b2) else b1
        parts.append(
            f"extra at end of longer: ...{longer[len(shorter) : len(shorter) + 40]}..."
        )
    return " | ".join(parts)


# Build 28 tool call messages to simulate the reported scenario
def build_test_messages(num_tool_calls: int = 28):
    """Build messages that simulate many turns of tool calling."""
    messages = [{"role": "system", "content": "You are a test assistant."}]

    for i in range(num_tool_calls):
        # Simulate assistant response with tool calls
        tool_call_msg = {
            "role": "assistant",
            "content": f"I'll help with task {i}.",
            "reasoning_content": f"Thinking about task {i}...",
            "tool_calls": [
                {
                    "id": f"call_{i:04d}_a",
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "arguments": json.dumps(
                            {
                                "queries": [
                                    f"machine learning paper {i} transformer",
                                    f"attention mechanism variant {i}",
                                ]
                            }
                        ),
                    },
                },
                {
                    "id": f"call_{i:04d}_b",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            {
                                "path": f"/tmp/data/task_{i:04d}.txt",
                                "encoding": "utf-8",
                                "max_chars": 50000,
                            }
                        ),
                    },
                },
            ],
        }
        messages.append(tool_call_msg)

        # Tool results
        for tc in tool_call_msg["tool_calls"]:
            result_msg = {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": f"Result for {tc['function']['name']} call {i}: "
                + "x" * (100 + i * 50),  # Varying length
            }
            messages.append(result_msg)

    return messages


def main():
    tmpdir = Path(tempfile.mkdtemp(prefix="crow-toolcall-test-"))
    db_path = tmpdir / "test.db"
    db_uri = f"sqlite:///{db_path}"

    print(f"DB: {db_uri}")
    print()

    # Create database
    create_database(db_uri)

    # Create session record
    session_id = get_coolname()
    engine = create_engine(db_uri)
    db = SQLAlchemySession(engine)
    db.add(
        SessionModel(
            session_id=session_id,
            system_prompt="test",
            tool_definitions=[],
            request_params={},
            model_identifier="qwen3.5-plus",
        )
    )
    db.commit()
    db.close()

    # Build test messages
    messages = build_test_messages(28)
    print(f"Built {len(messages)} messages ({28} tool call pairs)")

    # ── Step 1: Store through actual Session.add_message() ──
    print("\n[Step 1] Storing messages via Session.add_message()...")
    session = Session(session_id, db_uri=db_uri, cwd="/tmp")
    session.model_identifier = "qwen3.5-plus"

    for msg in messages:
        session.add_message(msg)

    print(f"  Stored {len(session.messages)} messages")

    # ── Step 2: Compute hashes of in-memory messages ──
    print("\n[Step 2] Computing in-memory hashes...")
    mem_hashes = {}
    mem_tool_args = {}
    for i, msg in enumerate(session.messages):
        mem_hashes[i] = sha256(msg)
        if "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                args = tc["function"]["arguments"]
                mem_tool_args[(i, tc["id"])] = args

    # ── Step 3: Load through actual Session.load() ──
    print("\n[Step 3] Loading via Session.load()...")
    loaded_session = Session.load(session_id, db_uri=db_uri)
    print(f"  Loaded {len(loaded_session.messages)} messages")

    # ── Step 4: Compare ──
    print("\n[Step 4] Comparing in-memory vs loaded...")

    count_mismatch = len(session.messages) != len(loaded_session.messages)
    hash_mismatches = 0
    tool_arg_mismatches = 0

    max_len = max(len(session.messages), len(loaded_session.messages))
    for i in range(max_len):
        if i >= len(session.messages):
            print(f"  [{i:03d}] MISSING from in-memory")
            continue
        if i >= len(loaded_session.messages):
            print(f"  [{i:03d}] MISSING from loaded")
            continue

        mem = session.messages[i]
        loaded = loaded_session.messages[i]

        mem_hash = mem_hashes[i]
        loaded_hash = sha256(loaded)

        if mem_hash != loaded_hash:
            hash_mismatches += 1
            role = mem.get("role", "?")
            print(f"  [{i:03d}] role={role}: HASH MISMATCH")

            # Find which field differs
            all_keys = set(mem.keys()) | set(loaded.keys())
            for key in sorted(all_keys):
                mv = mem.get(key)
                lv = loaded.get(key)
                if mv != lv:
                    if key == "tool_calls":
                        print(f"    [{key}] tool_calls differ")
                        # Compare each tool call
                        if mv and lv:
                            for j, (mtc, ltc) in enumerate(zip(mv, lv)):
                                if sha256(mtc) != sha256(ltc):
                                    for f in set(mtc.keys()) | set(ltc.keys()):
                                        mfv = mtc.get(f)
                                        lfv = ltc.get(f)
                                        if mfv != lfv:
                                            if f == "arguments":
                                                diff = byte_diff(str(mfv), str(lfv))
                                                print(f"      tool[{j}].{f}: {diff}")
                                            else:
                                                print(
                                                    f"      tool[{j}].{f}: {str(mfv)[:80]} vs {str(lfv)[:80]}"
                                                )
                    elif isinstance(mv, str) and isinstance(lv, str):
                        diff = byte_diff(mv, lv)
                        print(f"    [{key}] {diff}")
                    else:
                        print(f"    [{key}] VALUES DIFFER")

            # Check tool args specifically
            if "tool_calls" in mem:
                for tc in mem["tool_calls"]:
                    key = (i, tc["id"])
                    if key in mem_tool_args:
                        # Find matching loaded tool call
                        if "tool_calls" in loaded:
                            for ltc in loaded["tool_calls"]:
                                if ltc["id"] == tc["id"]:
                                    if (
                                        ltc["function"]["arguments"]
                                        != tc["function"]["arguments"]
                                    ):
                                        tool_arg_mismatches += 1
                                        diff = byte_diff(
                                            tc["function"]["arguments"],
                                            ltc["function"]["arguments"],
                                        )
                                        print(
                                            f"    *** TOOL ARG DRIFT *** call={tc['id']}: {diff}"
                                        )

    # ── Step 5: Summary ──
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)

    if count_mismatch:
        print(
            f"✗ COUNT MISMATCH: in_memory={len(session.messages)} loaded={len(loaded_session.messages)}"
        )
    if hash_mismatches > 0:
        print(
            f"✗ HASH MISMATCHES: {hash_mismatches} of {len(session.messages)} messages differ"
        )
    if tool_arg_mismatches > 0:
        print(f"✗ TOOL ARG DRIFT: {tool_arg_mismatches} tool call arguments differ")
    if not count_mismatch and hash_mismatches == 0 and tool_arg_mismatches == 0:
        print(f"✓ BIT-FOR-BIT PARITY: {len(session.messages)} messages match perfectly")
        print(f"  ({28 * 2} tool calls + {28} tool results)")

    print("=" * 60)

    # Cleanup
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)

    sys.exit(
        0
        if (not count_mismatch and hash_mismatches == 0 and tool_arg_mismatches == 0)
        else 1
    )


if __name__ == "__main__":
    main()
