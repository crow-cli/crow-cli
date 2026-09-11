---
kind: ideas
session: serious-generous-ammonite-of-aptitude
agent: serious-generous-ammonite-of-aptitude-2-1
model: github-copilot/gpt-5.6-luna
cwd: /home/thomas/.agents/crow/src/crow-cli
generated: 2026-09-10T13:02:48.269555+00:00
---

## Assumptions worth attacking

### 1. A rendered system prompt is the correct boundary for harness capabilities

Crow currently has a useful separation:

```text
MCP tools → model-visible function calls
subtools → persistent execute environment
skills → prompt-disclosed workflows
```

The proposed generic agent layer extends that by making prompt construction programmable. The hidden assumption is that telling the model about a capability in Jinja is enough to make the capability usable.

It may not be.

A subtool can be:

- present in the kernel but absent from the prompt;
- described in the prompt but not actually imported;
- imported under a different name;
- changed after the prompt was rendered;
- available in the parent process but unavailable after kernel reset;
- callable but missing a useful usage example.

The existing `reload()` mechanism makes this especially important: the execute kernel can change its ambient namespace independently of the initial system prompt.

**What to do instead:** treat prompt disclosure and runtime loading as two outputs of one capability definition. A custom subtool should produce:

```text
runtime loader
prompt manifest
version/hash
```

The prompt should say what was loaded, not merely what the author intended to load.

**What would prove this attack wrong:** a test suite showing that a fresh agent can reliably discover, import, call, reset, and call again every declared subtool, with no prompt/runtime drift across multiple kernel resets.

### 2. Persisting `template + prompt_args + rendered prompt` is sufficient for reproducibility

This is a strong foundation, but it assumes the prompt is the only dynamic input.

A prompt callback may inspect:

- filesystem state;
- current skills;
- MCP tool schemas;
- environment variables;
- model configuration;
- git state;
- current date;
- database contents;
- custom application state.

Persisting the callback’s return value preserves the rendered prompt, but not necessarily why the callback returned it or whether the referenced files still exist. A fork can faithfully preserve the text while losing the semantic environment that produced it.

The existing session model already persists `prompt_args`, `system_prompt`, tool definitions, and model information. That is good, but the generic agent contract needs to define whether a session is:

```text
textually reproducible
```

or:

```text
behaviorally reproducible
```

Those are not the same.

**What to do instead:** persist a prompt-build record containing:

```text
template content or content hash
prompt args
rendered prompt
tool manifest
skill manifest
agent-definition version
environment/config fingerprint
```

Do not rerun the callback on load or fork unless explicitly requested.

**What would prove this attack wrong:** loading and forking a session from a different process, after changing the project files and installed skills, produces the same system message and equivalent tool environment without rerunning the builder.

### 3. `on_compact` is enough as the primary customization seam

The existing flow is clean:

```text
AcpAgent
  → react_loop(on_compact=...)
    → compact(on_compact=...)
```

The internal callback registers the new compacted session, and a user callback can be composed with it. That part should absolutely be exposed.

But the callback has two competing meanings:

- observe compaction after the new session exists;
- influence how compaction is performed.

Those are different contracts. A callback that receives:

```python
(old_agent_id, compacted_session)
```

cannot customize the summary prompt, the last-message policy, the analysis pass, or the new session’s prompt arguments. It is an event hook, not a compaction strategy.

**What to do instead:** preserve `on_compact` as a post-compaction event and add separate named policies:

```python
prompt_builder
compaction_prompt_builder
compaction_passes
on_compact
```

Do not turn every callback into an overloaded lifecycle object.

**What would prove this attack wrong:** a real custom project agent can replace the default compaction behavior using only `on_compact`, without modifying `compact.py`, duplicating session creation, or depending on private internals. If it cannot, the hook is not the customization seam people think it is.

### 4. The default Crow agent can be generalized without losing its character

The current default prompt assembly includes assumptions about:

- workspace;
- directory tree;
- AGENTS files;
- skill roots;
- agent catalogs;
- persistent execute;
- memory;
- web behavior;
- source-first spawning;
- compaction;
- forks;
- tool descriptions.

Turning those into a default `AgentDefinition` is the right architectural direction. But there is a danger in making every default policy injectable: the default agent can become a bag of callbacks whose interactions are no longer understandable.

