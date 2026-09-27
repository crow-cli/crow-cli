#!/bin/sh
# Run the crow-gui suite in a real headless browser (wasm32-unknown-unknown).
#
#   scripts/test-web.sh                 every crow-gui test, in Chrome
#   scripts/test-web.sh translate       ...only the tests whose name matches
#
# src/input.rs's tests are a dual harness: the same bodies run as `#[test]` on
# the host (`cargo test -p crow-gui`) and as `#[wasm_bindgen_test]` here. Both
# halves have to stay green -- the crate's whole claim is that key and mouse
# translation behaves identically in the native window and in the browser.
#
# Needs on PATH:
#   wasm-bindgen-test-runner  ships with the wasm-bindgen CLI; its version must
#                             match the wasm-bindgen crate (0.2.129).
#   chromedriver              chrome-for-testing build, from
#                             https://googlechromelabs.github.io/chrome-for-testing/
# Chrome itself: the playwright Chrome for Testing whose major version matches
# chromedriver's. Override with CHROME=/path/to/chrome.
#
# If chromedriver finds Chrome but cannot start it, drop a `webdriver.json`
# next to crow-gui's Cargo.toml -- the runner looks for one and merges it into
# the session capabilities:
#   {"goog:chromeOptions":{"args":["--no-sandbox","--headless=new"]}}
set -eu
cd "$(dirname "$0")/.."

for tool in chromedriver wasm-bindgen-test-runner; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "test-web.sh: $tool is not on PATH" >&2
    exit 1
  }
done

# chromedriver refuses a browser whose major version differs from its own, and
# the playwright cache can hold several. Pick the one that matches.
if [ -z "${CHROME:-}" ]; then
  driver_major=$(chromedriver --version | awk '{print $2}' | cut -d. -f1)
  CHROME=$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux64/chrome 2>/dev/null \
           | sort -Vr \
           | while read -r candidate; do
               major=$("$candidate" --version 2>/dev/null | awk '{print $NF}' | cut -d. -f1)
               if [ "$major" = "$driver_major" ]; then echo "$candidate"; break; fi
             done)
  if [ -z "$CHROME" ]; then
    echo "test-web.sh: no Chrome $driver_major in ~/.cache/ms-playwright to match" \
         "chromedriver; set CHROME=/path/to/chrome" >&2
    exit 1
  fi
fi
[ -x "$CHROME" ] || { echo "test-web.sh: $CHROME is not executable" >&2; exit 1; }

# chromedriver locates the browser itself and only looks in the usual places; a
# playwright cache is not one of them. `chrome` on PATH is the name it finds.
BIN=$(mktemp -d)
trap 'rm -rf "$BIN"' EXIT
ln -s "$CHROME" "$BIN/chrome"
PATH="$BIN:$PATH"

WASM_BINDGEN_USE_BROWSER=1
CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUNNER=wasm-bindgen-test-runner
export WASM_BINDGEN_USE_BROWSER CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUNNER

exec cargo test -p crow-gui --features web --target wasm32-unknown-unknown "$@"
