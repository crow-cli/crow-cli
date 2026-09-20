To support $N$ different Jupyter kernels (like Node, R, Bash, etc.), you need to explicitly pass `kernel_name` to `KernelManager`, track which kernel type is active for the session, and—critically—disable your Python-specific setup (the prelude, prologue, and executable overrides) when a non-Python kernel is loaded.

Here are the specific modifications needed for both files.

**1. Update `kernel.py` (The Kernel Wrapper)**

Modify `CrowKernel.__init__` to accept `kernel_name`. You must pass this to `KernelManager` and ensure that the `python_path` override only applies to the default Python kernel so you don't overwrite another language's executable.

```python
class CrowKernel:
    """A small wrapper around jupyter_client for crow's ``execute`` tool."""

    def __init__(
        self, 
        python_path: str | None = None, 
        cwd: str | None = None,
        kernel_name: str = "python3"
    ):
        # Initialize with the requested kernel type
        self.km = KernelManager(kernel_name=kernel_name)

        # Point the kernel at crow-cli's own interpreter ONLY if it's Python
        if python_path and kernel_name == "python3":
            self.km.kernel_spec.argv[0] = python_path

        if cwd:
            self.km.start_kernel(cwd=cwd)
        else:
            self.km.start_kernel()

        self.client = self.km.client()
        self.client.start_channels()
        self._wait_ready()

```

**2. Update `main.py` (The Tool & State Manager)**

You need to track the active kernel type per session so you can force a reset if the user swaps languages mid-session. You also need to gate the Python-specific injected code (`_prologue` and `_run_prelude`) so you don't send Python syntax to an R or Node REPL.

Add a state dictionary at the top with `_kernels`:

```python
_kernels: dict[str, CrowKernel] = {}
_kernel_names: dict[str, str] = {}  # Tracks language type per session

```

Update `get_kernel` to accept `kernel_name` and handle dynamic language swapping:

```python
def get_kernel(key: str, cwd: str, kernel_name: str = "python3") -> CrowKernel:
    """Get or lazily start the persistent kernel for a key."""
    kernel = _kernels.get(key)
    current_name = _kernel_names.get(key)
    
    # If the user asked for a different language than what's running, force reset
    if kernel is not None and current_name != kernel_name:
        logger.info(f"Kernel type changed from {current_name} to {kernel_name} for {key}")
        kernel.shutdown()
        kernel = None

    if kernel is None:
        logger.info(f"Starting new {kernel_name} kernel for {key} in {cwd}")
        kernel = CrowKernel(python_path=sys.executable, cwd=cwd, kernel_name=kernel_name)
        
        # Only run Python setup in Python kernels
        if kernel_name == "python3":
            _run_prelude(kernel)
            
        _kernels[key] = kernel
        _kernel_names[key] = kernel_name
        
    return kernel

```

Update the `execute` tool signature and core logic:

```python
@mcp.tool
async def execute(
    ctx: Context,
    code: str,
    reset: bool = False,
    timeout: float | None = 30.0,
    kernel_name: str = "python3",  # <--- New Optional Argument
) -> str:
    # ... docstrings ...
    try:
        key, cwd, session_id, parent_tcid, db_uri, images_dir, rlm_depth = (
            _kernel_context(ctx)
        )

        if reset:
            old = _kernels.pop(key, None)
            _kernel_names.pop(key, None)  # Clear the type tracking
            if old:
                old.shutdown()
                logger.info(f"Reset kernel for {key}")
            if not code.strip():
                return f"Kernel ({kernel_name}) reset successfully. All previous state lost."

        kernel = get_kernel(key, cwd, kernel_name=kernel_name)
        
        if code.strip():
            # Only inject the Python identity prologue if running Python
            if kernel_name == "python3":
                code = _prologue(session_id, parent_tcid, db_uri, images_dir, rlm_depth) + code
                
            output = kernel.execute(code, timeout=timeout)
            return _cap(output) if output else "[no output]"

    except Exception as e:
    # ... remaining exception handling ...

```

Don't forget to clean up `_kernel_names` in `shutdown_all`:

```python
def shutdown_all() -> None:
    for key in list(_kernels):
        kernel = _kernels.pop(key, None)
        _kernel_names.pop(key, None)
        if kernel:
            kernel.shutdown()

```


---



That's gemini



here's chatgpt