The current agent works partly because the assumptions are centralized. A generic API that exposes every internal seam may produce an “agent framework” that is technically flexible but impossible to reason about.

**What to do instead:** define a small stable contract and keep the rest private:

```text
prompt builder
capability manifest
MCP server selection
hooks
on_compact
compaction policy
```

Do not expose every internal function merely because it can be passed as a callback.

**What would prove this attack wrong:** three substantially different agents—a default coding agent, a research agent, and a domain agent—can be implemented without private imports, while the default agent remains readable as a single definition rather than a maze of overrides.

### 5. Historical forks are valid counterfactual experiments

The message-granular fork is unusually powerful. The session can be forked twelve messages before the head, interrogated, and continued. That is a real executable history, not a flattened transcript.

But a fork is not automatically a controlled experiment. It may share:

- mutable filesystem state;
- external services;
- browser sessions;
- databases;
- model nondeterminism;
- changing MCP server versions;
- environment variables;
- a warm or cold inference cache.

The fork controls conversation history, not the entire world.

**What to do instead:** label experiments precisely:

```text
historical replay
context-controlled comparison
full environment-controlled replay
```

Capture a workspace/git reference and capability manifest with every benchmark instance. Do not call every fork result causal evidence.

**What would prove this attack wrong:** repeated baseline/variant runs from the same fork boundary show stable attribution when only one declared harness dimension changes. If results vary more than the mutation effect, forks are useful for reflection but not for causal benchmarking.

### 6. ACP is the right outer boundary for every deployment

ACP is a good agent/client boundary, and Crow already speaks ACP over stdio with experimental HTTP support. But ACP is a turn/session protocol. The proposed project-agent API is primarily about defining runtime behavior, prompt construction, capabilities, and lifecycle.

Those concerns do not all belong in ACP.

A project agent may need:

- capability discovery;
- task submission;
- prompt rendering;
- session resume;
- background events;
- artifact retrieval;
- configuration changes;
- health checks;
- schema/version negotiation.

ACP may carry some of these eventually, especially v2, but forcing all control-plane concerns through the conversational protocol could recreate the client/agent confusion that the background-daemon discussion exposed.

**What to do instead:** keep the agent runtime contract independent of transport. ACP v1/v2 should be adapters:

```text
AgentDefinition/runtime
  ├── ACP stdio adapter
  ├── ACP HTTP adapter
  ├── embedded Python adapter
  └── test/replay adapter
```

**What would prove this attack wrong:** a project-defined agent can run embedded in Python and over ACP without changing its prompt, tools, persistence, or lifecycle semantics.

## Prior art you should steal from

### 1. PydanticAI’s `Agent` and dependency-aware system prompts

PydanticAI has the closest conceptual shape to the desired `main.py` API:

```python
Agent(
    model,
    deps_type=...,
    system_prompt=...,
    tools=[...],
)
```

Its important mechanism is not the decorator syntax. It is the explicit runtime dependency/context object passed to dynamic system prompts and tools.

Crow should steal:

```text
typed run context
explicit dependencies
dynamic system-prompt functions
tool registration as code
```

A Crow equivalent could be:

```python
@dataclass
class AgentContext:
    cwd: Path
    session_id: str
    config: Config
    tools: CapabilitySet
    skills: SkillSet
```

Then:

```python
async def build_prompt(ctx: AgentContext) -> PromptSpec:
    ...
```

**Cost:** PydanticAI’s dependency model adds typing and lifecycle complexity. Crow should not import its whole agent architecture or pretend all context is statically typed.

**What would prove this wrong:** if dynamic prompt construction never needs runtime dependencies beyond `cwd`, config, and a static capability manifest, a context object becomes ceremony rather than leverage.

### 2. LangGraph’s graph/checkpoint/config separation

LangGraph separates:

```text
graph definition
runtime configuration
thread/session identity
checkpointed state
```

Crow already has analogous pieces:

```text
AcpAgent
AgentSession
agent_id/session_id
SQLite persistence
forks/compaction
```

What Crow should steal is the explicit distinction between:

- definition-time configuration;
- invocation-time context;
- durable thread state;
- mutable execution state.

