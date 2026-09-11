---
kind: ideas
session: serious-generous-ammonite-of-aptitude
agent: serious-generous-ammonite-of-aptitude-1-1
model: github-copilot/gpt-5.6-luna
cwd: /home/thomas/.agents/crow/src/crow-cli
generated: 2026-09-09T18:38:45.278495+00:00
---

I cannot persist the file in this turn, but here is the standalone content that should be written to `.agents/crow/ideas/`:

# Adversarial Review of Crow CLI

## Assumptions worth attacking

### 1. Protocol correctness will compensate for implementation gaps

Crow correctly treats ACP/MCP as more authoritative than local naming, but protocol alignment is not binary. The current `load_session` behavior is known to approximate replay semantics while omitting the frontend replay contract. That is not merely a naming mismatch: clients can render an apparently empty session, lose tool state, or duplicate messages.

**What breaks if false:** ACP clients cannot reliably reconnect, reconstruct UI state, or distinguish resumed context from replayed history. Crow becomes “ACP-compatible enough for one client” rather than interoperable.

**Evidence:** this session explicitly identified that `load_session` does not replay the full session to the frontend.

**Alternative:** build a protocol conformance layer with recorded ACP transcripts. Test `new → prompt → disconnect → load/resume → replay` against a reference client, including tool calls, artifacts, thoughts, modes, and cancellation.

**Proved wrong if:** a reference ACP client can reconnect to arbitrary persisted sessions and reconstruct the exact visible state from the wire, including interrupted and tool-heavy turns.

### 2. SQLite plus stable IDs equals durable agent execution

SQLite makes history durable and forks easy to inspect, but it does not make live execution durable. The Celery experiment exposed the distinction: task results can persist, while a running worker, kernel, subprocess, or in-memory async task may disappear on process death.

**What breaks if false:** a daemon reports work as active when the worker is gone; completion events are lost; a session can be resumed but not know whether its subprocess was still running; duplicate work becomes likely.

**Evidence:** Crow’s RLM background path keeps live tasks in process-local state while writing transcripts to SQLite. The proposed daemon architecture also relies on completion wakeups.

**Alternative:** model execution as durable state transitions, not as a live task plus a transcript. Every job needs an idempotency key, heartbeat, lease, attempt number, external process identity, completion record, and recovery policy.

**Proved wrong if:** killing the agent daemon, Celery worker, broker, or subprocess at each lifecycle stage results in exactly-once semantic completion or a clearly recoverable state without manual repair.

### 3. A single local model endpoint is effectively unlimited

The local AMD machine removes API cost, but it does not remove prefill latency, memory contention, thermal limits, context-window pressure, or scheduling conflicts. The user already identified prefill as the scarce resource.

**What breaks if false:** automatic reminders and completion reviews produce a self-inflicted queue of expensive supervisor turns. Ambient research competes with user interaction. Persistent context becomes a liability instead of an advantage.

**Evidence:** the proposed daemon would wake on idle/completion events, run periodic prompts, review subagents, and maintain research pipelines against one llama.cpp endpoint.

**Alternative:** introduce a model-turn scheduler before building broad autonomy. Prioritize interactive user turns, active project supervision, and ambient research separately. Batch events into one review, deduplicate wakeups, and use compact state references instead of replaying transcripts.

**Proved wrong if:** a benchmark with realistic completion bursts shows that automatic supervision preserves acceptable interactive latency and does not cause unbounded model backlog.

### 4. `execute` is a sufficient universal composition substrate

The persistent kernel is unusually powerful, but it has environment, lifecycle, and trust boundaries. The Celery installation mistake demonstrated that “the project environment” and “the current kernel environment” can diverge. A separate subprocess may use one `.venv`, while the active kernel uses another. `reload()` refreshes modules; it does not repair arbitrary interpreter or dependency state.

**What breaks if false:** generated workflows work in one session and fail in another; hot-installed dependencies are invisible; daemon jobs inherit the wrong cwd, credentials, or Python environment; self-modifying code becomes hard to reproduce.

