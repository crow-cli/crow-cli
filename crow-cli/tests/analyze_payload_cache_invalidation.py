#!/usr/bin/env python3
"""
Analyze payload files to detect context cache invalidation.

Compares chronological payloads to find where messages that should be
"frozen in amber" (earlier messages) are being modified between requests.
This is what causes llama.cpp to invalidate its KV cache and re-compute tokens.
"""

import hashlib
import json
import os
import sys
from pathlib import Path


def find_session_dir(session: str | None = None):
    """Resolve the --debug log dir for a session (or the most recent one)."""
    logs = Path(os.path.expanduser("~/.crow/logs"))
    if session:
        d = logs / session
        return d if d.is_dir() else None
    # Auto-detect: most recent session dir that has request logs.
    candidates = sorted(
        logs.glob("*/turn-*-request.json"), key=lambda p: p.stat().st_mtime
    )
    return candidates[-1].parent if candidates else None


def load_payloads(session: str | None = None) -> list[tuple[str, float, list]]:
    """Load per-turn request payloads for a session, sorted chronologically.

    Reads the --debug request logs (``turn-*-request.json``); each holds the
    exact request sent to the LLM. We analyze its ``messages`` — the
    append-only chat history that must stay frozen across turns.
    """
    session_dir = find_session_dir(session)
    if session_dir is None:
        return []
    payloads = []
    for path in session_dir.glob("turn-*-request.json"):
        mtime = path.stat().st_mtime
        with open(path) as fh:
            request = json.load(fh)
        msgs = request.get("messages", [])
        payloads.append((path.name, mtime, msgs))
    # sort by modification time (chronological order)
    payloads.sort(key=lambda x: x[1])
    return payloads