That would prevent prompt callbacks from accidentally becoming session mutation callbacks.

A project agent could define:

```python
AgentDefinition(...)
```

while each session receives:

```python
RunContext(...)
```

and persists:

```python
SessionSnapshot(...)
```

**Cost:** LangGraph’s state graph model can become verbose and framework-heavy. Crow should not force every linear ReAct loop into a graph.

**What would prove this wrong:** if a small `PromptSpec` plus capability manifest handles all current project-agent use cases and no one needs resumable named state beyond `AgentSession`, adding a graph/state abstraction would be unnecessary.

### 3. OpenHands’ separation of agent, runtime, and event stream

OpenHands separates the agent’s reasoning from the runtime that executes actions and the event system that records them. This is relevant because Crow’s subtools are not MCP tools: they are runtime capabilities used through `execute`.

The useful thing to steal is the explicit capability boundary:

```text
agent policy
  → runtime action
  → structured event
```

Crow already has much of this:

- `execute`;
- subtool registration;
- ACP emissions;
- persisted `subtool_calls`;
- tool-call identity;
- session memory.

The project-agent layer should formalize it rather than converting subtools into fake MCP tools.

**Cost:** event-sourced runtimes produce large event surfaces and require careful replay semantics.

**What would prove this wrong:** if the existing subtool register and ACP emission already provide every event needed for debugging and replay, a second event abstraction would only duplicate the current one.

### 4. Jupyter/IPython’s kernel-plus-frontend model

Crow’s persistent execute design is much closer to Jupyter than to ordinary shell execution:

```text
persistent kernel
  → execute requests
  → display/output channels
  → state survives requests
  → reset is explicit
```

The critical idea to steal is that the kernel has a formal **startup/prelude contract** and a frontend/backend protocol, rather than merely running imported functions.

Crow’s `PRELUDE` and `reload()` are already moving in this direction. Custom subtools should be registered as kernel extensions with:

- import path;
- startup loader;
- reset behavior;
- display/persistence metadata;
- prompt manifest.

**Cost:** kernel lifecycle and extension loading become another compatibility surface.

**What would prove this wrong:** if custom subtools can be safely injected as ordinary imports into every project’s `main.py` without reset, reload, or identity problems, a formal kernel extension contract is unnecessary.

### 5. ACP v2’s explicit replay and update lifecycle

ACP v2’s separation between prompt acceptance, `session/update`, running state, idle state, and replay is directly relevant to the future agent-definition contract.

Crow should steal the conceptual separation:

```text
prompt accepted
  ≠ turn complete
  ≠ session idle
  ≠ background work finished
```

That distinction matters for custom `on_compact`, hooks, project events, and future supervisors. A project-defined callback should know whether it is reacting to:

- a turn;
- a compaction;
- a state transition;
- a background result;
- a replay.

**Cost:** v2 is still draft and should not force a migration of the Python v1 runtime before the semantics stabilize.

**What would prove this wrong:** if all supported project agents remain strictly synchronous, one prompt at a time, with no background events, v2 lifecycle complexity can remain outside the first implementation.

### 6. GEPA and MemoHarness

The `learn` skill already names these systems, so this is not a new direction in the repository. The relevant mechanism is worth stating precisely:

```text
execution traces
  → natural-language reflection
  → targeted harness mutation
  → Pareto selection
```

Crow’s historical forks make this more executable than a static trace evaluator. The project should steal the distinction between:

```text
agent task quality
```

and:

```text
harness quality
```

A failed session can be forked before the failure and replayed with a different prompt builder, subtool manifest, or compaction policy.

**Cost:** reflective evaluation is expensive, especially on a local model where compaction already costs multiple long generations.

**What would prove this wrong:** if fork-backed variants do not produce stable, attributable improvements over ordinary prompt A/B testing, the additional historical machinery is not earning its complexity.

## Directions nobody has pointed at

### 1. Make the prompt builder a compiler, not a callback

The proposed callback is the right starting point, but the stronger product is a prompt compiler.

Input:

```python
AgentDefinition(
    prompt_template=...,
    prompt_builder=...,
    skills=...,
    subtools=...,
    mcp_servers=...,
)
```

Output:

```text
PromptSpec
CapabilityManifest
ValidationReport
ProvenanceRecord
```