**Alternative:** expose runtime identity in the kernel: executable path, project root, environment fingerprint, package-lock digest, loaded tool versions, and subprocess inheritance rules. Treat kernel reset as a defined environment boundary.

**Proved wrong if:** a test can install a dependency, reset or spawn the intended kernel, import it, launch a child process, and reproduce the same environment from a clean machine using only declared project metadata.

### 5. A read-only MCP remains a read-only agent capability

The MCP may be read-only with respect to Component Service while the host agent can generate GenBank files, operate an authenticated browser, upload artifacts, and trigger mutations through the UI.

**What breaks if false:** security review approves a supposedly read-only agent while overlooking the actual side-effect path. Tool-level authorization becomes misleading because the agent’s capability is the composition of all tools and interfaces.

**Evidence:** this session demonstrated the authenticated LMnext UI and Playwright access, and explicitly recognized that a read-only domain MCP can drive write workflows through `execute` and the browser.

**Alternative:** classify capabilities at the composition boundary. Track data access, local artifact creation, external network access, browser mutation, backend mutation, and publication separately. Require approval at irreversible edges, not merely at MCP calls.

**Proved wrong if:** a capability manifest for an agent accurately predicts every side effect it can perform, including indirect UI mutations, and tests reject an unapproved upload or submit path.

### 6. Self-modification naturally improves the harness

Crow can edit tools, prompts, skills, and source, then reload and continue. That is a capability, not a guarantee of improvement. A system that can mutate itself can also silently degrade its own reliability.

**What breaks if false:** prompt changes improve one task while damaging another; tool schema changes invalidate clients; skills accumulate contradictory instructions; a successful local experiment becomes an unreviewed permanent regression.

**Evidence:** the `learn` skill already recognizes this by requiring copies, one-dimension mutations, judging, Pareto retention, and explicit diffs before promotion.

**Alternative:** make self-modification transactional. Every mutation gets a parent revision, affected capability list, test/bench evidence, rollback pointer, and promotion status. Keep live execution on a known-good revision until evaluation passes.

**Proved wrong if:** repeated optimization runs produce improvements across held-out tasks without increasing regressions, tool failures, or prompt size, and every promotion can be rolled back deterministically.

### 7. A client daemon is merely a transport wrapper

The proposed daemon is more than HTTP around an agent. It would own session attachment, job execution, wakeups, scheduling, completion handling, and possibly ACP-compatible control. If it is treated as a thin server, its lifecycle semantics will be underspecified.

**What breaks if false:** clients disagree about ownership, events are lost, prompts race with cancellation, and a daemon restart changes the meaning of “active session.”

**Evidence:** the proposed architecture distinguishes the daemon agent from the client daemon and from Celery workers, while also requiring ACP-style session control.

**Alternative:** define the daemon as a stateful control plane with explicit ownership and event semantics. ACP should be the conversational interface; a small extension surface should manage jobs, subscriptions, schedules, artifacts, and approvals.

**Proved wrong if:** multiple clients can attach, detach, reconnect, subscribe, prompt, cancel, and resume the same session without duplicated turns or ambiguous ownership.

## Prior art you should steal from

### 1. Agent Client Protocol and its session-resume direction

ACP provides the canonical boundary Crow should conform to rather than reinterpret. The important mechanism is separating conversational session identity from transport connection identity, then defining what resume and replay mean.

**Steal:** conformance fixtures for session creation, reconnection, replay, cancellation, tool updates, and capability negotiation.

**Cost:** protocol replay is more work than simply loading internal state. It also forces Crow to preserve enough structured history to reconstruct frontend-visible state.

**How it lands here:** turn Crow’s existing SQLite transcript into an ACP replay source. Keep internal `load` and external replay semantics distinct even if one implementation initially serves both.

**Failure condition:** if real ACP clients do not need replay, or if Crow’s own clients never consume it, prioritize other work. But an external client interoperability test should decide this, not intuition.

### 2. Temporal durable execution

Temporal treats long-running work as durable workflows with event history, signals, retries, timers, and recovery rather than as background functions that happen to return results.

