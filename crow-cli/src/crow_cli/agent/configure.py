"""
Configuration management for crow-cli.

Default config files are Python string constants imported from defaults.
On first access to ~/.agents/crow, defaults are written to disk if nothing exists.
The user's config.yaml is read from disk for actual runtime config.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from crow_memory import normalize_db_uri
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from crow_cli.agent.default import (
    COMPOSE_YAML,
    CONFIG_YAML,
    SEARXNG_SETTINGS_YML,
    SYSTEM_PROMPT,
)
from crow_cli.agent.logger import setup_logger

ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")

AGENTS_DIR = Path.home() / ".agents"
# Config lives under ~/.agents/crow; the shared workspaces (skills, notes,
# global AGENTS.md) are SIBLINGS of the config dir, directly under ~/.agents.
DEFAULT_CONFIG_DIR = AGENTS_DIR / "crow"
SKILLS_DIR = AGENTS_DIR / "skills"
NOTES_DIR = AGENTS_DIR / "notes"
GLOBAL_AGENTS_MD = AGENTS_DIR / "AGENTS.md"


def get_default_config_dir(config_dir: Path | str | None = None) -> Path:
    """Return the config directory. If config_dir is given, use it. Otherwise ~/.agents/crow."""
    if config_dir is None:
        return DEFAULT_CONFIG_DIR
    return Path(config_dir).resolve()


# All default files as (destination_relative_path, content_string)
_DEFAULT_FILES: dict[str, str] = {
    "config.yaml": CONFIG_YAML,
    "compose.yaml": COMPOSE_YAML,
    "prompts/system_prompt.jinja2": SYSTEM_PROMPT,
    "searxng/settings.yml": SEARXNG_SETTINGS_YML,
}


def _write_defaults_if_missing(config_dir: Path) -> None:
    """Write default config files to disk only if they don't already exist."""
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "logs").mkdir(exist_ok=True)

    for rel_path, content in _DEFAULT_FILES.items():
        target = config_dir / rel_path
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)


def resolve_env_vars(value: Any, missing: set[str] | None = None) -> Any:
    """Recursively replace ${VAR} with environment variable values.

    Unset variables expand to "" (parity with the Rust CLI), but their names
    are collected in `missing` so the caller can warn instead of failing later
    with an opaque provider error.
    """
    if isinstance(value, str):

        def _sub(m: re.Match) -> str:
            name = m.group(1)
            val = os.getenv(name)
            if val is None:
                if missing is not None:
                    missing.add(name)
                return ""
            return val

        return ENV_PATTERN.sub(_sub, value)
    elif isinstance(value, dict):
        return {k: resolve_env_vars(v, missing) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_env_vars(v, missing) for v in value]
    return value


# OpenAI reasoning models (gpt-5, o3, ...) accept `reasoning_effort` instead
# of `temperature`. These are the enumerable values from the OpenAI API
# reference (developers.openai.com): none, minimal, low, medium, high, xhigh,
# max. We validate config.yaml against this set so a typo fails fast at load
# time instead of as an opaque provider 400 mid-turn.
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
REASONING_EFFORT_VALUES = ("none", "minimal", "low", "medium", "high", "xhigh", "max")

# Per-model modality LIST — what the model can take as input. Default
# ["text", "image"] = assume vision-capable until proven otherwise; a
# text-only model gets ["text"]. audio/video are filled in by hand (or by a
# probe) for models that natively take them (qwen3.x-max takes video).
Modality = Literal["text", "image", "audio", "video"]
MODALITY_VALUES = ("text", "image", "audio", "video")


class ReasoningEffortModel(BaseModel):
    """Validate a reasoning_effort value against OpenAI's enumerable set."""

    reasoning_effort: ReasoningEffort


def parse_reasoning_effort(raw: Any) -> str:
    """Validate and normalize a config.yaml reasoning_effort value.

    Raises ValueError naming the valid set when the value is not enumerable.
    """
    value = str(raw).strip().lower()
    try:
        return ReasoningEffortModel(reasoning_effort=value).reasoning_effort
    except ValidationError:
        raise ValueError(
            f"reasoning_effort must be one of {', '.join(REASONING_EFFORT_VALUES)}, "
            f"got {raw!r}"
        ) from None


# Optional per-model sampling pass-through keys and their types. Absent key
# = None = omitted from the request; explicit 0 / 0.0 values ARE sent.
OPTIONAL_SAMPLING_PARAMS = (
    ("top_p", float),
    ("top_k", int),
    ("min_p", float),
    ("presence_penalty", float),
    ("repetition_penalty", float),
)


