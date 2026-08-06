#!/usr/bin/env python3
"""9.8 e2e: crowctl-driven verifier chain, end to end.

`crowctl run verifier "<task>"` drives: conductor -> crow-verifier proxy ->
crow worker. The worker does the task; on idle the proxy intercepts and calls
the verifier daemon (crow-server, ACP HTTP via HttpClient), which reads the
worker history (query_session) and returns a verdict; PASS forwards the idle.

Assertions: exit 0, artifact file correct, daemon log grew query_session +
verdict tool calls after the run started.

    uv run python e2e_verifier_chain.py

Needs: built target/debug/crowctl, verifier-daemon running on 8081
(crowctl daemon start verifier-daemon), configured LLM.
"""
import os
import pathlib
import subprocess
import sys
import time

TIMEOUT = 420
ARTIFACT = "/tmp/verifier-chain-e2e.txt"
CONTENT = "PINEAPPLE"
TASK = (
    f"Create a file {ARTIFACT} containing exactly the word {CONTENT}. "
    "Then stop."
)
DAEMON_LOG = pathlib.Path.home() / ".agents/crow/logs/verifier-daemon.log"


def main():
    ctl = pathlib.Path(__file__).parent / ".." / "target" / "debug" / "crowctl"
    if not ctl.exists():
        sys.exit(f"missing {ctl} — build first")

    if os.path.exists(ARTIFACT):
        os.unlink(ARTIFACT)
    log_offset = DAEMON_LOG.stat().st_size if DAEMON_LOG.exists() else 0
    t0 = time.time()

    proc = subprocess.run(
        [str(ctl.resolve()), "run", "verifier", TASK],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    took = time.time() - t0

    if proc.returncode != 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:], file=sys.stderr)
        sys.exit(f"FAIL: crowctl run verifier exited {proc.returncode} ({took:.0f}s)")
    print(f"PASS chain run exited 0 ({took:.0f}s)")

    try:
        content = pathlib.Path(ARTIFACT).read_text()
    except FileNotFoundError:
        sys.exit("FAIL: worker never created the artifact")
    if content.strip() != CONTENT:
        sys.exit(f"FAIL: artifact content {content!r}")
    print(f"PASS artifact on disk: {content!r}")

    # The verification round must show up in the daemon log AFTER our start.
    log = DAEMON_LOG.read_text()[log_offset:] if DAEMON_LOG.exists() else ""
    for marker in ("tool: query_session", "tool: verdict"):
        if marker not in log:
            sys.exit(f"FAIL: daemon log has no '{marker}' for this run")
    print("PASS verifier daemon ran query_session + verdict")

    print("PASS e2e complete: verifier chain")


if __name__ == "__main__":
    main()