**Steal:** workflow IDs, idempotent activities, durable timers, signals for follow-up prompts, and explicit retry/compensation semantics.

**Cost:** deterministic workflow constraints and an additional service can be heavy for a local single-machine system.

**How it lands here:** do not adopt Temporal wholesale. Borrow its state-machine vocabulary for the Crow client daemon and Celery bridge: `submitted`, `leased`, `running`, `waiting`, `completed`, `failed`, `cancel_requested`, `recovered`.

**Failure condition:** if a SQLite event ledger plus Celery already survives all injected failures at acceptable complexity, Temporal’s machinery is unnecessary.

### 3. Celery events, Beat, and result backends

Celery already provides task queues, worker execution, retries, periodic scheduling, task state, and monitoring events.

**Steal:** task IDs, event receivers, Beat schedules, retry policies, and worker heartbeats.

**Cost:** broker/backend operational complexity, event-vs-result ambiguity, and weak semantics for conversational agents and durable subprocess ownership.

**How it lands here:** Celery should be the worker plane, not the session plane. Crow should persist its own semantic event ledger and treat Celery events as inputs. Completion should enqueue a structured review event rather than inject raw task output into the model.

**Failure condition:** if Celery cannot reliably run locally with the required broker, persistence, and process supervision, replace it with a smaller local executor before designing around its APIs.

### 4. Prime Agent’s persistent REPL and daemon

Prime Agent makes the persistent REPL and child-agent orchestration explicit. Its useful ideas include retained child sessions, direct follow-up, a background daemon, session recovery, and harness state as mutable objects.

**Steal:** named child identity, direct follow-up, daemon-owned session lifecycle, and a first-class distinction between initial delegation and later communication.

**Cost:** more runtime state, cleanup logic, process recovery, and a larger conceptual surface.

**How it lands here:** Crow already has the primitives: `execute`, historical forks, `session/load`, session IDs, memory, and ACP drivers. Add a small follow-up API to RLM, then put richer lifecycle control in the client daemon rather than making RLM carry every orchestration feature.

**Failure condition:** if sequential one-shot delegation plus CLI resume handles actual user workflows better than retained children, do not import Prime’s persistent-child abstraction merely for symmetry.

### 5. Pi’s extension and hot-reload model

Pi’s appeal is not only its TUI. Its extension ecosystem gives users a clear way to add tools, commands, prompts, and behavior without modifying the core.

**Steal:** an explicit extension contract, discoverable package layout, reloadable capability registry, and generated documentation for installed extensions.

**Cost:** compatibility burden and a public API that becomes difficult to change.

**How it lands here:** Crow’s skills and live module reload are more powerful but less productized. Define a capability manifest for a skill: tools added, files touched, dependencies, restart requirements, and compatibility version. Generated MCP CLIs and `SKILL.md` files are a natural distribution mechanism.

**Failure condition:** if users can reliably compose skills from ordinary Python today and no one needs installation/versioning, formal extension packaging may be premature.

### 6. GEPA and MemoHarness

The existing `learn` skill is already built around these ideas: reflective trace analysis, six optimization dimensions, Pareto frontiers, minibatches of failures, and evidence-backed mutation.

**Steal:** reflection over traces rather than scalar scores; preserve complementary winners; separate context, tools, generation, orchestration, memory, and output dimensions.

**Cost:** benchmarks are expensive, judging is noisy, and prompt improvements can overfit the trace distribution.

**How it lands here:** the historical fork mechanism is an excellent missing primitive for learning. An optimizer can fork a session at the exact pre-failure offset, ask the historical agent what it believed, test an alternative prompt/tool configuration, and compare the resulting branch without destroying the original.

**Failure condition:** if historical interrogation does not produce better mutation proposals than reading transcripts directly, do not make branching central to optimization.

### 7. Git’s branches, reflog, and content-addressed history

Crow’s session forks are conceptually closer to Git branches than to disposable subagents. A fork shares history up to an anchor, then diverges.

**Steal:** immutable anchors, branch labels, parent pointers, reflog-like recovery, and cheap comparison between branches.

