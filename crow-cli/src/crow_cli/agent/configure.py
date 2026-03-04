import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Regex to find ${VAR_NAME} in strings
ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")

CROW_DIR = ".crow"


def get_default_config_dir() -> Path:
    config_dir = Path.home() / CROW_DIR
    config_src = Path(__file__).parents[3]
    if not os.path.exists(config_dir):
        shutil.copytree(config_src, config_dir)
        log_dir = config_dir / "logs"
        log_dir.mkdir(exist_ok=True, parents=True)
        log_file = log_dir / "crow-cli.log"
        log_file.touch()
    return config_dir


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
    # supports_vision: bool = False
    """Whether this model supports vision/image inputs"""


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
    db_uri: str = ""
    mcp_servers: dict[str, Any] = field(default_factory=dict)

    max_steps_per_turn: int = 100
    max_retries_per_step: int = 3

    # Tool Constants
    TERMINAL_TOOL: str = "terminal"
    WRITE_TOOL: str = "write"
    READ_TOOL: str = "read"
    EDIT_TOOL: str = "edit"
    SEARCH_TOOL: str = "web_search"
    FETCH_TOOL: str = "web_fetch"

    # Compaction parameters
    MAX_COMPACT_TOKENS: int = 120000
    N_STEPS_BACK_COMPACT: int = 8

    @property
    def log_path(self) -> str:
        """Dynamic property so log_path updates if config_dir changes."""
        return str(self.config_dir / "logs" / "crow-cli.log")

    def get_builtin_mcp_config(self) -> dict[str, Any]:
        """Return MCP config dict in FastMCP format.

        FastMCP expects: {"mcpServers": {<name>: {...}}}
        """
        mcp_servers: dict[str, Any] = dict(self.mcp_servers or {})

        # If the config references a non-existent local path, auto-correct.
        crow_mcp = mcp_servers.get("crow-mcp")
        if isinstance(crow_mcp, dict):
            args = crow_mcp.get("args")
            if isinstance(args, list) and "--project" in args:
                try:
                    idx = args.index("--project")
                except ValueError:
                    idx = -1
                if idx >= 0 and idx + 1 < len(args):
                    candidate = Path(args[idx + 1])
                    if not candidate.exists():
                        repo_root = Path(__file__).resolve().parents[4]
                        local_path = repo_root / "crow-mcp"
                        if local_path.exists():
                            args[idx + 1] = str(local_path)

        return {"mcpServers": mcp_servers}

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
            target_dir = get_default_config_dir()
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
            return cls(config_dir=target_dir, db_uri=db_fallback)

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
                # supports_vision=m_data.get("supports_vision", False),
            )

        # Database URI (fallback to sqlite in the config dir if not provided)
        db_uri = parsed_config.get("db_uri") or os.getenv(
            "DATABASE_PATH", f"sqlite:///{target_dir / 'crow.db'}"
        )

        # Handle common misconfig: sqlite:///Users/... (missing leading slash)
        if db_uri.startswith("sqlite:///") and not db_uri.startswith("sqlite:////"):
            path = db_uri[len("sqlite:///") :]
            root = path.split("/", 1)[0]
            if (
                path
                and not path.startswith("/")
                and root in {"Users", "var", "home", "tmp", "opt"}
            ):
                db_uri = "sqlite:////" + path

        # Collect overrides for fields that have defaults on the dataclass.
        # Any key in the YAML that matches a Config field name wins.
        _OVERRIDABLE = {
            "max_steps_per_turn": int,
            "max_retries_per_step": int,
            "TERMINAL_TOOL": str,
            "WRITE_TOOL": str,
            "READ_TOOL": str,
            "EDIT_TOOL": str,
            "SEARCH_TOOL": str,
            "FETCH_TOOL": str,
            "MAX_COMPACT_TOKENS": int,
            "N_STEPS_BACK_COMPACT": int,
        }
        overrides = {}
        for key, typ in _OVERRIDABLE.items():
            if key in parsed_config:
                overrides[key] = typ(parsed_config[key])

        return cls(
            config_dir=target_dir,
            llm=llm_config,
            mcp_servers=parsed_config.get("mcpServers", {}),
            db_uri=db_uri,
            **overrides,
        )
