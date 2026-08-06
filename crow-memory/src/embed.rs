//! Multivector embeddings (ColBERT text + ColQwen2 images) via ollama /api/embed.
//!
//! Configurable via `EmbedConfig` — no hardcoded hosts or model names.

pub const EMBED_DIM: usize = 128;

/// Embedding server configuration.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct EmbedConfig {
    /// Base URL of the embedding server (ollama-compatible).
    #[serde(default = "default_base_url")]
    pub base_url: String,
    /// Optional API key (sent as Bearer token).
    #[serde(default)]
    pub api_key: Option<String>,
    /// Model name for text embeddings (ColBERT multivector).
    #[serde(default = "default_text_model")]
    pub text_model: String,
    /// Model name for image embeddings (ColQwen2 multivector).
    #[serde(default = "default_image_model")]
    pub image_model: String,
}

fn default_base_url() -> String {
    "http://127.0.0.1:11392".into()
}
fn default_text_model() -> String {
    "hf.co/LiquidAI/LFM2.5-ColBERT-350M-GGUF:LFM2.5-ColBERT-350M-BF16.gguf".into()
}
fn default_image_model() -> String {
    "hf.co/odellus/colqwen2-v1.0-gguf:colqwen2-llm-f16.gguf".into()
}

impl Default for EmbedConfig {
    fn default() -> Self {
        Self {
            base_url: default_base_url(),
            api_key: None,
            text_model: default_text_model(),
            image_model: default_image_model(),
        }
    }
}

impl EmbedConfig {
    /// Load from environment variables (CROW_OLLAMA_HOST, CROW_TEXT_MODEL, etc.)
    /// with defaults. Used as fallback when no config file section exists.
    pub fn from_env() -> Self {
        Self {
            base_url: std::env::var("CROW_OLLAMA_HOST")
                .unwrap_or_else(|_| default_base_url()),
            api_key: std::env::var("CROW_EMBED_API_KEY").ok(),
            text_model: std::env::var("CROW_TEXT_MODEL")
                .unwrap_or_else(|_| default_text_model()),
            image_model: std::env::var("CROW_IMAGE_MODEL")
                .unwrap_or_else(|_| default_image_model()),
        }
    }

    pub fn client(&self) -> reqwest::Client {
        let mut builder = reqwest::Client::builder();
        if let Some(key) = &self.api_key {
            builder = builder.default_headers({
                let mut h = reqwest::header::HeaderMap::new();
                h.insert(
                    reqwest::header::AUTHORIZATION,
                    format!("Bearer {key}").parse().unwrap(),
                );
                h
            });
        }
        builder.build().unwrap_or_default()
    }

    /// Embed text via /api/embed with colbert=true.
    /// Returns Vec<Vec<f32>> (n_tokens x 128), or empty vec on failure.
    pub async fn embed_text(&self, client: &reqwest::Client, text: &str) -> Vec<Vec<f32>> {
        let body = serde_json::json!({
            "model": self.text_model,
            "input": if text.is_empty() { " " } else { text },
            "colbert": true,
        });
        match client
            .post(format!("{}/api/embed", self.base_url))
            .json(&body)
            .timeout(std::time::Duration::from_secs(120))
            .send()
            .await
        {
            Ok(resp) => match resp.json::<serde_json::Value>().await {
                Ok(data) => parse_colbert_response(&data),
                Err(e) => {
                    tracing::warn!("embed parse error: {e}");
                    Vec::new()
                }
            },
            Err(e) => {
                tracing::debug!("embed server unavailable: {e}");
                Vec::new()
            }
        }
    }

    /// Embed an image (base64 PNG/JPEG) via /api/embed with colbert=true.
    pub async fn embed_image(&self, client: &reqwest::Client, image_b64: &str) -> Vec<Vec<f32>> {
        let body = serde_json::json!({
            "model": self.image_model,
            "images": [image_b64],
            "colbert": true,
        });
        match client
            .post(format!("{}/api/embed", self.base_url))
            .json(&body)
            // CPU image embeds need warmup — generous timeout (12.3).
            .timeout(std::time::Duration::from_secs(300))
            .send()
            .await
        {
            Ok(resp) => match resp.json::<serde_json::Value>().await {
                Ok(data) => parse_colbert_response(&data),
                Err(e) => {
                    tracing::warn!("image embed parse error: {e}");
                    Vec::new()
                }
            },
            Err(e) => {
                tracing::debug!("embed server unavailable: {e}");
                Vec::new()
            }
        }
    }
}

