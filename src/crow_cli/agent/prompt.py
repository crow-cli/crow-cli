"""
Template rendering and content normalization utilities.

Handles Jinja2 prompt templates and converts ACP content blocks
(text, image, resource_link) to OpenAI-compatible format.
"""

import base64
import mimetypes
from functools import lru_cache
from logging import Logger
from pathlib import Path

import httpx
from acp.schema import (
    AudioContentBlock,
    EmbeddedResourceContentBlock,
    ImageContentBlock,
    ResourceContentBlock,
    TextContentBlock,
)
from jinja2 import Environment, FileSystemLoader


from crow_cli.config import Config


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
