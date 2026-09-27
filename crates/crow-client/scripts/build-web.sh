#!/bin/sh
# Build the crow-gui browser runtime and stage it next to web/index.html.
#
#   scripts/build-web.sh                       build + wasm-bindgen
#   python3 -m http.server 8123 --directory web   serve, then open :8123
#
# Headless verification: playwright-cli open http://127.0.0.1:8123/ then poll
# `window.__crowProbe.ready` and screenshot (see CONTEXT.md "Web / wasm route").
set -eu
cd "$(dirname "$0")/.."

cargo build --release -p crow-gui --features web --target wasm32-unknown-unknown

wasm-bindgen \
  --out-name crow_web \
  --out-dir web/target \
  --target web \
  target/wasm32-unknown-unknown/release/crow-web.wasm

echo "staged web/target/ — serve with: python3 -m http.server 8123 --directory web"
