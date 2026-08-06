# TODO — crow-cli v2

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Unordered. PLAN.md has the numbered ship list. Everything from the crow-rs
eras is done or dropped; history is in git.

- 1.x ollama-mv provisioning behind `crow-cli daemon install ollama-mv`:
  clone forks → build (Go+cmake) → systemd unit → start → pull ColBERT
  model → verify embed. Fresh-machine path for crates.io distribution.
- crow-cli services up/down/pull/logs/status (docker compose shellout);
  searxng first; migrate live searxng from ~/.crow to ~/.agents/crow.
- crow-cli daemon watch (health poll → restart, flap guard/budget).
- crates.io publish of crow-cli + GH Releases + curl install from
  crow-ai.dev.
- verify tool → separate MCP server; daemon agents rendering
  verifier-flavored system prompts (investigate).
- coolname → own crate + python coolname attribution + dictionary
  additions.
- swiss-army: daemon start --port, crow-cli memory surface, crow-cli
  ports table.
- later: container fleet (compose healthchecks) → k3s when multi-node.
- housekeeping: stale ~/.cargo/bin/crowctl binary can be deleted once
  nothing references it.