Yeah — I think the cleanest extension is to make the **kernel runtime a property of the kernel instance**, rather than trying to mutate the existing `KernelManager` after it has started.

Right now your lifecycle is essentially:

> session ID → `CrowKernel` → one kernelspec/runtime

and `reset=True` destroys that `CrowKernel` and creates a fresh one. That gives you a very natural place to select a different runtime.

The main thing I'd change is **don't overload `python_path` to represent runtime type**. `python_path` is an executable; a Jupyter runtime/kernel type is a **kernelspec name**.

### 1. Add `kernel_name` to `CrowKernel`

Your current constructor:

```python
def __init__(self, python_path: str | None = None, cwd: str | None = None):
    self.km = KernelManager()
```

could become:

```python
def __init__(
    self,
    python_path: str | None = None,
    cwd: str | None = None,
    kernel_name: str = "python3",
):
    self.km = KernelManager(kernel_name=kernel_name)

    if python_path:
        self.km.kernel_spec.argv[0] = python_path

    if cwd:
        self.km.start_kernel(cwd=cwd)
    else:
        self.km.start_kernel()
```

The important distinction is:

* `kernel_name="python3"` → select a **Jupyter kernelspec**
* `python_path="/path/to/python"` → override the executable *inside that kernelspec*

That means your existing crow behavior can remain intact for Python while opening the door to other supported kernels. 

---

## 2. Make `get_kernel()` accept the runtime

Currently:

```python
def get_kernel(key: str, cwd: str) -> CrowKernel:
```

I'd make it:

```python
def get_kernel(
    key: str,
    cwd: str,
    kernel_name: str = "python3",
) -> CrowKernel:
    kernel = _kernels.get(key)

    if kernel is None:
        logger.info(
            f"Starting new {kernel_name} kernel for {key} in {cwd}"
        )
        kernel = CrowKernel(
            python_path=sys.executable if kernel_name == "python3" else None,
            cwd=cwd,
            kernel_name=kernel_name,
        )
        _run_prelude(kernel)
        _kernels[key] = kernel

    return kernel
```

Although I'd actually go one step further and **not hard-code `python3`** here. Define your supported runtimes centrally.

For example:

```python
SUPPORTED_KERNELS = {
    "python": {
        "kernel_name": "python3",
        "python_path": sys.executable,
    },
    "julia": {
        "kernel_name": "julia",
    },
    "ir": {
        "kernel_name": "ir",
    },
}
```

Or, if you literally want the user to specify kernelspec names:

```python
SUPPORTED_KERNELS = {
    "python3",
    "julia",
    "ir",
}
```

I'd favor the **named/allowlisted approach**, because otherwise your MCP tool is effectively allowing the caller to ask the server to launch arbitrary installed kernels.

---

## 3. Put the runtime argument on `execute()`

I'd make the public API:

```python
async def execute(
    ctx: Context,
    code: str,
    reset: bool = False,
    timeout: float | None = 30.0,
    kernel: str | None = None,
) -> str:
```

Then the semantics are:

| `reset` | `kernel`   | Behavior                                                  |
| ------- | ---------- | --------------------------------------------------------- |
| false   | none       | Continue existing kernel                                  |
| false   | `"python"` | Continue existing kernel; probably ignore/reject mismatch |
| true    | none       | Reset to default kernel                                   |
| true    | `"julia"`  | Reset and create Julia kernel                             |
| true    | `"ir"`     | Reset and create R kernel                                 |

I would **not silently switch runtimes without `reset=True`**.

Something like:

```python
if kernel is not None and kernel not in SUPPORTED_KERNELS:
    return (
        f"Error: unsupported kernel {kernel!r}. "
        f"Supported kernels: {', '.join(sorted(SUPPORTED_KERNELS))}"
    )

if kernel is not None and not reset and key in _kernels:
    return (
        "Error: kernel runtime can only be changed when reset=True"
    )
```

That gives you a very predictable contract.

---

## 4. The reset path becomes very simple

You currently have:

```python
if reset:
    old = _kernels.pop(key, None)
    if old:
        old.shutdown()
```



I'd change the surrounding logic to:

```python
kernel_name = kernel or DEFAULT_KERNEL

if reset:
    old = _kernels.pop(key, None)
    if old:
        old.shutdown()

    if not code.strip():
        # Important: if reset=True with a kernel name,
        # actually create the requested runtime.
        get_kernel(key, cwd, kernel_name=kernel_name)
        return f"Kernel reset successfully to {kernel_name!r}."

kernel = get_kernel(
    key,
    cwd,
    kernel_name=kernel_name,
)
```