def parse_sampling_number(model_name: str, key: str, raw: Any) -> float | int:
    """Coerce a config.yaml sampling value to its number type, failing fast
    with a message naming the model and key instead of a bare cast error."""
    cast = dict(OPTIONAL_SAMPLING_PARAMS)[key]
    if isinstance(raw, bool):  # YAML true/false would sneak through int()/float()
        raise ValueError(f"model {model_name!r}: {key} must be a number, got {raw!r}")
    try:
        return cast(raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"model {model_name!r}: {key} must be a number, got {raw!r}"
        ) from None


def build_sampling_params(
    reasoning_effort: str | None,
    temperature: float,
    top_p: float | None = None,
    top_k: int | None = None,
    min_p: float | None = None,
    presence_penalty: float | None = None,
    repetition_penalty: float | None = None,
) -> dict[str, Any]:
    """The one sampling rule for every LLM call (react loop AND compaction):
    reasoning_effort when set — ALL other sampling params omitted, reasoning
    models reject them — else temperature plus any optional params the model
    config set (None = omit, so explicit 0 / 0.0 values ARE sent). top_k,
    min_p and repetition_penalty are non-standard OpenAI fields and are
    packed into extra_body for pass-through to compatible servers."""
    if reasoning_effort:
        return {"reasoning_effort": reasoning_effort}
    params: dict[str, Any] = {"temperature": temperature}
    if top_p is not None:
        params["top_p"] = top_p
    if presence_penalty is not None:
        params["presence_penalty"] = presence_penalty
    extra_body = {
        name: value
        for name, value in (
            ("top_k", top_k),
            ("min_p", min_p),
            ("repetition_penalty", repetition_penalty),
        )
        if value is not None
    }
    if extra_body:
        params["extra_body"] = extra_body
    return params


def sampling_params_for(config: "Config", model_id: str) -> dict[str, Any]:
    """Per-model sampling rule for every LLM call (react loop AND compaction):
    the configured model's reasoning_effort XOR temperature (+ optional
    top_p / top_k / min_p / presence_penalty / repetition_penalty). Models
    not in config get the defaults (temperature 0.6, no effort)."""
    model = next(
        (m for m in config.llm.models.values() if m.model_id == model_id), None
    )
    if model is None:
        return {"temperature": 0.6}
    return build_sampling_params(
        model.reasoning_effort,
        model.temperature,
        top_p=model.top_p,
        top_k=model.top_k,
        min_p=model.min_p,
        presence_penalty=model.presence_penalty,
        repetition_penalty=model.repetition_penalty,
    )


@dataclass
class LLMProvider:
    name: str
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)


@dataclass
class LLModel:
    name: str
    provider_name: str
    model_id: str
    # Per-model sampling, XOR: reasoning_effort wins and ALL other sampling
    # params are omitted entirely (reasoning models reject them); else
    # temperature plus any of the optional knobs below that are set.
    temperature: float = 0.6
    reasoning_effort: ReasoningEffort | None = None
    # Optional sampling pass-through (None = omit). top_p / presence_penalty
    # are standard OpenAI fields; top_k / min_p / repetition_penalty are not
    # and are sent via extra_body to OpenAI-compatible servers.
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    presence_penalty: float | None = None
    repetition_penalty: float | None = None
    # Input modalities. Assume vision-capable until proven otherwise;
    # ["text"] models get image/audio/video blocks stripped / routed around
    # (see model_routing).
    modality: list[Modality] = field(default_factory=lambda: ["text", "image"])
    # Ordered fallback chain (model NAMES from this config) used when this
    # model cannot handle the modalities present in the conversation.
    fallbacks: list[str] = field(default_factory=list)


@dataclass
class LLMConfig:
    providers: dict[str, LLMProvider] = field(default_factory=dict)
    models: dict[str, LLModel] = field(default_factory=dict)


