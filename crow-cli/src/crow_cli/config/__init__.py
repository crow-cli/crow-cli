"""crow_cli.config — configuration for crow-cli, shared by every layer.

Config/load/defaults/overrides live here (moved out of crow_cli/agent:
everybody's using it — agent, CLI client, MCP server, tests). The default
file templates (config.yaml, compose.yaml, system prompt, searxng) live in
crow_cli.config.default.
"""

from crow_cli.config.config import (
    AGENTS_DIR,
    DEFAULT_CONFIG_DIR,
    ENV_PATTERN,
    GLOBAL_AGENTS_MD,
    LLMConfig,
    LLModel,
    LLMProvider,
    MODALITY_VALUES,
    NOTES_DIR,
    OPTIONAL_SAMPLING_PARAMS,
    REASONING_EFFORT_VALUES,
    SKILLS_DIR,
    Config,
    apply_config_overrides,
    build_sampling_params,
    get_default_config_dir,
    max_compact_tokens_for,
    parse_model_number,
    parse_reasoning_effort,
    resolve_env_vars,
    sampling_params_for,
)

__all__ = [
    "AGENTS_DIR",
    "DEFAULT_CONFIG_DIR",
    "ENV_PATTERN",
    "GLOBAL_AGENTS_MD",
    "LLMConfig",
    "LLModel",
    "LLMProvider",
    "MODALITY_VALUES",
    "NOTES_DIR",
    "OPTIONAL_SAMPLING_PARAMS",
    "REASONING_EFFORT_VALUES",
    "SKILLS_DIR",
    "Config",
    "apply_config_overrides",
    "build_sampling_params",
    "get_default_config_dir",
    "max_compact_tokens_for",
    "parse_model_number",
    "parse_reasoning_effort",
    "resolve_env_vars",
    "sampling_params_for",
]
