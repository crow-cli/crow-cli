# crow-cli + Spec Kit Integration Options

## Overview

You have three main integration strategies for combining your artisanal crow-cli agent with GitHub's Spec Kit framework.

---

## Option 1: crow-cli as a Generic Agent (⭐ RECOMMENDED)

**Concept:** Use Spec Kit's workflow with crow-cli as your "bring your own agent" implementation.

### How It Works

1. Install Spec Kit in your project:
```bash
specify init . --ai generic --ai-commands-dir ~/.crow/commands/
```

2. Spec Kit creates wrapper scripts in `~/.crow/commands/` that translate `/speckit.*` commands into crow-cli interactions

3. Run crow-cli and use spec-kit commands:
```bash
crow-cli
> /speckit.constitution "Establish coding standards..."
> /speckit.specify "Build a photo album app..."
> /speckit.plan "Use Vite + vanilla JS..."
> /speckit.tasks
> /speckit.implement
```

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Spec Kit Workflow                     │
│  /speckit.constitution → /speckit.specify → /speckit.plan│
│              ↓              ↓              ↓            │
│         /speckit.tasks → /speckit.implement             │
└─────────────────────────────────────────────────────────┘
                          ↓
         ┌────────────────────────────────────┐
         │   Wrapper Scripts (~/.crow/commands/)  │
         │   Translate /speckit.* to LLM prompts │
         └────────────────────────────────────┘
                          ↓
         ┌────────────────────────────────────┐
         │        crow-cli (ACP Agent)        │
         │  - ReAct loop with streaming       │
         │  - Session persistence             │
         │  - Tool execution                  │
         └────────────────────────────────────┘
                          ↓
         ┌────────────────────────────────────┐
         │       LLM + MCP Tools              │
         │  - ZAI API / other providers       │
         │  - terminal, read, write, edit     │
         └────────────────────────────────────┘
```

### Implementation Steps

1. **Create command wrappers** in `~/.crow/commands/`:
   - `constitution.md` - wrapper for /speckit.constitution
   - `specify.md` - wrapper for /speckit.specify
   - `plan.md` - wrapper for /speckit.plan
   - `tasks.md` - wrapper for /speckit.tasks
   - `implement.md` - wrapper for /speckit.implement

2. **Each wrapper does:**
   - Reads the spec-kit template
   - Injects user prompt
   - Formats as crow-cli compatible prompt
   - Executes via crow-cli's tool system

3. **Update crow-cli** to recognize `/speckit.*` commands and route to appropriate wrappers

### Pros
- ✅ Minimal changes to crow-cli
- ✅ Uses Spec Kit's battle-tested templates
- ✅ Crow-cli remains your core execution engine
- ✅ Can leverage Spec Kit's extension system
- ✅ Full control over agent behavior

### Cons
- ❌ Need to create wrapper scripts
- ❌ Some command translation overhead
- ❌ May need to customize templates for crow-cli

---

## Option 2: crow-cli as a Spec Kit Extension

**Concept:** Package crow-cli's capabilities as a Spec Kit extension.

### How It Works

1. Create a `crow-cli-extension` with `extension.yml` manifest
2. Extension provides crow-cli specific commands and tools
3. Install extension into spec-kit projects

### Example Extension Manifest

```yaml
schema_version: "1.0"

extension:
  id: "crow-cli"
  name: "Crow CLI Extension"
  version: "0.1.0"
  description: "Integrates crow-cli ACP agent with Spec Kit"
  author: "Your Name"

provides:
  commands:
    - name: "speckit.crow.init"
      file: "commands/crow-init.md"
      description: "Initialize crow-cli agent in spec-kit project"
    
    - name: "speckit.crow.execute"
      file: "commands/crow-execute.md"
      description: "Execute tasks using crow-cli"

  tools:
    - name: "crow-terminal"
      description: "Execute terminal commands via crow-cli"
    
    - name: "crow-read"
      description: "Read files via crow-cli"
