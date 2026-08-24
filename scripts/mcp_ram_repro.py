#!/usr/bin/env python
"""MCP RAM regression repro — proves crow-cli mcp stays flat under load.

History: a long-lived `crow-cli mcp` (stdio server for an agent session)
was found at 746 MB RSS. The leak was NOT the terminal tool — it was the
memory tools: list_sessions / query_memory loaded EVERY agents-table row
IN FULL (each row carries that agent's system prompt + tool definitions)
just to map agent ids. On a real db that is a ~577 MB transient spike PER
CALL; glibc never returns the arenas, so RSS ratcheted ~12 MB per call
(197 -> 822 MB over 50 calls). Fix: columns-only queries. This script is
the standing proof that it stays fixed.

Two modes:

  server  end-to-end: spawn a real `crow-cli mcp` over stdio, hammer it
          with terminal calls (large outputs) + list_sessions calls, and
          print the server's RSS curve. Flat curve = healthy.

  trace   in-process: tracemalloc peak of store.list_sessions /
          store.search against the REAL db (read-only). Was ~577 MB
          before the fix, ~2 MB after.

Usage:
  uv --project . run python scripts/mcp_ram_repro.py            # server mode
  uv --project . run python scripts/mcp_ram_repro.py trace
  uv --project . run python scripts/mcp_ram_repro.py server --calls 20 --big 3
"""

import argparse
import asyncio
import os
import subprocess


# ---------------------------------------------------------------------------
# server mode — drive a real crow-cli mcp over stdio and watch its RSS
# ---------------------------------------------------------------------------

def _driver_children_rss_kb() -> int:
    """RSS of this process's `crow-cli mcp` children (robust against other
    instances already running on the machine)."""
    total = 0
    me = os.getpid()
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/stat") as f:
                stat = f.read()
            # fields after comm (which may contain spaces/parens): strip it
            rest = stat.rsplit(")", 1)[1].split()
            ppid = int(rest[1])  # field 4 in stat, index 1 after ')'
            if ppid != me:
                continue
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().decode(errors="replace")
            if "crow-cli" in cmd and "mcp" in cmd:
                with open(f"/proc/{pid}/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            total += int(line.split()[1])
        except OSError:
            continue
    return total


async def server_mode(calls: int, big: int, list_sessions: int) -> None:
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    here = os.path.dirname(os.path.abspath(__file__))
    venv_bin = os.path.normpath(os.path.join(here, "..", ".venv", "bin"))
    transport = StdioTransport(
        command=os.path.join(venv_bin, "crow-cli"), args=["mcp"]
    )
    client = Client(transport)

    def report(label: str) -> None:
        print(
            f"{label:>32}: server RSS = {_driver_children_rss_kb() / 1024:8.1f} MB",
            flush=True,
        )

    async with client:
        await client.ping()
        report("baseline (post-init)")

        for i in range(calls):
            await client.call_tool("terminal", {"command": "seq 1 40000"})
            if i % 10 == 9:
                report(f"after {i + 1}x ~260KB terminal")

        for i in range(big):
            await client.call_tool("terminal", {"command": "seq 1 400000"})
            report(f"after ~5MB terminal output {i + 1}")

        for i in range(list_sessions):
            await client.call_tool("list_sessions", {"limit": 50})
            if i % 10 == 9:
                report(f"after {i + 1}x list_sessions")

        await asyncio.sleep(2)
        report("final (idle)")


# ---------------------------------------------------------------------------
# trace mode — in-process tracemalloc peak against the real db
# ---------------------------------------------------------------------------

def trace_mode() -> None:
    import gc
    import tracemalloc

    import crow_cli.mcp.memory.store as store

    def peak_mb(fn) -> float:
        fn()  # warmup: engine creation, query compilation
        gc.collect()
        tracemalloc.start()
        try:
            fn()
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        return peak / 1024 / 1024

    ls = peak_mb(lambda: store.list_sessions(limit=50))
    se = peak_mb(lambda: store.search("the", limit=20))
    print(f"list_sessions traced peak: {ls:8.1f} MB   (pre-fix: ~577 MB)")
    print(f"search        traced peak: {se:8.1f} MB")
    if ls > 50:
        raise SystemExit("REGRESSION: list_sessions materializes agent payloads")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("mode", nargs="?", default="server", choices=["server", "trace"])
    p.add_argument("--calls", type=int, default=50, help="medium terminal calls")
    p.add_argument("--big", type=int, default=10, help="~5MB terminal calls")
    p.add_argument("--list-sessions", type=int, default=50)
    args = p.parse_args()
    if args.mode == "trace":
        trace_mode()
    else:
        asyncio.run(server_mode(args.calls, args.big, args.list_sessions))


if __name__ == "__main__":
    main()