**Cost:** users may misunderstand message history as executable state; merge semantics are difficult when branches contain conflicting tool actions.

**How it lands here:** expose session ancestry and fork anchors as inspectable metadata. Add “compare branches” as a first-class analysis operation, not a merge operation. Historical forks should be read/interrogate/replay branches by default.

**Failure condition:** if users only ever need latest-session resume and never compare alternate trajectories, ancestry tooling becomes decoration.

## Directions nobody has pointed at

### 1. A protocol conformance laboratory for agents

Crow could become a test harness for ACP implementations, not merely an ACP agent. Given a persisted transcript and a protocol scenario, it could replay, fork, inject disconnects, inspect notifications, and score another agent’s behavior.

This follows directly from the protocol-first architecture and the historical fork machinery.

**Prove it wrong:** build three conformance scenarios against Crow, a second ACP agent, and a real client. If the results reveal no actionable interoperability failures, do not make conformance tooling a product.

### 2. A session debugger and “time-travel debugger” for agents

The combination of SQLite history, agent indexes, fork offsets, and programmable execution supports a debugger-like product:

```text
show what the agent knew here
show tools available here
fork before this mistake
ask why it chose that action
rerun with a changed prompt
compare branches
```

This is more valuable than a conventional transcript viewer because it treats agent behavior as a replayable program.

**Prove it wrong:** give experienced users three failure traces and measure whether historical interrogation identifies root cause faster than ordinary transcript inspection. If not, keep it as internal tooling.

### 3. A local inference scheduler optimized for prefill

The daemon could schedule model turns using estimated prompt-token cost, cached session locality, urgency, and user interaction priority. Completion events would be coalesced into one review prompt.

This is specifically suited to the Ryzen/llama.cpp deployment described in this session and would differentiate Crow from cloud-first swarm architectures.

**Prove it wrong:** benchmark naive wake-on-event against coalesced, token-budgeted scheduling. If interactive latency and total prefill are not materially better, do not add scheduler complexity.

### 4. An intent compiler for the user’s evolving work

The daemon agent could compile user messages into durable hypotheses:

- active goals;
- project candidates;
- constraints;
- recurring interests;
- unresolved questions;
- explicit decisions;
- likely next research.

The critical feature would be provenance and confidence. It must preserve whether something was explicitly requested, inferred, suggested, or merely observed.

**Prove it wrong:** run it over a month of real user messages and inspect whether it produces useful, non-annoying research prompts without turning agent speculation into fake requirements. If most outputs are noise or require manual correction, keep memory retrieval instead.

### 5. MCP as a schema compiler and capability distribution format

The Component Service experiment suggests a broader product: one typed MCP domain surface generates an agent interface, a CLI, a Crow skill, test fixtures, and UI render contracts.

The generated CLI is not just convenience. It is an executable consumer that exposes whether the MCP schema is understandable and complete.

**Prove it wrong:** generate a CLI and skill from the first real Component Service MCP, then have a human use both without reading the server implementation. If the generated artifacts are unusable or lose important domain semantics, the MCP schema is not yet a good canonical contract.

### 6. Human-reviewed definition-of-done production

The proposed comprehensive definitions of done could become an agent-maintained evidence system. Agents gather implementation evidence, tests, screenshots, API traces, and historical decisions; humans curate claims and approve the final definition.

This is stronger than documentation generation because each requirement could point to evidence and a verification procedure.

**Prove it wrong:** select one real workflow and ask agents to draft its definition of done from code, UI, API, and existing artifacts. If human reviewers spend more time correcting hallucinated scope than editing useful evidence, the approach is not ready.

### 7. A capability firewall for compositional agents

Because read-only MCP plus `execute` plus browser automation can produce writes, Crow could expose a machine-readable capability graph:

```text
domain read
local file write
network request
browser mutation
backend mutation
publication
```

Every tool and subtool declares the capabilities it enables. The agent daemon can require approval when a composed path crosses a policy boundary.

**Prove it wrong:** model a real LMNext upload workflow and see whether the graph predicts its side effects without either overblocking ordinary work or missing a mutation path.

## What would make this obsolete