```

### Pros
- ✅ Clean integration with Spec Kit ecosystem
- ✅ Can publish to community catalog
- ✅ Reusable across projects
- ✅ Follows Spec Kit extension patterns

### Cons
- ❌ More complex to set up
- ❌ Need to understand Spec Kit extension system deeply
- ❌ May conflict with crow-cli's native tool execution

---

## Option 3: Hybrid - Spec Kit Templates in crow-cli

**Concept:** Integrate Spec Kit's templates directly into crow-cli as skills/prompts.

### How It Works

1. Copy Spec Kit templates into crow-cli's `prompts/` directory
2. Add `/speckit.*` commands to crow-cli's command routing
3. Use crow-cli's session system to manage spec artifacts

### Architecture

```
┌─────────────────────────────────────────────────┐
│                   crow-cli                      │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │  Prompts/Skills Layer                   │   │
│  │  - system_prompt.jinja2                 │   │
│  │  - speckit_constitution.jinja2 ← NEW   │   │
│  │  - speckit_specify.jinja2 ← NEW        │   │
│  │  - speckit_plan.jinja2 ← NEW           │   │
│  └─────────────────────────────────────────┘   │
│                      ↓                          │
│  ┌─────────────────────────────────────────┐   │
│  │  ReAct Loop + Session Management        │   │
│  │  - Session persistence (SQLite)         │   │
│  │  - Event tracking                       │   │
│  │  - Compaction                           │   │
│  └─────────────────────────────────────────┘   │
│                      ↓                          │
│  ┌─────────────────────────────────────────┐   │
│  │  Tool Execution                         │   │
│  │  - ACP/MCP tools                        │   │
│  │  - Parallel execution                   │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### Implementation Steps

1. **Copy Spec Kit templates** to `crow-cli/prompts/`:
   ```bash
   cp spec-kit/templates/*.jinja2 crow-cli/prompts/
   ```

2. **Add command routing** in crow-cli:
   ```python
   # In crow-cli/agent/main.py
   async def handle_speckit_command(self, command: str, args: str):
       if command == "constitution":
           return await self.render_prompt("speckit_constitution", args)
       elif command == "specify":
           return await self.render_prompt("speckit_specify", args)
       # ... etc
   ```

3. **Store artifacts** in `.specify/` directory structure

### Pros
- ✅ Tightest integration
- ✅ No wrapper overhead
- ✅ Crow-cli manages everything natively
- ✅ Full control over spec artifacts

### Cons
- ❌ More invasive changes to crow-cli
- ❌ Need to maintain templates separately
- ❌ Lose Spec Kit's CLI tooling

---

## Recommended Approach: Option 1 (Generic Agent)

**Why Option 1?**

1. **Minimal friction** - Uses Spec Kit as-is with crow-cli as the execution engine
2. **Preserves your investment** - crow-cli remains your artisanal, frameworkless agent
3. **Leverages Spec Kit strengths** - Templates, workflows, and community ecosystem
4. **Incremental adoption** - Can start with basic commands and expand
5. **Easy to test** - Try it today without major refactoring

### Quick Start for Option 1

```bash
# 1. Create command wrapper directory
mkdir -p ~/.crow/commands

# 2. Copy Spec Kit command templates
cp -r /path/to/spec-kit/templates/commands/* ~/.crow/commands/

# 3. Initialize spec-kit project with generic agent
cd /your/project
specify init . --ai generic --ai-commands-dir ~/.crow/commands/

# 4. Run crow-cli
crow-cli

# 5. Use spec-kit commands
> /speckit.constitution "Write code that follows PEP 8..."
> /speckit.specify "Build a photo album app..."
```

### Wrapper Script Example

**File:** `~/.crow/commands/constitution.md`

```markdown
---
description: "Create project constitution"
---

# Project Constitution

{{ ARGUMENTS }}

Please create a comprehensive constitution document that establishes:
1. Coding standards and best practices
2. Testing requirements
3. Architecture principles
4. Documentation guidelines

Save this to `.specify/memory/constitution.md`
```

---

## Next Steps

1. **Try Option 1** - Set up the generic agent integration
2. **Test with a simple project** - Verify the workflow
3. **Customize as needed** - Adjust templates for crow-cli
4. **Consider Option 3** - If you want deeper integration later

Would you like me to:
- Create the wrapper scripts for Option 1?
- Help you set up the extension for Option 2?
- Implement the template integration for Option 3?
