"""
Agent session management - persistence layer for conversation state.

One row = One message. No conv_index gymnastics. No reconstruction headaches.
Just serialize the message dict, deserialize it back.

Agent owns the session. agent_id = "{session_id}-{agent_idx}-{fork_idx}"
is the PK (schema v5; trunk carries fork_idx=1). session_id is derived from
agent_id for ACP upstream routing.
"""

import os
from logging import Logger
from pathlib import Path
from typing import Any

import yaml
from coolname import generate_slug

from crow_cli.agent.memory import DEFAULT_MEMORY_PATH, MemoryClient, MemoryServiceError
from crow_cli.memory import build_agent_id
from crow_cli.agent.prompt import render_template
from crow_cli.agent.context import get_directory_tree

from crow_cli.config import (
    AGENTS_DIR,
    NOTES_DIR,
    SKILLS_DIR,
    Config,
)

async def get_session_by_cwd(cwd, memory_path=DEFAULT_MEMORY_PATH):
    """
    Lookup agents by working directory via the memory db.

    Returns list of session info dicts with session_id, title, updated_at.
    """
    client = MemoryClient(memory_path)
    try:
        result = []
        for agent in await client.list_agents():
            prompt_args = agent.prompt_args or {}
            if prompt_args.get("workspace") != cwd:
                continue

            # Title from the second message (index 1, after the system message).
            # Fetch the first three records so len > 2 tells us a title exists.
            title = "Untitled Chat"
            recs = await client.query_messages(
                agent_id=agent.agent_id, order="asc", limit=3
            )
            if len(recs) > 2:
                try:
                    content = recs[1].data.get("content", "")
                    if isinstance(content, list):
                        title = "".join(
                            b.get("text", "")
                            for b in content
                            if b.get("type") == "text"
                        )[:50]
                    else:
                        title = str(content)[:50]
                    if not title:
                        title = "Untitled Chat"
                except (AttributeError, TypeError):
                    title = "Untitled Chat"

            result.append(
                {
                    "cwd": cwd,
                    "session_id": agent.session_id,
                    "agent_id": agent.agent_id,
                    "title": title,
                    "updated_at": agent.created_at,
                }
            )
        return result
    finally:
        await client.close()


def get_coolname() -> str:
    """Generate a memorable slug"""
    return generate_slug(4)


async def lookup_or_create_prompt(
    template: str,
    name: str,
    memory_path: str = DEFAULT_MEMORY_PATH,
) -> str:
    """
    Lookup existing prompt by template content, or create new one if not found.
    """
    client = MemoryClient(memory_path)
    try:
        return await client.lookup_or_create_prompt(template, name)
    finally:
        await client.close()


