# PROMPT: Test Understanding Against Reality

Welcome to the Crow Agent project. Your mission: **Build working systems while building understanding.**

## Start Here - In This Order

### 1. **Read AGENTS.md in FULL and obey its edicts**
   
This is non-negotiable. AGENTS.md contains:
- Critical rules (git commits, sys.path, uv usage)
- **The Dialectical Development Process** (our core methodology)
- How tests encode understanding, not just verify code
- Why essays are agent memory

Read it. Understand it. OBEY IT.

### 2. **Catch up with current state**

Read IMPLEMENTATION_PLAN.md to understand:
- What we've accomplished (85% complete)
- What's in progress (E2E tests, SDK polish)
- What's left to do (hooks, compaction, extensions)

If IMPLEMENTATION_PLAN.md is woefully out of date, **your first task is to update it** based on what you find in:
- `docs/essays/` - The agent's memory of understandings
- `ACKNOWLEDGEMENTS.md` - What's been figured out
- Test results (what works, what doesn't)

### 3. **Understand the Dialectic: Both Top-Down AND Bottom-Up**

We use two complementary approaches:

**Top-Down (Understanding → Reality):**
1. UNDERSTAND through research and reading
2. DOCUMENT in essays (`docs/essays/`)
3. BUILD CONSTRAINTS (tests that encode understanding)
4. Let reality negate assumptions (~X)
5. SYNTHESIZE new understanding (Y)
6. Implement

**Bottom-Up (Reality → Understanding):**
1. Build working examples (scripts/, REPL tests)
2. See what actually works
3. Learn from practical failures
4. Document discoveries in essays
5. "Feed my sheep" - produce measurable results

**Why Both?**
- Top-down gives us deep understanding
- Bottom-up grounds us in reality
- You don't understand what you can't build
- E2E tests are "synthetic cells" - minimal working systems

### 4. **Your Mission: Create SDK Example + Fix E2E Tests**

**Primary Goal:** Make the Crow SDK usable in IPython REPL

**Shortest Path:**
1. Run `scripts/simple_example.py` - Does it work?
2. Run E2E tests: `uv --project . run pytest tests/e2e/ -v`
3. See what fails - that's ~X (reality negating X)
4. Fix or create working examples
5. Update tests from new understanding

**What Success Looks Like:**

```python
# In IPython REPL (this MUST work):
from crow.agent import Agent, Config

agent = Agent()
session = await agent.new_session(cwd="/tmp")
response = await agent.prompt([{"type": "text", "text": "hello"}], session.session_id)
```

## Breadcrumbs Left For You

### In AGENTS.md:
- The dialectical development process (X → ~X → Y)
- How tests encode understanding
- Why sys.path is forbidden

### In docs/essays/:
- `00-file-editor-semantics.md` - What file editor IS for LLMs
- `02-hooks-realization.md` - Why we need hooks
- `05-python-sdk-that-emerged.md` - The config system philosophy
- Read these to understand WHAT we built and WHY

### In IMPLEMENTATION_PLAN.md:
- Current status (85% complete)
- What's working vs what's not
- Next steps clearly laid out

### In test_agent_e2e.py:
- Tests that encode our UNDERSTANDING of how agents work
- May fail initially (that's TDD - let them teach you)
- Fix them to match reality, update understanding

## Your Process

1. **Search/Understand** (broad exploration)
2. **Document** (essays capture understanding)
3. **Test Understanding** (write/run tests, see failures)
4. **Build Working Examples** (scripts/, REPL - "feed my sheep")
5. **Synthesize** (new understanding from X + ~X → Y)
6. **Implement** (code that embodies synthesis)
7. **Refactor** (clean up while preserving understanding)

## Key Directories

```
src/crow/              # The SDK itself
crow-mcp-server/       # MCP tools (file_editor, web_search, fetch)
tests/                 # Understanding constraints
  ├─ unit/             # Fast semantic tests
  ├─ integration/      # Component interactions  
  └─ e2e/              # Full system (REAL, NO MOCKS)
scripts/               # Working examples (bottom-up)
docs/essays/           # Agent memory (top-down)
refs/                  # Reference implementations (READ ONLY)
```

## Critical Reminders

1. **NEVER make git commits** - Human only
2. **NEVER manipulate sys.path** - Fix packages properly
3. **ALWAYS use `uv --project .`** - Every command
4. **Write essays for insights** - Agent memory
5. **Test understanding via reality** - Both directions
6. **Working examples matter** - Don't just have theory

## Final Goal

Build something that **WORKS** and demonstrates **UNDERSTANDING**.

The next agent should be able to pick up where you left off by:
1. Reading this PROMPT.md
2. Reading AGENTS.md (obey or die)
3. Reading IMPLEMENTATION_PLAN.md (catch up)
4. Running your working examples (see reality)
5. Running your tests (test understanding)
6. Continuing the dialectic

Good luck. Build to understand. Understand to build.

---

*Remember: The code grounds our understanding through tests. The tests encode our understanding. Working examples prove both.*
