"""
Prompt construction: templates, context blocks, and content normalization.

Owns everything that goes *into* a prompt — the Jinja2 templates, the context
blocks assembled from the filesystem (skills catalog, AGENTS.md rule files, the
directory tree), and converting ACP content blocks (text, image,
resource_link) to OpenAI-compatible format. Session lifecycle lives in
``session.py``; this module never touches the database.
"""

import base64
import itertools
import logging
import mimetypes
from collections.abc import Iterable
from functools import lru_cache
from logging import Logger
from pathlib import Path

import httpx
import yaml
from acp.schema import (
    AudioContentBlock,
    EmbeddedResourceContentBlock,
    ImageContentBlock,
    ResourceContentBlock,
    TextContentBlock,
)
from jinja2 import Environment, FileSystemLoader


from crow_cli.config import AGENTS_DIR, Config


import json
import os
import re
from logging import Logger
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from directory_tree import DisplayTree


def maximal_deserialize(data):
    """
    Recursively drills into dictionaries and lists,
    deserializing any JSON strings it finds until
    no more strings can be converted to objects.
    """
    # 1. If it's a string, try to decode it
    if isinstance(data, str):
        try:
            # We strip it to avoid trying to load plain numbers/bools
            # as JSON if they are just "1" or "true"
            if data.startswith(("{", "[")):
                decoded = json.loads(data)
                # If it successfully decoded, recurse on the result
                # (to handle nested-serialized strings)
                return maximal_deserialize(decoded)
        except json.JSONDecodeError, TypeError, ValueError:
            # Not valid JSON, return the original string
            pass
        return data

    # 2. If it's a dictionary, recurse on its values
    elif isinstance(data, dict):
        return {k: maximal_deserialize(v) for k, v in data.items()}

    # 3. If it's a list, recurse on its elements
    elif isinstance(data, list):
        return [maximal_deserialize(item) for item in data]

    # 4. Return anything else as-is (int, float, bool, None)
    return data


def number_lines(content: str) -> list[str]:
    return [f"{k:6}\t{line}" for k, line in enumerate(content.split("\n"))]


def context_fetcher(uri: str, logger: Logging) -> str:

    res = find_line_numbers(uri)
    if res["status"] == "success":
        # pull out everything before the #L
        file_uri = uri.split("#L")[0]
        file_path = uri_to_path(file_uri)
        with open(file_path, "r") as f:
            content = f.read()
        split_content = number_lines(content)
        start = res["start"]
        end = res["end"]
        if start is not None and end is not None:
            content = split_content[start - 1 : end]
        elif start is not None:
            content = split_content[start - 1 :]
        elif end is not None:
            content = split_content[:end]
        else:
            content = split_content
    else:  # no line numbers, read whole file
        file_path = uri_to_path(uri)
        with open(file_path, "r") as f:
            content = f.read()
        content = number_lines(content)

    return "\n".join([file_path] + content)


def uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    return url2pathname(parsed.path)


def find_line_numbers(uri: str) -> dict[str, Any]:
    pattern = r"#L(\d+)?(?::(\d+))?$"
    match = re.search(pattern, uri)
    response = {}
    if match:
        start, end = match.groups()
        response["status"] = "success"
        response["start"] = int(start) if start else None
        response["end"] = int(end) if end else None
    else:
        response["status"] = "failure"
        response["start"] = None
        response["end"] = None
    return response


def get_directory_tree(cwd: str) -> str:
    """Returns a string representation of the directory tree rooted at cwd.

    Always returns a string. If the tree cannot be generated (e.g. a
    permission-denied or missing directory), DisplayTree returns None; we
    coerce that to an empty string so the ``-> str`` contract holds and callers
    never have to handle None.
    """
    ignores = ["node_modules", "*.egg_info", "__pycache__", ".venv", "refs"]
    tree = DisplayTree(stringRep=True, dirPath=cwd, ignoreList=ignores, maxDepth=3.0)
    return tree or ""


def build_display_tree(cwd: str) -> str:
    """Build the directory-tree context block shown to an agent.

    Renders exactly one tree, rooted at cwd — even when cwd is $HOME. Mixing
    the shared ``~/.agents`` workspaces into the tree made models join cwd to
    entries that live elsewhere, producing 404 paths; skills stay discoverable
    through the SKILLS catalog block instead. Returns ``""`` when the tree
    cannot be generated, keeping the ``-> str`` contract.
    """
    return get_directory_tree(cwd)


# ---------------------------------------------------------------------------
# Prompt context — rule files (AGENTS.md) and the skills catalog
# ---------------------------------------------------------------------------

#: A rule file is dumped in full up to this many lines. Longer files are demoted
#: to the progressive-disclosure list instead of being cut: a rule list that
#: stops mid-entry is worse than one the agent has to open.
AGENTS_FULL_LINES = 200

#: Lines of preview shown for a progressively disclosed rule file.
AGENTS_PREVIEW_LINES = 5

#: Hidden directories never descended into while looking for skills or rules.
_SCAN_SKIP = frozenset(
    {".git", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".hg", ".svn"}
)


