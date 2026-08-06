# PLAN — crow-cli v2 (Rust, ACP-native)

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

v2 is a hard break: ACP v2 only, no v1 backportability (v1 lives in git
history/releases for whoever wants it). crow-cli is more client than agent
— everything is exposed through it. Code is cheap/throwaway/useful to the
person making it. Distribution = cargo/crates.io + images later.

Numbered ship list. Do it, verify it, mark it done, move on.
Build: `cargo build -j 2` (hermetic — protobuf-src compiles protoc).
Install: `scripts/install.sh` (one release build → ~/.cargo/bin).

1. ✅ DONE — **ollama-mv behind the CLI** — `crow-cli daemon install ollama-mv`
   provisions everything on a fresh machine: clone the forks
   (crow-cli/ollama + crow-cli/llama.cpp at the pinned tag) into
   {config_dir}/vendor, build from source (Go + cmake, CPU), install the
   systemd unit, start, then pull the ColBERT embedding model and verify a
   real embed call. The embeddings download IS the first embed call —
   ollama pulls `hf.co/LiquidAI/LFM2.5-ColBERT-350M-GGUF` on demand.
   Gate for crates.io distribution.
2. **crow-cli services** — docker compose backend for the swiss-army
   knife: `crow-cli services up|down|pull|logs|status` shelling out to
   `docker compose -f {config_dir}/compose.yaml` (std::process::Command,
   no FFI). First payload: searxng (templates already embedded in init);
   migrate the live searxng off ~/.crow onto ~/.agents/crow.
3. **crow-cli daemon watch** — the reconcile loop: poll declared ports /
   /healthz, N consecutive failures → restart (SIGTERM→SIGKILL exists),
   flap guard (restart budget per window → stop and yell).
4. **Distribution** — publish crow-cli to crates.io, GitHub Releases, curl
   install.sh from crow-ai.dev. Docker images after. Published so far @0.2.0:
   crow-memory-types, crow-memory-sdk, crow-memory, crow-mcp, plus
   crow-streamdown-{core,ansi,config,syntax,parser,render} (rename-fork of
   streamdown-rs carrying the text_wrap fix upstream never released).
   crates.io strips git deps at publish, so crow-cli is BLOCKED on ONE thing:
   ACP SDK — needs a release > 2.0.0 (our rev 7d21931 uses APIs not in the
   published 2.0.0); decision 2026-08-06: WAIT for upstream (they published
   12 days before, active). alacritty RESOLVED: crow-alacritty-terminal 0.2.0
   published (bit-for-bit zed pin 4c129667, from crow-cli/alacritty branch
   crow-publish). streamdown RESOLVED via crow-streamdown-*. Meanwhile:
   `cargo install --git https://github.com/crow-cli/crow-cli.git`.
5. **Verify tool → its own MCP server**; investigate why daemon agents
   render verifier-flavored system prompts.
6. **coolname → its own crate**: extract from crow-cli, attribute the
   python `coolname` package, fatten the dictionaries (coolername).
7. **Fleet containers/k8s (later)** — everything gets a healthcheck first
   (compose/systemd stage, portable), k3s when multi-node matters.
   Compose files translate 1:1 to manifests; nothing thrown away.
8. **Swiss-army remainders** — `daemon start --port` override,
   `crow-cli memory` surface (health/resolved-url/log tail),
   `crow-cli ports` table.

Standing facts:
- Ports: daemon 2769 (CROW), memory 27697 (CROWS). One knob:
  $CROW_MEMORY_PORT in {config_dir}/.env > config memory_port > default.
- 11.9 `sudo loginctl enable-linger thomas` is Thomas's task.
- Config home: ~/.agents/crow (config.yaml, .env, client_settings.yaml,
  prompts/, run/, logs/). Skills: ~/.agents/skills. Global AGENTS.md:
  ~/.agents/AGENTS.md.