### 1. Agent hosts may absorb the entire runtime

VS Code, Zed, OpenAI, Anthropic, and model providers are all moving toward persistent agent hosts with session recovery, tools, background work, and cross-client attachment. If those hosts provide a durable protocol, local execution environment, rich extension system, and provider-neutral model routing, Crow’s core value could collapse into “another ACP client.”

**The maintainer should worry about:** protocol compatibility alone is not a moat. If the host owns the session daemon and extensions, Crow’s native persistence becomes an implementation detail.

**Countermeasure:** own the programmable control plane and historical agent debugger, not just ACP compliance.

**Obsolete if:** three mainstream hosts provide equivalent local session orchestration, self-modification, background jobs, and historical branching with open APIs.

### 2. Models may stop drifting enough to need Crow’s persistence story

A model with a huge reliable context window, strong compaction, and provider-managed session state could reduce the perceived value of durable local memory.

**The maintainer should worry about:** persistence is valuable partly because today’s models are unreliable long-horizon workers. If the model itself becomes much better at maintaining task state, users may accept provider-hosted sessions.

**Countermeasure:** emphasize inspectability, portability, local ownership, and orchestration—not merely “we remember.”

**Obsolete if:** users prefer opaque provider sessions even when they can no longer audit, fork, export, or locally resume them.

### 3. Local inference may remain technically cheap but operationally unpleasant

The project assumes enthusiasts will maintain local models, proxies, quantizations, networking, and browser auth. Most users will not. A hosted plan with a polished agent may win despite higher cost.

**The maintainer should worry about:** local-first architecture can become a hobbyist advantage with no broad adoption path.

**Countermeasure:** preserve provider neutrality and make the runtime work equally well with local llama.cpp, OpenAI-compatible endpoints, and hosted models. Keep the local path excellent without making it mandatory.

**Obsolete if:** the majority of target users report that model setup, latency, and compatibility are more painful than the persistence benefits are worth.

### 4. Self-modifying execution may fail enterprise trust requirements

A tool that can edit its own code, install dependencies, control a browser, launch subprocesses, and alter skills is difficult to approve in regulated environments. Capability composition makes “read-only” labels unreliable.

**The maintainer should worry about:** the feature that makes Crow ambitious also makes it hard to deploy safely.

**Countermeasure:** add capability manifests, approval boundaries, audit logs, signed skill revisions, sandbox profiles, and reproducible execution records.

**Obsolete if:** target customers require a fixed, centrally reviewed tool graph that cannot support Crow’s dynamic runtime.

### 5. The ecosystem may punish unknown clients regardless of technical quality

Provider User-Agent allowlists, plan-specific agent whitelists, editor integrations, and marketplace distribution create a compatibility moat around established agents. A technically superior local harness can remain invisible if it cannot access the same models and integrations.

**The maintainer should worry about:** discovery and access are separate from engineering merit.

**Countermeasure:** distribute ACP/MCP adapters, generated CLIs, skills, and provider-compatible integration layers. Make Crow useful even when a provider refuses to recognize its identity.

**Obsolete if:** provider policies require a closed agent identity that Crow cannot legally or technically support, and target users will not run compatible local endpoints.

### 6. Complexity can outrun the maintainer

The current project already spans ACP, MCP, TUI, SQLite memory, kernels, browser automation, skills, provider routing, and experimental orchestration. A daemon, Celery integration, scheduler, artifact system, and replay protocol can turn a small agent into an unmaintainable distributed system.

**The maintainer should worry about:** the project’s extensibility could become an accumulation of half-defined lifecycle models.

**Countermeasure:** keep the core small, protocol-driven, and boring. Put daemon/task features behind explicit state machines and integration boundaries. Prefer fewer primitives with strong semantics over many tools.

**Obsolete if:** adding each new subsystem creates more cross-layer bugs than user value, or the maintainer can no longer explain ownership and recovery for every persistent object.

## Cheapest decisive experiments

### 1. ACP replay conformance test

**Question:** Does Crow’s session loading/replay behavior actually interoperate with a real ACP client?