def _parse_frontmatter(text: str) -> dict | None:
    """Parse a leading YAML frontmatter block (between ``---`` markers).

    Returns the parsed mapping, or None when there is no frontmatter, it is
    unterminated, it is not valid YAML, or it is not a mapping. Uses PyYAML —
    already a project dependency — so multi-line descriptions, arbitrary
    indentation, comments, and extra keys are handled for free instead of by a
    hand-rolled parser.
    """
    if not text.startswith("---"):
        return None
    try:
        end = text.index("---", 3)
        data = yaml.safe_load(text[3:end])
    except (ValueError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def _git_root(start: Path) -> Path | None:
    """The nearest enclosing directory holding a ``.git``, or None."""
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    return None


def _ancestors(cwd: Path) -> list[Path]:
    """``cwd`` up to the git root inclusive, nearest first.

    Outside a repository this is just ``[cwd]``: walking an arbitrary directory
    chain to ``/`` looking for other people's rule files would pull in whatever
    happens to sit above the workspace.
    """
    root = _git_root(cwd)
    out = [cwd]
    if root is None or root == cwd:
        return out
    for d in cwd.parents:
        out.append(d)
        if d == root:
            break
    return out


def _hidden_dirs(directory: Path) -> list[Path]:
    """Subdirectories of ``directory`` whose names start with a dot."""
    try:
        entries = sorted(
            (p for p in directory.iterdir() if p.name.startswith(".") and p.is_dir()),
            key=lambda p: p.name,
        )
    except OSError:
        return []
    return [p for p in entries if p.name not in _SCAN_SKIP]


def skill_roots(cwd: str, skills_dir: str) -> list[Path]:
    """Ordered skill roots — project scopes first, the user scope last.

    Every hidden directory from ``cwd`` up to the git root that holds a
    ``skills/`` dir is a root (``<project>/.agents/skills``, and whatever else a
    team has filed its skills under), so a repo carries its own skills and they
    travel with it. The user-level ``skills_dir`` comes last, which is what lets
    a project skill shadow a personal one by name.
    """
    roots: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: Path) -> None:
        key = candidate.resolve()
        if key not in seen:
            seen.add(key)
            roots.append(candidate)

    for directory in _ancestors(Path(cwd)):
        for hidden in _hidden_dirs(directory):
            root = hidden / "skills"
            if root.is_dir():
                add(root)
    user = Path(skills_dir).expanduser()
    if user.is_dir():
        add(user)
    return roots


def get_skills(roots: Path | Iterable[Path]) -> list[dict]:
    """Scan skill roots, parse SKILL.md frontmatter, return structured skills.

    Returns ``{"name", "description", "path"}`` dicts so prompt templates can
    iterate with Jinja (``{% for skill in skills %}``) instead of rendering a
    pre-baked catalog string; ``path`` is absolute so the agent can read the
    body on demand.

    Earlier roots win a name collision — that is how ``<project>/.agents/skills``
    overrides ``~/.agents/skills`` — and a shadowed skill is logged rather than
    silently dropped. A root holding a single skills dir behaves exactly like the
    old single-directory scan.
    """
    if isinstance(roots, Path):
        roots = [roots]
    found: dict[str, dict] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for skill_dir in sorted(root.iterdir(), key=lambda p: p.name):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
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
            if not name or not description:
                continue
            name = str(name).strip()
            skill = {
                "name": name,
                "description": str(description).strip(),
                "path": str(skill_md),
            }
            shadowed = found.get(name)
            if shadowed:
                logging.getLogger(__name__).warning(
                    "Skill %r at %s shadows %s", name, skill["path"], shadowed["path"]
                )
                continue
            found[name] = skill
    return list(found.values())


def build_agents_context(cwd: str) -> dict[str, list[dict]]:
    """Split discovered rule files into fully loaded and progressively disclosed.

    Two files are dumped in full (up to :data:`AGENTS_FULL_LINES`): the global
    ``~/.agents/AGENTS.md`` and the workspace's own ``<cwd>/AGENTS.md`` — the two
    the agent is expected to be operating under. Everything else found between
    ``cwd`` and the git root, including rule files inside hidden client dirs and
    per-package files in a monorepo, is returned as a catalog of location plus
    :data:`AGENTS_PREVIEW_LINES` lines so the agent opens only what the task
    needs. A file longer than the cap is demoted to that catalog rather than
    truncated mid-rule.

    Returns ``{"full": [{"path", "content"}], "catalog": [{"path", "preview"}]}``.
    """
    cwd_path = Path(cwd)

    def read_lines(path: Path, limit: int) -> list[str]:
        try:
            with open(path, "r") as f:
                return list(itertools.islice(f, limit))
        except OSError:
            return []

    full: list[dict] = []
    catalog: list[dict] = []
    seen: set[Path] = set()

    def take(path: Path, *, full_ok: bool) -> None:
        """Add one rule file: in full when allowed and short enough, else preview."""
        key = path.resolve()
        if key in seen or not path.is_file():
            return
        seen.add(key)
        if full_ok:
            lines = read_lines(path, AGENTS_FULL_LINES + 1)
            if 0 < len(lines) <= AGENTS_FULL_LINES:
                body = "".join(lines).strip()
                if body:
                    full.append({"path": str(path), "content": body})
                return
            # Over the cap: demote to the catalog rather than cut a rule mid-list.
        preview = "".join(read_lines(path, AGENTS_PREVIEW_LINES)).strip()
        if preview:
            catalog.append({"path": str(path), "preview": preview})

    take(AGENTS_DIR / "AGENTS.md", full_ok=True)
    take(cwd_path / "AGENTS.md", full_ok=True)

    for directory in _ancestors(cwd_path):
        candidates = [directory / "AGENTS.md", *(h / "AGENTS.md" for h in _hidden_dirs(directory))]
        for candidate in candidates:
            take(candidate, full_ok=False)

    if not full and not catalog:
        full.append({"path": "", "content": "No AGENTS.md found"})
    return {"full": full, "catalog": catalog}


