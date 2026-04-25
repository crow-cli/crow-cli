#!/usr/bin/env python3
"""
Deep-dive into payload content: check if llama.cpp chat template rendering
could be producing different tokens from identical messages.

Also checks: does the system message stay identical? Do tool responses
stay byte-for-byte identical? Are there any subtle encoding issues?
"""

import hashlib
import json
import os
import sys


def load_payloads(session_prefix: str) -> list[tuple[str, list]]:
    log_dir = os.path.expanduser("~/.crow/logs")
    files = sorted(
        f
        for f in os.listdir(log_dir)
        if f.startswith(f"payload-{session_prefix}-") and f.endswith(".json")
    )
    payloads = []
    for fname in files:
        path = os.path.join(log_dir, fname)
        with open(path) as fh:
            msgs = json.load(fh)
        payloads.append((fname, msgs))
    return payloads


def content_hash(msg: dict) -> str:
    """Hash just the content field, not role or other metadata."""
    content = msg.get("content", "")
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def full_hash(msg: dict) -> str:
    """Hash the entire message."""
    return hashlib.sha256(
        json.dumps(msg, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def content_char_count(msg: dict) -> int:
    """Count actual characters in content."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return len(content)
    elif isinstance(content, list):
        return sum(len(b.get("text", "")) for b in content if isinstance(b, dict))
    return 0


def find_key_differences(prev_msgs: list, curr_msgs: list) -> list[str]:
    """Find subtle differences that could affect template rendering."""
    diffs = []
    overlap = min(len(prev_msgs), len(curr_msgs))

    for i in range(overlap):
        prev = prev_msgs[i]
        curr = curr_msgs[i]

        # Check role
        if prev.get("role") != curr.get("role"):
            diffs.append(
                f"  msg[{i}]: role changed '{prev.get('role')}' -> '{curr.get('role')}'"
            )

        # Check name field (some APIs use this)
        if prev.get("name") != curr.get("name"):
            diffs.append(
                f"  msg[{i}]: name changed '{prev.get('name')}' -> '{curr.get('name')}'"
            )

        # Check tool_call_id
        if prev.get("tool_call_id") != curr.get("tool_call_id"):
            diffs.append(f"  msg[{i}]: tool_call_id changed")

        # Check content type
        prev_content = prev.get("content")
        curr_content = curr.get("content")
        prev_type = type(prev_content).__name__
        curr_type = type(curr_content).__name__
        if prev_type != curr_type:
            diffs.append(f"  msg[{i}]: content type changed {prev_type} -> {curr_type}")

        # For list content, check block count and types
        if isinstance(prev_content, list) and isinstance(curr_content, list):
            if len(prev_content) != len(curr_content):
                diffs.append(
                    f"  msg[{i}]: block count changed {len(prev_content)} -> {len(curr_content)}"
                )
            prev_types = [b.get("type") for b in prev_content if isinstance(b, dict)]
            curr_types = [b.get("type") for b in curr_content if isinstance(b, dict)]
            if prev_types != curr_types:
                diffs.append(
                    f"  msg[{i}]: block types changed {prev_types} -> {curr_types}"
                )

    return diffs


def check_system_message_consistency(payloads):
    """Verify system message is identical across all payloads."""
    system_msgs = []
    for fname, msgs in payloads:
        if msgs and msgs[0].get("role") == "system":
            system_msgs.append((fname, msgs[0]))

    if len(system_msgs) < 2:
        return "Only one system message found"

    first_name, first_msg = system_msgs[0]
    first_hash = full_hash(first_msg)

    results = []
    for fname, msg in system_msgs[1:]:
        h = full_hash(msg)
        if h != first_hash:
            results.append(f"SYSTEM MESSAGE CHANGED: {first_name} vs {fname}")

    if results:
        return "\n".join(results)
    return f"System message identical across all {len(system_msgs)} payloads ({content_char_count(first_msg)} chars)"


def check_tool_response_consistency(payloads):
    """Track each tool response across payloads to see if any change."""
    # Build a map: (index_in_payload) -> content_hash
    # Tool responses are at positions where role == "tool"

    tool_hashes_by_position = {}  # position -> [(fname, hash, char_count)]

    for fname, msgs in payloads:
        for i, msg in enumerate(msgs):
            if msg.get("role") == "tool":
                h = content_hash(msg)
                cc = content_char_count(msg)
                if i not in tool_hashes_by_position:
                    tool_hashes_by_position[i] = []
                tool_hashes_by_position[i].append((fname, h, cc))

    issues = []
    for pos, entries in sorted(tool_hashes_by_position.items()):
        if len(entries) > 1:
            hashes = set(e[1] for e in entries)
            if len(hashes) > 1:
                issues.append(
                    f"  Tool response at position [{pos}] changed between payloads:"
                )
                for fname, h, cc in entries:
                    issues.append(f"    {fname}: hash={h} chars={cc}")

    if issues:
        return "\n".join(issues)
    return f"All {len(tool_hashes_by_position)} tool response positions consistent across payloads"


def analyze_assistant_responses(payloads):
    """Check if assistant responses (non-tool) stay consistent."""
    issues = []

    for pi in range(len(payloads) - 1):
        prev_name, prev_msgs = payloads[pi]
        curr_name, curr_msgs = payloads[pi + 1]

        for i in range(min(len(prev_msgs), len(curr_msgs))):
            if prev_msgs[i].get("role") == "assistant":
                prev_h = content_hash(prev_msgs[i])
                curr_h = content_hash(curr_msgs[i])
                if prev_h != curr_h:
                    prev_cc = content_char_count(prev_msgs[i])
                    curr_cc = content_char_count(curr_msgs[i])
                    issues.append(
                        f"  Assistant msg [{i}] changed: {prev_name} ({prev_cc} chars, hash={prev_h}) "
                        f"-> {curr_name} ({curr_cc} chars, hash={curr_h})"
                    )

    if issues:
        return "\n".join(issues)
    return "All assistant responses consistent across payloads"


def check_json_encoding_issues(payloads):
    """Look for potential encoding/serialization issues."""
    issues = []
    for fname, msgs in payloads:
        raw = json.dumps(msgs, sort_keys=True, ensure_ascii=False)
        utf8_bytes = raw.encode("utf-8")

        # Check for surrogate characters or other oddities
        for i, msg in enumerate(msgs):
            content = msg.get("content", "")
            if isinstance(content, str):
                for j, ch in enumerate(content):
                    if ord(ch) > 0xFFFF:
                        issues.append(
                            f"  {fname} msg[{i}]: non-BMP character at position {j}: U+{ord(ch):04X}"
                        )
            elif isinstance(content, list):
                for bi, block in enumerate(content):
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        for j, ch in enumerate(text):
                            if ord(ch) > 0xFFFF:
                                issues.append(
                                    f"  {fname} msg[{i}] block[{bi}]: non-BMP char at pos {j}: U+{ord(ch):04X}"
                                )

    if issues:
        return "\n".join(issues)
    return "No encoding issues found"


def main():
    session_prefix = "inventive-innocent-manatee-of-focus-f29a9d"
    payloads = load_payloads(session_prefix)

    print(f"Deep analysis of {len(payloads)} payloads\n")

    # 1. System message consistency
    print("=== SYSTEM MESSAGE CONSISTENCY ===")
    print(check_system_message_consistency(payloads))
    print()

    # 2. Tool response consistency
    print("=== TOOL RESPONSE CONSISTENCY ===")
    print(check_tool_response_consistency(payloads))
    print()

    # 3. Assistant response consistency
    print("=== ASSISTANT RESPONSE CONSISTENCY ===")
    print(analyze_assistant_responses(payloads))
    print()

    # 4. JSON encoding issues
    print("=== JSON ENCODING ISSUES ===")
    print(check_json_encoding_issues(payloads))
    print()

    # 5. Subtle key differences
    print("=== SUBTLE KEY DIFFERENCES BETWEEN CONSECUTIVE PAYLOADS ===")
    any_diffs = False
    for pi in range(len(payloads) - 1):
        prev_name, prev_msgs = payloads[pi]
        curr_name, curr_msgs = payloads[pi + 1]
        key_diffs = find_key_differences(prev_msgs, curr_msgs)
        if key_diffs:
            any_diffs = True
            print(f"\n{prev_name} -> {curr_name}:")
            print("\n".join(key_diffs))

    if not any_diffs:
        print("No subtle key differences found.")
    print()

    # 6. Content character counts across payloads for each position
    print("=== CHARACTER COUNTS BY POSITION ===")
    max_msgs = max(len(msgs) for _, msgs in payloads)
    for pos in range(max_msgs):
        counts = []
        for fname, msgs in payloads:
            if pos < len(msgs):
                msg = msgs[pos]
                cc = content_char_count(msg)
                role = msg.get("role", "?")
                h = content_hash(msg)
                counts.append(
                    f"{fname.split('-')[-1].replace('.json', '')}: role={role} chars={cc} hash={h}"
                )

        # Check if all hashes match
        hashes = set()
        for c in counts:
            h = c.split("hash=")[1]
            hashes.add(h)

        marker = " *** CHANGED ***" if len(hashes) > 1 else ""
        print(f"\nPosition [{pos}]:{marker}")
        for c in counts:
            print(f"  {c}")

    print(f"\n{'=' * 80}")
    print("CONCLUSION")
    print(f"{'=' * 80}")
    print("If all checks pass, our payloads are truly append-only and immutable.")
    print("Then llama.cpp's cache invalidation is caused by:")
    print("  1. Chat template rendering producing different tokens for same messages")
    print("  2. BOS/EOS token handling inconsistency")
    print("  3. Whitespace normalization differences in template")
    print("  4. KV cache management bug in llama.cpp server")


if __name__ == "__main__":
    main()