But there's a subtle question here.

### I wouldn't actually start the kernel on an empty reset

Your current behavior:

```python
execute("", reset=True)
```

means "destroy the old kernel and don't necessarily need to create the replacement yet."

That's a nice lazy behavior.

So I'd preserve it:

```python
if reset:
    old = _kernels.pop(key, None)
    if old:
        old.shutdown()

    if not code.strip():
        _pending_kernels[key] = kernel_name
        return f"Kernel reset successfully to {kernel_name!r}."
```

Then the next execution creates it.

However, that introduces `_pending_kernels`, which may be more complexity than you want.

So my preferred API is actually:

```python
execute(
    code="",
    reset=True,
    kernel="julia",
)
```

**creates the Julia kernel immediately**, while:

```python
execute(
    code="",
    reset=True,
)
```

retains your existing lazy/default behavior.

---

# There's one bigger issue I'd address

Your `_kernels` dictionary currently only stores:

```python
_kernels: dict[str, CrowKernel] = {}
```



Once runtime selection exists, I'd make the runtime explicit in the object itself:

```python
class CrowKernel:
    def __init__(
        self,
        *,
        kernel_name: str,
        cwd: str | None = None,
        python_path: str | None = None,
    ):
        self.kernel_name = kernel_name
        ...
```

Then you can detect accidental mismatches:

```python
existing = _kernels.get(key)

if existing is not None:
    if kernel is not None and existing.kernel_name != kernel:
        return (
            f"Error: session is currently using "
            f"{existing.kernel_name!r}; use reset=True to switch "
            f"to {kernel!r}."
        )

    return existing
```

That's much safer than relying on the caller to remember which runtime is currently alive.

---

# I'd also rename `kernel` → `runtime`

There's a semantic distinction worth preserving:

```python
async def execute(
    ctx: Context,
    code: str,
    reset: bool = False,
    timeout: float | None = 30.0,
    runtime: str | None = None,
)
```

Then the call reads nicely:

```text
execute(code="...", reset=True, runtime="julia")
```

rather than:

```text
execute(code="...", reset=True, kernel="julia")
```

because `CrowKernel` is your Python wrapper object, while `"julia"` / `"ir"` / `"python3"` is the **Jupyter kernelspec/runtime**.

---

## One more important consideration: your prologue

This is the part I'd be most careful about.

Every non-empty execution currently gets:

```python
code = _prologue(...) + code
```



and `_prologue()` assumes the target runtime can execute Python:

```python
from crow_cli.tools.register import begin_cell as _crow_begin
_crow_begin(...)
```



So if by "N different supported Jupyter kernel runtime types" you mean **actual different languages** — e.g. Python, Julia, R, etc. — you can't blindly prepend that prologue to all of them.

I'd introduce a runtime descriptor:

```python
@dataclass(frozen=True)
class Runtime:
    kernelspec: str
    language: str
    crow_prologue: Callable[..., str] | None = None
```

Then:

```python
RUNTIMES = {
    "python": Runtime(
        kernelspec="python3",
        language="python",
        crow_prologue=_python_prologue,
    ),
    "julia": Runtime(
        kernelspec="julia",
        language="julia",
        crow_prologue=None,
    ),
}
```

Now `execute()` can do:

```python
runtime = resolve_runtime(runtime_name)

if runtime.crow_prologue:
    code = runtime.crow_prologue(...) + code
```

That gives you a really clean architecture:

```text
                   ┌─────────────────────┐
                   │     MCP execute     │
                   └──────────┬──────────┘
                              │
                    runtime="python"
                              │
                    ┌─────────▼─────────┐
                    │ Runtime descriptor │
                    │                   │
                    │ kernelspec         │
                    │ language           │
                    │ prologue           │
                    │ interpreter opts   │
                    └─────────┬─────────┘
                              │
                       reset=True
                              │
                    ┌─────────▼─────────┐
                    │    CrowKernel     │
                    │                   │
                    │ KernelManager     │
                    │ kernel_name       │
                    └───────────────────┘
```

### If your "N runtime types" are all Python runtimes

For example, you're really talking about things like:

```text
python-system
python-venv
python-3.12
python-3.13
pypy
```

then **don't introduce the language/prologue abstraction yet**. In that case I'd keep the architecture much simpler: a runtime registry mapping a logical runtime name to a kernelspec and/or Python executable.

