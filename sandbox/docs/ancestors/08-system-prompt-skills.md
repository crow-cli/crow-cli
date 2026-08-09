# System Prompt and Skill Management

## Overview

Crow's system prompt is dynamically constructed from multiple sources to provide rich context without hard-coding knowledge. Skills are first-class citizens loaded from standard repositories.

## System Prompt Construction

### Components

```python
SYSTEM_PROMPT_TEMPLATE = """# Crow AI Assistant

You are a Python-focused coding agent that helps developers build, debug, and understand software.

## Core Identity

You reason primarily in Python and have access to:
- A persistent Python REPL environment (like Jupyter)
- MCP tools for file operations, search, and more
- A suite of skills for common tasks
- The internet via search APIs

## Communication Style

- Be concise and direct
- Show code early, explain after
- Use proper Python idioms and patterns
- Ask clarifying questions when uncertain
- Admit when you don't know something

## Reasoning Approach

1. Understand the goal clearly
2. Search for information when needed (use multiple sources in parallel)
3. Prototype solutions in the Python REPL
4. Test edge cases
5. Refine based on results

{TOOL_DESCRIPTIONS}

{PROJECT_CONTEXT}

{AVAILABLE_SKILLS}

{RECENT_CONVERSATION_SUMMARY}
"""
```

### Tool Descriptions

Dynamic injection of available MCP tools:

```python
async def build_tool_description_section(mcp_client: Client) -> str:
    """Generate tool description section from available MCP tools"""
    
    tools = await mcp_client.list_tools()
    
    descriptions = []
    for tool in tools:
        desc = f"""### {tool.name}
{tool.description}

**Parameters:** {json.dumps(tool.inputSchema, indent=2)}
"""
        descriptions.append(desc)
    
    return "## Available Tools\n\n" + "\n".join(descriptions)
```

### Project Context (AGENTS.md)

Read and include project-specific context:

```python
def load_project_context(workspace_path: str) -> str:
    """Load project-specific context from AGENTS.md"""
    
    agents_md = Path(workspace_path) / "AGENTS.md"
    
    if agents_md.exists():
        content = agents_md.read_text()
        return f"## Project Context\n\n{content}"
    
    return ""
```

### Skills Section

List available and loaded skills:

```python
def build_skills_section(loaded_skills: list[str], available_skills: list[str]) -> str:
    """Build skills section"""
    
    loaded = "## Loaded Skills\n\n"
    if loaded_skills:
        loaded += "The following skills are currently active:\n\n"
        for skill in loaded_skills:
            loaded += f"- `{skill}`: {get_skill_description(skill)}\n"
    else:
        loaded += "No specific skills are loaded. Using general Python coding capability.\n"
    
    available = "## Available Skills (Not Loaded)\n\n"
    if available_skills:
        available += "These skills can be loaded if relevant to your task:\n\n"
        for skill in available_skills:
            available += f"- `{skill}`: {get_skill_description(skill)}\n"
    else:
        available = ""
    
    return loaded + "\n" + available if available else loaded
```

## Skill System

### Skill Repository Structure

```
~/.crow/skills/
├── core/
│   ├── python_debugging.skill
│   ├── file_operations.skill
│   └── search_strategy.skill
├── contributed/
│   ├── web_scraping.skill (from user)
│   └── ml_workflow.skill (from user)
└── external/
    ├── openhands/ (borrowed from OpenHands)
    │   ├── git_operations.skill
    │   └── docker.skill
    └── custom/
        └── specialized_tool.skill
```

### Skill Format

