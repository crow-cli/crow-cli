"""Capability-aware model routing (carried v1 TODO item, now in scope).

Conversations carry modalities (images, audio) that not every model accepts.
Per request:

1. Requested model's capabilities unknown (unset in config) or covering the
   present modalities → use it unchanged.
2. Otherwise walk the model's `fallbacks` chain and take the first model
   capable of every present modality. The LLM client is bound to one
   provider, so only same-provider fallbacks are considered.
3. No capable model anywhere → keep the requested model and report which
   modalities to strip; send_request replaces those blocks with placeholders
   (auto-strip on downgrade) instead of hard-failing.
"""

from __future__ import annotations

import logging
from typing import Any

from crow_cli.agent.configure import Config

logger = logging.getLogger(__name__)

# OpenAI chat-completions content block type -> modality
BLOCK_MODALITIES: dict[str, str] = {
    "image_url": "vision",
    "image": "vision",
    "input_audio": "audio",
    "audio": "audio",
}

PLACEHOLDERS: dict[str, str] = {
    "vision": "[image omitted: model has no vision capability]",
    "audio": "[audio omitted: model has no audio capability]",
}


def modalities_in_messages(messages: list[dict[str, Any]]) -> set[str]:
    """Which modalities are present in normalized message content."""
    mods: set[str] = set()
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict):
                mod = BLOCK_MODALITIES.get(block.get("type", ""))
                if mod:
                    mods.add(mod)
    return mods


def _model_by_id(config: Config, model_id: str):
    return next(
        (m for m in config.llm.models.values() if m.model_id == model_id), None
    )


def _capable(model, modalities: set[str]) -> bool:
    # Unknown capabilities (None) = permissive: assume the model handles it.
    return model.capabilities is None or modalities <= model.capabilities


def route_model(
    config: Config, requested_model_id: str, modalities: set[str]
) -> tuple[str, set[str]]:
    """Return (model_id to use, modalities to strip) for this request."""
    if not modalities:
        return requested_model_id, set()

    requested = _model_by_id(config, requested_model_id)
    if requested is None or _capable(requested, modalities):
        return requested_model_id, set()

    for name in requested.fallbacks:
        cand = config.llm.models.get(name)
        if cand is None:
            logger.warning(
                "fallback model %r of %r not in config; skipping",
                name,
                requested.name,
            )
            continue
        if cand.provider_name != requested.provider_name:
            logger.info(
                "fallback %r is on provider %r (need %r); skipping",
                name,
                cand.provider_name,
                requested.provider_name,
            )
            continue
        if _capable(cand, modalities):
            logger.warning(
                "model %r lacks %s; falling back to %r",
                requested_model_id,
                sorted(modalities),
                cand.model_id,
            )
            return cand.model_id, set()

    logger.warning(
        "no capable fallback for %r; stripping %s blocks",
        requested_model_id,
        sorted(modalities),
    )
    return requested_model_id, modalities


def strip_unsupported_blocks(
    messages: list[dict[str, Any]], modalities: set[str]
) -> list[dict[str, Any]]:
    """Replace blocks of the given modalities with text placeholders,
    preserving position. Session history is never mutated."""
    if not modalities:
        return messages
    stripped: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            stripped.append(msg)
            continue
        new_blocks: list[dict[str, Any]] = []
        for block in content:
            mod = (
                BLOCK_MODALITIES.get(block.get("type", ""))
                if isinstance(block, dict)
                else None
            )
            if mod and mod in modalities:
                new_blocks.append({"type": "text", "text": PLACEHOLDERS[mod]})
            else:
                new_blocks.append(block)
        new_msg = dict(msg)
        new_msg["content"] = new_blocks
        stripped.append(new_msg)
    return stripped