fn parse_colbert_response(data: &serde_json::Value) -> Vec<Vec<f32>> {
    if let Some(col) = data.get("colbert_embeddings").and_then(|c| c.as_array()) {
        if let Some(first) = col.first().and_then(|f| f.as_array()) {
            return first
                .iter()
                .filter_map(|tok| {
                    tok.as_array().map(|dims| {
                        dims.iter()
                            .filter_map(|d| d.as_f64().map(|f| f as f32))
                            .collect()
                    })
                })
                .collect();
        }
    }
    tracing::warn!("no colbert_embeddings in response");
    Vec::new()
}

/// Extract text from a message dict for embedding.
pub fn text_for_embedding(msg: &serde_json::Value) -> String {
    let mut parts = Vec::new();
    if let Some(content) = msg.get("content") {
        if let Some(s) = content.as_str() {
            parts.push(s.to_string());
        } else if let Some(arr) = content.as_array() {
            for b in arr {
                if let Some(t) = b.get("type").and_then(|t| t.as_str()) {
                    match t {
                        "text" => {
                            if let Some(text) = b.get("text").and_then(|t| t.as_str()) {
                                parts.push(text.to_string());
                            }
                        }
                        "image" | "image_url" | "image_ref" => parts.push("[image]".into()),
                        _ => {}
                    }
                }
            }
        }
    }
    if let Some(rc) = msg.get("reasoning_content").and_then(|r| r.as_str()) {
        parts.push(rc.to_string());
    }
    if let Some(tcs) = msg.get("tool_calls").and_then(|t| t.as_array()) {
        for tc in tcs {
            if let Some(f) = tc.get("function") {
                let name = f.get("name").and_then(|n| n.as_str()).unwrap_or("");
                let args = f.get("arguments").and_then(|a| a.as_str()).unwrap_or("");
                parts.push(format!("{name}: {args}"));
            }
        }
    }
    let text = parts
        .iter()
        .filter(|p| !p.trim().is_empty())
        .cloned()
        .collect::<Vec<_>>()
        .join("\n");
    if text.is_empty() {
        format!(
            "[{}]",
            msg.get("role").and_then(|r| r.as_str()).unwrap_or("message")
        )
    } else {
        text
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn text_for_embedding_string_content() {
        let msg = serde_json::json!({"role": "user", "content": "hello world"});
        assert_eq!(text_for_embedding(&msg), "hello world");
    }

    #[test]
    fn text_for_embedding_array_content() {
        let msg = serde_json::json!({
            "role": "user",
            "content": [
                {"type": "text", "text": "part one"},
                {"type": "image_url", "image_url": {"url": "data:..."}},
                {"type": "text", "text": "part two"},
            ]
        });
        let text = text_for_embedding(&msg);
        assert!(text.contains("part one"));
        assert!(text.contains("[image]"));
        assert!(text.contains("part two"));
    }

    #[test]
    fn text_for_embedding_with_reasoning() {
        let msg = serde_json::json!({
            "role": "assistant",
            "content": "answer",
            "reasoning_content": "thinking about it"
        });
        let text = text_for_embedding(&msg);
        assert!(text.contains("answer"));
        assert!(text.contains("thinking about it"));
    }

    #[test]
    fn text_for_embedding_with_tool_calls() {
        let msg = serde_json::json!({
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "terminal", "arguments": "{\"command\": \"ls\"}"}}]
        });
        let text = text_for_embedding(&msg);
        assert!(text.contains("terminal"));
    }

    #[test]
    fn text_for_embedding_empty() {
        let msg = serde_json::json!({"role": "system"});
        assert_eq!(text_for_embedding(&msg), "[system]");
    }

    #[test]
    fn embed_config_default() {
        let cfg = EmbedConfig::default();
        assert!(cfg.base_url.contains("11392"));
        assert!(cfg.text_model.contains("ColBERT"));
        assert!(cfg.image_model.contains("colqwen"));
        assert!(cfg.api_key.is_none());
    }

    #[test]
    fn embed_config_deserialize() {
        let yaml = r#"
base_url: "http://gpu-box:11434"
api_key: "sk-test"
text_model: "my-colbert"
image_model: "my-colqwen"
"#;
        let cfg: EmbedConfig = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(cfg.base_url, "http://gpu-box:11434");
        assert_eq!(cfg.api_key.as_deref(), Some("sk-test"));
        assert_eq!(cfg.text_model, "my-colbert");
    }
}
