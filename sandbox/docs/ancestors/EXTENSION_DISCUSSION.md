# Extension Discussion - Crow Framework

## Overview

This document captures the architectural discussions around building a frameworkless, extension-based agent framework for Crow.

## Core Principles

### Frameworkless Framework
- Core logic is <300 lines (react loop, MCP integration)
- Everything else is an extension
- No built-in tools - all tools come from MCP servers
- No hardcoded providers - swappable via extensions

### Protocol-Based Architecture
- **ACP** (Agent Client Protocol) - Agent-Client communication
- **MCP** (Model Context Protocol) - Agent-Tool communication
- Build on existing protocols, don't reinvent

### Dynamic Discovery
- Skills not in system prompt (saves context window)
- Agent calls `discover_skills(query)` to find relevant skills
- MCP server uses ColBERT/semantic routing to filter skills
- Full skill instructions loaded only when needed

## Architecture

### Crow Core
```
Crow Core (300 lines)
├── ACP Protocol (agent-client-protocol)
├── MCP Client (user's tools)
├── MCP Server (Dynamic Discovery)
│   ├── discover_skills(query) → ColBERT filters → XML
│   └── get_skill_details(name) → full SKILL.md
├── Session Manager
│   ├── Persistence (database with token tracking)
│   └── Compaction (auto-trigger when tokens > threshold)
├── Template Engine (Jinja for system prompt)
└── Progress Disclosure System
    ├── Load skill metadata at startup
    ├── Activate full skill when needed
    └── Load scripts/assets on demand
```

### Extensions
| Extension Type | Format | Integration |
|----------------|--------|-------------|
| **Provider** | Python module | Swaps out react loop logic |
| **Skills** | `SKILL.md` + scripts | MCP prompts + filesystem access |
| **Custom ACP** | JSON-RPC methods | `_crow/compact`, `_crow/subagent` |

## Key Insights

### Skills Architecture
1. **Discovery** - Scan directories for `SKILL.md` files
2. **Metadata loading** - Parse YAML frontmatter (name, description)
3. **System prompt injection** - `<available_skills>` XML block
4. **Keyword matching** - Agent decides which skills are relevant
5. **Activation** - Load full instructions when skill is used
6. **Execution** - Run scripts, access resources

### Dynamic Discovery MCP
The "Secret Sauce":
- Context window savings (no dumping 50 skills)
- Late-interaction mapping (ColBERT filters at runtime)
- Cross-language portability (MCP interface)
- Async cancellation support (ACP can drop tasks)

### AgentSkills Standard
```
skill-name/
└── SKILL.md          # Required: instructions + metadata
├── scripts/          # Optional: executable code
├── references/       # Optional: documentation
└── assets/           # Optional: templates, resources
```

YAML frontmatter:
```yaml
---
name: skill-name
description: A description of what this skill does and when to use it.
triggers: [keyword1, keyword2]
---
```

## Implementation Plan

### Phase 1: Core
- [ ] ACP protocol glue (agent-client-protocol python-sdk)
- [ ] MCP client integration (fastmcp)
- [ ] Session persistence (database with token tracking)
- [ ] Compaction (auto-trigger when tokens > threshold)

### Phase 2: Dynamic Discovery
- [ ] Skills MCP server (wrapping skills-ref library)
- [ ] `discover_skills(query)` with ColBERT semantic routing
- [ ] XML generation for system prompt injection
- [ ] Progressive disclosure (metadata at startup, full on trigger)

### Phase 3: Extensions
- [ ] Provider extensions (swappable react loop logic)
- [ ] Skills repository aggregator
- [ ] Custom ACP methods (`_crow/compact`, `_crow/subagent`)

## Files

### Core Files
- `database.py` - Session and event persistence with token tracking
- `streaming_async_react.py` - React loop with token capture
- `streaming_async_react_with_db.py` - React loop with database persistence

### Documentation
- `docs/EXTENSION_DISCUSSION.md` - This file
- `TABLE_SCHEMA.md` - Database schema
- `SESSION_PERSISTENCE.md` - Session persistence guide

## Next Steps

1. Implement `discover_skills` with ColBERTv2 integration
2. Skills stored as `skills/{name}/SKILL.md`
3. XML generation for system prompt injection
4. Jinja templates for skill content injection
5. Provider extensions (swappable react loop logic)

## References

- [Agent Client Protocol](https://agentclientprotocol.com/)
- [Model Context Protocol](https://github.com/modelcontextprotocol)
- [Agent Skills](https://agentskills.io/)
- [pi agent](https://shittycodingagent.ai/)
- [ACE (Agentic Context Engineering)](https://github.com/ace-agent/ace)