@dataclass
class Config:
    config_dir: Path
    llm: LLMConfig = field(default_factory=LLMConfig)
    db_uri: str = ""
    skills_dir: str = str(SKILLS_DIR)
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    max_retries_per_step: int = 3
    MAX_COMPACT_TOKENS: int = 190000
    MAX_TOKENS: int = 38192
    chunk_log: bool = False  # Write every raw chunk to JSONL for debugging
    system_prompt: str = SYSTEM_PROMPT
    system_prompt_path: Path | None = None
    @property
    def log_path(self) -> str:
        return str(self.config_dir / "logs" / "crow-cli.log")

    def get_builtin_mcp_config(self) -> dict[str, Any]:
        """Return MCP config dict in FastMCP format."""
        cfg = {"mcpServers": dict(self.mcp_servers or {})}
        return cfg

    @property
    def is_configured(self) -> bool:
        """Check if the config has at least one LLM provider and model."""
        return bool(self.llm.providers and self.llm.models)

    @classmethod
    def load(cls, config_dir: Path | None = None) -> "Config":
        target_dir = get_default_config_dir(config_dir)
        _logger = setup_logger(target_dir / "logs" / "crow-cli.log")

        # Write defaults if nothing exists yet
        if not (target_dir / "config.yaml").exists():
            _write_defaults_if_missing(target_dir)

        # Load .env
        env_file = target_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)



        # If no config.yaml, return a bare Config
        config_file = target_dir / "config.yaml"
        if not config_file.exists():
            _logger.info("No config.yaml found, returning bare Config")
            return cls(
                config_dir=target_dir,
                db_uri=f"sqlite:///{DEFAULT_CONFIG_DIR / 'crow.db'}",
            )

        with open(config_file) as f:
            raw = yaml.safe_load(f) or {}

        # Sampling is per-model now (see LLModel) — a leftover global would be
        # silently ignored, so reject it with a migration hint instead.
        for stale in ("TEMPERATURE", "reasoning_effort"):
            if stale in raw:
                raise ValueError(
                    f"config.yaml: global {stale!r} was removed; set it per "
                    f"model under models: (temperature / reasoning_effort)."
                )

        _logger.info("RAW config.yaml mcpServers: %s", raw.get("mcpServers", {}))
        missing_vars: set[str] = set()
        parsed = resolve_env_vars(raw, missing_vars)
        _logger.info("PARSED config.yaml mcpServers after resolve_env_vars: %s", parsed.get("mcpServers", {}))
        if missing_vars:
            _logger.warning(
                "config.yaml references unset environment variables (expanded to empty): %s",
                ", ".join(f"${{{v}}}" for v in sorted(missing_vars)),
            )

        # Parse providers
        llm = LLMConfig()
        for name, data in parsed.get("providers", {}).items():
            llm.providers[name] = LLMProvider(
                name=name,
                api_key=data.get("api_key"),
                base_url=data.get("base_url"),
            )

        # Parse models
        for name, data in parsed.get("models", {}).items():
            raw_effort = data.get("reasoning_effort")
            raw_modality = data.get("modality", ["text", "image"])
            if isinstance(raw_modality, str):
                raw_modality = [raw_modality]
            if not isinstance(raw_modality, list):
                raise ValueError(
                    f"model {name!r}: modality must be a list, got {raw_modality!r}"
                )
            modality = [str(m).strip().lower() for m in raw_modality]
            bad = [m for m in modality if m not in MODALITY_VALUES]
            if bad:
                raise ValueError(
                    f"model {name!r}: modality entries must be one of "
                    f"{', '.join(MODALITY_VALUES)}, got {bad}"
                )
            llm.models[name] = LLModel(
                name=name,
                provider_name=data.get("provider", ""),
                model_id=data.get("model", ""),
                temperature=float(data.get("temperature", 0.6)),
                reasoning_effort=(
                    parse_reasoning_effort(raw_effort)
                    if raw_effort is not None
                    else None
                ),
                # Optional sampling pass-through; absent key = None = omit
                # (0 / 0.0 are valid values and must survive).
                **{
                    key: parse_sampling_number(name, key, data[key])
                    for key, _ in OPTIONAL_SAMPLING_PARAMS
                    if data.get(key) is not None
                },
                modality=modality,
                fallbacks=list(data.get("fallbacks") or []),
            )

        # Parse overrides. db_uri is the canonical key; legacy memory_path
        # (a plain path) still works and becomes a sqlite URI. Default is
        # config_dir-relative so custom config dirs stay self-contained.
        db_uri = normalize_db_uri(
            parsed.get("db_uri") or parsed.get("memory_path") or str(target_dir / "crow.db")
        )
        skills_dir = os.path.expanduser(parsed.get("skills_dir") or str(SKILLS_DIR))
        overrides = {}
        for key, typ in (
            ("max_retries_per_step", int),
            ("MAX_COMPACT_TOKENS", int),
            ("MAX_TOKENS", int),
        ):
            if key in parsed:
                overrides[key] = typ(parsed[key])
        if "chunk_log" in parsed:
            overrides["chunk_log"] = bool(parsed["chunk_log"])

        mcp_servers = parsed.get("mcpServers", {})
        _logger.info("FINAL mcp_servers stored in Config: %s", mcp_servers)
        system_prompt_path = None
        if "system_prompt_path" in parsed:
            system_prompt_path = Path(os.path.expanduser(parsed["system_prompt_path"]))

        return cls(
            config_dir=target_dir,
            llm=llm,
            db_uri=db_uri,
            skills_dir=skills_dir,
            mcp_servers=mcp_servers,
            system_prompt_path=system_prompt_path,
            **overrides,
        )