def msg_fingerprint(msg: dict) -> str:
    """Create a stable fingerprint for a message."""
    return hashlib.sha256(
        json.dumps(msg, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def msg_summary(msg: dict, idx: int) -> str:
    """Short human-readable summary of a message."""
    role = msg.get("role", "?")
    content = msg.get("content", "")
    if isinstance(content, list):
        text_blocks = [b.get("text", "") for b in content if b.get("type") == "text"]
        preview = text_blocks[0][:80] if text_blocks else "(no text)"
        block_types = [b.get("type", "?") for b in content]
        return f"[{idx}] role={role} blocks={block_types} preview={preview!r}"
    else:
        preview = str(content)[:80]
        return f"[{idx}] role={role} preview={preview!r}"


def compare_pair(prev_name: str, prev_msgs: list, curr_name: str, curr_msgs: list):
    """Compare two consecutive payloads and report what changed."""
    prev_len = len(prev_msgs)
    curr_len = len(curr_msgs)

    # Build fingerprints for previous messages
    prev_fps = {}
    for i, msg in enumerate(prev_msgs):
        prev_fps[i] = msg_fingerprint(msg)

    # Build fingerprints for current messages
    curr_fps = {}
    for i, msg in enumerate(curr_msgs):
        curr_fps[i] = msg_fingerprint(msg)

    changes = []

    # Check messages that should be frozen (all messages that exist in both)
    # The overlap region: messages 0..prev_len-1 in prev should match 0..prev_len-1 in curr
    min_len = min(prev_len, curr_len)
    for i in range(min_len):
        if prev_fps[i] != curr_fps[i]:
            changes.append(
                {
                    "index": i,
                    "type": "MODIFIED",
                    "prev_summary": msg_summary(prev_msgs[i], i),
                    "curr_summary": msg_summary(curr_msgs[i], i),
                    "prev_fp": prev_fps[i],
                    "curr_fp": curr_fps[i],
                }
            )

    # New messages appended
    if curr_len > prev_len:
        for i in range(prev_len, curr_len):
            changes.append(
                {
                    "index": i,
                    "type": "ADDED",
                    "summary": msg_summary(curr_msgs[i], i),
                }
            )

    # Messages removed (shouldn't happen but let's catch it)
    if curr_len < prev_len:
        for i in range(curr_len, prev_len):
            changes.append(
                {
                    "index": i,
                    "type": "REMOVED",
                    "summary": msg_summary(prev_msgs[i], i),
                }
            )

    return changes


def show_full_diff(prev_msgs: list, curr_msgs: list, modified_idx: int):
    """Show a detailed diff of a modified message."""
    msg = f"\n{'=' * 80}\nFULL CONTENT DIFF for message [{modified_idx}]:\n{'=' * 80}"
    prev_content = prev_msgs[modified_idx].get("content", "")
    curr_content = curr_msgs[modified_idx].get("content", "")

    if isinstance(prev_content, list):
        prev_text = json.dumps(prev_content, indent=2, ensure_ascii=False)
    else:
        prev_text = str(prev_content)

    if isinstance(curr_content, list):
        curr_text = json.dumps(curr_content, indent=2, ensure_ascii=False)
    else:
        curr_text = str(curr_content)

    msg += f"\n\nPREVIOUS (len={len(prev_text)}):\n{prev_text[:2000]}"
    if len(prev_text) > 2000:
        msg += f"\n... (truncated, {len(prev_text)} total chars)"

    msg += f"\n\nCURRENT (len={len(curr_text)}):\n{curr_text[:2000]}"
    if len(curr_text) > 2000:
        msg += f"\n... (truncated, {len(curr_text)} total chars)"

    msg += f"\n{'=' * 80}\n"
    return msg


def main():
    session = sys.argv[1] if len(sys.argv) > 1 else None
    session_dir = find_session_dir(session)
    if session_dir is None:
        print("No --debug request logs found (run the agent with --debug first).")
        sys.exit(1)

    print(f"Loading request payloads for session: {session_dir.name}")
    payloads = load_payloads(session)

    if not payloads:
        print("No turn-*-request.json files found!")
        sys.exit(1)

    print(f"Found {len(payloads)} payload files (chronological order):\n")
    for fname, mtime, msgs in payloads:
        print(f"  {fname}  ({len(msgs)} messages)")

    print(f"\n{'=' * 80}")
    print("COMPARING CONSECUTIVE PAYLOADS FOR CACHE INVALIDATION")
    print(f"{'=' * 80}\n")

    total_modifications = 0
    total_messages = 0

    for i in range(len(payloads) - 1):
        prev_name, _, prev_msgs = payloads[i]
        curr_name, _, curr_msgs = payloads[i + 1]

        changes = compare_pair(prev_name, prev_msgs, curr_name, curr_msgs)
        modifications = [c for c in changes if c["type"] == "MODIFIED"]
        additions = [c for c in changes if c["type"] == "ADDED"]
        removals = [c for c in changes if c["type"] == "REMOVED"]

        total_messages += len(prev_msgs)

        if modifications:
            total_modifications += len(modifications)

        status = "OK" if not modifications else "CACHE INVALIDATION DETECTED"
        print(f"\n{prev_name} ({len(prev_msgs)} msgs)")
        print(f"  -> {curr_name} ({len(curr_msgs)} msgs)")
        print(f"  Status: {status}")

        if additions:
            print(f"  + {len(additions)} new message(s) appended")

        if modifications:
            for mod in modifications:
                print(f"  *** MODIFIED message [{mod['index']}]:")
                print(f"      BEFORE: {mod['prev_summary']}")
                print(f"      AFTER:  {mod['curr_summary']}")

                # Show full diff for modified messages
                full_diff = show_full_diff(prev_msgs, curr_msgs, mod["index"])
                print(full_diff)

        if removals:
            for rem in removals:
                print(f"  *** REMOVED message [{rem['index']}]:")
                print(f"      {rem['summary']}")

        if not modifications and not additions and not removals:
            print(f"  (no changes - identical payloads)")

    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"Total consecutive comparisons: {len(payloads) - 1}")
    print(f"Total messages examined:       {total_messages}")
    print(f"Total cache-invalidating mods: {total_modifications}")

    if total_modifications > 0:
        print(f"\n*** BUG CONFIRMED: llama.cpp is correct. Messages are being")
        print(f"    modified between requests, invalidating the KV cache.")
        print(f"    This means {total_modifications} messages that should be")
        print(f"    frozen were changed, causing re-computation.")
    else:
        print(f"\nNo cache invalidation detected in payloads.")
        print(f"llama.cpp may be lying, or the issue is elsewhere.")


if __name__ == "__main__":
    main()
