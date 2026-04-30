"""
Configuration management for crow-cli.

Default config files are Python string constants imported from defaults.
On first access to ~/.crow, defaults are written to disk if nothing exists.
The user's config.yaml is read from disk for actual runtime config.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from crow_cli.agent.default import (
    COMPOSE_YAML,
    CONFIG_YAML,
    LITELLM_CONFIG_YAML,
    SEARXNG_SETTINGS_YML,
    SYSTEM_PROMPT,
)

ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")

CROW_DIR = Path.home() / ".crow"


def get_default_config_dir(config_dir: Path | str | None = None) -> Path:
    """Return the config directory. If config_dir is given, use it. Otherwise ~/.crow."""
    if config_dir is None:
        return CROW_DIR
    return Path(config_dir).resolve()


# All default files as (destination_relative_path, content_string)
_DEFAULT_FILES: dict[str, str] = {
    "config.yaml": CONFIG_YAML,
    "compose.yaml": COMPOSE_YAML,
    "litellm/config.yaml": LITELLM_CONFIG_YAML,
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


def resolve_env_vars(value: Any) -> Any:
    """Recursively replace ${VAR} with environment variable values."""
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda m: os.getenv(m.group(1), ""), value)
    elif isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_env_vars(v) for v in value]
    return value


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


@dataclass
class LLMConfig:
    providers: dict[str, LLMProvider] = field(default_factory=dict)
    models: dict[str, LLModel] = field(default_factory=dict)


@dataclass
class Config:
    config_dir: Path
    llm: LLMConfig = field(default_factory=LLMConfig)
    db_uri: str = ""
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    max_retries_per_step: int = 3
    MAX_COMPACT_TOKENS: int = 190000
    MAX_TOKENS: int = 38192

    @property
    def log_path(self) -> str:
        return str(self.config_dir / "logs" / "crow-cli.log")

    def get_builtin_mcp_config(self) -> dict[str, Any]:
        """Return MCP config dict in FastMCP format."""
        return {"mcpServers": dict(self.mcp_servers or {})}

    @property
    def is_configured(self) -> bool:
        """Check if the config has at least one LLM provider and model."""
        return bool(self.llm.providers and self.llm.models)

    @classmethod
    def load(cls, config_dir: Path | None = None) -> "Config":
        target_dir = get_default_config_dir(config_dir)

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
            return cls(
                config_dir=target_dir,
                db_uri=os.getenv("DATABASE_PATH", str(target_dir / "crow.db")),
            )

        with open(config_file) as f:
            raw = yaml.safe_load(f) or {}

        parsed = resolve_env_vars(raw)

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
            llm.models[name] = LLModel(
                name=name,
                provider_name=data.get("provider", ""),
                model_id=data.get("model", ""),
            )

        # Parse overrides
        db_uri = parsed.get("db_uri") or os.getenv(
            "DATABASE_PATH", str(target_dir / "crow.db")
        )
        overrides = {}
        for key, typ in (
            ("max_retries_per_step", int),
            ("MAX_COMPACT_TOKENS", int),
            ("MAX_TOKENS", int),
        ):
            if key in parsed:
                overrides[key] = typ(parsed[key])

        return cls(
            config_dir=target_dir,
            llm=llm,
            db_uri=db_uri,
            mcp_servers=parsed.get("mcpServers", {}),
            **overrides,
        )
