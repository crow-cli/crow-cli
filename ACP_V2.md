# ACP v2 in crow-cli — what is done, what it bought, and the next proposal

Session `dashing-optimal-fulmar-of-judgment`. Written against `main` at
`07f4ec9b`. Everything here was read out of the tree or measured on the wire;
nothing is recalled from a summary.

Contents:

1. [Where things stand](#1-where-things-stand)
2. [Phase 2: protocol negotiation — done, committed](#2-phase-2-protocol-negotiation)
3. [The v2 conversion: what it bought](#3-the-v2-conversion-what-it-actually-bought)
4. [Wake: built, wired, and the one missing link](#4-wake-built-wired-and-the-one-missing-link)
5. [PROPOSAL: `remind` — mechanism shipped as `/goal`, subtool unstarted](#5-proposal-remind)
6. [Settled design decisions](#6-settled-design-decisions-do-not-re-litigate)
7. [SDK and wire facts worth keeping](#7-sdk-and-wire-facts-worth-keeping)
8. [Known open holes](#8-known-open-holes)
9. [Git state](#9-git-state)

---

## 1. Where things stand

| thing | state |
|---|---|
| ACP v2 agent (`agent2/`), client (`client2/`), MCP server (`mcp2/`) | built, committed at `1d3211a6` |
| Protocol **negotiation** instead of declaration | built, committed at `07f4ec9b` |
| Wake bus (`wake.py`), mailbox (`task_deliveries`), watcher (`agent2/watcher.py`) | built **and wired** |
| Celery timer wheel (`timers.py`), `crow-cli timers` worker | built and tested, **no production caller** |
| `task` / `task_send` / `task_cancel` / `task_read` subtools | built, `_LAZY_V2` only |
| A model-facing way to feed **itself** | **built** — §5.4's mechanism, with a goal as the thing that defers |
| `/goal`: the persisted objective, the continuation loop, its ceilings and its exits | built — `memory/models.Goal`, `agent2/goal.py`, `driver._goal_continuation`, `tools/goal.py`, `agent2/slash.py` |
| `remind`, the self-note subtool §5 proposes | **not built** — §5.10 is unstarted and nothing below depends on it |
| Test suite | 1407 passed (`tests/{unit,mcp,memory,integration}`), 26 passed (`tests/e2e`) |
| Python 3.13 compile | 351 files, 0 failures |

---

## 2. Phase 2: protocol negotiation

### 2.1 The bug that started it

`~/.agents/crow/configs/v2_agent.yaml` plus a `v2-agent` entry in
`~/.agents/crow/config.yaml`. Then:

```
crow-cli run -a v2-agent -m qwen3.8-max "hey"
```

**Hung. The session never initialized. No error on either side.**

Root cause: the entry declared no `protocol:`, so `parse_agent_server`
defaulted it to `V1`, and `run` dispatched the **v1 client** to a **v2 agent**.
`crow-cli agents` cheerfully reported `v2-agent | acp`. The v1 client sent a
v1-shaped `initialize`; the v2 agent answered `-32602 Invalid params`
(`{'type':'missing','loc':['info'],'msg':'Field required'}`); the v1 client had
no idea what to do with that and waited.

### 2.2 The ruling

> the `protocol` field shouldn't be needed at all — the agent reports its
> version at `initialize`.

So: **the protocol is negotiated, not declared.** `AgentServer.protocol` is now
`Optional[str] = None`, and `None` means "ask." A declared value is an override
that skips the round trip. Guessing from the argv is still wrong, and a config
field that disagrees with the agent it names is a hang with no error on either
side — which is the bug above.

The durable lesson, and it is not a v2 lesson: **the peer tells you what it
speaks. Config is a cache of that answer at best and a lie at worst.**

### 2.3 What the spec says

From <https://agentclientprotocol.com/protocol/v2/migration>, verbatim:

> **Version negotiation** — The mechanism is unchanged: the Client sends the
> latest protocol version it supports in `initialize`, and the Agent responds
> with the same version if supported, or its own latest version otherwise. To
> use v2, send `"protocolVersion": 2`. **An Agent that only supports v1 will
> answer with `"protocolVersion": 1`**, and the Client decides whether to
> continue with v1 or disconnect. Treat v2 support as additive. […] Each side
> selects its v1 or v2 surface per connection based on the negotiated version.
> Nothing about v2 changes the underlying JSON-RPC framing, so **a single
> connection always speaks exactly one negotiated version after `initialize`**.

> **Supporting v1 and v2 side by side** — Supporting both versions is the
> recommended path, not an edge case […] Version negotiation gives you one
> protocol version per connection, so the cleanest approach is to keep two thin
> protocol surfaces behind shared application logic and select one after
> `initialize`.

> Negotiating `protocolVersion: 2` does **not** imply any of them [the
> unstable/draft surfaces]. Gate each behind its own capability or feature flag
> the same as v1.

The SDK's own agent side agrees: `acp/experimental/negotiation.py` has
`AgentProtocolRouter` / `_AgentNegotiationHandler`. `requested >= v2.PROTOCOL_VERSION`
selects v2; else `>= 1` selects v1 and `_normalize_initialize` converts
v2-shaped params to v1 shape with `protocol_version=1`.

### 2.4 One union initialize probes both — measured

```
v1-agent <- v1-shape: OK protocolVersion=1
v1-agent <- v2-shape: OK protocolVersion=1
v1-agent <- union   : OK protocolVersion=1
v2-agent <- v1-shape: ERROR -32602 Invalid params  data: {'type':'missing','loc':['info'],'msg':'Field required'}
v2-agent <- v2-shape: OK protocolVersion=2 keys=['capabilities','info','protocolVersion']
v2-agent <- union   : OK protocolVersion=2
```

The union works because `initialize` is the one method whose params v1 and v2
still share a shape for. v1 ignores the v2-only keys; v2 ignores the v1-only
ones; each finds the field it requires.

**This has a shelf life.** v3 may not share the shape, and then discovery needs
a ladder (try v3-shaped, on `invalid_params` fall back) rather than one request.
`discover.py`'s *structure* — spawn once, ask, hand over the live streams —
ports cleanly to Rust. `_handshake`'s single-request assumption does not.

Supporting facts:

- `acp.PROTOCOL_VERSION == 1` (int); `acp.experimental.v2.PROTOCOL_VERSION == 2` (int).
- v1 `InitializeRequest` fields: `protocolVersion`, `clientCapabilities`,
  `clientInfo`, `_meta`.
- v2 `InitializeRequest` **and** `InitializeResponse` both require
  `['protocolVersion','info']`. v2 has **no `client_info`**.
- `Implementation` requires `['name','version']`.
- v2's `ClientCapabilities` has only `auth`, `elicitation`, `nes`,
  `position_encodings` — no `terminal`/`fs` to decline, so `capabilities: {}`
  is correct. v1's `ClientCapabilities(terminal=False)` existed purely to
  *decline* the terminal.
- `ClientCapabilities(terminal=False).model_dump(mode="json", by_alias=True,
  exclude_none=True)` gives
  `{"fs":{"readTextFile":false,"writeTextFile":false},"terminal":false,"auth":{"terminal":false}}`.
- Wire framing: newline-delimited JSON, `json.dumps(payload,
  separators=(",",":")) + "\n"`.
- crow's real v1 agent (`agent/main.py:388`) returns
  `InitializeResponse(protocol_version=PROTOCOL_VERSION, ...)` — the
  **imported constant**, not the echoed request version. Spec-correct. A
  scripted test peer must do the same: an agent that only speaks v1 answers
  `1`.

### 2.5 `src/crow_cli/discover.py` (new, 317 lines)

```python
PROBE_TIMEOUT = 120.0        # a SPAWN budget (uv run cold-starts), not a network one
STDERR_LINES = 200
LATEST = v2.PROTOCOL_VERSION # 2
BY_VERSION = {V1_VERSION: V1, LATEST: V2}   # 1 -> "acp", 2 -> "acp2"
CLIENT_NAME = "crow-client"; CLIENT_TITLE = "Crow Client"; _REQUEST_ID = 0
logger = logging.getLogger("crow-discover")

class ProtocolError(Exception)   # message carries the child's stderr tail + exit code

def handshake_params() -> dict[str, Any]   # the union
def adopt_v2(conn: Any, response: dict[str, Any]) -> None

@dataclass(frozen=True)
class Connection:
    protocol: str; reader; writer; proc
    initialized: bool            # False = entry declared, stack handshakes itself
    response: Optional[dict] = None
    stderr: collections.deque = field(default_factory=lambda: deque(maxlen=STDERR_LINES))
    drainer: Optional[asyncio.Task] = None
    def stderr_tail(self) -> str

@asynccontextmanager
async def agent_connection(server, cwd, *, timeout=PROBE_TIMEOUT) -> AsyncIterator[Connection]
async def _drain_stderr(proc, sink)
async def _handshake(writer, reader, proc, drainer, stderr, timeout) -> dict
async def _silent(proc, drainer, stderr, what) -> str
```

Design points:

- **The probe IS the connection.** Spawn once, union-initialize, hand the live
  handshaked streams to whichever stack the answer selects. A probe that threw
  the connection away and let the stack re-spawn would pay the `uv run`
  cold-start twice and could land on a different agent.
- **`initialized`** distinguishes "I already did the handshake, adopt it" from
  "the entry declared its protocol, do it yourself."
- **The probe owns the single stderr drainer** and hands the deque *and* the
  task to the adopting stack. Two readers on one `StreamReader` split lines
  between them, so the handover is by ownership transfer, not duplication.
- `spawn_stdio_transport` is from **`acp.stdio`**, signature
  `(command, *args, env=None, cwd=None, stderr=PIPE, limit=None, shutdown_timeout=2.0)`
  yielding `(process.stdout, process.stdin, process)`. Its default env is a
  **TRIM**, so crow passes `env={**os.environ, **server.env}` — `env` on a spawn
  is an OVERLAY.
- `_silent` reaps: `if getattr(proc, "returncode", None) is None:` then a
  bounded `await asyncio.wait_for(proc.wait(), 2.0)`. Without it, `proc.returncode`
  stays `None` and the error message cannot say how the child died.
- `acp/connection.py:55` — `self._next_request_id = 0`. The SDK's connection
  starts ids at 0, the same value `_REQUEST_ID` uses. Safe: JSON-RPC ids only
  distinguish requests outstanding *together*, and the probe's is answered
  before the stack sends anything.

### 2.6 `adopt_v2` and the SDK's local gate — the landmine

`acp/experimental/v2/_initialization.py` has `InitializationState`, and v2's
`ClientSideConnection` gates **every** method on a *local* state machine:

```python
class ClientSideConnection:
    def __init__(self, client, input_stream, output_stream=None, **kw):
        self._state = InitializationState()          # private, no injection point
        router = _ClientRouter(client, self._state)  # every call: await self._state.require(method)
    async def initialize(self, request):
        self._state.begin(request)                   # local transition
        response = await self._conn.send_request(...)  # AND the wire send — FUSED
        self._state.complete(parsed)
```

`require(method)` raises `RequestError.invalid_request({"details": f"ACP v2
connection must be initialized before {method!r}"})` unless phase is
`"initialized"`. A second `initialize` on the wire is refused by the agent
(`"ACP v2 connections may only be initialized once"`).

**The SDK exposes no way to adopt an already-negotiated connection.** Hence:

```python
def adopt_v2(conn, response):
    parsed = v2.schema.InitializeResponse.model_validate(response)
    request = v2.schema.InitializeRequest(
        protocol_version=v2.PROTOCOL_VERSION, info=parsed.info
    )
    conn._state.begin(request)
    conn._state.complete(parsed)
```

Poking a private attribute, deliberately, and pinned by
`test_adopting_a_v2_connection_opens_its_local_gate` so an SDK rename fails a
test rather than a session. This is also why the doc's "gate v2 behind a flag
until it stabilizes" advice matters: `acp.experimental.v2` is allowed to move.

Two related traps:

- `str(RequestError)` is just `"Invalid request"` — the details dict is **not**
  in the string, so `pytest.raises(..., match="must be initialized")` fails.
  Assert on `_state.phase` instead.
- `open_connection(handler, input_stream, output_stream)` wants
  `input_stream` = `asyncio.StreamWriter` and `output_stream` =
  `asyncio.StreamReader`. So `v2.ClientSideConnection(client, writer, reader)`
  is correct despite the confusing naming.

**v1 has no such local gate.** `connect_client(proc, client, initialized=True)`
skipping `conn.initialize(...)` just works, which is why `client/main.py` only
needed an `initialized=` flag.

### 2.7 The dispatch in `cli/main.py`

`run`'s order: fork-flag validation first, then `Config.load` +
`apply_config_overrides`, then `select_agent_server(...)`, then
`config.llm.option_value(model)`, then fork-idx, then the three-part wire id,
and only then:

```python
if server.protocol is None:
    asyncio.run(_dispatch(...)); return
if server.protocol == V2:
    ...run_v2...
asyncio.run(_run_async(...))
```

`_dispatch` sits between `_emit_json` and `_run_async`; it lazy-imports
`ProtocolError, agent_connection`, and lazy-imports `run_v2` **inside** the
`if conn.protocol == V2:` branch.

`_run_async`'s new parameter is named **`discovered`**, not `conn` — the
function already has a local `conn` (the v1 `ClientSideConnection`).

`cli/main.py` has no `from __future__ import annotations`, so the hint is a
string and the import is `TYPE_CHECKING`-only:

```python
if TYPE_CHECKING:
    # crow_cli.discover imports the v2 schema (~0.36s), and a run whose entry
    # declares its protocol must never pay that. The annotation is the only
    # thing here that needs the name.
    from crow_cli.discover import Connection
```

**Verified**: after `import crow_cli.cli.main`, `sys.modules` contains no
`acp.experimental.v2`, no `crow_cli.discover`, no `crow_cli.client2`.

`agents` now prints `"protocol": s.protocol or "auto"`, with the footnote
`protocol 'auto' = asked at initialize`.

### 2.8 `client2/subagent.py` — adoption

```python
async def start(self, cwd, model=None, config_dir=None, config_file=None,
                argv=None, env=None, conn: Optional[Connection] = None) -> None:
    if conn is not None:
        reader, writer = conn.reader, conn.writer
        self.proc = conn.proc
        self.stderr = conn.stderr        # take the drain over; two readers on one
        self._drainer = conn.drainer     # StreamReader would split lines
    else:
        reader, writer, self.proc = await self._stack.enter_async_context(
            spawn_stdio_transport(...))
        self._drainer = asyncio.create_task(self._drain_stderr(),
                                            name="crow-subagent-stderr")
    self.conn = v2.ClientSideConnection(self.client, writer, reader)
    if conn is not None and conn.initialized:
        adopt_v2(self.conn, conn.response)
    else:
        await self.conn.initialize(v2.schema.InitializeRequest(
            protocol_version=v2.PROTOCOL_VERSION, info=self.info))
```

`close()` needed no change: `self._stack` is empty when adopted, so `aclose()`
is a no-op and `agent_connection` owns shutdown. `close()` cancels `_drainer`;
`agent_connection`'s `finally` cancels again, which is a no-op.

### 2.9 Files changed, and verification

```
src/crow_cli/discover.py               317   NEW
src/crow_cli/agents.py                 286   protocol: Optional[str] = None
src/crow_cli/tui/agent_servers.py      230   one line: `not in (None, V1)`
src/crow_cli/client/main.py            537   initialized= flag, __version__
src/crow_cli/cli/main.py              1456   _dispatch + 3-way run + agents 'auto'
src/crow_cli/client2/main.py           649   conn= threading, discovered protocol
src/crow_cli/client2/subagent.py       583   start(conn=), adopt_v2
tests/unit/test_discover.py            291   13 tests, NEW
tests/unit/test_agents_registry.py     349   38 tests, 2 updated
tests/integration/test_cli_run_dispatch.py 734  27 collected, 5 new + a peer fix
```

Commit `07f4ec9b feat: ask the agent which protocol it speaks instead of
declaring it` — 10 files, 976 insertions, 104 deletions.

Verification, all green:

- **3.13 compile**: 351 files across `src` + `tests`, 0 failures, Python 3.13.13.
- **Full suite**: `uv run --project . pytest tests/unit tests/mcp tests/memory
  tests/integration -q` gives **1326 passed, 0 failed** in 434s (baseline was
  1311).
- **`crow-cli agents`** against the real config: all four entries show `auto`;
  `v2-agent`'s tools show `crow-mcp2`.
- **Live smoke, undeclared v1** (`smoke-v1` running `crow-cli acp`): rc 0,
  banner `Agent: smoke-v1 (acp)`, `SMOKE-V1-OK`.
- **Live smoke, undeclared v2** (`smoke-v2` running `crow-cli acp2`): rc 0,
  banner `Agent: smoke-v2 (acp2)`, `SMOKE-V2-OK`, `idle (end_turn)`.
- **Live, the real entry**: `crow-cli run -a v2-agent -m qwen3.8-max "Reply
  with exactly: V2-AGENT-OK"` gives rc 0, `Agent: v2-agent (acp2)`, `MCP
  servers: crow-mcp2`, `V2-AGENT-OK`, `idle (end_turn)`.
- **Mutations killed** (4): `BY_VERSION.get(version)` to `.get(version, V2)`;
  dropping `proc.wait()` in `_silent`; `if server.protocol is None:` to `if
  True:`; the discovered `Connection(..., True, ...)` to `False`.

Smoke-test environment, for reproduction: strip every `CROW_CONFIG*` key from
`os.environ`, add `NO_COLOR=1 COLUMNS=200`, `cwd="/tmp"`, and point
`--config-file` at a scratch registry. Leave `TERM` alone — `TERM=dumb` makes
rich force 80 columns regardless of `COLUMNS`.

### 2.10 Config fixes applied to `~/.agents/crow/` (not version controlled)

The `v2-agent` entry in `config.yaml` is now:

```yaml
  # No `protocol:` — `run` asks the agent at `initialize` and drives it with
  # whatever it answers, so this entry cannot disagree with its own agent.
  # The tool supply belongs HERE rather than in a `--config-file`: agent2 reads
  # no config for tools, the client hands them over at `session/new`. And
  # `mcp2` serves `execute` and nothing else, so it takes no --include-tools.
  v2-agent:
    type: custom
    command: uv
    args: [--project, /home/thomas/.agents/crow/src/crow-cli, run, crow-cli, acp2]
    mcpServers:
      crow-mcp2:
        transport: stdio
        command: /home/thomas/.agents/crow/src/crow-cli/.venv/bin/crow-cli
        args: [mcp2]
```

**`~/.agents/crow/configs/v2_agent.yaml` was deleted** — orphaned and inert. It
was wrong for two independent reasons:

1. **`mcp2` has no `--include-tools`.** `cli/main.py:265`: *"subtools ambient in
   the kernel, so there is no --include-tools here."* Settled: `mcp2` gets no
   `--include-tools`.
2. **`agent2` never reads `config.mcp_servers`** — only `request.mcp_servers`
   (`agent2/agent.py:272, 378, 445`). So a `--config-file`'s `mcpServers` is
   inert for tool supply. `acp2` *does* accept `--config-file`/`-o`
   (`cli/main.py:149`); that part was valid, just useless here.

Other config facts, because they cost time to rediscover:

- Keys are **FLAT**, not nested under `llm:`.
- `apply_config_overrides` handles each key as an **ASSIGNMENT, not a merge**
  — an override yaml listing `agent_servers` replaces the whole registry.
- `db_uri: sqlite:////~/.agents/crow/crow.db`. 5 providers (alibaba, llamacpp,
  unsloth, fireworks, openrouter), 25 models. `qwen3.8-max` mapping to alibaba
  is the e2e pin.
- `MAX_COMPACT_TOKENS 180000`, `max_retries_per_step 3`, `system_prompt_path` set.
- Four `agent_servers`: `crow-execute` (top = default), `crow-dev`,
  `bonsai-micro`, `v2-agent`. **None declares `protocol`.**
- **No `redis_url` key**, so it falls back to `redis://localhost:6379/0`,
  which is up (`PING -> True`). No `image_store.s3`.
- `config/config.py:374-377` logs `INFO:crow_logger:RAW config.yaml
  mcpServers: …` to **stderr** on every `Config.load`. Pre-existing noise; it
  does not pollute `-j` stdout, but it *will* appear in a captured stderr and
  has already been mistaken for a real error once.

---

## 3. The v2 conversion: what it actually bought

**One real gain, structural. The rest a wash with genuine costs.**

### The gain

In v1, `session/prompt` returns `PromptResponse(stop_reason=...)`. The response
**ends the turn**, which makes a prompt a function call: you block, and the only
way to stop waiting is to kill the callee.

In v2, `PromptResponse` carries only `field_meta`. It acknowledges acceptance,
and the stop reason moved to a `state_update` notification.

Three consequences, and the third is the reason to have done this at all:

1. `SubagentDriver.prompt` splits into *send* and *wait*, so a caller that ran
   out of patience can hand the turn to a background waiter instead of killing
   a child that was about to answer.
2. **A wake can look exactly like a prompt.** Both are events into the same
   inbox; neither is a return value somebody is blocked on.
3. Every carried agent2 design decision — a parked session reports `idle` with
   no second resting state, `task` as a subtool, mailbox row committed then
   published, one subscriber task per agent process, `wait=False` as the
   default — is a **session state machine shape that v1 could not hold**. v1's
   loop returned when it ran out of foreground work, the generator ended, and
   with it all awareness of the session. That is why v1 needed the delegation
   hold: block *inside* the turn polling the mailbox every two seconds, because
   a returned loop was a deaf loop.

§5 is the first feature that spends that gain.

### The wash

- v2 removes the client fs/terminal/modes surface crow never used.
  `ClientCapabilities(terminal=False)` existed purely to *decline* the
  terminal; v2 has nothing to decline. A real loss for an IDE-hosted agent —
  which is Zed's use case, not crow's.
- `set_mode` becoming `set_config_option` is a genuine unification; crow
  already published `model` as a config option in both protocols.
- `session/load` becoming `session/resume` with an explicit `replayFrom`.
  crow's headless driver doesn't ask: the transcript is already in the shared
  sqlite.
- Unknown-value tolerance in enums and unions. crow constructs 21 of 23 union
  members; `_RENDERS` covers 17; `UNRENDERED = {"plan_update","plan_removed"}`
  deliberately. The rule: **a renderer prints what it does not understand.**
- `MethodRouter` answers `method_not_found` for missing handlers, so v1's
  explicit stubs were deleted rather than ported.

### The costs

- **The wire didn't change.** *"Nothing about v2 changes the underlying
  JSON-RPC framing."* Every transport problem is identical: the
  undrained-stderr-blocks-the-child landmine, `spawn_stdio_transport`'s
  default env being a trim, `env` as an overlay, the 120s spawn budget.
- It is `acp.experimental.v2`, and the doc says gate it behind flags until it
  stabilizes — which is exactly why `adopt_v2` pokes `conn._state`.
- **"null = cleared" is unimplementable through this SDK**: `agent.py:_dump`
  uses `exclude_none=True, exclude_unset=True`, so a `None` field never
  reaches the wire.
- **Append vs replace**: `ToolCallContentChunk` APPENDS,
  `ToolCallUpdate.content` REPLACES. This is the sole reason `_run_mcp_tool`
  has no `progress_handler` — see §8.
- **Two capability vocabularies forever.** 317 lines of `discover.py` that
  would not exist with one protocol.

### Unchanged either way

The react loop, tools, memory, compaction, model routing. `agent2/tools.py:466
_execute_payload` even has a plain-text fallback, so agent2 tolerates a **v1**
MCP server. The reverse is not true: agent1 has no tolerance for the v2
envelope, and `mcp2` returns `json.dumps({exit_code, output, timed_out,
raw_bytes_b64})` where `mcp` returns plain text.

### For the Rust work

Two things to check **before** writing the Rust transport:

1. Does the Rust `ClientSideConnection` separate "mark myself initialized"
   from "send initialize"? If it fuses them the way Python's does, the Rust
   client needs the same adoption hook.
2. The union initialize has a shelf life (§2.4).

---

## 4. Wake: built, wired, and the one missing link

### 4.1 The three pieces

**`src/crow_cli/wake.py`** (130 lines) — `Poke` plus `publish_wake`. ONE redis
channel for the whole deployment (`CHANNEL`). The row is committed first, the
poke second, and the poke carries only `session_id` + `task_id`: **"go look,"
never "here is what you will find."** Every bus failure degrades to latency,
never to a wrong answer:

| failure | effect |
|---|---|
| redis down | `PARK_BACKSTOP_S` (30s) poll |
| poke lost | same |
| poke twice | second consult finds an empty mailbox |
| poke for a session this process doesn't own | dropped by the subscriber |

v1 had no bus at all, which is why it needed the delegation hold.

**`src/crow_cli/timers.py`** (278 lines) — celery as **the timer wheel only**:
`default_redis_url()`, `database_url()`, `configure()`, `fire_timer(task_id,
db_uri, redis_url)`, `make_app(redis_url) -> Celery`, a module-level
`app = make_app(default_redis_url())` so bare `celery -A crow_cli.timers:app
worker` resolves, `schedule_timer(...)` at `:205`, and `run_worker(redis_url,
*, concurrency=1, loglevel="INFO")` with `--pool=solo`. `TASK_NAME =
"crow.fire_timer"`; `KIND = "timer"`; queue `crow` (tests use
`crow-test-<pid>`).

`fire_timer` is `finish_task` (row terminal plus delivery in ONE commit) then
`publish_wake`. Idempotent, so celery's at-least-once is safe — a redelivery
that finds a terminal row does nothing at all. Everything the job needs rides in
the message, because a worker has no rail; owner, priority, kind and note do
not, because they are on the row.

`make_app` is a **factory**, not a reconfigured global, because celery caches
the broker connection ON the app and a connection that failed once keeps failing
for the life of the process.

CLI: `crow-cli timers` at `cli/main.py:293`.

Tests: `tests/unit/test_timers.py` (URL arithmetic, `fire_timer` called
directly, redelivery), `tests/integration/test_timers_live.py` (4 tests, real
broker, spawns a worker, dead-broker degradation).

**`agent2/deliveries.py`** — the consult half:

```python
async def consult(engine, session, emitter, *, high_only=False) -> bool:
    deliveries = claim_deliveries(engine, emitter.session_id, "high" if high_only else None)
    if not deliveries: return False
    for d in deliveries:
        await session.add_message({"role": "user", "content": d["content"]})
        await emitter.user_chunk(emitter.start_message(), d["content"])
    return True
```

`claim_deliveries` is ONE `UPDATE...RETURNING`, so concurrent consult points
race for the same rows and each delivery is injected **exactly once** — on
sqlite the whole-db write lock serializes claimers, on postgres the same holds
at row level across machines. Returning True tells the react loop it **must
react rather than end the turn**. Each delivery is echoed to the client as a
`user_message_chunk`, because the model is about to respond to something the
user did not type, and a conversation that hides its own inputs cannot be
followed or replayed.

The four consult breakpoints in `agent2/react.py`:

| line | where | claims |
|---|---|---|
| `:115` | prompt-start drain, before the first model call | everything |
| `:134` | top of every loop iteration | `high` only |
| `:227` | model produced a final answer with no tool calls | everything — and if it got anything, `Continue()` instead of `Done` |
| `:272` | between tool batches | `high` only |

### 4.2 Wiring — what is actually connected

| link | where | state |
|---|---|---|
| `WakeWatcher` class | `agent2/watcher.py:41` | built |
| subscriber task | `agent2/watcher.py:74` `create_task(self._listen(), name="crow-wake-watcher")` | built |
| registry constructs it | `agent2/sessions.py:180` `WakeWatcher(config.redis_url, self._inbox_for)` | **wired** |
| registry starts / stops it | `agent2/sessions.py:592` / `:644` | **wired** |
| poke to inbox route | `agent2/sessions.py:543` `_inbox_for` returning `self.drivers.get(sid)` | **wired** |
| `publish_wake` in production | `tools/task.py:310` `live.poked = await publish_wake(...)` | **wired** |
| react consult breakpoints | `agent2/react.py:115, 134, 227, 272` | **wired** |
| driver park on the inbox | `agent2/driver.py:419-443` | **wired** |
| `schedule_timer` caller | — | **NOTHING** |

Degradation: an empty `config.redis_url` makes `WakeWatcher.start` a no-op and
`publish_wake` return False, so it is mailbox polling only (`config/config.py:465`,
pinned by `tests/unit/test_configure.py:132`).

### 4.3 The gap

`schedule_timer` has **no production caller**. Grep finds only its own `def` at
`timers.py:205` plus tests. It is not in `_LAZY_V2`; nothing in `agent2/`
reaches it. The timer wheel is built, tested, runnable — and nothing ever puts a
job on it.

And the deeper gap is the one §5 addresses: **the model has no way to feed
itself.**

---

## 5. PROPOSAL: `remind`

> *Self-directed input that fires when the session goes idle.*

**Status 2026-09-24: the MECHANISM shipped; `remind` did not.** §5.4's
state-triggered wake is built and load-bearing — the driver consults a
persisted objective at the idle transition and, when it decides to continue,
writes an ordinary mailbox row that the loop's existing check picks up. What
ships on top of it is `/goal`, not `remind`: one objective per session that
keeps re-firing until its row leaves `active`, with the ceilings §5.8
recommended skipping. The subtool below, a model leaving itself a single note,
is unstarted, and §5.10's checklist is with it.

§5.1–§5.3 and §5.5–§5.9 remain the argument for why the trigger is a state and
not a clock, and nothing in `/goal` contradicts them; §5.3 in particular is now
proven rather than asserted, because a goal continuation is exactly the case
§5.3 describes and it needs no worker, no broker and no poke. §5.4 ends with
what actually shipped and the three places it differs.

### 5.1 What the model gets

```python
r = await remind("the migration job should be done by now — check it and report")
# r.task_id == "task-12", r.status == "running"
```

The turn continues. The model finishes what it was doing, produces its final
answer, the driver reports `idle` — **and at that instant** the note lands in the
mailbox and starts a **new turn** whose first user message is the note.

`task_read()` lists it next to the subagents. `task_cancel("task-12")` drops it
before it fires. Both already work, unchanged, because it is an ordinary task
row.

### 5.2 Why not `task`

Three separate walls, all enforced rather than documented:

1. **`task()` always mints a child.** `_register_task` writes
   `owner_session=cell.session_id`, then `driver.new_session(...)` and
   `set_task_sub_session(engine, task_id, sub)`. Owner is the caller; `sub` is
   a fresh session. There is no branch where the target is the caller.
2. **`_resolve(engine, ref)` cannot address self.** It matches `get_task(ref)`
   (a `task_id`) or `task_by_sub_session(ref)` — the **child's** wire id.
   Never the caller's own session id.
3. **`task_send` requires a sub-session.** `if not sub: raise
   TaskError(f"{row.task_id} never got a subagent session, so there is nothing
   to re-attach to — launch a new task instead")`.

The degenerate workaround — `task("reply with exactly: …", wait=False)` — does
technically self-prompt, because the child's completion lands in the parent's
mailbox. It costs a whole crow process, a fresh context and a model call, and the
text comes back wrapped in somebody else's answer framing. A self-message routed
through a stranger.

### 5.3 Why not a delay

A clock is the wrong trigger for "tell me this when you're free."

- If the session is still mid-turn when the timer fires, the delivery lands at
  whatever consult breakpoint comes next and **interrupts** — the opposite of
  the intent.
- If the session idles before the timer fires, nothing happens until the clock
  says so. The session sits idle with work it could be doing.
- A delay needs celery, which needs a worker process running, which is a
  deployment dependency for what should be a local state transition.

What is actually wanted is a **state-triggered** wake: fire on `running` to
`idle`. That is a property of the driver, and the driver is the only thing that
knows the state. This is also the feature that spends §3's gain — v1's loop
returned and was deaf, so there was no idle state to trigger on.

`schedule_timer` stays as built. It is correct, tested, and the right answer to a
question nobody is asking yet. This proposal does not use it and does not remove
it.

### 5.4 The mechanism: fire at the idle transition

The key realization is that **the deferral belongs in the task row's status, not
in the mailbox.** A `Task` with `status="running"` and no `sub_session` already
means exactly "something is pending that has not produced a delivery yet." So:

- `remind()` writes the row and **stops**. No delivery, no poke, no celery.
- The driver, at the moment it enters `idle`, closes every running reminder
  row it owns. `finish_task` lands the delivery in the same commit.
- Everything downstream is unchanged, because by the time anything looks, it
  is an **ordinary pending delivery**.

This is much smaller than the obvious alternative — a third `priority` value
meaning "claimable only at a real turn boundary" — which would need changes to
`claim_deliveries`, to `consult`, to `react.py:227`, and to *two* different
callers of `_mailbox_pending()` that turn out to be asking different questions
(`driver.py:209` asks "should I skip parking?", `driver.py:261` asks "was this
wake real?"). Deferring in the row's status keeps the mailbox meaning one thing.

`agent2/driver.py`, as proposed (the shipped `_park` differs in ordering — see
the end of this section):

```python
async def _park(self) -> bool:
    await self._set_state(
        "idle", stop_reason=self._last_stop, usage=self._last_usage
    )
    if self._fire_deferred():
        # Idle has been announced, and a deferred self-input was waiting on
        # exactly that transition. Do not block: return to the loop, which
        # re-drains, sees a non-empty mailbox, and runs the turn.
        return True
    try:
        event = await asyncio.wait_for(self.inbox.get(), timeout=PARK_BACKSTOP_S)
    except TimeoutError:
        return not self._stopping
    self.submit(event)
    return True

def _fire_deferred(self) -> bool:
    """Close every running reminder this session owns, landing its delivery.

    The trigger is the state transition, not a clock. ``finish_task`` writes
    the mailbox row in the SAME commit that takes the row terminal, so the
    wake path below — ``_mailbox_pending``, ``consult``, the prompt-start
    drain — carries it with no idea it was deferred, and none of it changed.

    Idempotent by construction: ``finish_task`` returns False for a row that
    is already terminal, so two processes racing to fire one reminder produce
    one delivery between them.
    """
    if not self.deps.engine:
        return False
    fired = False
    for row in deferred_reminders(self.deps.engine, self.session_id):
        fired |= finish_task(
            self.deps.engine,
            row.task_id,
            result=row.prompt,
            status="completed",
            content=row.prompt,
        )
    return fired
```

One new read in `memory/reads.py`, mirroring `running_tasks`:

```python
def deferred_reminders(engine, owner_session: str) -> list[Task]:
    """Running reminder rows this session owns, oldest first."""
    with Session(engine) as db:
        return (
            db.query(Task)
            .filter_by(
                owner_session=owner_session,
                kind=KIND_REMINDER,
                status="running",
            )
            .order_by(Task.created_at)
            .all()
        )
```

And the subtool, in `tools/task.py` beside its siblings:

```python
@subtool(tool="remind")
async def remind(note: str, *, priority: str = "low") -> TaskResult:
    """Leave yourself a message that arrives when this session goes idle.

    Not a timer and not a subagent. The note becomes a user message in YOUR
    OWN transcript, opening a NEW turn, at the moment this turn ends and the
    session reports idle. Use it to hold a thought across a turn boundary
    rather than to defer work to a child.

    The turn you are in finishes first, and its final answer stands: the note
    does not extend the current turn, it opens the next one. Cancel it with
    ``task_cancel(r.task_id)`` before it fires; list it with ``task_read()``.

    Args:
        note: the text you will be handed. Verbatim, as a user message.
        priority: as ``task`` — "high" makes the new turn surface it at the
          top of its first loop iteration instead of at the prompt-start drain.

    Returns:
        TaskResult with the handle. ``status`` is "running" until it fires.

    Raises:
        TaskError: there is no identity rail or no database.
    """
    cell = _cell()
    engine = _engine()
    task_id = launch_next_task(
        engine,
        owner_session=cell.session_id,
        kind=KIND_REMINDER,
        tool_call_id=cell.parent_tool_call_id,
        prompt=note,
        priority=priority,
    )
    return TaskResult(
        task_id=task_id, status="running", session_id="",
        prompt=note, waited=False, result="",
    )
```

`KIND_REMINDER = "reminder"` goes in `memory/models.py` next to `Task`, because
the writer (`tools/`) and the reader (`agent2/driver.py`) both need it and
`agent2` must not import from `tools`. (`timers.KIND = "timer"` should arguably
move there too for symmetry; that is optional churn and not part of this.)

Register in `tools/__init__.py:42`:

```python
_LAZY_V2 = {
    "remind": ("crow_cli.tools.task", "remind"),
    "task": ("crow_cli.tools.task", "task"),
    ...
}
```

#### What actually shipped, and where it differs

Built 2026-09-24 as the `/goal` continuation. The shape is the one above —
consult at the idle transition, write a mailbox row, let the loop's existing
`_mailbox_pending()` find it — with three differences, each forced by what the
deferring thing turned out to be.

| the proposal | what shipped | why |
|---|---|---|
| `remind()` writes a `Task` row with `kind="reminder"`, `status="running"` | `set_goal()` writes a `Goal` row with `status="active"` | A note is one-shot and a goal is a loop, so the row carries the loop's account: `turns_used`, `tokens_used`, `time_used_seconds`, `token_budget`, `blocked_reason`. None of that fits a `Task`, whose counters describe one child's run. |
| `_fire_deferred()` calls `finish_task`, which lands the delivery in the same commit that takes the row terminal | `_goal_continuation()` calls `queue_delivery`, then `account_goal_usage` | A goal has no task row to finish, and it has to SURVIVE firing — the row is the loop's state, not the note's envelope. `queue_delivery` is `finish_task`'s inline delivery write, exposed. Two commits instead of one, and the window between them is benign: a crash there leaves one continuation queued against a counter one low, which is a rounding error on a loop guard and not a way to loop forever. |
| `_park` announces `idle`, THEN fires | `_park` consults the goal BEFORE announcing `idle` | A session that is about to start another turn on its own account is not idle, and saying so is a lie the client renders. Hence `states() == ["idle","running","idle"]` for TWO turns: `_set_state` dedupes a state that never changed, so the continuation never announces itself. |

The real names, for grepping:

- `memory/models.py` — `Goal`, plus `GOAL_ACTIVE`, `GOAL_PAUSED`,
  `GOAL_BLOCKED`, `GOAL_BUDGET_LIMITED`, `GOAL_COMPLETE`.
- `memory/reads.py` — `get_goal`, `active_goal`.
- `memory/writes.py` — `set_goal`, `update_goal_status`, `clear_goal`,
  `account_goal_usage`, `queue_delivery`.
- `agent2/goal.py` — `CONTINUATION_PROMPT`, `continuation_text`, `progress`,
  `eligible`, `Verdict`.
- `agent2/driver.py` — `_goal_continuation` (the consult), `_settle_goal` (the
  accounting, and the cancel-pauses / error-blocks exits), and `_park`'s first
  two lines.
- `agent2/react.py` — `Done.tools_used`, `Done.tokens_spent`.
- `tools/goal.py` — `goal_done`, `goal_blocked`, bound in `_LAZY_V2`.
- `agent2/slash.py` — `goal_command`, imported for its side effect from
  `agent2/agent.py` so that a v1 process never sees the name.
- `config/config.py` — `GoalConfig`, `goal: {max_turns: 25, max_tokens: null}`.

What did NOT change is still §5.5's list, and the two rows that matter most
held. `consult` injects `d["content"]` verbatim and has no idea a goal wrote
it. `wake.py`, `watcher.py` and redis are not involved — no poke, no bus, and
the whole thing works with none configured. `timers.py` and celery are
likewise untouched and still have no production caller, which is §5.3's
argument surviving contact with the one feature that looked like it would need
a scheduler.

### 5.5 What does NOT change

This is the point of the design. Verified by reading, not assumed:

| thing | why it is untouched |
|---|---|
| `TaskDelivery` schema | Unchanged. It is now constructed in TWO places rather than one — `finish_task` and `queue_delivery`, both in `writes.py`, the second being the first's delivery write exposed for a caller with no task row. Same columns, same `status="pending"`, no new field. |
| `Task` schema | `sub_session` is already `nullable=True`; `kind` is already free text defaulting to `"subagent"`. |
| `claim_deliveries` | Keyed on `session_id` with an optional exact `priority` match. No join to `tasks`. Never asks where a row came from. |
| `consult` | Injects `d["content"]` verbatim as a user message and echoes it. Unchanged. |
| `react.py:115/134/227/272` | All four breakpoints behave identically; the row is a normal pending delivery by then. |
| `pending_deliveries` / `_mailbox_pending` | Filters on `status="pending"` only, no priority filter, so it sees the row the moment `finish_task` — or `queue_delivery` — commits. |
| `wake.py`, `watcher.py`, redis | **Not involved.** No poke. The trigger is local driver state, so `remind` (and the `/goal` continuation that shipped instead) works with no bus configured at all. |
| `timers.py`, celery | Not involved — and this row is now load-bearing rather than incidental. `/goal` is the feature that looked most like it would need a scheduler: it re-fires on its own, indefinitely, with nobody watching. It needs no clock, no broker and no worker, because the trigger is a state the driver already passes through. §5.3's argument is no longer a prediction. `schedule_timer` still has no production caller. |
| v1 / `agent/` | Not touched. v1 has no driver and no park, so a v1 kernel would write a row nobody ever fires — which is why this is `_LAZY_V2`. |
| `launch_next_task` | Its docstring already claims two callers: *"the `task` subtool, and a scheduled wake. Both need the same id space, because both write rows the same mailbox delivers from and the same owner reads with the same `task_read()`."* `remind` becomes the second one in practice. |

The whole feature is: one subtool (~40 lines with the docstring), one read (~12
lines), one driver method (~20 lines), four lines in `_park`, one constant, one
`_LAZY_V2` entry.

### 5.6 Walkthrough

```
turn N
  model: execute(...) -> remind("check the migration")   row task-12 running, kind=reminder
  model: ...more tool calls...
  model: final answer, no tool calls
  react.py:227  consult() -> nothing pending (task-12 has NO delivery yet)
  react returns Done(stop_reason="end_turn")
driver.run() loop
  _drain() -> empty
  _mailbox_pending() -> False            (no pending rows; task-12 is running, not delivered)
  _park()
    _set_state("idle", stop_reason="end_turn")   <- client sees idle
    _fire_deferred() -> finish_task(task-12)     <- delivery row committed, returns True
    return True (does NOT block on the inbox)
  loop
  _drain() -> empty
  _mailbox_pending() -> True                     (task-12 is now pending)
  _run_turn([])
    prompts empty, _mailbox_pending() True -> does not bail
    _set_state("running")                        <- client sees the boundary
    react()
      :115 prompt-start drain claims task-12
           -> add_message({"role":"user","content":"check the migration"})
           -> user_message_chunk to the client
      model sees its own note as the first input of turn N+1
```

The `idle` is real, not vestigial: the client sees `idle` then `running`, the
transcript gets a turn boundary, and turn N's final answer is committed before
the note is injected. That last part is the substantive difference from a
`priority="low"` delivery, which `react.py:227` claims *inside* the turn and then
`Continue()`s — the model never gets to finish its thought.

Note what this makes possible that was not possible before: **a session that
continues itself with no client involved.** Combined with `task`, a session can
spawn children, defer its own next input, and wake itself. That is the
stateful react loop, and it is the thing v2 was worth doing for.

### 5.7 Durability, races, restarts

- **Process death before idle.** The row stays `running`. On resume,
  `driver_for` leads to `provision`, the loop starts, `_drain()` is empty,
  `_mailbox_pending()` is False, so `_park()` runs, emits idle, and **fires
  the reminder**. A restart picks it up where a poke-based design would have
  lost the wake. The trigger is durable because it is a state, not an event.
- **Two processes, one session.** `_inbox_for` returns `None` for a session
  this process doesn't hold, so only the owning driver parks and fires. If a
  resume races the original, `finish_task` returns False for the loser — one
  delivery, not two.
- **Session never idles** (model loops to `max_turns`).
  `Done(stop_reason="max_turn_requests")`, the driver parks, fires. Same path.
- **Reminder written while a subagent is still running.** The driver parks
  anyway — *"There is no second resting state. A delegated task still running
  is background activity."* So the reminder fires while the child works. That
  is correct: the reminder is about *this* session's foreground work, and the
  child's completion arrives in the mailbox on its own schedule.
- **Bus off.** Works. No redis anywhere in the path.
- **No engine** (`config.db_uri` empty). `_fire_deferred` returns False;
  `remind` raises `TaskError` from `_engine()` at write time, same as `task`.

### 5.8 The one real hazard: the self-sustaining loop

A model that reminds itself every turn spins forever, burning tokens with no
human in the loop. This is genuinely new: a `task` child eventually stops; a
self-reminder is a loop with no external termination.

Assessment: **ship it without a budget**, for three reasons.

1. The spin is **visible**. Every iteration emits `idle` then `running` and a
   `user_message_chunk` the client renders. A `wait=False` task storm is
   off-screen; this is on-screen by construction.
2. The spin is **stoppable**. `session/cancel` kills the foreground work,
   `session/close` ends the session, and `task_cancel` drops a pending
   reminder.
3. A budget has no obvious home. `rlm`'s depth budget exists because *"a
   delegate is a copy of its caller… an infinity mirror"* — the depth is a
   property of the call stack and rides the identity rail. A reminder is not
   recursive: it is one row per turn, and the natural counter (rows fired for
   this session) would need to live on the session, the row, or the kernel,
   none of which is obviously right.

If it turns out to be a problem in practice, the cheapest brake is a per-park cap
in `_fire_deferred` plus a counter on the session — but that is a fix for an
observed failure, not a speculative one.

**What happened instead.** `/goal` shipped with three brakes, and the argument
above lost on point 3 only: the spin is still visible and still stoppable, but
"a budget has no obvious home" was wrong. The home is the row that persists the
objective — which a one-shot note, having nothing to persist, never had.
`Goal.turns_used` is the counter and `config.goal.max_turns` (default 25) the
cap; `Goal.tokens_used` against `token_budget` is the second one, flipped in the
SQL `CASE` inside `account_goal_usage` so the write and the limit are one
commit. Both are consulted at the park by `agent2/goal.eligible`, not inside a
per-park counter.

The third brake is the one this assessment could not have predicted, because it
is not a budget: a CONTINUATION turn that ran no tools ends the goal, as
`blocked`. That covers the case where the model is not spinning hard but
spinning still — talking about the work instead of doing it — which no token or
turn ceiling catches early. It is only safe to have because the driver tracks
whether the turn it just finished was one IT caused (`_continuation_in_flight`,
consumed at the top of `_run_turn`), so a person who interjects "what's the
status?" mid-goal gets a text-only answer without blocking their own goal.

### 5.9 Open decisions

| # | question | recommendation |
|---|---|---|
| 1 | Name: `remind` / `wake` / `self_prompt` / `note` / `defer` | **`remind`**. `wake` collides with `wake.py` (the bus). `self_prompt` is accurate but clunky in a transcript. The repo's rule is that names say what they do and that a mode-string dispatcher hides capability — `remind` is a verb the model already knows from human usage. |
| 2 | Does it take `priority`? | **Yes, default `"low"`.** It costs nothing (the column exists, `finish_task` copies it onto the delivery) and it reuses the existing two-value ladder rather than inventing a third. `"high"` means the new turn surfaces the note at `react.py:134` instead of riding the `:115` drain. |
| 3 | Fire all pending reminders at one park, or one per park? | **All.** Matches `_drain`'s existing philosophy — *"All queued prompts go into ONE turn rather than one turn each."* Two notes the model left itself are one turn's worth of context. |
| 4 | Should `remind` also publish a poke? | **No.** The trigger is local driver state; a poke could only cause a spurious wake of a driver that is about to park anyway. Fewer moving parts, and no bus dependency. |
| 5 | Fire on a park that follows a *user* prompt too, or only on a natural end-of-turn? | **Both — don't distinguish.** The driver cannot tell them apart without new state, and "when this session goes idle" is simpler and more predictable than "when this session goes idle for the right reason." |
| 6 | Does `schedule_timer` get wired too? | **Not in this change.** A timed delay isn't interesting. Leave it built and unwired; if a delay is ever wanted, `remind(note, after=300)` delegating to `schedule_timer` is additive and needs no new machinery. |

### 5.10 Implementation checklist

**Unstarted, and now smaller than this.** Every item is about `remind`, which
did not ship. The two driver items were built in a different shape for `/goal`
and are in §5.4's table instead, and the `_LAZY_V2` item is a pattern
`goal_done` and `goal_blocked` followed. Kept as the spec for `remind` if a
model-facing one-shot note is ever wanted: the mechanism it needed now exists,
so what is left is a subtool, a read and a `kind`, with no driver work at all.

- [ ] `KIND_REMINDER = "reminder"` in `memory/models.py`, next to `Task`.
- [ ] `deferred_reminders(engine, owner_session)` in `memory/reads.py`; export
  from `crow_cli.memory`.
- [ ] `remind` in `tools/task.py`, `@subtool(tool="remind")`, importing `KIND_REMINDER`.
- [ ] `_LAZY_V2["remind"]` in `tools/__init__.py`.
- [ ] `SessionDriver._fire_deferred()` plus the four lines in `_park`, in
  `agent2/driver.py`.
- [ ] Tests:
  - unit — `deferred_reminders` returns only running reminder rows for that
    owner; `finish_task` on one lands a pending delivery with the note as
    content.
  - unit — `remind` writes a row with `kind="reminder"`,
    `owner_session=cell.session_id`, no `sub_session`, and returns a
    `TaskResult` with `status="running"`.
  - integration (gate harness) — script a turn that calls `remind` then ends;
    assert `states()` shows `running`, `idle`, `running`; that the second
    turn's history contains the note as a **user** message; and that a
    `user_message_chunk` was emitted for it.
  - integration — `task_cancel` on a pending reminder closes it and it never fires.
  - integration — two reminders in one turn both land in the next turn, one turn.
  - integration — a reminder survives a driver restart: park a fresh driver on
    the same session and assert it fires.
- [ ] `_cancel_orphan`'s message says *"no child of this kernel was driving it
  — the row had been orphaned and has been closed."* For a reminder that is
  functionally right and verbally wrong. Worth a small wording pass so
  `task_cancel` on a reminder reads as a cancellation and not as a cleanup of
  somebody else's mess.

---

## 6. Settled design decisions — do not re-litigate

### From the negotiation work

1. **The protocol is negotiated, not declared.** `AgentServer.protocol` is
   `Optional[str] = None`; `None` means ask at `initialize`. A declared value
   is an override that skips the round trip.
2. **The probe IS the connection** — spawn once, union-initialize, hand the
   live handshaked streams to the chosen stack.
3. **The union initialize carries exactly what each version's own client would
   have sent** for its own fields, including v1's `terminal: false`.
4. **The probe owns the single stderr drainer** and hands the deque plus the
   task to the adopting stack.
5. **`adopt_v2` pokes `conn._state`**, because the SDK fuses the local
   transition to the wire send and offers no adoption path. Pinned by a test
   so an SDK rename fails a test, not a session.
6. **A scripted test peer must obey the spec**: an agent that only speaks v1
   answers `1`, not the echoed request version.
7. `requires-python = ">=3.13"`, and the tree must actually compile on 3.13
   (verified over 351 files). PEP 758 parenless `except A, B:` is **3.14**
   syntax and must not appear.
8. The v1 agent keeps `FileSnapshotHook`. **agent1 is frozen** — deleting dead
   code is still allowed.

### Carried

A parked session reports `idle`; there is no second resting state · the client
echoes the human's message and the agent's required echo is held back for the
length of the turn it owns (`own_echo`) · `timeout=None` in `run_v2` is correct —
there is no `--timeout` flag on `run` · the client defines tools entirely, always
· a client that speaks one protocol REFUSES an entry declared for the other · the
registry lives in `crow_cli/agents.py` and `tui/agent_servers.py` is an adapter ·
the argv LIST is the truth, `.launch` is decoration, no `shlex.split` round trip ·
model choice travels over `session/set_config_option` for BOTH protocols, never
in argv · `run`'s default agent is the TOP entry, and its empty-registry fallback
is crow's own **v2** agent while the TUI's stays v1 · an unknown `-a NAME` raises
and never falls back, spawning nothing · a renderer prints what it does not
understand · terminal bytes go to `sys.stdout.buffer`, not through rich, and the
model's ANSI-stripped `raw_output` is NOT rendered on success · a
`terminal_update` snapshot is skipped for any terminal that already streamed
chunks · `TerminalClient` subclasses `HeadlessClient` and calls
`super().session_update()` FIRST · `env` on a spawn is an OVERLAY · `--fork-idx`
becomes a three-part wire id resolved ONCE in `run` · an unknown `-m` fails
client-side before the spawn · `crow-cli agents` takes `-o/--config-file` · read
the UNION, not the `$defs` entry · sweep by enumeration, not by reading · read the
title back out of the store · derive the root agent id (compaction swaps it) · one
attempt, not one success, for a fact that can never become knowable · `updated_at`
is not sent · **a deletion is a fix** · request/notification absence asymmetry is
principled · a log line worth keeping is worth pinning · unwired adapter surface
stays when it duplicates nothing · raw `_conn.send_request(method, None)` for
refusal tests · **a surviving mutation is a reason to DELETE code, not to write a
test for it** — unless it is load-bearing, in which case it is a test gap · redis
pub/sub poke · `task` as a subtool · FULL REWRITE, not a shim · no internal
tool-calling framework · mailbox row committed then published · one subscriber
task per agent process · `wait=False` default · **celery is the timer wheel only**
· `make_app()` is a factory · queue `crow` / `crow-test-<pid>` · `--pool=solo` ·
**`mcp2` gets NO `--include-tools`** · `DEFAULT_PORT = 2770` · the gate's agent
transport yields once per outgoing message · `completed` carries a `summary` ONLY
when nothing streamed · `gate()` takes `compactor=` · `session/list` with no cwd
lists ALL · base64 `{"offset": N}` cursor, `PAGE_SIZE = 50` · title = the ROOT
agent's first user message, 50 chars · forks excluded · `session/close` on a
not-held session SUCCEEDS · replay mints `replay/<seq>/<llm id>` ·
`set_agent_model` is a sync writer · `persist` is keyword-only defaulting False ·
`str()` is the right `AnyUrl` coercion.

### Out of scope

The TUI (said several times). The bare-`run` retarget — *"bare crow-cli run is
still v1 sounds about right"*; the top entry `crow-execute` stays the default.
The 3.13 venv.

---

## 7. SDK and wire facts worth keeping

Expensive to re-derive. All measured.

### `crow_cli/agents.py` public surface

```
V1="acp"; V2="acp2"; PROTOCOLS=(V1,V2); CROW_IDENTITY="crow-ai.dev"
class AgentServerError(Exception)
@dataclass(frozen=True) class AgentServer:
    name, command, args=(), env={}, protocol=None, display_name="",
    mcp_servers=None, builtin=False
    .argv -> [command, *args]   .title -> display_name or name   .launch -> " ".join(argv)
parse_agent_server / resolve_agent_server (unknown name RAISES) / parse_agent_servers
  (config order; bad entries logged+skipped on logger "crow_cli.agents")
crow_agent_server(protocol=V1, config_dir=None, config_file=None)
default_agent_server(...)   # TOP entry, else crow's own in fallback_protocol
select_agent_server(name, agent_servers, fallback_protocol=V1, config_dir=None, config_file=None)
tool_supply(server, config_mcp_servers)
```

`env` and `args` are coerced with `str()`. `parse_agent_server` does
`protocol = spec.get("protocol")` and then `if protocol is not None and protocol
not in PROTOCOLS:` — the error strings are unchanged (`"unknown protocol 'acp3'"`,
`"expected one of acp, acp2"`). Consumers: `cli/tui_cmd.py:22,52-67`,
`tui/app.py:852,868`, `tui/screens/store.py:30,501`,
`cli/init_cmd.py:149 add_default_agent_server` leading to
`cli/source.py:72 default_agent_server_entry`.

### `cli/main.py` structure (1456 lines, maxlen 120)

`_content_mode` · `cli_list_sessions` · `cli_query_memory` · `cli_query_session` ·
`_sampling_label` · `models` · commands at `:65 acp`, `:130 acp2`, `:195 mcp`,
`:247 mcp2`, `:293 timers`, `:348 init`, `:378 auth`, `:403 inspect`,
`:568 list-sessions`, `:596 query-memory`, `:637 query-session` · `agents` around
`:789` · `run` around `:866` · `_emit_json` · `_dispatch` around `:1126` ·
`_run_async` around `:1183` · `_print_version_and_exit` · `global_callback`
(`--version/-V`, eager) · `main`.

### v1 vs v2 client connection methods

```
v1 acp/client/connection.py:111 ClientSideConnection:
  initialize, new_session, load_session, list_sessions, set_session_mode,
  set_config_option, authenticate, prompt, fork_session, resume_session,
  close_session, cancel, ext_method, ext_notification, close

v2 acp/experimental/v2/client.py:33 ClientSideConnection:
  initialize, login, logout, list_providers, set_provider, disable_provider,
  new_session, list_sessions, delete_session, fork_session, resume_session,
  close_session, set_config_option, prompt, cancel_session, mcp_message,
  notify_mcp, start_nes, suggest_nes, accept_nes, reject_nes, close_nes,
  did_open, did_change, did_close, did_save, did_focus,
  send_extension_request, send_extension_notification, close
```

- v1 `SetSessionConfigOptionResponse.config_options` is **REQUIRED** — an
  agent returning `None` makes the CLIENT raise `ValidationError`. v2's too.
- v1 `set_config_option(config_id, session_id, value)` with a **str** value
  builds the SELECT variant; v2 takes
  `SetSessionConfigOptionIdRequest(session_id, config_id, value, type="id")`.
- Both crow agents publish `model` option values as
  `f"{provider_name}:{model_id}"` with `name=m.name` (`agent/main.py:349`,
  `agent2/sessions.py:333`) — which is why `-m` is translated client-side by
  `LLMConfig.option_value(name)`.

### v2 emitter field names the renderer reads

```
SessionTerminalUpdate:      terminal_id, command, cwd, output(TerminalOutput.data = BASE64), exit_status
SessionTerminalOutputChunk: terminal_id, data (BASE64)
SessionToolCallUpdate:      tool_call_id, name, title, kind, status, content,
                            locations, raw_input, raw_output
Agent/Thought/UserMessageChunk: message_id, content (ONE block)
*MessageUpdate variants:                            message_id, content (LIST of blocks)
UsageUpdate: used, size, cost(Cost: amount, currency)
IdleSessionStateUpdate: state, stop_reason, usage     RunningSessionStateUpdate: state
SessionCompactionUpdate: compaction_id, status, summary, error
AvailableCommandsUpdate: available_commands           ConfigOptionUpdate: config_options
ToolKind = read|edit|delete|move|search|execute|think|fetch|other
ToolCallStatus = pending|in_progress|completed|failed|cancelled
```

`UpdateSessionNotification.update` is a union of 23 members with 19
discriminators. `_RENDERS` covers 17; `UNRENDERED = {"plan_update","plan_removed"}`
is deliberate. `user_message_chunk` = mailbox deliveries
(`agent2/deliveries.py:57`); `user_message` = the prompt echo (`driver.py:348`)
and replay (`replay.py:135`). Different discriminators — which is what makes the
narrow `own_echo` suppression safe.

### Other SDK facts

- `acp/experimental/v2/agent.py:28 _dump(model)` = `model_dump(mode="json",
  by_alias=True, exclude_none=True, exclude_unset=True)`. `exclude_none` is
  why a `null` clear is UNSENDABLE.
- `MethodRouter` (`acp/experimental/v2/_router.py`): a missing handler
  attribute gives `RequestError.method_not_found(spec.method)` for a REQUEST
  and a silent `return` for a NOTIFICATION. `_`-prefixed methods route to
  `handle_extension_request` / `handle_extension_notification`.
- `AgentCapabilities` keys: `session, auth, providers, nes, positionEncoding,
  _meta`. crow sets only `session`. `ToolCallLocation` is emitted path-only
  (`agent2/tools.py:679,696`); adding `line=` needs `positionEncoding`
  negotiation.
- `run_agent(agent, input_stream=None, output_stream=None, *,
  stdio_buffer_limit_bytes=52428800, **kw)`.
- fastmcp 3.4.7: `Client.call_tool_mcp(name, arguments, progress_handler=None,
  timeout=None, meta=None)`; `MCPConfigTransport(cfg, name_as_prefix=False)`.
- The authoritative spec is on disk at
  `~/.agents/crow/src/python-sdk/schema/v2/schema.json` (265 `$defs`, each
  with a `description`), plus `schema/schema.json` (v1) and
  `schema/v2/meta.json`. Some models are inline `anyOf` branches and are NOT
  in `$defs` — use `getattr(vs, name)`, and **read the union, not the `$defs`
  entry**. Live: `https://agentclientprotocol.com/protocol/v2/...`.

### `crow_cli.memory` exports

`get_engine, get_ro_engine, normalize_db_uri, create_database, build_agent_id,
parse_agent_id, wire_session_id, get_max_agent_idx(engine, session_id,
fork_idx=1)` (**`max(..., default=1)`**), `get_max_fork_idx, running_tasks,
pending_deliveries, session_title, Agent, Session`. `crow_cli.memory.db` does NOT
export `Agent`. `crow_cli.memory.running_tasks` STAYS — v1's delegation hold uses
it at `agent/react.py:932`.

Task-side reads and writes, for the §5 work:

```
memory/writes.py   launch_task :87    launch_next_task :117   set_task_sub_session :162
                   reopen_task :172   finish_task :186 (TaskDelivery( at :216)
                   cancel_task :227   mark_delivered :242   claim_deliveries :252
memory/reads.py    get_task   task_by_sub_session :126   count_tasks
                   running_tasks   owner_tasks   pending_deliveries :176
```

`finish_task(engine, task_id, *, result, status="completed", content="", deliver=True)`
returns False for a row that is missing or already terminal — that is the
idempotence the whole at-least-once story rests on. `deliver=False` closes the row
without a mailbox message, for the one case where the owner already knows: a launch
that failed synchronously and raised at the caller.

### `mcpServers` — measured

`mcp --include-tools execute` and `mcp2` both serve exactly `['execute']`. What
differs is the RESULT CONTRACT: v1 `mcp/execute/main.py:213` returns plain text;
v2 `mcp2/execute/main.py:282` returns
`json.dumps({exit_code, output, timed_out, raw_bytes_b64})`. `agent2/tools.py:466
_execute_payload` has a documented plain-text fallback so agent2 tolerates a v1
server; agent1 has no tolerance for the v2 envelope. The global `mcpServers` key
has exactly ONE reader (`tui/mcp.py::load_mcp_servers:51`). **Do not repoint the
global entry — the per-entry `mcpServers` override is the answer.**

`mcp --include-tools X --list-tools` lists ALL 13 tools: `--list-tools`
short-circuits before selection (`cli/main.py:226` vs `:232`). Correct, not a bug.

### `execute`'s model-facing args

`code, reset, timeout, prelude_path, python_path`. `prelude_path` and
`python_path` are honored **only with `reset=True`** (`main.py:226-230` returns an
error string otherwise).

### The tools split

`tools/__init__.py`: `_LAZY = {edit, fs, memory, rlm, sg, vision, web, write}`;
`_LAZY_V2 = {task, task_send, task_read, task_cancel}` — **v2 kernels only**,
because v1 already ships `task` as an MCP tool from the agent process, so a v1
kernel with both would have two launchers minting ids off the same global counter
and writing the same two tables. And v1 is frozen.
`PRELUDE = "from crow_cli.tools import reload\nreload()"`,
`PRELUDE_V2 = "...\nreload(v2=True)"`,
`_IS_V2 = globals().setdefault("_IS_V2", False)` — remembered rather than
inferred, so an interactive `reload()` re-binds the set the kernel started with
instead of silently dropping the task tools mid-session.

The identity rail: `tools/register.py` holds `CellContext(session_id,
parent_tool_call_id, cell_seq, agent_id, rlm_depth)`, a `_current_cell` ContextVar,
and `begin_cell(session_id, parent_tool_call_id, cell_seq, agent_id, db_uri,
images_dir, redis_url, rlm_depth)`. `db_uri()` and `redis_url()` are module-level
and resolved **by the agent out of its own config, injected by execute's
prologue** — the kernel reads NO config. `redis_url()` returns `""` when there is
none, which is a configuration and not an error. Outside a cell (plain scripts,
tests) no context exists and the tools stay usable as ordinary Python; call
`begin_cell(db_uri=...)` first, which is exactly what execute's prologue does.

### The gate harness

`tests/integration/test_agent2_gate.py`, 2432 lines, 35 tests. Everything real
except the scripted model. `gate(tmp_path, scripts, config=None, model=None,
compactor=None)`; `Gate` members: `updates, kinds(), of_kind(k), kinds_for(sid),
updates_for(sid), last_result(), init_capabilities, states(), idles(), agent_id,
agent_id_of(sid), history(), initialize(), new_session(mcp_servers=, cwd=),
prompt(*blocks), cancel(), list_sessions(cwd=, cursor=), resume_session(...),
close_session(), fork_session(sid, **meta), set_config_option(config_id, value,
session_id), wait_for(pred, timeout=20), wait_for_idle(count, timeout=20),
close()`. Script helpers: `text(*pieces)`, `thought(*pieces)`, `usage(n)`, `HANG`.
Logger name for `caplog` is **`"crow-agent2"`**. `_bus_reachable(url)` gates the
redis tests with `pytest.skip`. The **yielding transport** wrapper inside `gate()`
is load-bearing. Don't assert the whole idle dict — it also carries `usage`.

### Test totals

```
tests/{unit,mcp,memory,integration}   1326 passed in 434.58s   0 failed
tests/e2e (26 tests)                    26 passed in 1593.72s  0 failed
tests/unit/test_discover.py             13 passed
tests/integration/test_cli_run_dispatch.py  27 collected (26 defs, one parametrized x2)
tests/unit/test_agents_registry.py      38 passed
```

pytest config: `testpaths=["tests"]`, `asyncio_mode="auto"` (a plain `async def
test_*` needs no marker), `asyncio_default_fixture_loop_scope="function"`,
`addopts="-v --strict-markers"`. `tests/integration/` has NO `__init__.py`, so a
probe there uses absolute imports. `pyproject.toml` has no `[tool.ruff]` and no
`[tool.black]` — line length is informal convention: files stay at or under ~92,
`cli/main.py` at or under 120.

---

## 8. Known open holes

### 8.0 The 3.13 regression this work caused, and the check that missed it

`requires-python` went `>=3.14` to `>=3.13` in `1d3211a6`, the branch commit
merged into main in Phase 1. That changed which interpreter `uv tool install`
resolves, and it broke the TUI on install: **3.14's PEP 649 defers annotation
evaluation, 3.13 evaluates it eagerly**, so five latent annotation bugs in the
vendored TUI were harmless on 3.14 and fatal on 3.13. Fixed in `6ae60699`:

| site | bug | fix |
|---|---|---|
| `tui/acp/protocol.py:486` | `usage: Usage`, `Usage` defined 56 lines later | `from __future__ import annotations` |
| `tui/acp/agent.py:74` | `cost: Cost`, `Cost` defined 15 lines later | moved `Cost` above `ContextUsage` |
| `tui/widgets/terminal.py:48` | nested `@dataclass` annotating the enclosing `Terminal` | `from __future__ import annotations` |
| `tui/widgets/shell_terminal.py:17` | same self-reference | `from __future__ import annotations` |
| `tui/widgets/throbber.py:42` | `Callable` used, never imported | `from collections.abc import Callable` |

The last one is the important case. Stringifying that annotation would have
*hidden* a name that genuinely does not exist — `from __future__ import
annotations` is the right fix for an ordering or self-reference problem and the
wrong fix for a missing import.

**The check that passed this was worthless.** Phase 1's "3.13 compile: 351 files,
0 failures" was `py_compile`, which validates SYNTAX ONLY. A forward reference
and a missing import are both perfectly valid syntax; they fail at import time.
Reporting that as 3.13 compatibility was a false claim.

The replacement check imports every module **by path** under the installed 3.13
tool interpreter, which matters because `tui/acp/` is a namespace package with
no `__init__.py` and `pkgutil.walk_packages` does not descend into it — the
first sweep walked 169 modules and missed 10 of the 12 failures:

```python
root = pathlib.Path(REPO) / "src"; sys.path.insert(0, str(root))
for p in sorted(p for p in root.rglob("*.py")
                if "__pycache__" not in p.parts and p.name != "__init__.py"):
    importlib.import_module(".".join(p.relative_to(root).with_suffix("").parts))
```

202 modules. 3.13 and 3.14 now report the same two failures and nothing else —
`crow_cli.mcp.memory.client` and `crow_cli.mcp.vision.client`, both
`ValueError: Could not infer a valid transport from: main.py`, pre-existing on
both interpreters (fastmcp infers a transport from the filename; these are client
stubs not meant to be imported standalone).

**Rule going forward: a version-compatibility claim needs an import, not a
compile.** Anything that changes `requires-python` must run this sweep on the
new floor.

Features, not bugs.

1. **`remind`** — §5. Still unstarted, but no longer the thing blocking
   self-directed input: §5.4's mechanism shipped under `/goal`, so what is left
   here is the one-shot note and its subtool, not the wake.
2. **`schedule_timer` has no production caller.** Built, tested, runnable,
   unwired. §5.3 argues it should stay that way for now.
3. **`_run_mcp_tool` has no `progress_handler`** (`agent2/tools.py:361`).
   Blocked on an append-vs-replace ruling: `ToolCallContentChunk` APPENDS
   while `ToolCallUpdate.content` REPLACES, so streaming MCP progress needs a
   decision about which one crow emits before it can forward anything.
4. **The `except OSError` guard in `discover._handshake` may be unreachable.**
   For a ~300-byte request the write fits the 64KB pipe buffer, so
   `write()`/`drain()` succeed even against a dead child and the readline path
   produces `"closed stdout without answering"` with the same stderr tail. Its
   mutation was never run. Per the repo principle — *a surviving mutation is a
   reason to DELETE code* — if it survives, delete it.
5. **`_cancel_orphan`'s wording** is subagent-shaped and will read oddly for a
   cancelled reminder (§5.10).

---

## 9. Git state

**Stale, and kept as the record of the session that wrote it.** It predates the
merge of `acp-v2-agent` into main and the `/goal` work; in particular "the
worktree workflow is over" is no longer true — `/goal` was built in
`~/.agents/crow/src/worktrees/goal`, off a main that has moved well past
`07f4ec9b`. Read the commit list below as history, not as the current tree.

```
main = 07f4ec9b  feat: ask the agent which protocol it speaks instead of declaring it
       ac4d3a12  chore: repoint the agent-client-protocol source path for main's checkout
       20f7699d  fix(test): execute's schema test missed the two kernel options
       665ad668  merge: bring main's 3.13 backport and execute kernel options into acp-v2-agent
       1d3211a6  feat: ACP v2 agent, client and MCP server; crow-cli run is the registry-driven client
       87f66c92  refactor: vendor ACP v1 schema helpers into crow_cli.acp_helpers
```

Nothing pushed, no PR open.

The working tree carries an **uncommitted version bump** — `pyproject.toml`
`0.1.44` to `0.1.45` and the matching one-line `uv.lock` change. Not this
session's work; left alone deliberately.

Trees:

```
MAIN = ~/.agents/crow/src/crow-cli                  07f4ec9b [main]   <- the work tree, and the kernel's venv
WT   = ~/.agents/crow/src/worktrees/acp-v2-agent    20f7699d          merged, clean, IDLE/STALE
RS   = ~/.agents/crow/src/worktrees/crow-cli-rs     ee2cb032          Rust reference, unused
D    = ~/.agents/crow/src/python-sdk                c1004f8           ACP v2 clone, editable, 0.12.1
```

The worktree workflow is over; MAIN's venv *is* the merged tree.
`../../python-sdk` (from the worktree) vs `../python-sdk` (from main) is a
permanent two-commit difference. Never hand-merge `uv.lock` — resolve
`pyproject.toml`, then `uv lock`.

### Where the project goes

The TUI replacement will be substantial and in Rust: forks of `herdr` and
`martty` plus crow's own ACP v2 Rust client, with `herdr` refactored to be
ACP-first and to coordinate primarily with `crow-cli agents`, possibly informed by
`nori`. An orchestrator built out of **ACP proxies instead of hook-api**, so
integration works with any ACP agent. The `acp-v2` skill
(`~/.agents/skills/acp-v2/SKILL.md`) covers the verified Rust wire types and the
crow-cli v2 scaffold.
