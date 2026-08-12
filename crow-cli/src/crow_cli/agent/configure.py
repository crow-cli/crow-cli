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


def build_sampling_params(
    reasoning_effort: str | None,
    temperature: float,
) -> dict[str, Any]:
    """The one sampling rule for every LLM call (react loop AND compaction):
    reasoning_effort when set — temperature omitted, reasoning models reject
    it — else temperature. Never both, never neither (no provider defaults)."""
    return (
        {"reasoning_effort": reasoning_effort}
        if reasoning_effort
        else {"temperature": temperature}
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
    # None = unknown → assume capable of everything (permissive default).
    # A set restricts: e.g. set() is text-only, {"vision"} handles images.
    capabilities: set[str] | None = None
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
    memory_path: str = ""
    skills_dir: str = str(SKILLS_DIR)
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    max_retries_per_step: int = 3
    MAX_COMPACT_TOKENS: int = 190000
    MAX_TOKENS: int = 38192
    TEMPERATURE: float = 0.6
    # When set, sent to the LLM INSTEAD of temperature — reasoning models
    # (gpt-5, o3, ...) reject temperature. Validated against OpenAI's enum.
    reasoning_effort: ReasoningEffort | None = None
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
                memory_path=str(DEFAULT_CONFIG_DIR / "crow.db"),
            )

        with open(config_file) as f:
            raw = yaml.safe_load(f) or {}

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
            raw_caps = data.get("capabilities")
            capabilities = set(raw_caps) if raw_caps is not None else None
            llm.models[name] = LLModel(
                name=name,
                provider_name=data.get("provider", ""),
                model_id=data.get("model", ""),
                capabilities=capabilities,
                fallbacks=list(data.get("fallbacks") or []),
            )

        # Parse overrides
        memory_path = os.path.expanduser(parsed.get("memory_path") or "~/.agents/crow/crow.db")
        skills_dir = os.path.expanduser(parsed.get("skills_dir") or str(SKILLS_DIR))
        overrides = {}
        for key, typ in (
            ("max_retries_per_step", int),
            ("MAX_COMPACT_TOKENS", int),
            ("MAX_TOKENS", int),
            ("TEMPERATURE", float),
        ):
            if key in parsed:
                overrides[key] = typ(parsed[key])
        if "reasoning_effort" in parsed and parsed["reasoning_effort"] is not None:
            overrides["reasoning_effort"] = parse_reasoning_effort(
                parsed["reasoning_effort"]
            )
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
            memory_path=memory_path,
            skills_dir=skills_dir,
            mcp_servers=mcp_servers,
            system_prompt_path=system_prompt_path,
            **overrides,
        )
