<p align="center">
    <img src="assets/crow-logo-crop.png" alt="crow logo" width=500/>
</p>

# 🐦‍⬛ Crow

Monorepo for the Crow coding agent, rewritten in Rust for
[ACP v2](https://agentclientprotocol.com/).

Crow is an ACP-native coding agent that runs in your terminal and inside
ACP-compatible editors. It reads and edits code, runs shell commands, searches
the web — and it **remembers**: every session is written to a shared LanceDB
memory you can query across sessions.

v1 (Python) lives in git history at `591260b2`. This trunk is v2.

## Crates

| Crate | What it is |
|-------|-----------|
| `crow-cli` | The agent — ACP v2 client + agent, ReAct loop, memory client, daemon manager |
| `crow-mcp` | MCP toolserver: terminal, edit, read, write, web search/fetch, vision, verdict |
| `crow-memory` | Memory server — axum + LanceDB + embeddings (single writer) |
| `crow-memory-sdk` | reqwest client for the memory HTTP API |
| `crow-memory-types` | Wire types shared by memory server and SDK |
| `crow-server` | Serves the Crow agent over ACP HTTP/SSE |
| `crow-verifier` | Conductor proxy: intercepts worker idle, runs a verifier, acts on the verdict |

## Getting started

```bash
git clone https://github.com/crow-cli/crow-cli
cd crow-cli
cargo build --release

# write config.yaml, .env, and the system prompt from LLM_*_API_KEY env vars
./target/release/crow-cli init -y

# one-shot prompt to the default model
./target/release/crow-cli run "explain this project"
```

Config lives in `~/.agents/crow/` (`config.yaml`, `.env`,
`prompts/system_prompt.hbs`, `client_settings.yaml`).

## Usage

```text
crow-cli init -y                            write config from LLM_*_API_KEY env vars
crow-cli models                             list configured models (* = default)
crow-cli run "fix the failing test"         one-shot prompt to the default agent
crow-cli run -m gpt-5 "fix the test"        one-shot with an explicit model
crow-cli run verifier -p PROMPT.md          named chain from client_settings.yaml
crow-cli run -j "list files" | jq .         JSON output: one line per session update
crow-cli run -s <session-id> "keep going"   resume a session (append-only history)
crow-cli run --headless "long task"         fire-and-forget in the background
crow-cli agents                             list servers + chains from client_settings.yaml
crow-cli acp                                run as an ACP v2 agent over stdio
crow-cli acp --http                         resident multi-session agent over HTTP/SSE
crow-cli acp --relay URL                    disposable stdio front for a resident daemon
crow-cli serve <name> --port 2769           serve an agent/chain as a persistent ACP HTTP endpoint
crow-cli daemon list|start|stop|status      manage daemons declared in client_settings.yaml
crow-cli daemon install ollama-mv           promote to a systemd user unit (boot persistence)
```

Daemons with a `port:` in `client_settings.yaml` run under a pidfile backend by
default; `daemon install <name>` promotes one to a systemd user unit
(`crow-<name>.service`, `Restart=always`). Boot persistence needs linger:
`sudo loginctl enable-linger $USER`. `ollama-mv` is special — when its binary
is missing it is built from source, and the ColBERT embedding model is pulled
and verified with a real embed call on startup.

## Memory

Sessions, prompts, and agents persist in LanceDB behind the crow-memory
server (`memory_url` / `memory_port` in config.yaml). Agents get
`list_sessions`, `query_memory`, and `query_session` tools to read each
other's work — delegation is just `crow-cli run -s <session-id> "follow-up"`
plus a shared memory.

## Development

```bash
cargo test --workspace                # unit + integration tests
python crow-cli/e2e_serve.py          # e2e: ACP-over-HTTP serve
python crow-cli/e2e_verifier_chain.py # e2e: verifier conductor chain
python crow-verifier/e2e.py           # e2e: verifier proxy standalone
```

Dependencies are all crates.io except `agent-client-protocol*`, pinned to a
rust-sdk git rev (crates.io 2.0.0 predates the unstable v2 APIs we need; see
the comment in `crow-cli/Cargo.toml`). `Cargo.lock` is committed.

## License

MIT. See [LICENSE.md](./LICENSE.md).
