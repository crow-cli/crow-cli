import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Regex to find ${VAR_NAME} in strings
ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def resolve_env_vars(value: Any) -> Any:
    """Recursively traverse dictionaries/lists and replace ${VAR} with env variables."""
    if isinstance(value, str):

        def replace(match):
            env_var = match.group(1)
            # Return the env var, or original string if not found
            return os.getenv(env_var, "")

        return ENV_PATTERN.sub(replace, value)
    elif isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_env_vars(v) for v in value]
    return value


@dataclass
class LLMProvider:
    """LLM provider configuration."""

    name: str
    base_url: str | None = None
    # repr=False hides the key from logs
    api_key: str | None = field(default=None, repr=False)


@dataclass
class LLModel:
    """Large Language Model"""

    name: str
    provider_name: str
    model_id: str


@dataclass
class LLMConfig:
    """LLM configurations holding providers and models."""

    providers: dict[str, LLMProvider] = field(default_factory=dict)
    models: dict[str, LLModel] = field(default_factory=dict)


@dataclass
class Config:
    """Configuration for Crow Agent."""

    config_dir: Path
    llm: LLMConfig = field(default_factory=LLMConfig)
    database_path: str = ""
    mcp_servers: dict[str, Any] = field(default_factory=dict)

    max_steps_per_turn: int = 100
    max_retries_per_step: int = 3

    # Tool Constants
    TERMINAL_TOOL: str = field(default="crow-mcp_terminal", init=False)
    WRITE_TOOL: str = field(default="crow-mcp_write", init=False)
    READ_TOOL: str = field(default="crow-mcp_read", init=False)
    EDIT_TOOL: str = field(default="crow-mcp_edit", init=False)
    SEARCH_TOOL: str = field(default="crow-mcp_web_search", init=False)
    FETCH_TOOL: str = field(default="crow-mcp_web_fetch", init=False)

    # Compaction parameters
    MAX_COMPACT_TOKENS: int = field(default=120000, init=False)
    N_STEPS_BACK_COMPACT: int = field(default=8, init=False)

    @property
    def log_path(self) -> str:
        """Dynamic property so log_path updates if config_dir changes."""
        return str(self.config_dir / "logs" / "crow-acp.log")

    @classmethod
    def load(cls, config_dir: str | Path | None = None) -> "Config":
        """
        Factory method to initialize the configuration.
        1. Sets the target directory.
        2. Loads the .env file.
        3. Loads config.yaml and interpolates environment variables.
        4. Maps the YAML data to dataclasses.
        """
        if config_dir is None:
            target_dir = Path.home() / ".crow"
        else:
            target_dir = Path(config_dir)

        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Load environment variables from .env in the config directory
        env_file = target_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)

        yaml_file = target_dir / "config.yaml"
        if not yaml_file.exists():
            # Return a default config if no yaml exists yet
            db_fallback = os.getenv(
                "DATABASE_PATH", f"sqlite:///{target_dir / 'crow.db'}"
            )
            return cls(config_dir=target_dir, database_path=db_fallback)

        # 2. Load and parse YAML
        with open(yaml_file, "r") as f:
            raw_config = yaml.safe_load(f) or {}

        # 3. Interpolate ${ENV_VARS} recursively
        parsed_config = resolve_env_vars(raw_config)

        # 4. Map to Dataclasses
        llm_config = LLMConfig()

        # Parse Providers
        for p_name, p_data in parsed_config.get("providers", {}).items():
            llm_config.providers[p_name] = LLMProvider(
                name=p_name,
                api_key=p_data.get("api_key"),
                base_url=p_data.get("base_url"),
            )

        # Parse Models
        for m_name, m_data in parsed_config.get("models", {}).items():
            llm_config.models[m_name] = LLModel(
                name=m_name,
                provider_name=m_data.get("provider", ""),
                model_id=m_data.get("model", ""),
            )

        # Database URI (fallback to sqlite in the config dir if not provided)
        db_uri = parsed_config.get("db_uri") or os.getenv(
            "DATABASE_PATH", f"sqlite:///{target_dir / 'crow.db'}"
        )

        return cls(
            config_dir=target_dir,
            llm=llm_config,
            mcp_servers=parsed_config.get("mcpServers", {}),
            database_path=db_uri,
        )
