# `@assistant-ui/acp`

[ACP (Agent Client Protocol)](https://agentclientprotocol.com/) adapter for
[assistant-ui](https://www.assistant-ui.com/). The sequel to
[`@assistant-ui/react-a2a`](../react-a2a/README.md): where react-a2a speaks
Google's A2A protocol over fetch + SSE, this package speaks ACP v1 over a
single WebSocket carrying JSON-RPC in both directions — the transport used by
agents like [crow](https://crow-ai.dev) (`crow acp --http`).

- ACP session ↔ assistant-ui thread
- `session/update` notifications ↔ streamed assistant message parts
  (text chunks, thought chunks, tool calls)
- `session/request_permission` server requests ↔ tool-call **approvals**
  (ACP's `allow_once`/`allow_always`/`reject_once`/`reject_always` map 1:1 to
  assistant-ui's approval option kinds)

## Installation

```sh
npm install @assistant-ui/acp @assistant-ui/react
```

## Usage

```tsx
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useAcpRuntime } from "@assistant-ui/acp";

export function App() {
  const runtime = useAcpRuntime({
    url: "ws://127.0.0.1:2770/",
    // permissions: "auto-allow",  // default "ask" shows approval UI
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {/* your thread UI, e.g. the shadcn kit's <Thread /> */}
    </AssistantRuntimeProvider>
  );
}
```

### Options

| Option             | Description                                                                 |
| ------------------ | --------------------------------------------------------------------------- |
| `url`              | WebSocket endpoint of the ACP agent (`ws://` / `wss://`).                    |
| `client`           | Pre-built `AcpClient` (alternative to `url`).                                |
| `cwd`              | Absolute working directory for `session/new` (default `"/"`). Set it when    |
|                    | the agent's file tools need a project root.                                  |
| `mcpServers`       | MCP servers to pass to `session/new`.                                        |
| `clientInfo`       | Client identity for the `initialize` handshake.                              |
| `permissions`      | `"ask"` (default) or `"auto-allow"`.                                         |
| `autoConnect`      | Connect + `initialize` on mount (default `true`).                            |
| `restoreOnConnect` | After the handshake, open the agent's newest thread for `cwd` — or mint one  |
|                    | when it remembers none — so a session id exists before the first prompt      |
|                    | (default `false`: the first prompt mints the session).                       |
| `unstable_enableMessageQueue` | A send made while a turn is running waits in `composer.queue`   |
|                    | and goes out as its own `session/prompt` when the turn settles, instead of   |
|                    | cancelling it (default `false`). See [Queueing sends](#queueing-sends-while-a-turn-runs). |
| `webSocketFactory` | Inject a custom WebSocket implementation (tests, proxies).                   |
| `onError`          | Error callback (connection failures, prompt errors).                         |
| `onCancel`         | Called after a run has been cancelled.                                       |

### Bringing your own `AcpClient`

Pass `client` to configure the transport yourself — not to share one connection
between runtimes. An `AcpClient` holds exactly one ACP session, so two runtimes
on one client would prompt the same session and each show only its own half of
the conversation: the silent fork the Limitations section warns about. Approvals
cannot be shared either (see below): a runtime puts back the handler it
replaced only while that handler is still the current one, so the last of two
to unmount reinstates one owned by a controller that is already gone, and every
later permission request is cancelled without ever reaching an approval UI.
Give each runtime its own client.

The runtime **subscribes** to the client (`subscribeSessionUpdate` /
`subscribeConnectionChange`) and unsubscribes when it unmounts, so your own
listeners keep working alongside it.

Approvals are the one thing a client can only have one of. A client constructed
with a `permissionHandler` keeps it — the runtime does not replace it, and the
approval UI stays out of the way. A client without one gets the runtime's
handler for as long as the runtime is mounted, and the refusing default back
when it unmounts.

### Changing a config option (the model picker)

`session/new` and `session/load` report the session's `configOptions` — for
crow-cli that is a single `select` option listing every configured model — and
`useAcpConfigOptions` reads them. Changing one is the matching extras action,
because the answer is per-session state rather than a message:

```tsx
const runtime = useAcpRuntime({ url, cwd, restoreOnConnect: true });
const options = useAcpConfigOptions();
const setConfigOption = useAcpSetConfigOption();
const model = options?.find((option) => option.type === "select");

await setConfigOption("model", "anthropic:claude-sonnet-4-5");
```

The action reaches the runtime's own client, so a picker needs no `AcpClient`
of its own. It connects and mints a session if needed, sends
`session/set_config_option`, and adopts the full `configOptions` array the agent
returns as the new truth — no `config_option_update` follows a client-initiated
change, so the connection change it emits is what carries the new list back into
`useAcpConfigOptions`. ACP v1 advertises no capability for the method; the option
list itself is the capability, so an id the agent never advertised is refused
before anything is sent, and the refusal surfaces through `onError` rather than
as a thrown action. Outside an ACP runtime the hook hands back an action that
rejects, so a picker rendered without a runtime says so instead of doing
nothing.

### Queueing sends while a turn runs

By default a send made mid-turn **cancels the turn in flight** and replaces it —
the same thing the TUI does when you type over a running agent. Pass
`unstable_enableMessageQueue: true` to queue instead:

```tsx
const runtime = useAcpRuntime({
  url,
  cwd,
  restoreOnConnect: true,
  unstable_enableMessageQueue: true,
});
```

With the flag on, `capabilities.queue` is true and an append made while a run is
in flight lands in `composer.queue` rather than on the wire. Nothing is sent
until the running turn settles; then the queue drains FIFO, one
`session/prompt` per item, each becoming its own assistant message. Render the
pending items with `ComposerPrimitive.Queue` and
`QueueItemPrimitive.{Text,Remove,Steer}`, or act on them through
`aui.composer.queueItem({ id }).edit(…)` / `.move(…)` / `.remove()` /
`.steer()`.

`composer.send({ steer: true })` — Cmd/Ctrl+Shift+Enter in `ComposerInput` —
does not wait in a lane. Its `session/prompt` goes out **immediately**, while
the turn in flight is still running, and the controller's run queue gives it its
own turn and its own assistant message the moment that turn settles. An agent
that takes a second prompt mid-turn serialises it behind the one running (crow's
does; it answers the frames in the order they arrived), so the steered reply
lands after the reply it rode behind and neither is attributed to the other.
`run` never passes through idle in between, so a draining queue or a scroll lock
watching the idle edge sees one continuous run. This is the TUI's `ctrl+enter`
steer — "lands at the next agent step" — and the adapter reaches it through
`ExternalThreadQueueAdapter.sendNow`; an agent that refuses the second prompt
reports the rejection through `onError` and ends the turn it was owed
incomplete.

Three behaviours are worth stating, because each is a choice rather than a
limit of the protocol:

- **The queue is per session.** Prompts typed in a background session wait for
  the user to come back instead of draining into whatever conversation is on
  screen. Switching threads holds the queue it leaves and releases it on the
  way back, so a switch (which cancels the turn) cannot settle into the wrong
  session. Deleting a thread clears the prompts that could no longer be sent.
- **Cancelling drains, it does not discard.** The adapter omits
  `__internal_notifyCancelled`, so an interrupted turn settles straight into the
  next queued prompt — including a steer already on the wire, which the agent
  has and will answer. Nothing is silently dropped either way — the items stay
  on screen until they go — but a host that wants "stop means stop" should clear
  the queue itself on `onCancel`. A teardown (thread switch, delete, detach) is
  the exception: it drops the pending turns, whose session is going away.
- **A steer sends now; a plain send still supersedes.** No `cancel` driver is
  registered with the queue, so moving an item into the steer lane reorders the
  queue without interrupting the turn. A plain mid-run send with the queue off
  cancels and replaces the turn in flight as before; with the queue on it waits
  in a lane, and behind any steer already on the wire, because the agent answers
  frames in the order they arrived.

### Extras hooks

Every hook falls back to a safe default when no ACP runtime is active.

```tsx
import {
  useAcpAgentCapabilities,
  useAcpAgentInfo,
  useAcpAvailableCommands,
  useAcpConfigOptions,
  useAcpConnectionState,
  useAcpCurrentModeId,
  useAcpPlan,
  useAcpSessionId,
  useAcpSessionTitle,
  useAcpSetConfigOption,
  useAcpUsage,
} from "@assistant-ui/acp";
```

## How it maps ACP → assistant-ui

| ACP                                        | assistant-ui                                             |
| ------------------------------------------ | -------------------------------------------------------- |
| WebSocket connection + `initialize`        | runtime connection state (`useAcpConnectionState`)       |
| `session/new` → `sessionId`                | thread (`useAcpSessionId`)                               |
| `session/prompt`                           | append / run                                             |
| `agent_message_chunk`                      | text content part (streamed)                             |
| `agent_thought_chunk`                      | reasoning content part (streamed)                        |
| `tool_call` / `tool_call_update`           | tool-call content part (name, args, result, status)      |
| `session/request_permission`               | tool-call approval (`requires-action` until answered)    |
| `session/cancel`                           | cancel                                                   |
| `plan`                                     | `useAcpPlan`                                             |
| `session_info_update`                      | `useAcpSessionTitle`                                     |
| `modes` + `current_mode_update`            | `useAcpCurrentModeId`                                    |
| `available_commands_update`                | `useAcpAvailableCommands`                                |
| `configOptions` + `config_option_update`   | `useAcpConfigOptions`                                    |
| `session/set_config_option`                | `useAcpSetConfigOption`                                  |
| `usage_update`                             | `useAcpUsage`                                            |
| `initialize` → `agentInfo`/`agentCapabilities` | `useAcpAgentInfo` / `useAcpAgentCapabilities`        |

`session/new` and `session/load` report the session's initial `modes` and
`configOptions`; the two `_update` notifications only fire on later changes, so
both feed the extras hooks from the response as well.

A tool call's `toolName` is the key apps register tool UIs against, so it has to
be stable for the life of the call: the protocol's programmatic `name` when the
agent sends one, then its `kind` (`read`/`edit`/`execute`/…), and only then the
human-readable `title`. A `tool_call_update` carries only what changed, so the
three are accumulated across a call's updates: a frame that omits `name` cannot
downgrade the key to the title it happens to carry. All three stay readable on
the part as `providerMetadata.acp` (`{ name?, kind?, title? }`), so a renderer
can still show the label.

Browser clients advertise **no** filesystem or terminal capabilities, so a
conforming ACP agent will never send `fs/*` or `terminal/*` requests; any such
request is answered with JSON-RPC `-32601`.

## Limitations

**Editing and regenerating a message are not offered.**
An ACP v1 session's history lives on the agent and can only be appended to —
stable v1 has no fork or rewind primitive (`session/fork` is in the schema but
marked UNSTABLE, and takes no turn anchor). Re-sending an edited or reloaded
user message on the *same* session would branch the assistant-ui thread while
leaving the agent holding every turn the UI replaced, so the runtime wires
neither `onEdit` nor `onReload` and both actions stay disabled. Fork-and-replay
support belongs in a follow-up.

**There is no history adapter: the agent owns the transcript.**
`useAcpRuntime` takes no `adapters.history` and ignores one a thread list
provides through `RuntimeAdapterProvider`. A transcript restored from storage
would put messages on screen that the next `session/new` knows nothing about, so
the agent would answer from an empty context while the user reads a full
conversation. Persisting the ACP `sessionId` with the thread and restoring it
with `session/load` is what makes a restored thread real; it belongs in a
follow-up.

**A dropped connection cannot silently continue the thread.**
The agent loses the session when the socket goes away. On reconnect the client
calls `session/load` for the session it lost, if `agentCapabilities.loadSession`
advertises it, and otherwise rejects the next prompt with an error naming that
session. Every later prompt keeps rejecting until a load succeeds, so a retry
cannot fork into a `session/new` whose agent lacks the transcript the user is
reading. The replay an agent sends while loading is dropped, because the thread
already shows it — and a load that fails or times out keeps dropping that
session's updates rather than letting a late replay through.

**Recovering from a lost session takes a new thread, not a retry.**
`useAcpRuntime` drives a single thread with no thread list, so there is no
`onSwitchToNewThread` to hang a reset on, and the transcript and the session
have to go together: clearing one without the other is exactly the fork above.
Surface the error as a "start a new thread" action that hands the hook a new
`client`, changes one of the managed options (`url`, `cwd`, `mcpServers`,
`clientInfo`), or remounts the component that calls `useAcpRuntime` — each
builds a fresh client and controller with an empty transcript and a new
session. Until that happens the thread stays put: it keeps showing what it has
and refuses to prompt.

**Attachments the agent did not opt into are withheld.**
ACP's baseline prompt content is text and resource links; `image`, `audio` and
embedded `resource` blocks all need `agentCapabilities.promptCapabilities`.
Whatever the agent cannot accept is left out of `session/prompt`, and `onError`
reports the omission. An embedded resource keeps what survives instead of being
withheld — its text travels as a text block, and a URI the agent can fetch
travels as a resource link — so only inline bytes behind a client-local `file:`
URI, which survive neither way, end up dropped and reported. A downgrade is not
a drop: what the agent does receive is never reported as missing. The message
keeps its attachments in the transcript either way.

**`cwd` defaults to `"/"`.** ACP requires an absolute path; set `cwd` when the
agent's file or terminal tools need a real project root.