def get_attr(block, name, default=""):
    return (
        block.get(name, default)
        if isinstance(block, dict)
        else getattr(block, name, default)
    )


@lru_cache(maxsize=64)
def get_jinja_env() -> Environment:
    """Cached Jinja environment for template rendering"""
    # Use FileSystemLoader to support {% include %} directives
    prompts_dir = Path(__file__).parent / "prompts"
    return Environment(
        loader=FileSystemLoader(prompts_dir),
        autoescape=False,
    )


def render_template(template_str: str, **args) -> str:
    """
    Render a Jinja2 template string with args.

    Args:
        template_str: Jinja2 template content
        **args: Template variables

    Returns:
        Rendered template string
    """
    env = get_jinja_env()
    template = env.from_string(template_str)
    return template.render(**args).strip()


async def normalize_prompt(
    prompt: list[
        TextContentBlock
        | ImageContentBlock
        | AudioContentBlock
        | ResourceContentBlock
        | EmbeddedResourceContentBlock
    ],
    logger: Logger,
) -> list[dict]:

    # Build user message content (supports text, images, and resource links)
    user_content = []
    for block in prompt:
        _type = get_attr(block, "type")
        if _type == "text":
            text = get_attr(block, "text")
            # Skip empty text blocks - API requires non-empty text
            if text:
                user_content.append({"type": "text", "text": text})
        elif _type == "resource":
            resource = get_attr(block, "resource")
            uri = get_attr(resource, "uri")
            text = get_attr(resource, "text")
            text = f"file_location:{uri}\n{text}"
            # Skip empty text blocks - API requires non-empty text
            if text:
                user_content.append({"type": "text", "text": text})
        elif _type == "image":
            # Handle ACP image content block
            # ACP format: {"type": "image", "mimeType": "image/png", "data": "base64..."}
            # or with uri: {"type": "image", "mimeType": "image/png", "uri": "..."}
            # OpenAI format: {"type": "image_url", "image_url": {"url": "data:...base64..."}}
            mime_type = get_attr(block, "mimeType")
            data = get_attr(block, "data")
            uri = get_attr(block, "uri")

            # Build the image_url value (base64 data URL required for llama.cpp)
            if data:
                # Already base64-encoded - use as-is
                if not mime_type:
                    mime_type = "image/png"  # Default fallback
                image_url_value = f"data:{mime_type};base64,{data}"
            elif uri:
                # Fetch and encode the image from URI
                try:
                    if uri.startswith("file://"):
                        # Read local file
                        file_path = uri_to_path(uri)
                        with open(file_path, "rb") as f:
                            image_bytes = f.read()
                    elif uri.startswith(("http://", "https://")):
                        # Fetch from URL
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(uri)
                            image_bytes = resp.content
                    else:
                        logger.warning(f"Unsupported URI scheme: {uri}")
                        continue

                    # Detect mime type if not provided
                    if not mime_type:
                        mime_type = mimetypes.guess_type(uri)[0] or "image/png"

                    # Base64 encode
                    data = base64.b64encode(image_bytes).decode("utf-8")
                    image_url_value = f"data:{mime_type};base64,{data}"
                except Exception as e:
                    logger.error(f"Failed to fetch image from URI {uri}: {e}")
                    continue
            else:
                logger.warning(f"Image block missing data or uri: {block}")
                continue

            # OpenAI expects this format:
            # {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
            user_content.append(
                {"type": "image_url", "image_url": {"url": image_url_value}}
            )

        elif _type == "resource_link":
            uri = get_attr(block, "uri")
            logger.info(f"resource uri: {uri}")
            fetched = context_fetcher(uri, logger)
            # Skip empty text blocks - API requires non-empty text
            if fetched:
                user_content.append({"type": "text", "text": fetched})

    return user_content


def normalize_blocks(content):
    normalized_blocks = []
    for block in content:
        if isinstance(block, str):
            # Old format: just a string
            normalized_blocks.append({"type": "text", "text": block})
        elif isinstance(block, dict):
            # Already in correct format, keep as-is
            if block.get("type") == "text" and not block.get("text", "").strip():
                continue
            normalized_blocks.append(block)
    return normalized_blocks
