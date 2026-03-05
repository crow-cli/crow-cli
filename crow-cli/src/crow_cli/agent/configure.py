import os
import re
import shutil
from dataclasses import dataclass, field
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Regex to find ${VAR_NAME} in strings
ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")

CROW_DIR = ".crow"


def get_default_config_dir() -> Path:
    config_dir = Path.home() / CROW_DIR

    # 1. Base directory creation
    if not config_dir.exists():
        config_dir.mkdir(parents=True, exist_ok=True)

        # Grab the resource as a Traversable object
        config_src = files("crow_cli.agent.default")

        # as_file guarantees src_path is a real directory on disk
        with as_file(config_src) as src_path:
            shutil.copytree(src_path, config_dir, dirs_exist_ok=True)

    # 2. THE CRITICAL PART: Always ensure logs exist.
    # This is what stops the uvx crash.
    log_dir = config_dir / "logs"
    log_dir.mkdir(exist_ok=True, parents=True)

    log_file = log_dir / "crow-cli.log"
    if not log_file.exists():
        log_file.touch()

    return config_dir


def resolve_env_vars(value: Any) -> Any:
    """Recursively traverse dictionaries/lists and replace ${VAR} with env variables."""
    if isinstance(value, str):

        def replace(match):
            env_var = match.group(1)
            return os.getenv(env_var, "")

        return ENV_PATTERN.sub(replace, value)
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
        return str(self.config_dir / "logs" / "crow-cli.log")

    def get_builtin_mcp_config(self) -> dict[str, Any]:
        """Return MCP config dict in FastMCP format."""
        mcp_servers: dict[str, Any] = dict(self.mcp_servers or {})

        crow_mcp = mcp_servers.get("crow-mcp")
        if isinstance(crow_mcp, dict):
            args = crow_mcp.get("args")
            if isinstance(args, list) and "--project" in args:
                try:
                    idx = args.index("--project")
                    if idx + 1 < len(args):
                        candidate = Path(args[idx + 1])
                        if not candidate.exists():
                            repo_root = Path(__file__).resolve().parents[4]
                            local_path = repo_root / "crow-mcp"
                            if local_path.exists():
                                args[idx + 1] = str(local_path)
                except ValueError:
                    pass

        return {"mcpServers": mcp_servers}

    @classmethod
    def load(cls, config_dir: str | Path | None = None) -> "Config":
        if config_dir is None:
            target_dir = get_default_config_dir()
        else:
            target_dir = Path(config_dir)
            (target_dir / "logs").mkdir(parents=True, exist_ok=True)
            (target_dir / "logs" / "crow-cli.log").touch(exist_ok=True)

        target_dir.mkdir(parents=True, exist_ok=True)

        env_file = target_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)

        yaml_file = target_dir / "config.yaml"
        if not yaml_file.exists():
            db_fallback = os.getenv(
                "DATABASE_PATH", f"sqlite:///{target_dir / 'crow.db'}"
            )
            return cls(config_dir=target_dir, db_uri=db_fallback)

        with open(yaml_file, "r") as f:
            raw_config = yaml.safe_load(f) or {}

        parsed_config = resolve_env_vars(raw_config)
        llm_config = LLMConfig()

        for p_name, p_data in parsed_config.get("providers", {}).items():
            llm_config.providers[p_name] = LLMProvider(
                name=p_name,
                api_key=p_data.get("api_key"),
                base_url=p_data.get("base_url"),
            )

        for m_name, m_data in parsed_config.get("models", {}).items():
            llm_config.models[m_name] = LLModel(
                name=m_name,
                provider_name=m_data.get("provider", ""),
                model_id=m_data.get("model", ""),
            )

        db_uri = parsed_config.get("db_uri") or os.getenv(
            "DATABASE_PATH", f"sqlite:///{target_dir / 'crow.db'}"
        )

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