The compiler should detect:

- undeclared Jinja variables;
- declared but unused arguments;
- subtools mentioned but not loaded;
- tools loaded but not described;
- duplicate names;
- prompt size;
- unstable dynamic values;
- missing required sections.

This turns prompt construction from string assembly into a validated build artifact.

**What would prove it wrong:** if project agents rarely have more than five static arguments and prompt failures are never a source of debugging time, a compiler is overengineering.

### 2. Treat the agent definition as a package manifest

A project agent should be installable and inspectable like a Python package:

```text
agent.py
pyproject.toml
prompts/system.jinja2
skills/
subtools/
tests/
```

The manifest could expose:

```text
agent name/version
prompt template hash
skills
subtools
MCP servers
supported transports
model requirements
compaction policy
```

This would let Crow:

- list installed agents;
- launch one from TUI or CLI;
- expose one through ACP;
- generate a skill or CLI;
- validate compatibility;
- store the definition identity in sessions.

The current `sandbox/repl-agent` is already the prototype, but it is still an ad hoc script.

**What would prove it wrong:** if every intended user is comfortable importing Crow directly and writing a local `main.py`, packaging adds friction without creating a distribution benefit.

### 3. Add capability profiles rather than individual tool lists

A project agent probably does not want to manually specify every ambient subtool and MCP server forever. Define profiles:

```python
capabilities = [
    "execute",
    "memory",
    "web-research",
    "filesystem-read",
]
```

Each profile expands into:

```text
MCP tools
ambient subtools
prompt documentation
permissions
tests
```

This is especially useful because MCP and subtools are intentionally different channels. A profile can describe both without collapsing them.

For example:

```text
research
  → web MCP tools
  → web subtool helper
  → research skill
  → prompt section
```

**What would prove it wrong:** if profile expansion makes security and provenance less clear than explicit lists, require explicit declarations and abandon profiles.

### 4. Build a prompt/runtime consistency checker

The most likely failure in custom agents will not be ACP. It will be drift:

```text
the prompt says `lookup_component` exists
but the kernel does not expose it
```

A test command could start the project agent, render its prompt, reset the execute kernel, inspect the namespace, and compare the declared manifest to reality.

```bash
crow-agent check
```

It should verify:

- every declared subtool is importable;
- every prompt-visible subtool is registered;
- every MCP server starts;
- every skill path resolves;
- prompt args serialize;
- compaction can create a new session;
- load/fork preserves the definition snapshot.

**What would prove it wrong:** if custom agents are so small and local that developers can observe all drift manually, the checker is not worth maintaining.

### 5. Make “agent character” versioned independently from Crow runtime

A session should record both:

```text
runtime version
agent-definition version
```

Otherwise a historical session can be reloaded under a changed prompt builder and appear to be the same agent when it is not.

This would let the current Crow agent evolve from hardcoded defaults into a built-in definition without invalidating old sessions.

**What would prove it wrong:** if the persisted `system_prompt`, `prompt_args`, tools, and model are always sufficient for every supported replay path, a separate definition version adds little.

### 6. Turn compacted generations into typed handoff artifacts

Compaction currently creates a new agent row and invokes `on_compact`. That can become a generalized handoff protocol.

A compacted generation could produce:

```text
summary
last messages
open files/artifacts
pending actions
tool environment
prompt definition
parent generation
```

Then custom agents could consume a typed handoff rather than parsing a summary string.

This matters for domain agents and future supervisors. A project-level `on_compact` callback could save a structured artifact, while the default agent continues to use the normal conversational handoff.

**What would prove it wrong:** if every consumer only needs the existing summary text and no project agent needs machine-readable continuation state, typed handoffs are premature.

### 7. Use custom agents as a compatibility target for third-party ACP clients

The project-agent API could become the easiest way to make a domain agent compatible with Toad, Crow ADE, assistant-ui backends, and other ACP clients.

The product would not be “a better TUI.” It would be:

```text
write one Python agent definition
→ expose it through ACP
→ use it from many clients
```

This makes the client/agent split productive rather than confusing. Toad’s web server becomes one possible frontend, not the center of the architecture.

**What would prove it wrong:** if ACP clients cannot agree on persistent sessions, streaming, authentication, or custom capability negotiation, third-party compatibility will remain a demo rather than a product.

