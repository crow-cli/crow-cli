"""
Explore Langfuse traces programmatically.

Usage:
    uv --project . run explore.py          # Fetch and display existing traces
    uv --project . run explore.py --run    # First run main.py to generate a trace, then fetch
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

BASE = "http://localhost:3000/api/public"
AUTH = (
    os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-67d6bf7b-3b3c-47fe-b2a5-2d4b0dca4277"),
    os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-897ed6fa-504f-4e71-84ef-469d4ca522ec"),
)


def run_example():
    """Run main.py to generate a trace."""
    print("=" * 60)
    print("RUNNING EXAMPLE TO GENERATE TRACE")
    print("=" * 60)
    result = subprocess.run(
        [sys.executable, "main.py"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(f"stderr: {result.stderr}")
        print(f"Exit code: {result.returncode}")
        sys.exit(1)
    print("\nTrace should now exist in Langfuse.\n")


def fetch_traces(limit=10, order_by=None):
    """Fetch traces from Langfuse."""
    params = {"limit": limit}
    if order_by:
        params["orderBy"] = order_by
    r = requests.get(f"{BASE}/traces", auth=AUTH, params=params)
    r.raise_for_status()
    return r.json()


def fetch_trace_detail(trace_id):
    """Fetch a single trace with all observations."""
    r = requests.get(f"{BASE}/traces/{trace_id}", auth=AUTH)
    r.raise_for_status()
    return r.json()


def fetch_observations(trace_id=None, limit=50):
    """Fetch observations, optionally filtered by trace."""
    params = {"limit": limit}
    if trace_id:
        params["traceId"] = trace_id
    r = requests.get(f"{BASE}/observations", auth=AUTH, params=params)
    r.raise_for_status()
    return r.json()


def display_trace_summary(trace):
    """Display a trace summary."""
    print(f"Trace: {trace['id']}")
    print(f"  Name: {trace.get('name')}")
    print(f"  Timestamp: {trace.get('timestamp')}")
    print(f"  Latency: {trace.get('latency')}s")
    print(f"  Input: {str(trace.get('input', {}))[:200]}")
    print(f"  Output: {str(trace.get('output', {}))[:200]}")
    obs_ids = trace.get("observations", [])
    print(f"  Observations: {len(obs_ids)}")
    print()


def display_trace_detail(trace_id):
    """Display full trace details with observations."""
    trace = fetch_trace_detail(trace_id)

    print("=" * 60)
    print(f"TRACE DETAIL: {trace_id}")
    print("=" * 60)
    print(f"Name: {trace.get('name')}")
    print(f"Timestamp: {trace.get('timestamp')}")
    print(f"Latency: {trace.get('latency')}s")
    print(f"Session: {trace.get('sessionId')}")
    print(f"Tags: {trace.get('tags')}")
    print()

    # Input
    inp = trace.get("input", {})
    print(f"INPUT ({len(json.dumps(inp))}B):")
    if isinstance(inp, list):
        for msg in inp:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            tc = msg.get("tool_calls", [])
            print(f"  [{role}] content={len(str(content))}B tool_calls={len(tc)}")
            if tc:
                for t in tc:
                    fname = t.get("function", {}).get("name", "?")
                    fargs = t.get("function", {}).get("arguments", "")
                    print(f"    -> {fname}({fargs[:100]})")
    print()

    # Output
    out = trace.get("output", {})
    print(f"OUTPUT ({len(json.dumps(out))}B):")
    if isinstance(out, dict):
        role = out.get("role", "?")
        content = out.get("content", "")
        tc = out.get("tool_calls", [])
        rc = out.get("reasoning_content", "")
        print(
            f"  [{role}] content={len(content)}B reasoning={len(rc)}B tool_calls={len(tc)}"
        )
    print()

    # Observations
    obs = fetch_observations(trace_id=trace_id)
    print(f"OBSERVATIONS ({obs.get('meta', {}).get('totalItems', 0)} total):")
    for o in obs.get("data", []):
        print(f"  [{o['type']}] {o.get('name')}")
        print(f"    start={o.get('startTime')} end={o.get('endTime')}")
        usage = o.get("usage", {})
        usage_details = o.get("usageDetails", {})
        print(f"    usage: {usage}")
        if usage_details:
            print(f"    usageDetails: {usage_details}")
        model_params = o.get("modelParameters", {})
        if model_params:
            print(f"    modelParams: {model_params}")
        model = o.get("model")
        if model:
            print(f"    model: {model}")
        print()


def compare_traces():
    """Compare all traces to find message drift."""
    traces_data = fetch_traces(limit=50, order_by="timestamp.asc")
    traces = traces_data.get("data", [])

    if len(traces) < 2:
        print("Need at least 2 traces to compare.")
        return

    print(f"Comparing {len(traces)} traces...")
    print()

    prev_msgs = None
    prev_tools = None
    prev_trace = None
    for i, t in enumerate(traces):
        trace_detail = fetch_trace_detail(t["id"])
        inp = trace_detail.get("input", {})

        # Langfuse wraps messages+tools in a dict for chat.completions
        if isinstance(inp, dict):
            curr_msgs = inp.get("messages", [])
            curr_tools = inp.get("tools", [])
        elif isinstance(inp, list):
            curr_msgs = inp
            curr_tools = []
        else:
            curr_msgs = []
            curr_tools = []

        n_curr = len(curr_msgs)
        n_tools = len(curr_tools)
        last_role = curr_msgs[-1].get("role", "?") if curr_msgs else "?"
        print(f"Trace[{i}]: {t['id'][:20]}... msgs={n_curr} tools={n_tools} last={last_role}")

        if prev_msgs is not None:
            n_prev = len(prev_msgs)

            # Check prefix match
            first_diff = None
            for j in range(min(n_prev, n_curr)):
                m1 = json.dumps(prev_msgs[j], sort_keys=True, default=str)
                m2 = json.dumps(curr_msgs[j], sort_keys=True, default=str)
                if m1 != m2:
                    first_diff = j
                    break

            tools_changed = json.dumps(prev_tools, sort_keys=True, default=str) != json.dumps(curr_tools, sort_keys=True, default=str)

            status = "PREFIX MATCH" if first_diff is None else f"DIFF AT MSG[{first_diff}]"
            if tools_changed:
                status += " + TOOLS CHANGED"
            print(f"  -> Trace[{i}]: {status}")

            if first_diff is not None:
                m1 = prev_msgs[first_diff]
                m2 = curr_msgs[first_diff]
                for key in set(list(m1.keys()) + list(m2.keys())):
                    v1 = str(m1.get(key, ""))
                    v2 = str(m2.get(key, ""))
                    if v1 != v2:
                        print(f"    {key}: prev={len(v1)}B -> curr={len(v2)}B")
                print()

            if tools_changed:
                prev_names = sorted([t["function"]["name"] for t in prev_tools])
                curr_names = sorted([t["function"]["name"] for t in curr_tools])
                if prev_names == curr_names:
                    # Same tools but schema changed — find which one
                    for j, (pt, ct) in enumerate(zip(prev_tools, curr_tools)):
                        if json.dumps(pt, sort_keys=True, default=str) != json.dumps(ct, sort_keys=True, default=str):
                            print(f"    Tool schema changed: {pt['function']['name']}")
                            for k in set(list(pt["function"].keys()) + list(ct["function"].keys())):
                                v1 = str(pt["function"].get(k, ""))
                                v2 = str(ct["function"].get(k, ""))
                                if v1 != v2:
                                    print(f"      {k}: prev={len(v1)}B -> curr={len(v2)}B")
                else:
                    print(f"    Tool list changed: {prev_names} -> {curr_names}")
                print()

        prev_msgs = curr_msgs
        prev_tools = curr_tools
        prev_trace = t


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run", action="store_true", help="Run main.py first to generate trace"
    )
    parser.add_argument("--detail", type=str, help="Show detail for specific trace ID")
    parser.add_argument(
        "--compare", action="store_true", help="Compare consecutive traces"
    )
    args = parser.parse_args()

    if args.run:
        run_example()

    if args.detail:
        display_trace_detail(args.detail)
        return

    if args.compare:
        compare_traces()
        return

    # Default: list all traces
    traces = fetch_traces(limit=20)
    total = traces.get("meta", {}).get("totalItems", 0)
    print(f"Total traces: {total}")
    print()
    for t in traces.get("data", []):
        display_trace_summary(t)


if __name__ == "__main__":
    main()