```yaml
# web_scraping.skill

name: web_scraping
description: Skills for web scraping, API interaction, and data extraction
version: "1.0.0"
author: "crow-ai"

dependencies:
  - "requests>=2.31.0"
  - "beautifulsoup4>=4.12.0"
  - "selenium>=4.15.0"

system_prompt_addition: |
  ## Web Scraping Skills
  
  You are experienced in:
  - HTTP request handling with requests library
  - HTML parsing with BeautifulSoup
  - Dynamic content extraction with Selenium
  - Rate limiting and respectful scraping
  - API interaction patterns
  
  Best practices:
  1. Always check robots.txt before scraping
  2. Use appropriate delays between requests
  3. Handle errors gracefully (404, 403, timeouts)
  4. Cache responses when possible
  5. Use session objects for connection pooling

tools:
  - name: fetch_url
    description: Fetch URL with error handling and retries
    implementation: tools/web_scraping.py::fetch_url
  
  - name: parse_html
    description: Parse HTML with BeautifulSoup
    implementation: tools/web_scraping.py::parse_html

examples:
  - task: "Scrape article titles from a blog"
    steps:
      - "Check robots.txt"
      - "Fetch main page with requests"
      - "Parse with BeautifulSoup to extract <article> tags"
      - "Extract title from each article"
      - "Return as list of dictionaries"
    code: |
      import requests
      from bs4 import BeautifulSoup
      
      response = requests.get('https://example.com/blog')
      soup = BeautifulSoup(response.text, 'lxml')
      articles = soup.find_all('article')
      [{'title': a.find('h2').text} for a in articles]

tags: [web, scraping, requests, beautifulsoup, selenium]
```

### Skill Manager

```python
from typing import List, Optional
import yaml
from pathlib import Path

class SkillManager:
    """Manages skill discovery, loading, and registration"""
    
    def __init__(self, skill_paths: list[str]):
        self.skill_paths = [Path(p) for p in skill_paths]
        self.loaded_skills: dict[str, Skill] = {}
        self.available_skills: dict[str, Skill] = {}
        
        self._discover_skills()
    
    def _discover_skills(self):
        """Discover all available skills"""
        self.available_skills = {}
        
        for path in self.skill_paths:
            if not path.exists():
                continue
            
            for skill_file in path.rglob("*.skill"):
                try:
                    skill = Skill.from_file(skill_file)
                    self.available_skills[skill.name] = skill
                except Exception as e:
                    print(f"Warning: Failed to load skill {skill_file}: {e}")
    
    async def load_skill(self, skill_name: str) -> bool:
        """Load a skill into the current session"""
        
        if skill_name not in self.available_skills:
            print(f"Skill '{skill_name}' not found")
            return False
        
        skill = self.available_skills[skill_name]
        
        # Check dependencies
        for dep in skill.dependencies:
            await self._install_dependency(dep)
        
        # Load tools from skill
        for tool_def in skill.tools:
            await self._register_tool(tool_def)
        
        # Track as loaded
        self.loaded_skills[skill_name] = skill
        
        return True
    
    async def unload_skill(self, skill_name: str):
        """Unload a skill"""
        if skill_name in self.loaded_skills:
            del self.loaded_skills[skill_name]
    
    async def _install_dependency(self, dependency: str):
        """Install a package if not present"""
        try:
            import importlib
            importlib.import_module(dependency)
        except ImportError:
            # Install via uv or pip
            await install_python_package(dependency)
    
    async def _register_tool(self, tool_def: dict):
        """
        Register a tool from skill definition.
        
        This integrates with the MCP server to expose the tool.
        """
        tool_name = tool_def['name']
        implementation_path = tool_def['implementation']
        
        # Dynamically import and register
        module_path, func_name = implementation_path.split('::')
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        
        # Register with MCP server
        register_mcp_tool(tool_name, func)
    
    def get_loaded_skills(self) -> List[str]:
        """Get list of currently loaded skill names"""
        return list(self.loaded_skills.keys())
    
    def get_available_skills(self) -> List[str]:
        """Get list of all discovered skill names"""
        return list(self.available_skills.keys())
    
    def get_skill(self, skill_name: str) -> Optional['Skill']:
        """Get skill object by name"""
        return self.available_skills.get(skill_name)

class Skill:
    """Represents a loaded skill"""
    
    def __init__(
        self,
        name: str,
        description: str,
        version: str,
        dependencies: List[str],
        system_prompt_addition: str,
        tools: List[dict],
        examples: List[dict],
        tags: List[str]
    ):
        self.name = name
        self.description = description
        self.version = version
        self.dependencies = dependencies
        self.system_prompt_addition = system_prompt_addition
        self.tools = tools
        self.examples = examples
        self.tags = tags
    
    @classmethod
    def from_file(cls, path: Path) -> 'Skill':
        """Load skill from YAML file"""
        
        with open(path) as f:
            data = yaml.safe_load(f)
        
        return cls(
            name=data['name'],
            description=data['description'],
            version=data['version'],
            dependencies=data.get('dependencies', []),
            system_prompt_addition=data.get('system_prompt_addition', ''),
            tools=data.get('tools', []),
            examples=data.get('examples', []),
            tags=data.get('tags', [])
        )
    
    def get_system_prompt_addition(self) -> str:
        """Get skill's system prompt addition"""
        return self.system_prompt_addition
```

