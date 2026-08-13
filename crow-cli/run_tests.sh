#!/usr/bin/env bash
# Run the crow-cli test suite (unit by default; pass extra pytest args, e.g.
# ./run_tests.sh tests/integration --run-integration).
cd "$(dirname "$0")" && exec uv --project . run pytest "$@"