class AgentSession:
    """
    Manages conversation state and persistence via an in-process sqlite db.

    agent_id = "{session_id}-{agent_idx}-{fork_idx}" is the key.
    session_id is derived for ACP upstream routing only.
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        agent_idx: int = 0,
        memory_path: str = DEFAULT_MEMORY_PATH,
        cwd: str = "/tmp",
        fork_idx: int = 1,
        forked_at: str | None = None,
    ):
        self.agent_id = agent_id
        self.session_id = session_id
        self.agent_idx = agent_idx
        self.fork_idx = fork_idx
        self.forked_at = forked_at
        self.memory_path = memory_path
        self.cwd = cwd
        self.messages: list[dict] = []
        self._client = None
        self.model_identifier = None

    @property
    def client(self) -> MemoryClient:
        """Lazy-load the memory client."""
        if self._client is None:
            self._client = MemoryClient(self.memory_path)
        return self._client

    async def add_message(self, msg: dict, usage: dict | None = None):
        """
        Add message to in-memory list AND persist to the service.

        Args:
            msg: Full message dict (role, content, tool_calls, etc.)
            usage: Token usage dict with prompt_tokens, completion_tokens, total_tokens
        """
        self.messages.append(msg)
        await self.client.add_message(self.agent_id, msg, usage)

    async def add_tool_response(
        self,
        tool_results: list[dict],
        logger: Logger,
    ):
        for tool_result in tool_results:
            logger.info(f"TOOL RESULT: {tool_result}")
            await self.add_message(tool_result)

    async def add_assistant_response(
        self,
        thinking: list[str],
        content: list[str],
        tool_call_inputs: list[dict],
        logger: Logger,
        usage: dict | None = None,
    ):
        """
        Handle complex react message building + tool calls + results.

        Args:
            thinking: List of thinking tokens
            content: List of content tokens
            tool_call_inputs: Tool calls from assistant
            logger: Logger instance
            usage: Token usage dict with prompt_tokens, completion_tokens, total_tokens
        """
        # Build react message
        if len(content) > 0 or len(tool_call_inputs) > 0 or len(thinking) > 0:
            thinking_text = "".join(thinking) if thinking else ""
            content_text = "".join(content) if content else ""
            msg = {"role": "assistant", "content": content_text}
            if thinking_text and thinking_text != "":
                msg["reasoning_content"] = thinking_text
            if tool_call_inputs:
                msg["tool_calls"] = tool_call_inputs

            logger.info(f"Adding message: {msg}")
            logger.info(f"Message usage: {usage}")
            # Add to database/list
            await self.add_message(msg, usage)

    async def _save_messages(self, messages: list[dict]):
        """Batch save messages to the service."""
        await self.client.save_messages(self.agent_id, messages)

    @classmethod
    async def create(
        cls,
        prompt_id: str,
        prompt_args: dict[str, Any],
        tool_definitions: list[dict],
        request_params: dict[str, Any],
        model_identifier: str,
        memory_path: str = DEFAULT_MEMORY_PATH,
        cwd: str = "/tmp",
        agent_idx: int = 1,
        fork_idx: int = 1,
        forked_at: str | None = None,
        session_id: str | None = None,
        initial_messages: list[dict[str, Any]] | None = None,
    ) -> "AgentSession":
        """Factory method to create a new agent session."""
        client = MemoryClient(memory_path)

        # Load and render prompt
        try:
            prompt = await client.get_prompt(prompt_id)
        except MemoryServiceError as e:
            if e.status == 404:
                raise ValueError(f"Prompt '{prompt_id}' not found") from e
            raise

        system_prompt = render_template(prompt.template, **prompt_args)
        if session_id is None:
            session_id = get_coolname()
        agent_id = build_agent_id(session_id, agent_idx, fork_idx)

        # Create agent record
        await client.create_agent(
            agent_id=agent_id,
            session_id=session_id,
            agent_idx=agent_idx,
            fork_idx=fork_idx,
            forked_at=forked_at,
            cwd=cwd,
            prompt_id=prompt_id,
            prompt_args=prompt_args,
            system_prompt=system_prompt,
            tool_definitions=tool_definitions,
            request_params=request_params,
            model_identifier=model_identifier,
        )
        await client.close()

        # Build session instance
        session = cls(
            agent_id,
            session_id,
            agent_idx,
            memory_path,
            cwd=cwd,
            fork_idx=fork_idx,
            forked_at=forked_at,
        )
        session.model_identifier = model_identifier
        session.tools = tool_definitions
        session.request_params = request_params
        session.prompt_id = prompt_id
        session.prompt_args = prompt_args

        # Start with system message
        session.messages = [{"role": "system", "content": system_prompt}]
        await session._save_messages(session.messages)

        # Add initial messages if provided
        if initial_messages:
            for msg in initial_messages:
                if msg.get("role") != "system":  # Skip system messages
                    await session.add_message(msg)

        return session

    @classmethod
    async def get_max_agent_idx(
        cls,
        session_id: str,
        memory_path: str = DEFAULT_MEMORY_PATH,
        fork_idx: int | None = 1,
    ) -> int:
        """Return the highest agent_idx for a given session_id.

        fork_idx=1 (default) follows the trunk; None scans all forks.
        """
        client = MemoryClient(memory_path)
        try:
            return await client.get_max_agent_idx(session_id, fork_idx=fork_idx)
        finally:
            await client.close()

    @classmethod
    async def list_sessions(
        cls,
        limit: int = 50,
        offset: int = 0,
        memory_path: str = DEFAULT_MEMORY_PATH,
    ) -> list[dict]:
        """List sessions ordered by most-recent message activity (desc)."""
        client = MemoryClient(memory_path)
        try:
            return await client.list_sessions(limit=limit, offset=offset)
        finally:
            await client.close()

    @classmethod
    async def load(
        cls,
        agent_id: str,
        memory_path: str = DEFAULT_MEMORY_PATH,
    ) -> "AgentSession":
        """Factory method to load existing agent session from the service."""
        client = MemoryClient(memory_path)
        try:
            agent, messages = await client.load(agent_id, hydrate=True)
        except MemoryServiceError as e:
            if e.status == 404:
                raise ValueError(f"Agent '{agent_id}' not found") from e
            raise
        finally:
            await client.close()

        session = cls(
            agent_id=agent.agent_id,
            session_id=agent.session_id,
            agent_idx=agent.agent_idx,
            memory_path=memory_path,
            cwd=agent.cwd,
            fork_idx=agent.fork_idx,
            forked_at=agent.forked_at,
        )
        session.model_identifier = agent.model_identifier
        session.tools = agent.tool_definitions
        session.request_params = agent.request_params
        session.prompt_id = agent.prompt_id
        session.prompt_args = agent.prompt_args
        session.messages = messages

        return session

    async def close(self):
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.close()
        self._client = None


def _parse_frontmatter(text: str) -> dict | None:
    """Parse a leading YAML frontmatter block (between ``---`` markers).

    Returns the parsed mapping, or None when there is no frontmatter, it is
    unterminated, it is not valid YAML, or it is not a mapping. Uses PyYAML —
    already a project dependency (see configure.py / cli/main.py) — so
    multi-line descriptions, arbitrary indentation, comments, and extra keys
    are all handled for free instead of by a hand-rolled parser.
    """
    if not text.startswith("---"):
        return None
    try:
        end = text.index("---", 3)
        data = yaml.safe_load(text[3:end])
    except (ValueError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def get_skills(skills_dir: Path) -> list[dict]:
    """Scan skills dir, parse SKILL.md frontmatter, return structured skills.

    Returns a list of ``{"name", "description", "path"}`` dicts so prompt
    templates can iterate over skills with Jinja (``{% for skill in skills %}``)
    instead of rendering a pre-baked catalog string. ``path`` is the absolute
    path to the skill's SKILL.md so the agent can read it on demand.
    """
    if not skills_dir.exists():
        return []
    skills = []
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            text = skill_md.read_text()
        except OSError:
            continue
        meta = _parse_frontmatter(text)
        if not meta:
            continue
        name = meta.get("name")
        description = meta.get("description")
        if name and description:
            skills.append(
                {
                    "name": str(name).strip(),
                    "description": str(description).strip(),
                    "path": str(skill_md),
                }
            )
    return skills


def _read_agents_file(directory: str) -> str | None:
    """Read AGENTS.typ (preferred) or AGENTS.md from a directory.

    Returns None when neither exists, so callers can decide whether to include
    a section rather than emitting a placeholder.
    """
    for name in ("AGENTS.typ", "AGENTS.md"):
        path = os.path.join(directory, name)
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
    return None


def build_display_tree(cwd: str, skills_dir: str | Path | None = None) -> str:
    """Build the directory-tree context block shown to an agent.

    Every agent sees the two shared workspaces — ``~/.agents/notes`` and
    ``~/.agents/skills`` — because the edit tool no longer sandboxes to cwd, so
    any agent can read and edit them. Agents working inside a real project also
    get their own cwd tree. The notes agent (cwd == $HOME) is the exception: it
    skips the cwd tree, since treeing $HOME is dominated by logs, the db, and
    VSCode-extension noise.
    """
    home = str(Path.home())
    notes_dir = str(NOTES_DIR)
    skills_dir = str(skills_dir or SKILLS_DIR)
    trees = [get_directory_tree(notes_dir), get_directory_tree(skills_dir)]
    if os.path.realpath(cwd) != os.path.realpath(home):
        trees.append(get_directory_tree(cwd))
    # Drop any tree that failed to generate (get_directory_tree returns "" in
    # that case) so we don't emit stray blank sections.
    return "\n\n".join(t for t in trees if t)


def build_agents_content(cwd: str) -> str:
    """Build the persistent-memory (AGENTS.md) context block for a session.

    Two memory files are in play:

    * the **global** one at ``~/.agents/AGENTS.md`` — cross-cutting rules
      that carry across every agent, and
    * the **local** one at ``<cwd>/AGENTS.md`` — project-specific knowledge.

    At ``cwd == $HOME`` there is no separate local file (``~/AGENTS.md`` never
    exists — that is all the kicker is for), so only the global memory loads.
    Anywhere else, the global memory loads first and the cwd's own AGENTS.md is
    appended when present.
    """
    home = str(Path.home())
    parts = []
    global_agents = _read_agents_file(str(AGENTS_DIR))
    if global_agents:
        parts.append(global_agents)
    if os.path.realpath(cwd) != os.path.realpath(home):
        local_agents = _read_agents_file(cwd)
        if local_agents:
            parts.append(local_agents)
    return "\n\n".join(parts) if parts else "No AGENTS.md found"


async def make_agent_session(
    config: Config,
    tools: list[dict],
    model_id: str,
    cwd: str,
    session_id: str | None = None,
    agent_idx: int | None = None,
    fork_idx: int = 1,
    forked_at: str | None = None,
):
    if config.system_prompt_path:
        template = config.system_prompt_path.read_text()
    else:
        template = config.system_prompt
    prompt_id = await lookup_or_create_prompt(
        template, name="crow-default", memory_path=config.db_uri
    )
    skills = get_skills(Path(config.skills_dir))

    # Context blocks: the directory tree (notes + skills, plus cwd unless cwd
    # is $HOME) and the persistent-memory AGENTS.md (global, plus the cwd's own
    # when cwd is not $HOME). See build_display_tree / build_agents_content.
    display_tree = build_display_tree(cwd, config.skills_dir)
    agents_content = build_agents_content(cwd)
    if session_id is None:
        session_id = get_coolname()
    if agent_idx is None:
        agent_idx = 1
    return await AgentSession.create(
        prompt_id=prompt_id,
        prompt_args={
            "workspace": cwd,
            "display_tree": display_tree,
            "agents_content": agents_content,
            "session_id": session_id,
            "skills": skills,
            "skills_dir": config.skills_dir,
        },
        tool_definitions=tools,
        request_params={"temperature": 0.2},
        model_identifier=model_id,
        memory_path=config.db_uri,
        cwd=cwd,
        agent_idx=agent_idx,
        fork_idx=fork_idx,
        forked_at=forked_at,
        session_id=session_id,
    )
