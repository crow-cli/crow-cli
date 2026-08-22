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

from crow_cli.agent.context import context_fetcher, uri_to_path
from crow_cli.config import Config


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