## What would make this obsolete

### 1. Model providers ship complete, extensible agent runtimes

The strongest threat is not another TUI. It is a model provider offering:

```text
persistent sessions
tool plugins
skills
prompt templates
background execution
browser/filesystem access
evaluation
web UI
```

with excellent model-specific integration and zero setup.

If users can define a custom agent in a hosted dashboard and receive a durable session, tool registry, and web client, Crow’s generic runtime becomes less compelling for ordinary users.

Crow’s defense cannot be “we have more features.” It must be:

- local-first;
- model-agnostic;
- inspectable;
- forkable;
- source-extensible;
- compatible with multiple clients;
- capable of running the same agent over different transports.

**Stop condition:** if a hosted runtime supports arbitrary local Python subtools, reproducible historical forks, and local model endpoints with comparable transparency, the general-purpose Crow runtime is no longer differentiated.

### 2. MCP absorbs the distinction between model tools and runtime skills

The current architecture deliberately distinguishes MCP tools from execute subtools. That is useful, but it creates two capability systems to document, load, test, and secure.

If MCP evolves to support:

- stateful kernels;
- client-side execution;
- prompt/resource injection;
- capability manifests;
- lifecycle hooks;
- rich UI artifacts;

then custom subtools may become an unnecessary second path.

**Stop condition:** if MCP can provide persistent Python runtime capabilities with equivalent identity rails, reset semantics, and prompt disclosure, consolidate instead of preserving a bespoke subtool system.

### 3. ACP becomes too narrow or loses ecosystem momentum

Crow’s value as an agent runtime depends partly on ACP becoming a real interoperability layer. If major clients settle on incompatible proprietary APIs, or if ACP remains unstable and fragmented, the transport story weakens.

The code can still be useful embedded, but “define once, use from many clients” becomes false.

**Stop condition:** if two strategically important target clients cannot consume the same project agent without custom adapters that exceed the runtime itself, treat ACP as one adapter rather than the product boundary.

### 4. Local inference economics change

The architecture is optimized around local inference realities:

- expensive prefill;
- cheap-ish repeated decode;
- warm history;
- avoiding pointless concurrent generations;
- persistent kernels;
- prompt-prefix reuse.

A future model server may provide cheap continuous batching, near-zero-cost context caching, or effectively unlimited cloud inference. Some of Crow’s strongest scheduling assumptions would then become obsolete.

**Stop condition:** benchmark a representative Crow workload against the new inference stack. If persistent local state and prompt-prefix reuse no longer improve latency or cost, remove complexity built solely around those assumptions.

### 5. Browser-native agents make ACP clients irrelevant

The user’s idea of using Crow as a backend behind a web interface is exposed to a threat: a browser-native agent may directly own the UI, tools, persistence, and user identity.

In that world, ACP is useful for desktop/editor integration but not sufficient for a web product. HTTP transport alone does not solve:

- authentication;
- multi-tenancy;
- reconnect/replay;
- permissions;
- artifact delivery;
- session ownership;
- browser-safe streaming.

**Stop condition:** if the intended audience only needs a browser application and no one uses the same agent from Toad, an editor, CLI, or Python, build a web-native service instead of preserving ACP as the primary public interface.

### 6. Prompt callbacks become a framework trap

The project may replace hardcoded assumptions with callbacks and end up recreating a framework that users must understand before they can write one agent.

The failure mode is:

```text
simple main.py
→ PromptContext
→ PromptSpec
→ CapabilityManifest
→ hooks
→ compact policy
→ runtime registration
→ transport adapter
→ persistence adapter
```

That is not syntactical sugar. It is a second programming language.

**Stop condition:** if a competent Python developer cannot create a custom agent in under fifty lines and understand its lifecycle from one page of documentation, reduce the API surface.

## Cheapest decisive experiments

### 1. Custom prompt builder end-to-end

**Question:** Can the existing backend support a project-defined prompt callback without special-casing or breaking persistence?

**Experiment:** Add the smallest possible `prompt_builder` argument to `AcpAgent`. Have it return:

```python
(template, {"project_name": "test-agent"})
```

Use a custom Jinja template, create a session, inspect the database, load the session in a new process, and fork it.

Verify:

