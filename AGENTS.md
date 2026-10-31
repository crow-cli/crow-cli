# RULES

## Launching crow: one agent server, in its own terminal

The agent is a **server**; the clients are separate processes. Never write the
launch as one chained command (`crow-cli acp2 --http && crow`, or `&`-backgrounding
the agent in the same block as the client). That reads as "this one command starts
both", and it does not — the IDE spawns nothing at all.

In one terminal, run a **single instance** and leave it running:

```bash
crow-cli acp2 --http        # ACP v2 over Streamable HTTP + WebSocket → ws://127.0.0.1:2771/acp
```

In another terminal, run a client:

```bash
crow                                                   # the IDE
crow serve-web                                         # the same IDE in a browser
```

One instance serves every dialling client on the machine. Do not start one per
client, and do not restart it to change a client.

## The args, and where they live

| Arg / setting | Where | Default | Meaning |
|---------------|-------|---------|---------|
| `--http` | `crow-cli acp`, `crow-cli acp2` | off (stdio) | serve Streamable HTTP + WebSocket instead of stdio |
| `--host` | same | `127.0.0.1` | bind address; `0.0.0.0` exposes it beyond loopback |
| `--port` | same | `2769` (v1), `2771` (v2) | the two protocol versions have two ports |
| `-d/--config-dir`, `-o/--config-file`, `-m/--model`, `-p/--system-prompt-path`, `--debug` | same | — | per-instance config overrides |
| `crowAcp.endpoint` | IDE extension settings | `ws://127.0.0.1:2771/acp` | what the chat panel dials |
| `crowAcp.protocol` | IDE extension settings | `2` | `1`, `2` or `auto` (detect) |
| `crowAcp.cwd` | IDE extension settings | the workspace folder | agent working directory |
| `crowAcp.mcpConfig` | IDE extension settings | `crow-cli mcp2` (YAML) | the tool supply handed over at `session/new` |
| `--agent`, `--agent-arg` | `crow-agent` | `crow-cli acp2` or `$CROW_AGENT` | the stdio agent it spawns itself |
| `-w/--workspace`, `--session-id`, `--model`, `--theme` | `crow-agent` | cwd, —, `$CROW_MODEL`, persisted | client-side session choices |
| `mcpServers` | `~/.agents/crow/config.yaml` | written by `crow-cli init` | the supply `crow-cli run` passes at `session/new` |
| `agent_servers` | `~/.agents/crow/config.yaml` | one `crow-cli` entry from init | what `run` spawns; the top entry is the default |

## Which client starts the agent

- **Spawns its own over stdio:** `crow-cli run` (top `agent_servers` entry), `crow-agent` (`--agent`).
- **Dials a running server:** the IDE chat panel — the desktop app and `crow serve-web` alike.
- **Third-party clients** (Zed, …) spawn the command you declare, and forward their
  `context_servers` as the tool supply.

## Two rules that are easy to get wrong

**The agent owns its tools.** The `mcpServers` in `~/.agents/crow/config.yaml`
are the base supply: every session gets them, whether or not the client sends
anything at `session/new`. Whatever the client sends is added on top, by name,
and a client entry that reuses a config name replaces that entry. `crow-cli init`
writes the `crow-mcp` entry there, and an `agent_servers` entry may carry its own
`mcpServers` that replaces the global supply for that agent only.

Consequence: an empty `mcpServers` list no longer means "no tools" — it means
"just the agent's own". There is no way to ask for zero yet.

**Nothing runs from a source checkout implicitly.** `cli/source.py:spawn_argv()`
is always the code that is actually running — a frozen build's own subcommand, or
`sys.executable -m crow_cli.agent[2].main`. `crow-cli init` clones
`~/.agents/crow/src/crow-cli` and writes one explicit `agent_servers` entry
pointing at it; that entry is ordinary config the user can edit or delete
(`--no-source` writes neither). Do not reintroduce an implicit checkout
override: it fights worktrees and project checkouts.
