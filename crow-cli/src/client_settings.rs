//! Client settings: `~/.agents/crow/client_settings.yaml`.
//!
//! Zed-style declaration of agent servers and named conductor chains:
//!
//! ```yaml
//! default: crow
//! agent_servers:
//!   crow:
//!     command: crow-cli
//!     args: [acp]
//!     default_config_options:
//!       model: qwen3.8-max-preview
//! chains:
//!   verifier:
//!     components: [crow-verifier, crow]   # last component is the agent
//! ```

use std::collections::HashMap;
use std::path::Path;

use indexmap::IndexMap;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AgentServerConfig {
    /// Server kind (`custom`, `registry`, ...) — informational for now.
    #[serde(rename = "type", skip_serializing_if = "Option::is_none")]
    pub kind: Option<String>,
    pub command: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub args: Vec<String>,
    #[serde(default, skip_serializing_if = "HashMap::is_empty")]
    pub env: HashMap<String, String>,
    #[serde(default, skip_serializing_if = "ConfigOptions::is_empty")]
    pub default_config_options: ConfigOptions,
    /// TCP port when this entry is a daemon (`crow-cli daemon start`); used
    /// for the startup health check and `status`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub port: Option<u16>,
    /// Daemons (other agent_servers entries) that must be up before this
    /// server is used; `crow-cli run` auto-starts them.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub requires: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize, Default)]
pub struct ConfigOptions {
    /// Model to select for this server via `NewSessionRequest._meta.model`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
}

impl ConfigOptions {
    pub fn is_empty(&self) -> bool {
        self.model.is_none()
    }
}

/// A named conductor proxy chain. Components are agent-server names or raw
/// command strings; the final component must be the agent.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ChainConfig {
    pub components: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize, Default)]
pub struct ClientSettings {
    /// Default agent server / chain for bare `crow-cli run`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub default: Option<String>,
    #[serde(default, skip_serializing_if = "IndexMap::is_empty")]
    pub agent_servers: IndexMap<String, AgentServerConfig>,
    #[serde(default, skip_serializing_if = "IndexMap::is_empty")]
    pub chains: IndexMap<String, ChainConfig>,
}

/// The resolved config directory (flag value or ~/.agents/crow).
pub fn config_dir_path(config_dir: Option<&Path>) -> anyhow::Result<std::path::PathBuf> {
    match config_dir {
        Some(d) => Ok(d.to_path_buf()),
        None => Ok(dirs::home_dir()
            .ok_or_else(|| anyhow::anyhow!("no home dir"))?
            .join(".agents/crow")),
    }
}

impl ClientSettings {
    /// Load `{config_dir}/client_settings.yaml`. Missing file → empty settings.
    pub fn load(config_dir: Option<&Path>) -> anyhow::Result<Self> {
        let dir = config_dir_path(config_dir)?;
        let path = dir.join("client_settings.yaml");
        if !path.exists() {
            return Ok(Self::default());
        }
        let text = std::fs::read_to_string(&path)?;
        let settings: Self = serde_yaml::from_str(&text)
            .map_err(|e| anyhow::anyhow!("{}: {e}", path.display()))?;
        Ok(settings)
    }

    /// Write back to `{config_dir}/client_settings.yaml`. Note: yaml
    /// comments do NOT survive a round trip — used today only to persist
    /// generated entries (e.g. the built-in ollama-mv declaration).
    pub fn save(&self, config_dir: &Path) -> anyhow::Result<()> {
        let path = config_dir.join("client_settings.yaml");
        std::fs::write(&path, serde_yaml::to_string(self)?)?;
        Ok(())
    }

    pub fn contains(&self, name: &str) -> bool {
        self.chains.contains_key(name) || self.agent_servers.contains_key(name)
    }

    /// Build the ACP agent command for a server entry (JSON form understood
    /// by `AcpAgent::from_str`: command + args + env).
    pub fn server_command(cfg: &AgentServerConfig) -> String {
        serde_json::json!({
            "command": cfg.command,
            "args": cfg.args,
            "env": cfg.env,
        })
        .to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_client_settings() {
        let yaml = r#"
default: crow
agent_servers:
  crow:
    command: crow-cli
    args: [acp]
    env:
      RUST_LOG: info
    default_config_options:
      model: qwen3.8-max-preview
  proxy:
    type: custom
    command: crow-verifier
chains:
  verifier:
    components: [proxy, crow]
"#;
        let s: ClientSettings = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(s.default.as_deref(), Some("crow"));
        let crow = &s.agent_servers["crow"];
        assert_eq!(crow.command, "crow-cli");
        assert_eq!(crow.args, vec!["acp"]);
        assert_eq!(crow.env["RUST_LOG"], "info");
        assert_eq!(crow.default_config_options.model.as_deref(), Some("qwen3.8-max-preview"));
        assert_eq!(s.agent_servers["proxy"].kind.as_deref(), Some("custom"));
        assert_eq!(s.chains["verifier"].components, vec!["proxy", "crow"]);
        assert!(s.contains("crow"));
        assert!(s.contains("verifier"));
        assert!(!s.contains("nope"));
    }
}