That's probably the version I'd implement first.

If you're talking about **different languages**, I think the runtime registry + language-specific prologue approach is the right long-term design. If you're talking about **Python environments**, there's a substantially simpler implementation.




---
here's me saying "we'd just make subtools in the N different languages we support it's NBD"



Ah, yeah — that changes my recommendation pretty substantially, and honestly makes the design **cleaner**.

If the runtimes are genuinely different language environments, I'd treat this as **runtime plugins/adapters**, not as "different Python paths."

The interesting part isn't launching the Jupyter kernel. `KernelManager(kernel_name=...)` handles that nicely. The interesting part is **what Crow injects into each kernel**.

Right now you effectively have:

```text
execute()
   │
   ├── _prologue(...)
   │       └── Python crow tooling
   │
   └── CrowKernel
           └── Python IPython kernel
```

I'd evolve that toward:

```text
execute(runtime="python")
        │
        ▼
   RuntimeRegistry
        │
        ├── PythonRuntime
        │     ├── kernelspec = python3
        │     ├── prologue
        │     └── native subtools
        │
        ├── JuliaRuntime
        │     ├── kernelspec = julia
        │     ├── prologue
        │     └── native subtools
        │
        └── RRuntime
              ├── kernelspec = ir
              ├── prologue
              └── native subtools
```

### The key abstraction I'd introduce

Something roughly like:

```python
class KernelRuntime(Protocol):
    name: str
    kernelspec: str

    def prologue(
        self,
        *,
        session_id: str | None,
        parent_tcid: str | None,
        db_uri: str | None,
        images_dir: str | None,
        rlm_depth: int,
    ) -> str: ...

    def prelude(self) -> str: ...
```

Then:

```python
class PythonRuntime:
    name = "python"
    kernelspec = "python3"

    def prologue(...):
        return """... Python begin_cell(...) ..."""

    def prelude(self):
        return PYTHON_PRELUDE
```

And eventually:

```python
class JuliaRuntime:
    name = "julia"
    kernelspec = "julia"

    def prologue(...):
        return """... Julia equivalent ..."""

    def prelude(self):
        return JULIA_PRELUDE
```

That means `CrowKernel` becomes almost completely runtime-agnostic:

```python
class CrowKernel:
    def __init__(
        self,
        runtime: KernelRuntime,
        cwd: str | None = None,
    ):
        self.runtime = runtime
        self.km = KernelManager(
            kernel_name=runtime.kernelspec,
        )
        ...
```

And your current `get_kernel()` becomes:

```python
def get_kernel(
    key: str,
    cwd: str,
    runtime: KernelRuntime,
) -> CrowKernel:
    kernel = _kernels.get(key)

    if kernel is None:
        kernel = CrowKernel(runtime=runtime, cwd=cwd)
        _run_prelude(kernel, runtime)
        _kernels[key] = kernel

    return kernel
```

### And I think the subtools are actually the easy part

I wouldn't try to make Python's `fs`, `web`, `memory`, `rlm`, etc. somehow polymorphic inside the kernel.

Instead, make each runtime's **native tool surface** responsible for adapting to Crow's underlying services.

For example, conceptually:

```text
Crow service layer
       │
       ├───────────────┬────────────────┐
       ▼               ▼                ▼
 Python bindings   Julia bindings    R bindings
       │               │                │
       ▼               ▼                ▼
     fs()            fs()             fs()
     web()           web()            web()
     rlm()           rlm()            rlm()
```

So Julia gets actual Julia functions/macros, rather than some ugly Python interop layer:

```julia
result = await web(...)
```

or whatever native syntax makes sense for the eventual API.

That has a **really nice consequence**: the LLM gets a runtime-appropriate programming environment. You aren't pretending Julia is Python.

---

### One thing I'd definitely change in your API

I'd make runtime selection explicit but optional:

```python
async def execute(
    ctx: Context,
    code: str,
    reset: bool = False,
    timeout: float | None = 30.0,
    runtime: str | None = None,
)
```

with:

```python
DEFAULT_RUNTIME = "python"
```

Then:

```text
execute("x = 42")
```

means exactly what it means today.

But:

```text
execute(
    "x = 42",
    reset=True,
    runtime="julia",
)
```

means:

> Kill this session's Python kernel and replace it with the Julia runtime.

And subsequent:

```text
execute("x += 1")
```

continues in Julia.

That matches the persistence semantics you've already built: state survives calls, and `reset=True` deliberately destroys it. 

---

### I'd also put runtime in the session state

This is important because right now `_kernels[key]` implicitly tells you everything.

I'd make it explicit:

```python
@dataclass
class KernelSession:
    kernel: CrowKernel
    runtime: KernelRuntime
```

Then:

```python
_sessions: dict[str, KernelSession] = {}
```

Now you can give good errors:

```text
Session is currently using runtime "julia".
Use reset=True to switch to "python".
```

rather than accidentally trying to feed Python into an existing Julia kernel.

---

### One subtle thing I really like about your current architecture

Your `_prologue()` is already conceptually an **identity/bootstrap layer** rather than business logic. 

That's exactly the seam I'd exploit.

I'd probably rename it eventually:

```python
runtime.prologue(...)
```

and move the current implementation into:

```python
PythonRuntime.prologue(...)
```

Then the rest of `execute()` doesn't care whether it's Python, Julia, R, etc.:

```python
runtime = registry.resolve(runtime_name)

if reset:
    destroy_session(key)

session = get_session(key, cwd, runtime)

if code.strip():
    code = runtime.prologue(...) + code

return session.kernel.execute(code, timeout=timeout)
```

That's a **very small conceptual change** to what you've already got, but it gives you a pretty powerful extension point.

And I'd resist building a giant generic runtime framework beyond that initially. You really only need three things to vary:

1. **How the Jupyter kernel is launched**
2. **What bootstrap code is injected**
3. **What native Crow subtools are installed into the runtime**

Everything else — session lifetime, timeout behavior, stale-message handling, output capping, reset semantics, image plumbing, DB identity, etc. — can stay in the existing infrastructure. Your current separation already makes that possible. 

So yeah: **I think this is quite a good fit for what you've already built.** The architecture doesn't need a rewrite; I'd make `Runtime` the one new first-class concept and push the language-specific stuff behind it.

---
ME:
lmfao here's an idea. just build an execute tool in N different languages I mean this is MCP. that would be MUCH cleaner conceptually but this would allow in-session swapping

---

CHATGPT:

😂 **YES.** That's arguably the more MCP-native design.

Instead of:

```text
execute(code, runtime="python")
execute(code, runtime="julia")
execute(code, runtime="r")
```

you expose:

```text
python.execute(code)
julia.execute(code)
r.execute(code)
...
```

Each tool has a completely different schema/description and can be implemented by its own native runtime.

That gives the model an incredibly clean mental model:

```text
MCP server
├── python.execute(...)
├── julia.execute(...)
├── r.execute(...)
└── ...
```

And each one can say, in its own tool description:

> Persistent Julia REPL for this session. Variables, imports, functions, etc. survive between calls.

No runtime argument. No runtime registry exposed to the model. No "what language am I currently in?" ambiguity.

### And you still get the killer feature

Because your underlying session key is already independent of the tool function, you can have:

```text
python.execute("x = 42")

julia.execute("x = 17")

python.execute("print(x)")
# 42

julia.execute("println(x)")
# 17
```

So you're not really **swapping** a runtime anymore.

You're giving the session **multiple persistent runtime lanes**.

That's actually substantially more interesting.

```text
                     ACP session
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
        Python REPL   Julia REPL     R REPL
             │            │            │
          state A       state B       state C
```

And `reset=True` becomes beautifully local:

```text
python.execute("", reset=True)
```

only nukes the Python REPL.

No need to destroy/recreate the session's "current runtime."

---

## It also solves the subtool problem elegantly

Each language implementation can bootstrap its own native Crow API:

```text
python.execute
    ↓
Python prelude
    ↓
fs, web, memory, rlm, vision, ...

julia.execute
    ↓
Julia prelude
    ↓
fs, web, memory, rlm, vision, ...

r.execute
    ↓
R prelude
    ↓
fs, web, memory, rlm, vision, ...
```

The MCP surface itself becomes the abstraction boundary.

That's **much cleaner than trying to make one mega-tool polymorphic**.

And because MCP tools are independently described, the model can potentially decide:

> I need Python for this data-science thing, but Julia would be better for this numerical computation.

without having to first call `execute(runtime="...")` and establish some hidden mode.

---

## The implementation can be hilariously boring

You could almost literally factor the existing `execute` into a factory:

```python
def make_execute_tool(
    *,
    name: str,
    kernel_name: str,
    prelude: str,
):
    @mcp.tool(name=name)
    async def execute(
        ctx: Context,
        code: str,
        reset: bool = False,
        timeout: float | None = 30.0,
    ) -> str:
        ...

    return execute
```

Then:

```python
python_execute = make_execute_tool(
    name="python.execute",
    kernel_name="python3",
    prelude=PYTHON_PRELUDE,
)

julia_execute = make_execute_tool(
    name="julia.execute",
    kernel_name="julia",
    prelude=JULIA_PRELUDE,
)
```

Although I'd probably avoid making the factory *too* clever. A tiny common `PersistentKernelTool` implementation with thin per-language wrappers would probably be easier to debug.

The really important part is that **the language-specific code lives with the language-specific tool**.

---

### There's an even nicer consequence

You don't necessarily need the tool names to imply that these are "kernels."

You could expose:

```text
python
julia
r
```

as the tools, with the descriptions making clear that they're persistent execution environments.

Or:

```text
python.execute
julia.execute
r.execute
```

if your MCP implementation/client handles dotted names naturally.

The latter is probably my preference because it leaves room for:

```text
python.install
python.inspect
python.help
```

later if you ever need them.

---

**So I'd actually abandon the `runtime=` idea.**

The `runtime=` version is technically neat, but it's solving a problem at the wrong abstraction layer. MCP already gives you a mechanism for exposing distinct capabilities. **Make each runtime a capability.**

Then the thing you have today isn't:

> "an execute tool that can become Julia"

It's:

> **"a collection of persistent language execution tools sharing the same Crow session infrastructure."**

That's a much more compelling architecture.


---
ME:
yeah why not just like execute the tool via mcp??? we don't need to build the interop it's called fastmcp

---

Exactly 😂. **FastMCP already is the interop layer.**

The mistake would be thinking:

> "How do we make one Python MCP tool talk to Julia/R/etc.?"

when the much simpler answer is:

> **"Don't. Expose Julia/R/etc. as MCP tools and let the kernel call MCP."**

That changes the architecture from language interop to **MCP composition**.

You'd have something like:

```text
                     FastMCP server
                          │
          ┌───────────────┼────────────────┐
          │               │                │
          ▼               ▼                ▼
    python.execute   julia.execute     r.execute
          │               │                │
          ▼               ▼                ▼
     Python REPL      Julia REPL        R REPL
          │               │                │
          └───────────────┼────────────────┘
                          │
                    shared Crow DB
                    shared identity
                    shared session
```

And inside Julia, instead of us inventing some `crow.web()` Julia binding, the Julia runtime can just invoke the appropriate MCP capability.

**That's the entire point of MCP.**

The really nice part is that this makes your existing `begin_cell` machinery much less special. The native runtime can simply be another MCP client/participant.

So I'd seriously consider making the architecture:

```text
runtime-specific execute tool
        ↓
persistent Jupyter kernel
        ↓
native runtime
        ↓
MCP client
        ↓
Crow MCP tools
```

rather than:

```text
runtime-specific execute tool
        ↓
persistent Jupyter kernel
        ↓
custom language bindings
        ↓
Crow internals
```

The former means you get **one interoperability protocol**, instead of building and maintaining:

* Python ↔ Crow
* Julia ↔ Crow
* R ↔ Crow
* whatever else ↔ Crow

You build:

* MCP ↔ Python
* MCP ↔ Julia
* MCP ↔ R

…and FastMCP is already sitting there.

### And there's a particularly cool implication

The runtime doesn't even necessarily need to know it's talking to "Crow."

Give each kernel an MCP client with the appropriate tool set, and its native bootstrap can teach it:

> These are the tools available to you.

Then the model can do something like:

```text
python.execute
  └─ Python asks MCP for database operation

julia.execute
  └─ Julia asks MCP for web operation

r.execute
  └─ R asks MCP for filesystem operation
```

while **the outer model sees all of those as ordinary MCP capabilities**.

That makes the whole thing composable rather than bespoke.

And your current code is already suspiciously close to being the right substrate: you have persistent per-session kernels, identity metadata, DB URI, image plumbing, and the prologue mechanism. 

So yeah, I think your instinct is right:

**Don't build a multi-language Crow API. Build multi-language MCP clients.**

That's *way* less code, and more importantly, it means every future runtime gets the same integration contract automatically.
