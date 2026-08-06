//! LLM client — async-openai configured from crow config.

use async_openai_thinking::Client;
use async_openai_thinking::config::OpenAIConfig;

use crate::config::{Config, ModelConfig, ProviderConfig};

pub fn make_client(provider: &ProviderConfig) -> Client<OpenAIConfig> {
    let mut cfg = OpenAIConfig::new();
    if let Some(key) = &provider.api_key {
        cfg = cfg.with_api_key(key);
    }
    if let Some(url) = &provider.base_url {
        cfg = cfg.with_api_base(url);
    }
    Client::with_config(cfg)
}

/// `CROW_LLM_TRACE`: JSONL dump of OpenAI request/response pairs for CLI
/// development (12.5). Unset/empty = off; `1` = {config_dir}/logs/llm-trace.jsonl;
/// anything else = that path.
pub fn trace_path(config_dir: &std::path::Path) -> Option<std::path::PathBuf> {
    match std::env::var("CROW_LLM_TRACE").ok().filter(|v| !v.is_empty()) {
        None => None,
        Some(v) if v == "1" => Some(config_dir.join("logs").join("llm-trace.jsonl")),
        Some(v) => Some(std::path::PathBuf::from(v)),
    }
}

/// Append one JSONL record to the trace file.
pub fn trace_append(path: &std::path::Path, record: serde_json::Value) {
    use std::io::Write;
    let mut line = record.to_string();
    line.push('\n');
    match std::fs::OpenOptions::new().create(true).append(true).open(path) {
        Ok(mut f) => {
            let _ = f.write_all(line.as_bytes());
        }
        Err(e) => tracing::warn!("CROW_LLM_TRACE: cannot open {}: {e}", path.display()),
    }
}

pub fn resolve_model<'a>(
    config: &'a Config,
    model_name: Option<&str>,
) -> anyhow::Result<(&'a ModelConfig, &'a ProviderConfig)> {
    let (name, model) = match model_name {
        Some(n) => {
            // Friendly name first, then model id.
            if let Some(m) = config.models.get(n) {
                (n, m)
            } else if let Some((k, m)) = config.models.iter().find(|(_, m)| m.model == n) {
                (k.as_str(), m)
            } else {
                let available: Vec<&str> = config.models.keys().map(String::as_str).collect();
                anyhow::bail!("model '{n}' not found (available: {})", available.join(", "));
            }
        }
        None => config.default_model()
            .ok_or_else(|| anyhow::anyhow!("no models in config"))?,
    };

    let provider = config.provider_for(model)
        .ok_or_else(|| anyhow::anyhow!("provider '{}' not found for model '{}'", model.provider, name))?;

    Ok((model, provider))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> (tempfile::TempDir, Config) {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join("config.yaml"),
            r#"
providers:
  alibaba:
    base_url: https://example.com/v1
    api_key: fake
models:
  qwen3.8-max-preview:
    provider: alibaba
    model: qwen3.8-max-preview
  minimax:
    provider: alibaba
    model: MiniMax-M2.5
"#,
        )
        .unwrap();
        let cfg = Config::load(Some(dir.path()), None).unwrap();
        (dir, cfg)
    }

    #[test]
    fn resolve_by_friendly_name() {
        let (_d, cfg) = test_config();
        let (m, _) = resolve_model(&cfg, Some("minimax")).unwrap();
        assert_eq!(m.model, "MiniMax-M2.5");
    }

    #[test]
    fn resolve_by_model_id() {
        let (_d, cfg) = test_config();
        let (m, _) = resolve_model(&cfg, Some("MiniMax-M2.5")).unwrap();
        assert_eq!(m.model, "MiniMax-M2.5");
    }

    #[test]
    fn resolve_default_is_first_configured() {
        let (_d, cfg) = test_config();
        let (m, _) = resolve_model(&cfg, None).unwrap();
        assert_eq!(m.model, "qwen3.8-max-preview");
    }

    #[test]
    fn resolve_unknown_lists_available() {
        let (_d, cfg) = test_config();
        let msg = format!("{}", resolve_model(&cfg, Some("nope")).unwrap_err());
        assert!(msg.contains("qwen3.8-max-preview") && msg.contains("minimax"), "{msg}");
    }
}
