"""Pytest configuration for crow-mcp.

Test tiers (mirrors crow-cli's path-based gating):

    tests/              fast, hermetic unit tests — always run
    tests/integration/  spawn the real MCP server over stdio — opt-in
    tests/e2e/          live external calls (web search/fetch) — opt-in

Default `pytest` runs only the unit tier so the suite stays green and fast.
Run the other tiers with:

    pytest --run-integration        (or CROW_RUN_INTEGRATION=1)
    pytest --run-e2e                (or CROW_RUN_E2E=1)
"""

import os

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run integration tests (spawn the real MCP server over stdio)",
    )
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="run end-to-end tests (live external calls: web search/fetch)",
    )


def pytest_collection_modifyitems(config, items):
    run_integration = config.getoption("--run-integration") or os.environ.get(
        "CROW_RUN_INTEGRATION"
    )
    run_e2e = config.getoption("--run-e2e") or os.environ.get("CROW_RUN_E2E")

    skip_integration = pytest.mark.skip(
        reason="integration tier: pass --run-integration (or CROW_RUN_INTEGRATION=1)"
    )
    skip_e2e = pytest.mark.skip(
        reason="e2e tier: pass --run-e2e (or CROW_RUN_E2E=1)"
    )

    for item in items:
        path = str(item.path)
        if "/integration/" in path and not run_integration:
            item.add_marker(skip_integration)
        elif "/e2e/" in path and not run_e2e:
            item.add_marker(skip_e2e)