```text
template persisted
args persisted
rendered system prompt persisted
load does not rerun callback
fork inherits the snapshot
```

**Cost:** one small implementation slice and focused tests.

**Stop if:** the callback must access internal mutable agent state, or if making it work requires duplicating `make_agent_session()` rather than cleanly injecting at the existing creation seam.

### 2. Custom `on_compact` composition

**Question:** Can a project observe compaction without replacing Crow’s mandatory in-memory session bookkeeping?

**Experiment:** Add `on_compact` to `AcpAgent`, compose it with the current internal callback, and use a test callback that writes the old/new agent IDs to a list or temporary file.

Trigger both:

```text
automatic compaction
/compact
```

Verify the callback fires exactly once in both paths and the next prompt resolves to the compacted agent.

**Cost:** a few lines of plumbing plus tests.

**Stop if:** the callback changes session registration semantics, fires inconsistently across paths, or must know private details of `react_loop`.

### 3. Subtool manifest versus prompt/runtime drift

**Question:** What is the minimal reliable way to auto-load custom execute subtools and describe them in the prompt?

**Experiment:** Define one project subtool using the existing `@subtool` decorator. Add a project manifest entry containing:

```text
name
function
description
usage
```

Start a fresh agent, render the prompt, execute a cell calling the subtool, reset the kernel, and call it again.

Then deliberately remove the loader while leaving the prompt declaration intact and ensure `crow-agent check` fails.

**Cost:** one custom subtool, one prelude/runtime extension, one consistency test.

**Stop if:** the runtime cannot distinguish built-in and project subtools without global mutable state, or if reload/reset causes identity and telemetry corruption.

### 4. Default agent as a definition object

**Question:** Can the existing Crow agent be expressed as a default project-like definition without behavioral drift?

**Experiment:** Extract current prompt argument assembly into `default_prompt_builder`. Leave the rendered output byte-for-byte identical. Compare a baseline session and a definition-backed session for:

- system prompt;
- tool schemas;
- skill catalog;
- execute behavior;
- compaction;
- fork behavior.

**Cost:** refactoring plus golden tests.

**Stop if:** the default builder needs access to private call-stack assumptions or if the refactor changes the prompt enough to invalidate existing behavioral characterization tests.

### 5. Prompt-definition validation

**Question:** Does prompt construction fail often enough to justify a compiler/check command?

**Experiment:** Build a validator that:

- parses the Jinja template;
- identifies undeclared variables;
- renders with the supplied args;
- checks declared subtools against the runtime manifest;
- checks skill paths;
- reports prompt size and missing required sections.

Run it against the current default prompt and two intentionally broken project agents.

**Cost:** small utility plus three fixtures.

**Stop if:** the current and two realistic custom prompts produce no useful validation failures, or if Jinja’s undeclared-variable analysis produces too many false positives to trust.

### 6. Project-agent scaffold

**Question:** Does the proposed `main.py` surface actually reduce complexity?

**Experiment:** Add a command that scaffolds:

```text
.agents/crow/agent.py
.agents/crow/prompts/system.jinja2
.agents/crow/pyproject.toml
```

The generated agent should select the default execute harness, one skill, one custom prompt arg, and one hook.

Measure:

```text
lines of user-authored code
time to first ACP session
number of Crow internals imported
```

Have a second developer—or a fresh Crow session—use it without reading the implementation.

**Cost:** scaffold plus one documentation example.

**Stop if:** the generated project requires more than roughly fifty lines to express a useful custom agent, or if users must import private modules to customize prompt construction.

### 7. Determine whether HTTP ACP is actually the right web backend

**Question:** Does the existing ACP-over-HTTP implementation provide enough for a real web client, or is a separate web API required?

**Experiment:** Connect the smallest web client or a minimal browser frontend to the HTTP ACP server and test:

- new session;
- streamed updates;
- reconnect;
- load/resume;
- cancellation;
- fork;
- concurrent sessions;
- authentication boundary;
- compaction transition.

Do not build the background daemon first.

**Cost:** a thin client and a short acceptance test.

**Stop if:** reconnect/replay, auth, or multi-session ownership require a second protocol immediately. In that case, keep ACP as the agent transport and design a separate web control plane instead of pretending ACP is already the web product.
