#!/usr/bin/env bash
# Run the crow-cli test suite — ALL tiers (unit + integration + e2e live LLM)
# run unconditionally. Pass extra pytest args to narrow, e.g.
# ./run_tests.sh tests/unit
cd "$(dirname "$0")" && exec uv --project . run pytest "$@"