**Experiment:** record a session containing text, tool calls, tool results, cancellation, and a fork. Disconnect. Reconnect through a reference ACP client and verify that the frontend reconstructs the same visible state.

**Cost:** one focused test fixture and a small protocol harness.

**Success:** identical reconstructed conversation and tool state.

**Wrong if:** the client cannot rebuild state without Crow-specific assumptions. Then replay must become a top-priority protocol implementation task.

### 2. Crash matrix for Celery plus Crow sessions

**Question:** Can the proposed background-job architecture recover cleanly?

**Experiment:** launch a subprocess task, then kill the worker, agent process, kernel, broker, and subprocess at different points. Inspect SQLite and resume from the recorded session/job ID.

**Cost:** one afternoon and a local memory broker or Redis instance.

**Success:** every interruption lands in a distinguishable state with no silent loss or duplicate semantic completion.

**Wrong if:** recovery requires manually inspecting logs or guessing whether work ran. Add a durable job ledger before building the daemon.

### 3. Historical interrogation versus transcript reading

**Question:** Does forking at an offset provide real debugging value?

**Experiment:** select ten historical mistakes from Crow sessions. For each, compare:
1. a human reading the transcript;
2. an agent asked from the original offset why it acted as it did;
3. an agent given only the final transcript.

Measure time to identify cause and propose a correction.

**Cost:** ten sessions and a simple rubric.

**Success:** offset forks produce materially better causal explanations or fixes.

**Wrong if:** they merely repeat the transcript or invent rationalizations. Keep the feature as a convenience, not a core optimization primitive.

### 4. Follow-up API versus direct driver composition

**Question:** Is adding follow-up to `rlm()` worth making public?

**Experiment:** implement a temporary helper that loads a forked wire ID and sends a second prompt. Use it on real delegated research tasks and compare ergonomics, failure handling, and transcript clarity with direct `SubagentDriver` code.

**Cost:** a small temporary wrapper and several real tasks.

**Success:** follow-up is common enough that hiding it behind direct driver plumbing is clearly wasteful.

**Wrong if:** almost all children are one-shot or follow-up needs daemon ownership, scheduling, and retries. Keep follow-up in the client daemon rather than RLM.

### 5. Prefill-aware wakeup benchmark

**Question:** Does event coalescing materially improve local responsiveness?

**Experiment:** replay a synthetic burst of 20 completions and periodic reminders against the local model. Compare immediate wakeups, fixed batching, and priority-based batching. Record prefill time, response latency, and user-turn delay.

**Cost:** one benchmark script and three scheduler policies.

**Success:** batching reduces prefill and preserves interactive latency.

**Wrong if:** the endpoint handles naive wakeups acceptably or batching harms review quality. Avoid prematurely building a scheduler.

### 6. Real Component Service MCP generated-artifact test

**Question:** Can one MCP schema produce useful agent, CLI, and skill surfaces?

**Experiment:** implement only three read tools—entry search, entry detail, and lineage—against the authenticated Component Service. Generate the CLI and `SKILL.md`. Use:
- the existing LMNext agent backend;
- the generated CLI;
- a Crow skill;
- a human unfamiliar with the adapter.

**Cost:** three tools, typed result models, and contract tests.

**Success:** all consumers retrieve the same stable IDs, provenance, and pagination without adapter-specific instructions.

**Wrong if:** structured results are insufficient for the UI, generated commands are confusing, or authorization cannot be propagated cleanly. Fix the domain contract before adding tool breadth.

### 7. Composite capability boundary test

**Question:** Can a “read-only MCP” agent be safely described and governed?

**Experiment:** give an agent the read-only Component MCP, `execute`, local file access, and authenticated Playwright. Ask it to generate a GenBank file and stop before upload, then separately ask it to upload only after explicit approval. Record every side effect.

**Cost:** one staged environment and a small capability manifest.

**Success:** the agent can do useful work while approvals occur exactly at upload/submission boundaries.

**Wrong if:** the agent can bypass the approval path or the manifest cannot express the workflow. Then the daemon needs a stronger capability firewall before broader deployment.