### Skill Auto-Discovery

```python
async def discover_and_load_relevant_skills(
    task_description: str,
    skill_manager: SkillManager,
    vector_store: 'VectorStore'
) -> List[str]:
    """
    Discover and load skills relevant to a task.
    
    Uses vector similarity to match task to skills.
    """
    
    # Get all available skills
    available = skill_manager.get_available_skills()
    
    if not available:
        return []
    
    # Create query embedding
    query_embedding = await embed_text(task_description)
    
    # Search for similar skills
    results = await vector_store.search(
        collection="skills",
        query_vector=query_embedding,
        limit=5
    )
    
    # Load top matches
    loaded = []
    for result in results:
        skill_name = result.payload['name']
        if skill_name in available and skill_name not in loaded:
            success = await skill_manager.load_skill(skill_name)
            if success:
                loaded.append(skill_name)
    
    return loaded
```

### Skill Placeholder Creation

When the finish tool identifies a missing skill, create a placeholder:

```python
async def create_skill_placeholder(
    session_id: str,
    skill_name: str,
    description: str,
    from_session: bool = False
):
    """
    Create a skill placeholder for future implementation.
    
    This is called by the finish tool when the agent identifies
    something that would have been useful as a skill.
    """
    
    placeholder_dir = Path("~/.crow/skills/placeholders").expanduser()
    placeholder_dir.mkdir(parents=True, exist_ok=True)
    
    skill_file = placeholder_dir / f"{skill_name}.skill"
    
    skill_yaml = f"""name: {skill_name}
description: {description}
version: "0.1.0"  # Placeholder
author: "crow-ai-auto-generated"
status: "placeholder"
source: "session_{session_id}" if from_session else "manual"

system_prompt_addition: |
  ## {skill_name}
  
  (This skill is a placeholder awaiting implementation)
  
  Intended purpose: {description}

tools: []
examples: []
tags: [placeholder]
"""
    
    with open(skill_file, 'w') as f:
        f.write(skill_yaml)
    
    print(f"Created skill placeholder: {skill_file}")
```

### Borrowing from OpenHands

Don't be too proud to use existing skills:

```bash
# Import OpenHands skills
git clone https://github.com/All-Hands-AI/OpenHands.git ~/.crow/skills/external/openhands

# Adapt their skill format to Crow's format
python -m crow.tools.import_openhands_skills ~/.crow/skills/external/openhands/skills ~/.crow/skills/contributed
```

```python
def import_openhands_skill(openhands_skill_path: Path, output_path: Path):
    """Convert OpenHands skill to Crow skill format"""
    
    # OpenHands has a different skill format, convert it
    # They use JSON with metadata
    
    with open(openhands_skill_path) as f:
        data = json.load(f)
    
    # Convert to YAML
    crow_skill = {
        'name': data['name'],
        'description': data['description'],
        'version': '1.0.0',
        'author': 'openhands',
        'system_prompt_addition': data.get('system_prompt', ''),
        'tools': [],
        'examples': [],
        'tags': data.get('tags', [])
    }
    
    with open(output_path.with_suffix('.skill'), 'w') as f:
        yaml.dump(crow_skill, f)
```

