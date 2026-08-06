//! Configuration loading from ~/.agents/crow/config.yaml + .env

use indexmap::IndexMap;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use serde::Deserialize;

/// Memory URL when config.yaml sets no explicit `memory_url`: honor
/// $CROW_MEMORY_PORT, then config `memory_port`, then the SDK default
/// (27697 — CROWS). One knob moves server + clients together.
fn memory_url_from_port(port: Option<u16>) -> String {
    let env_port = std::env::var("CROW_MEMORY_PORT")
        .ok()
        .and_then(|s| s.parse::<u16>().ok());
    match env_port.or(port) {
        Some(p) => format!("http://127.0.0.1:{p}"),
        None => crow_memory_sdk::default_memory_url(),
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProviderConfig {
    pub base_url: Option<String>,
    pub api_key: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ModelConfig {
    pub provider: String,
    pub model: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct McpServerConfig {
    #[allow(dead_code)]
    pub transport: Option<String>,
    pub command: Option<String>,
    pub args: Option<Vec<String>>,
    pub env: Option<HashMap<String, String>>,
}

#[derive(Debug, Clone, Deserialize)]
struct RawConfig {
    #[serde(default)]
    providers: IndexMap<String, ProviderConfig>,
    #[serde(default)]
    models: IndexMap<String, ModelConfig>,
    #[serde(default, rename = "mcpServers")]
    mcp_servers: IndexMap<String, McpServerConfig>,
    memory_url: Option<String>,
    memory_port: Option<u16>,
    /// System prompt template path (matches Python crow-cli convention). Relative → resolved against config_dir.
    /// Default: {config_dir}/prompts/system_prompt.hbs
    system_prompt_path: Option<String>,
    #[serde(default = "default_max_tokens")]
    #[serde(rename = "MAX_TOKENS")]
    max_tokens: u32,
    #[serde(default = "default_temperature")]
    #[serde(rename = "TEMPERATURE")]
    temperature: f32,
    #[serde(default = "default_max_compact_tokens")]
    #[serde(rename = "MAX_COMPACT_TOKENS")]
    max_compact_tokens: u32,
}

fn default_max_tokens() -> u32 { 38192 }
fn default_temperature() -> f32 { 0.6 }
fn default_max_compact_tokens() -> u32 { 190000 }

#[derive(Debug, Clone)]
pub struct Config {
    pub config_dir: PathBuf,
    /// Provider → env var name referenced by its api_key (`${VAR}`), before
    /// resolution. Advertised as ACP EnvVar auth methods.
    pub api_key_env_refs: IndexMap<String, String>,
    pub providers: IndexMap<String, ProviderConfig>,
    pub models: IndexMap<String, ModelConfig>,
    pub mcp_servers: IndexMap<String, McpServerConfig>,
    pub memory_url: String,
    pub max_tokens: u32,
    pub temperature: f32,
    pub max_compact_tokens: u32,
    pub system_prompt: String,
}

impl Config {
    pub fn is_configured(&self) -> bool {
        !self.providers.is_empty() && !self.models.is_empty()
    }

    /// The first model's provider + model id, for default selection.
    pub fn default_model(&self) -> Option<(&str, &ModelConfig)> {
        self.models.iter().next().map(|(k, v)| (k.as_str(), v))
    }

    /// Resolve a provider for a given model config.
    pub fn provider_for(&self, model: &ModelConfig) -> Option<&ProviderConfig> {
        self.providers.get(&model.provider)
    }

    pub fn load(
        config_dir: Option<&Path>,
        config_file: Option<&Path>,
    ) -> anyhow::Result<Self> {
        let config_dir = match config_dir {
            Some(d) => d.to_path_buf(),
            None => dirs::home_dir()
                .ok_or_else(|| anyhow::anyhow!("cannot determine home directory"))?
                .join(".agents/crow"),
        };

        // Load .env
        let env_file = config_dir.join(".env");
        if env_file.exists() {
            dotenvy::from_path(&env_file).ok();
        }

        let config_file_path = config_dir.join("config.yaml");
        if !config_file_path.exists() {
            return Ok(Self {
                config_dir,
                api_key_env_refs: IndexMap::new(),
                providers: IndexMap::new(),
                models: IndexMap::new(),
                mcp_servers: IndexMap::new(),
                memory_url: crow_memory_sdk::default_memory_url(),
                max_tokens: default_max_tokens(),
                temperature: default_temperature(),
                max_compact_tokens: default_max_compact_tokens(),
                system_prompt: String::new(),
            });
        }

        let raw_str = std::fs::read_to_string(&config_file_path)?;
        let raw: RawConfig = serde_yaml::from_str(&raw_str)?;

        // Resolve ${ENV_VAR} in provider configs
        let mut api_key_env_refs = IndexMap::new();
        let mut providers = raw
            .providers
            .into_iter()
            .map(|(name, mut p)| {
                if let Some(key) = &p.api_key {
                    if let Some(var) = env_ref(key) {
                        api_key_env_refs.insert(name.clone(), var);
                    }
                    p.api_key = Some(resolve_env(key));
                }
                if let Some(url) = &p.base_url {
                    p.base_url = Some(resolve_env(url));
                }
                (name, p)
            })
            .collect();

        let mut models = raw.models;
        let mut mcp_servers = raw.mcp_servers;
        let mut memory_url = raw.memory_url;
        let mut memory_port = raw.memory_port;
        let mut max_tokens = raw.max_tokens;
        let mut temperature = raw.temperature;
        let mut max_compact_tokens = raw.max_compact_tokens;
        let mut system_prompt_path = raw.system_prompt_path;

        // Apply --config-file overlay (takes precedence over config.yaml)
        if let Some(overlay_path) = config_file {
            if overlay_path.exists() {
                let overlay_str = std::fs::read_to_string(overlay_path)?;
                let overlay: serde_yaml::Value = serde_yaml::from_str(&overlay_str)?;
                if let Some(map) = overlay.as_mapping() {
                    if let Some(v) = map.get(&serde_yaml::Value::String("mcpServers".into())) {
                        if let Ok(servers) = serde_yaml::from_value::<IndexMap<String, McpServerConfig>>(v.clone()) {
                            mcp_servers = servers;
                        }
                    }
                    if let Some(v) = map.get(&serde_yaml::Value::String("memory_url".into())) {
                        if let Some(s) = v.as_str() {
                            memory_url = Some(s.to_string());
                        }
                    }
                    if let Some(v) = map.get(&serde_yaml::Value::String("memory_port".into())) {
                        if let Some(n) = v.as_u64() {
                            memory_port = Some(n as u16);
                        }
                    }
                    if let Some(v) = map.get(&serde_yaml::Value::String("MAX_TOKENS".into())) {
                        if let Some(n) = v.as_u64() {
                            max_tokens = n as u32;
                        }
                    }
                    if let Some(v) = map.get(&serde_yaml::Value::String("TEMPERATURE".into())) {
                        if let Some(f) = v.as_f64() {
                            temperature = f as f32;
                        }
                    }
                    if let Some(v) = map.get(&serde_yaml::Value::String("MAX_COMPACT_TOKENS".into())) {
                        if let Some(n) = v.as_u64() {
                            max_compact_tokens = n as u32;
                        }
                    }
                    if let Some(v) = map.get(&serde_yaml::Value::String("providers".into())) {
                        if let Ok(p) = serde_yaml::from_value::<IndexMap<String, ProviderConfig>>(v.clone()) {
                            api_key_env_refs.clear();
                            providers = p.into_iter()
                                .map(|(name, mut pc)| {
                                    if let Some(key) = &pc.api_key {
                                        if let Some(var) = env_ref(key) {
                                            api_key_env_refs.insert(name.clone(), var);
                                        }
                                        pc.api_key = Some(resolve_env(key));
                                    }
                                    if let Some(url) = &pc.base_url {
                                        pc.base_url = Some(resolve_env(url));
                                    }
                                    (name, pc)
                                })
                                .collect();
                        }
                    }
                    if let Some(v) = map.get(&serde_yaml::Value::String("models".into())) {
                        if let Ok(m) = serde_yaml::from_value::<IndexMap<String, ModelConfig>>(v.clone()) {
                            models = m;
                        }
                    }
                    if let Some(v) = map.get(&serde_yaml::Value::String("system_prompt_path".into())) {
                        if let Some(s) = v.as_str() {
                            system_prompt_path = Some(s.to_string());
                        }
                    }
                }
            }
        }

        // Explicit memory_url wins; otherwise derive from the port so the
        // server and clients never have to be wired by hand.
        let memory_url = memory_url.unwrap_or_else(|| memory_url_from_port(memory_port));

        // Load system prompt template
        let system_prompt = load_system_prompt(&config_dir, system_prompt_path.as_deref());

        Ok(Self {
            config_dir,
            api_key_env_refs,
            providers,
            models,
            mcp_servers,
            memory_url,
            max_tokens,
            temperature,
            max_compact_tokens,
            system_prompt,
        })
    }
}

/// The env var name when the string is exactly one `${VAR}` reference.
fn env_ref(s: &str) -> Option<String> {
    let inner = s.trim().strip_prefix("${")?.strip_suffix('}')?;
    if inner.is_empty() || inner.contains('$') || inner.contains('}') {
        return None;
    }
    Some(inner.to_string())
}

/// Replace ${VAR} patterns with environment variable values.
fn resolve_env(s: &str) -> String {
    let mut result = String::with_capacity(s.len());
    let mut rest = s;
    while let Some(start) = rest.find("${") {
        result.push_str(&rest[..start]);
        let after = &rest[start + 2..];
        if let Some(end) = after.find('}') {
            let var = &after[..end];
            result.push_str(&std::env::var(var).unwrap_or_default());
            rest = &after[end + 1..];
        } else {
            result.push_str("${");
            rest = after;
        }
    }
    result.push_str(rest);
    result
}

fn load_system_prompt(config_dir: &Path, custom: Option<&str>) -> String {
    let prompt_file = match custom {
        Some(p) => {
            let expanded = PathBuf::from(shellexpand::tilde(p).as_ref());
            // Relative paths resolve against the config dir
            if expanded.is_relative() {
                config_dir.join(expanded)
            } else {
                expanded
            }
        }
        None => config_dir.join("prompts/system_prompt.hbs"),
    };
    if prompt_file.exists() {
        std::fs::read_to_string(prompt_file).unwrap_or_default()
    } else {
        String::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_env_replaces() {
        unsafe { std::env::set_var("TEST_CROW_VAR", "secret123") };
        assert_eq!(resolve_env("${TEST_CROW_VAR}"), "secret123");
        assert_eq!(resolve_env("prefix-${TEST_CROW_VAR}-suffix"), "prefix-secret123-suffix");
    }

    #[test]
    fn resolve_env_missing_var() {
        assert_eq!(resolve_env("${NONEXISTENT_CROW_VAR_XYZ}"), "");
    }

    #[test]
    fn resolve_env_no_pattern() {
        assert_eq!(resolve_env("plain string"), "plain string");
    }

    #[test]
    fn load_from_real_config() {
        // Loads ~/.agents/crow/config.yaml — should have providers and models
        let config = Config::load(None, None).unwrap();
        assert!(config.is_configured(), "config should have providers+models");
        assert!(!config.providers.is_empty());
        assert!(!config.models.is_empty());
        assert!(config.max_tokens > 0);
        assert!(config.max_compact_tokens > 0);
    }
}
