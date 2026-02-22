import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# load_dotenv()


def get_config_dir() -> Path:
    """Get the configuration directory path (~/.crow)."""
    config_dir = Path.home() / ".crow"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_default_mcp_config(use_local: bool = True) -> dict[str, Any]:
    """Load default MCP server config, falling back to empty dict if missing."""
    config_dir = get_config_dir()
    mcp_file = config_dir / "mcp.json"

    if not mcp_file.exists():
        return {}

    with open(mcp_file, "r") as f:
        mcp_config = json.load(f)

    # Added safety check using .get() to prevent KeyErrors
    if use_local and "crow-mcp" in mcp_config.get("mcpServers", {}):
        path = Path(os.path.abspath(__file__))
        local_path = path.parent.parent.parent.parent / "crow-mcp"
        mcp_config["mcpServers"]["crow-mcp"]["args"][1] = str(local_path)

    return mcp_config


@dataclass
class LLModel:
    """Large Language Model"""

    model: str = field(default=None)
    provider: LLMProvider = field(default=None)


@dataclass
class LLMProvider:
    """LLM provider configuration."""

    # repr=False hides the key from logs, acting like Pydantic's SecretStr
    name: str = field(default=None)
    api_key: str = field(default=None, repr=False)
    base_url: str = field(default=None)


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    providers: dict[str, LLMProvider] = field(default_factory=dict)
    models: list[LLModel] = field(default_factory=list)


@dataclass
class Config:
    """Configuration for Crow Agent."""

    # Instance variables
    config_dir: Path = field(default_factory=get_config_dir)
    llm: LLMConfig = field(default_factory=LLMConfig)

    database_path: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_PATH", f"sqlite:///{get_config_dir() / 'crow.db'}"
        )
    )

    max_steps_per_turn: int = 100
    max_retries_per_step: int = 3
    mcp_servers: dict[str, Any] = field(default_factory=get_default_mcp_config)

    # Tool Constants
    TERMINAL_TOOL: str = field(default="crow-mcp_terminal", init=False)
    WRITE_TOOL: str = field(default="crow-mcp_write", init=False)
    READ_TOOL: str = field(default="crow-mcp_read", init=False)
    EDIT_TOOL: str = field(default="crow-mcp_edit", init=False)
    SEARCH_TOOL: str = field(default="crow-mcp_web_search", init=False)
    FETCH_TOOL: str = field(default="crow-mcp_web_fetch", init=False)

    # Logging constant
    LOG_PATH: str = field(default=f"{get_config_dir() / 'crow-acp.log'}")

    def get_builtin_mcp_config(self) -> dict[str, Any]:
        """Get the default MCP server configuration."""
        if not self.mcp_servers:
            return get_default_mcp_config()
        return self.mcp_servers


def get_default_config() -> Config:
    """Get default configuration from environment variables."""
    return Config(
        llm=LLMConfig(
            providers=[
                LLMProvider(
                    api_key=os.getenv("ZAI_API_KEY"), base_url=os.getenv("ZAI_BASE_URL")
                )
            ],
        )
    )


def load_toml_config() -> Config:
    """Load configuration from ~/.crow/config.toml and map it to dataclasses."""
    config_file = get_config_dir() / "config.toml"
    llm_config = LLMConfig()

    if not config_file.exists():
        # Fallback to default if no TOML exists (keeps your lower-level lib from crashing)
        print(config_file)
        return get_default_config()
    with open(config_file, "rb") as f:
        # tomllib requires reading the file in binary mode ("rb")
        toml_data = tomllib.load(f)

    # 1. Parse Providers
    providers_data = toml_data.get("providers", {})
    for prov_name, prov_info in providers_data.items():
        # Try to get API key from TOML, fallback to ENV vars based on provider name
        env_key_name = f"{prov_name.split(':')[-1].upper()}_API_KEY"
        api_key = prov_info.get("api_key") or os.getenv(env_key_name)

        llm_config.providers[prov_name] = LLMProvider(
            name=prov_name,
            base_url=prov_info.get("base_url"),
            api_key=api_key,
        )

    # 2. Parse Models
    models_data = toml_data.get("models", {})
    for _, mod_info in models_data.items():
        llm_config.models.append(
            LLModel(
                provider=mod_info.get("provider", ""),
                model=mod_info.get("model", ""),
            )
        )

    return Config(llm=llm_config)


settings = load_toml_config()