## Prompt Assembly

```python
class SystemPromptBuilder:
    """Assembles system prompt from multiple sources"""
    
    def __init__(
        self,
        skill_manager: SkillManager,
        persistence: SessionPersistence
    ):
        self.skill_manager = skill_manager
        self.persistence = persistence
    
    async def build_system_prompt(
        self,
        session_id: str,
        workspace_path: str,
        mcp_client: Client
    ) -> str:
        """Build complete system prompt for this session"""
        
        components = []
        
        # Core prompt
        components.append(SYSTEM_PROMPT_TEMPLATE)
        
        # Tool descriptions from MCP
        tools_desc = await build_tool_description_section(mcp_client)
        components.append(tools_desc)
        
        # Project context
        project_ctx = load_project_context(workspace_path)
        components.append(project_ctx)
        
        # Skills loaded
        loaded_skills = self.skill_manager.get_loaded_skills()
        available_skills = [s for s in self.skill_manager.get_available_skills() if s not in loaded_skills]
        skills_section = build_skills_section(loaded_skills, available_skills)
        components.append(skills_section)
        
        # Recent conversation summary (if exists)
        summary = await self.persistence.get_session_summary(session_id)
        if summary:
            components.append(f"## Session Context\n\n{summary}")
        
        # Combine all
        full_prompt = "\n\n".join(components)
        
        # Store for reference
        await self.persistence.set_system_prompt(session_id, full_prompt)
        
        return full_prompt
```

## Prompt Compaction

The system prompt can get large. Compress it periodically:

```python
async def compress_system_prompt(
    original: str,
    target_size: int = 2000  # tokens
) -> str:
    """
    Compress system prompt using LLM summarization.
    
    Keeps the most important parts while reducing token count.
    """
    
    # Split into sections
    sections = original.split("\n## ")
    
    # Always keep core identity
    core = sections[0]
    
    # Compress other sections
    compressed = [core]
    
    for section in sections[1:]:
        prompt = f"""Compress this section to {target_size // 10} tokens while preserving:
- Tool names and when to use them
- Key instructions
- Critical warnings

Section:
{section}

Provide compressed version without markdown headers (##)."""
        
        response = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        compressed.append(response.choices[0].message.content)
    
    return "\n\n".join(compressed)
```

## Testing

```python
async def test_skill_system():
    """Test skill discovery and loading"""
    
    skill_manager = SkillManager([
        "~/.crow/skills/core",
        "~/.crow/skills/contributed"
    ])
    
    # Discover skills
    available = skill_manager.get_available_skills()
    assert len(available) > 0
    
    # Load a skill
    success = await skill_manager.load_skill('python_debugging')
    assert success
    
    # Verify it's loaded
    loaded = skill_manager.get_loaded_skills()
    assert 'python_debugging' in loaded
    
    # Build system prompt with skill
    prompt = build_skills_section(loaded, [])
    assert 'python_debugging' in prompt

async def test_system_prompt_builder():
    """Test complete system prompt assembly"""
    
    builder = SystemPromptBuilder(mock_skill_manager, mock_persistence)
    
    prompt = await builder.build_system_prompt(
        session_id="test",
        workspace_path="/tmp/test",
        mcp_client=mock_mcp_client
    )
    
    # Verify all components present
    assert "Crow AI Assistant" in prompt
    assert "Available Tools" in prompt
    assert "Loaded Skills" in prompt
    
    print(f"System prompt length: {len(prompt)} chars")
```

## Best Practices

1. **Keep identity section concise** - Don't make the system prompt too long
2. **Skills should be additive** - Each skill enhances, doesn't replace
3. **Use examples in skills** - Show, don't just tell
4. **Borrow heavily** - Don't reinvent what OpenHands has built
5. **Version skills** - Track changes over time
6. **Tag skills appropriately** - For better search/discovery

## References

- OpenHands skills: https://github.com/All-Hands-AI/OpenHands
- Skill sharing patterns
- Prompt engineering best practices
