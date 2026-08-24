#!/usr/bin/env python
"""Live e2e drill: real agent, real memory tools, RAM watched.

Spawns a one-shot `crow-cli run` agent and orders it through five memory
calls (list_sessions, two query_memory terms, two query_session queries).
While it runs, every `crow-cli mcp` process is RSS-sampled — the one that
appears with the run is the agent's MCP server, and its curve must stay
flat (the columns-only fix). After the run, the session's transcript is
read back from crow.db over RAW sqlite (independent of the tool code) and
each tool result is checked against known ground truth.

Usage:
  uv --project . run python scripts/e2e_memory_live.py
"""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CROW = REPO / ".venv" / "bin" / "crow-cli"
DB = Path.home() / ".agents" / "crow" / "crow.db"

# Ground truth — this session's id and terms that definitely exist in it.
MY_SESSION = "olive-gerbil-of-unusual-performance"
PROMPT = (
    "Do the following EXACTLY, in order, using your memory tools, then give "
    "a brief summary of what each call returned:\n"
    "1. list_sessions(limit=10)\n"
    "2. query_memory(query='delegation hold', limit=5)\n"
    "3. query_memory(query='display tree', limit=5)\n"
    f"4. query_session(session_id='{MY_SESSION}', query='delegation hold', limit=5)\n"
    f"5. query_session(session_id='{MY_SESSION}', query='terminal output', limit=5)\n"
    "Do not skip any call."
)


def mcp_rss() -> dict[int, int]:
    """pid -> RSS kB for every crow-cli mcp process."""
    out = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                # argv is NUL-separated — normalize so " mcp" can match
                cmd = f.read().decode(errors="replace").replace("\x00", " ")
            if "crow-cli" in cmd and " mcp" in cmd:
                with open(f"/proc/{pid}/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            out[int(pid)] = int(line.split()[1])
        except OSError:
            continue
    return out


def sessions_in_db() -> set[str]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return {r[0] for r in con.execute("SELECT DISTINCT session_id FROM agents")}
    finally:
        con.close()


def transcript(session_id: str) -> list[dict]:
    """The run session's messages (all agents), ascending, via raw sqlite."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        aids = [
            r[0]
            for r in con.execute(
                "SELECT agent_id FROM agents WHERE session_id=? ORDER BY agent_idx",
                (session_id,),
            )
        ]
        rows = con.execute(
            "SELECT data FROM messages WHERE agent_id IN "
            f"({','.join('?' * len(aids))}) ORDER BY id",
            aids,
        ).fetchall()
    finally:
        con.close()
    return [json.loads(r[0]) for r in rows]


def tool_results(messages: list[dict]) -> dict[str, list[str]]:
    """tool-call name -> list of raw result strings, in call order."""
    # assistant tool_calls carry (id, name); tool messages carry tool_call_id
    name_by_id: dict[str, str] = {}
    for m in messages:
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            if tc.get("id"):
                name_by_id[tc["id"]] = fn.get("name", "")
    out: dict[str, list[str]] = {}
    for m in messages:
        if m.get("role") != "tool":
            continue
        name = name_by_id.get(m.get("tool_call_id", ""), "unknown")
        out.setdefault(name, []).append(m.get("content", ""))
    return out


def main() -> None:
    failures: list[str] = []
    before_sessions = sessions_in_db()
    before_pids = set(mcp_rss())
    print(f"pre-run: {len(before_sessions)} sessions, {len(before_pids)} mcp procs")

    proc = subprocess.Popen(
        [str(CROW), "run", PROMPT],
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # RSS watch: sampler thread tracks every mcp proc that appears after
    # launch (readline blocks on agent silence, so sampling can't ride it).
    new_peak: dict[int, int] = {}
    stop_sampler = threading.Event()

    def sample() -> None:
        while not stop_sampler.is_set():
            for pid, rss in mcp_rss().items():
                if pid not in before_pids:
                    new_peak[pid] = max(new_peak.get(pid, 0), rss)
            time.sleep(0.5)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()

    out_lines: list[str] = []
    start = time.time()
    assert proc.stdout is not None
    for line in proc.stdout:
        out_lines.append(line)
    proc.wait()
    stop_sampler.set()
    sampler.join(timeout=2)
    elapsed = time.time() - start
    stdout = "".join(out_lines)

    print(f"\n=== run finished in {elapsed:.0f}s, exit={proc.returncode} ===")
    print("--- agent stdout (tail) ---")
    print("\n".join(stdout.splitlines()[-15:]))

    # --- RAM report ---
    print("\n=== RAM: the run's MCP server(s) ===")
    if not new_peak:
        failures.append("no new crow-cli mcp process appeared during the run")
    for pid, peak in new_peak.items():
        alive = pid in mcp_rss()
        print(f"  pid {pid}: peak RSS = {peak / 1024:.1f} MB ({'still up' if alive else 'exited with run'})")
        if peak / 1024 > 350:
            failures.append(f"mcp pid {pid} peaked at {peak / 1024:.0f} MB (>350 MB budget)")

    # --- correctness: find the run's session, audit its transcript ---
    new_sessions = sessions_in_db() - before_sessions
    if len(new_sessions) != 1:
        failures.append(f"expected exactly 1 new session, got {new_sessions}")
        report(failures)
        return
    (sid,) = new_sessions
    print(f"\n=== transcript audit: session {sid} ===")
    results = tool_results(transcript(sid))

    def check(name: str, idx: int, must_contain: list[str], label: str) -> None:
        calls = results.get(name, [])
        if idx >= len(calls):
            failures.append(f"{label}: {name} call #{idx + 1} not found in transcript")
            return
        content = calls[idx]
        missing = [t for t in must_contain if t not in content]
        status = "PASS" if not missing else "FAIL"
        print(f"  [{status}] {label}: {len(content)} chars"
              + (f", missing {missing}" if missing else ""))
        if missing:
            failures.append(f"{label}: missing {missing}")

    check("list_sessions", 0, [MY_SESSION], "list_sessions shows this session")
    check("query_memory", 0, [MY_SESSION], "query_memory 'delegation hold' hits this session")
    check("query_memory", 1, ["session"], "query_memory 'display tree' returns hits")
    check("query_session", 0, ["delegation"], "query_session 'delegation hold' content")
    check("query_session", 1, ["terminal"], "query_session 'terminal output' content")

    # the agent's own summary should mention what it found
    final = next(
        (m.get("content", "") for m in reversed(transcript(sid))
         if m.get("role") == "assistant" and m.get("content")),
        "",
    )
    print(f"\n--- agent's final summary ({len(final)} chars) ---")
    print(final[:800])

    report(failures)


def report(failures: list[str]) -> None:
    print()
    if failures:
        print("DRILL FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("DRILL PASSED: memory tools correct end to end, MCP RAM flat.")


if __name__ == "__main__":
    main()
