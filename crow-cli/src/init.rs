//! `crow-cli init` — configuration wizard. Port of crow-cli v1 `init_cmd.py`.
//!
//! Writes config.yaml, .env, prompts/system_prompt.hbs (and optionally the
//! SearXNG compose stack) into the config directory. Provider discovery
//! priority: `LLM_*_API_KEY` / `LLM_*_BASE_URL` env vars (with `-y`), else
//! interactive prompts.

use std::io::Write;
use std::path::Path;

use indexmap::IndexMap;
use serde::Serialize;

const SYSTEM_PROMPT: &str = include_str!("../assets/system_prompt.hbs");
const SEARXNG_SETTINGS_YML: &str = include_str!("../assets/searxng_settings.yml");
const CLIENT_SETTINGS_YAML: &str = include_str!("../assets/client_settings.yaml");

/// compose.yaml written when SearXNG is requested (faithful to v1: searxng
/// service only, volumes block preserved).
const COMPOSE_SEARXNG: &str = r#"services:
  searxng:
    image: searxng/searxng
    restart: always
    ports:
      - "${SEARXNG_PORT}:8080"
    environment:
      - BASE_URL=http://0.0.0.0:${SEARXNG_PORT}
      - INSTANCE_NAME=crow-index
    volumes:
      - ./searxng/:/etc/searxng
volumes:
  database_data:
    driver: local
"#;

#[derive(Serialize)]
struct McpEntry {
    transport: String,
    command: String,
    args: Vec<String>,
}

#[derive(Serialize)]
struct ProviderEntry {
    base_url: String,
    api_key: String,
}

#[derive(Serialize)]
struct ModelEntry {
    provider: String,
    model: String,
}

/// Key order matches the v1 config.yaml layout.
#[derive(Serialize)]
struct InitConfig {
    #[serde(rename = "mcpServers")]
    mcp_servers: IndexMap<String, McpEntry>,
    /// Memory server port (clients derive memory_url from it; set
    /// memory_url explicitly only to point at a remote server).
    memory_port: u16,
    providers: IndexMap<String, ProviderEntry>,
    models: IndexMap<String, ModelEntry>,
    #[serde(rename = "MAX_COMPACT_TOKENS")]
    max_compact_tokens: u32,
    max_retries_per_step: u32,
}

struct ModelInfo {
    id: String,
    owned_by: String,
}

/// `LLM_FOO_API_KEY` → `("foo", "LLM_FOO_BASE_URL")`.
fn provider_from_env_key(key: &str) -> Option<(String, String)> {
    let mid = key.strip_prefix("LLM_")?.strip_suffix("_API_KEY")?;
    if mid.is_empty() {
        return None;
    }
    let provider = mid.to_lowercase();
    Some((provider.clone(), format!("LLM_{}_BASE_URL", provider.to_uppercase())))
}

/// Parse a model selection: "all", "none", or comma-separated 1-based indices.
/// Out-of-range indices are dropped; garbage → None.
fn parse_selection(input: &str, count: usize) -> Option<Vec<usize>> {
    match input.trim().to_lowercase().as_str() {
        "all" => return Some((0..count).collect()),
        "none" => return Some(vec![]),
        _ => {}
    }
    let mut out = vec![];
    for part in input.split(',') {
        let part = part.trim();
        if part.is_empty() {
            continue;
        }
        let idx: usize = part.parse().ok()?;
        if idx >= 1 && idx <= count {
            out.push(idx - 1);
        }
    }
    Some(out)
}

/// Default friendly name: model id after the last '/'.
fn friendly_default(model_id: &str) -> &str {
    model_id.rsplit('/').next().unwrap_or(model_id)
}

/// Render the bundled client_settings.yaml asset: {{HOME}} → the home dir,
/// {{CONFIG_DIR}} → the config dir, {{DEFAULT_MODEL}} → the first configured
/// model (no models → the default_config_options blocks are dropped).
fn render_client_settings(config_dir: &Path, default_model: &str) -> anyhow::Result<String> {
    let home = dirs::home_dir()
        .ok_or_else(|| anyhow::anyhow!("cannot determine home directory"))?;
    let rendered = CLIENT_SETTINGS_YAML
        .replace("{{HOME}}", &home.display().to_string())
        .replace("{{CONFIG_DIR}}", &config_dir.display().to_string())
        .replace("{{DEFAULT_MODEL}}", default_model);
    if !default_model.is_empty() {
        return Ok(rendered);
    }
    Ok(rendered
        .lines()
        .filter(|l| {
            let t = l.trim();
            t != "default_config_options:" && !t.starts_with("model:")
        })
        .collect::<Vec<_>>()
        .join("\n")
        + "\n")
}

fn ask(label: &str) -> anyhow::Result<String> {
    print!("{label}: ");
    std::io::stdout().flush()?;
    let mut s = String::new();
    std::io::stdin().read_line(&mut s)?;
    Ok(s.trim().to_string())
}

fn ask_default(label: &str, default: &str) -> anyhow::Result<String> {
    let s = ask(&format!("{label} [{default}]"))?;
    Ok(if s.is_empty() { default.to_string() } else { s })
}

fn confirm(label: &str, default: bool) -> anyhow::Result<bool> {
    let hint = if default { "[Y/n]" } else { "[y/N]" };
    loop {
        match ask(&format!("{label} {hint}"))?.to_lowercase().as_str() {
            "" => return Ok(default),
            "y" | "yes" => return Ok(true),
            "n" | "no" => return Ok(false),
            _ => {}
        }
    }
}

/// Fetch the model list from an OpenAI-compatible `/models` endpoint.
/// Warns and returns empty on any failure (wizard must survive offline).
async fn fetch_models(base_url: &str, api_key: &str) -> Vec<ModelInfo> {
    let url = format!("{}/models", base_url.trim_end_matches('/'));
    let resp = match reqwest::Client::new()
        .get(&url)
        .bearer_auth(api_key)
        .timeout(std::time::Duration::from_secs(30))
        .send()
        .await
    {
        Ok(r) => r,
        Err(e) => {
            eprintln!("Warning: could not fetch models from {url}: {e}");
            return vec![];
        }
    };
    if !resp.status().is_success() {
        eprintln!("Warning: {} from {url}", resp.status());
        return vec![];
    }
    let data: serde_json::Value = match resp.json().await {
        Ok(v) => v,
        Err(e) => {
            eprintln!("Warning: could not parse models from {url}: {e}");
            return vec![];
        }
    };
    let mut models: Vec<ModelInfo> = data
        .get("data")
        .and_then(|d| d.as_array())
        .map(|arr| {
            arr.iter()
                .map(|m| ModelInfo {
                    id: m
                        .get("id")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown")
                        .to_string(),
                    owned_by: m
                        .get("owned_by")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown")
                        .to_string(),
                })
                .collect()
        })
        .unwrap_or_default();
    models.sort_by(|a, b| a.id.cmp(&b.id));
    models
}

/// Interactive model picker. Returns (friendly_name, model_id) pairs.
fn select_models(models: &[ModelInfo]) -> anyhow::Result<Vec<(String, String)>> {
    if models.is_empty() {
        println!("No models available. You can add them manually later.");
        return Ok(vec![]);
    }
    println!("\nFound {} models. Select which ones to add:", models.len());
    for (i, m) in models.iter().enumerate() {
        println!("  {:>3}. {} ({})", i + 1, m.id, m.owned_by);
    }
    println!("\nEnter model numbers to add (comma-separated, e.g. 1,3,5) or 'all' or 'none':");
    let sel = ask_default("Models", "all")?;
    let indices = match parse_selection(&sel, models.len()) {
        Some(v) => v,
        None => {
            println!("Invalid selection");
            return Ok(vec![]);
        }
    };
    let mut selected = vec![];
    for idx in indices {
        let id = &models[idx].id;
        let friendly = ask_default(&format!("  Friendly name for {id}"), friendly_default(id))?;
        selected.push((friendly, id.clone()));
    }
    Ok(selected)
}

/// Run the initialization wizard.
pub async fn run(config_dir: Option<&Path>, yes: bool) -> anyhow::Result<()> {
    let config_dir = match config_dir {
        Some(d) => d.to_path_buf(),
        None => dirs::home_dir()
            .ok_or_else(|| anyhow::anyhow!("cannot determine home directory"))?
            .join(".agents/crow"),
    };

    println!("🪶 Crow CLI Setup\n");
    println!("This will create your configuration in {}", config_dir.display());

    let config_file = config_dir.join("config.yaml");
    let env_file = config_dir.join(".env");
    if config_file.exists() && !yes
        && !confirm(&format!("{} already exists. Overwrite?", config_file.display()), false)?
    {
        anyhow::bail!("Aborted.");
    }

    let mut providers: IndexMap<String, ProviderEntry> = IndexMap::new();
    let mut models: IndexMap<String, ModelEntry> = IndexMap::new();
    let mut env_vars: IndexMap<String, String> = IndexMap::new();

    // ── Step 1: LLM providers ──────────────────────────────────────────────
    println!("\n═══ Step 1: LLM Providers ═══\n");
    if yes {
        println!("→ --yes mode: checking env vars for providers...");
        for (key, value) in std::env::vars() {
            let Some((provider, base_url_key)) = provider_from_env_key(&key) else {
                continue;
            };
            let base_url = std::env::var(&base_url_key).unwrap_or_default();
            if base_url.is_empty() || value.is_empty() {
                continue;
            }
            println!("  ✓ Found provider: {provider} from env vars");
            providers.insert(
                provider.clone(),
                ProviderEntry {
                    base_url: base_url.clone(),
                    api_key: format!("${{{key}}}"),
                },
            );
            env_vars.insert(key, value.clone());
            for m in fetch_models(&base_url, &value).await {
                models.insert(
                    m.id.clone(),
                    ModelEntry {
                        provider: provider.clone(),
                        model: m.id,
                    },
                );
            }
        }
        if providers.is_empty() {
            println!(
                "  No providers found in env vars. \
                 Add LLM_<PROVIDER>_API_KEY + LLM_<PROVIDER>_BASE_URL."
            );
        }
    } else {
        loop {
            println!("--- Add a provider ---");
            let name = loop {
                let s = ask("Provider name (e.g., openai, anthropic, openrouter)")?;
                if !s.is_empty() {
                    break s.to_lowercase();
                }
                println!("Provider name required");
            };
            let base_url = loop {
                let s = ask("Base URL (e.g., https://api.openai.com/v1)")?;
                if !s.is_empty() {
                    break s;
                }
                println!("Base URL required");
            };
            let api_key = rpassword::prompt_password("API key (hidden): ")?.trim().to_string();
            if api_key.is_empty() {
                println!("Warning: No API key provided. You'll need to set it manually.");
            }
            let env_key = format!("{}_API_KEY", name.to_uppercase());
            providers.insert(
                name.clone(),
                ProviderEntry {
                    base_url: base_url.clone(),
                    api_key: format!("${{{env_key}}}"),
                },
            );
            env_vars.insert(env_key, api_key.clone());

            if !api_key.is_empty() {
                println!("\nFetching models from {name}...");
                for (friendly, id) in select_models(&fetch_models(&base_url, &api_key).await)? {
                    models.insert(
                        friendly,
                        ModelEntry {
                            provider: name.clone(),
                            model: id,
                        },
                    );
                }
            } else {
                println!("Skipping model fetch (no API key or base URL)");
            }

            if !confirm("\nAdd another provider?", false)? {
                break;
            }
        }
    }

    // ── Step 2: SearXNG ────────────────────────────────────────────────────
    println!("\n═══ Step 2: SearXNG (Local Search) ═══\n");
    let setup_searxng = if yes {
        let port = std::env::var("SEARXNG_PORT").unwrap_or_else(|_| "2946".into());
        env_vars.insert("SEARXNG_PORT".into(), port);
        println!("→ --yes mode: defaulting to SearXNG install");
        true
    } else if matches!(
        std::env::var("YES_INSTALL_SEARXNG")
            .unwrap_or_default()
            .to_lowercase()
            .as_str(),
        "1" | "true" | "yes"
    ) {
        let port = std::env::var("SEARXNG_PORT").unwrap_or_else(|_| "2946".into());
        env_vars.insert("SEARXNG_PORT".into(), port);
        println!("→ YES_INSTALL_SEARXNG=1 detected, skipping prompt");
        true
    } else if confirm("Set up local SearXNG search instance? (Requires Docker)", true)? {
        let port = ask_default("SearXNG port", "2946")?;
        env_vars.insert("SEARXNG_PORT".into(), port);
        true
    } else {
        false
    };

    // ── Step 3: Review ─────────────────────────────────────────────────────
    println!("\n═══ Step 3: Review ═══\n");
    let memory_url = crow_memory_sdk::default_memory_url();
    println!("Memory server: {memory_url} (crow-memory service)");
    if !providers.is_empty() {
        println!("\nProviders:");
        for (name, p) in &providers {
            println!("  {name}: {}", p.base_url);
        }
    }
    if !models.is_empty() {
        println!("\nModels:");
        for (name, m) in &models {
            println!("  {name}: provider={}, model={}", m.provider, m.model);
        }
    }
    println!("\nServices:");
    println!("  SearXNG: {}", if setup_searxng { "✓ Docker" } else { "✗ Skip" });
    println!("  Memory:  crow-memory service");
    println!("\nConfig directory: {}", config_dir.display());

    if !yes && !confirm("\nLooks good?", true)? {
        anyhow::bail!("Aborted. No files were written.");
    }

    // ── Step 4: Write files ────────────────────────────────────────────────
    println!("\n═══ Step 4: Writing Configuration ═══\n");
    std::fs::create_dir_all(&config_dir)?;

    let prompts_dir = config_dir.join("prompts");
    std::fs::create_dir_all(&prompts_dir)?;
    let prompt_file = prompts_dir.join("system_prompt.hbs");
    if prompt_file.exists() {
        println!("⊘ Prompt template already exists, skipping");
    } else {
        std::fs::write(&prompt_file, SYSTEM_PROMPT)?;
        println!("✓ Wrote prompt template to {}", prompt_file.display());
    }

    // mcpServers points at the installed crow-mcp binary. Absolute path —
    // config.yaml does not expand ~.
    let home = dirs::home_dir()
        .ok_or_else(|| anyhow::anyhow!("cannot determine home directory"))?;
    let mcp_bin = home.join(".cargo/bin/crow-mcp");
    let mut mcp_servers = IndexMap::new();
    mcp_servers.insert(
        "crow-mcp".into(),
        McpEntry {
            transport: "stdio".into(),
            command: mcp_bin.display().to_string(),
            args: vec![],
        },
    );

    let default_model = models.keys().next().cloned().unwrap_or_default();
    let init_config = InitConfig {
        mcp_servers,
        memory_port: crow_memory_sdk::DEFAULT_MEMORY_PORT,
        providers,
        models,
        max_compact_tokens: 190000,
        max_retries_per_step: 3,
    };
    std::fs::write(&config_file, serde_yaml::to_string(&init_config)?)?;
    println!("✓ Written {}", config_file.display());

    // client_settings.yaml: the daemon topology crow-cli run/daemon resolve
    // against. Without it crow-memory never comes up.
    let settings_file = config_dir.join("client_settings.yaml");
    if settings_file.exists() {
        println!("⊘ {} already exists, skipping", settings_file.display());
    } else {
        std::fs::write(&settings_file, render_client_settings(&config_dir, &default_model)?)?;
        println!("✓ Written {}", settings_file.display());
    }

    let env_lines: Vec<String> = env_vars.iter().map(|(k, v)| format!("{k}={v}")).collect();
    std::fs::write(&env_file, env_lines.join("\n") + "\n")?;
    println!("✓ Written {}", env_file.display());

    if setup_searxng {
        let searxng_dir = config_dir.join("searxng");
        std::fs::create_dir_all(&searxng_dir)?;
        std::fs::write(searxng_dir.join("settings.yml"), SEARXNG_SETTINGS_YML)?;
        println!("✓ Wrote SearXNG settings.yml");

        let compose_file = config_dir.join("compose.yaml");
        std::fs::write(&compose_file, COMPOSE_SEARXNG)?;
        println!("✓ Written {}", compose_file.display());
    }

    std::fs::create_dir_all(config_dir.join("logs"))?;

    // ── Step 5: Start services (instructions only) ─────────────────────────
    if setup_searxng {
        println!("\n═══ Step 5: Start Services ═══\n");
        println!("  cd {} && docker compose up -d\n", config_dir.display());
    }

    println!("✓ Configuration complete!\n");
    println!("Config:   {}", config_file.display());
    println!("Agents:   {}", settings_file.display());
    println!("Memory:   {memory_url} (crow-memory service)");
    println!("Logs:     {}", config_dir.join("logs").display());
    println!("Prompt:   {}", prompt_file.display());
    println!("Secrets:  {}", env_file.display());
    if setup_searxng {
        println!("Compose:  {}", config_dir.join("compose.yaml").display());
        println!("\nStart services: cd {} && docker compose up -d", config_dir.display());
    }
    println!("\nTest: crow-cli run \"hey\"");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn provider_from_env_key_parses() {
        assert_eq!(
            provider_from_env_key("LLM_DASHSCOPE_API_KEY"),
            Some(("dashscope".into(), "LLM_DASHSCOPE_BASE_URL".into()))
        );
        assert_eq!(
            provider_from_env_key("LLM_FOO_BAR_API_KEY"),
            Some(("foo_bar".into(), "LLM_FOO_BAR_BASE_URL".into()))
        );
        assert_eq!(provider_from_env_key("LLM__API_KEY"), None);
        assert_eq!(provider_from_env_key("OPENAI_API_KEY"), None);
        assert_eq!(provider_from_env_key("LLM_X_BASE_URL"), None);
    }

    #[test]
    fn parse_selection_modes() {
        assert_eq!(parse_selection("all", 3), Some(vec![0, 1, 2]));
        assert_eq!(parse_selection("NONE", 3), Some(vec![]));
        assert_eq!(parse_selection("1,3", 3), Some(vec![0, 2]));
        assert_eq!(parse_selection(" 2 ", 3), Some(vec![1]));
        assert_eq!(parse_selection("5", 3), Some(vec![]));
        assert_eq!(parse_selection("x", 3), None);
    }

    #[test]
    fn render_client_settings_substitutes_and_drops_model() {
        let dir = std::path::PathBuf::from("/tmp/crow-test");
        let home = dirs::home_dir().unwrap();
        let home_s = home.display().to_string();

        let with_model = render_client_settings(&dir, "qwen3.8-max-preview").unwrap();
        assert!(with_model.contains(&format!("command: {home_s}/.cargo/bin/crow-memory")));
        assert!(with_model.contains("args: [--config, /tmp/crow-test/config.yaml]"));
        assert!(with_model.contains("model: qwen3.8-max-preview"));
        assert!(!with_model.contains("{{"));
        // parses as valid client settings
        let s: crate::client_settings::ClientSettings =
            serde_yaml::from_str(&with_model).unwrap();
        assert_eq!(s.default.as_deref(), Some("crow"));
        assert_eq!(s.agent_servers["crow-memory"].port, Some(27697));
        assert_eq!(s.agent_servers["crow-daemon"].requires, vec!["crow-memory"]);
        assert!(s.chains.contains_key("verifier"));

        let no_models = render_client_settings(&dir, "").unwrap();
        assert!(!no_models.contains("default_config_options"));
        assert!(!no_models.contains("model:"));
        let s: crate::client_settings::ClientSettings =
            serde_yaml::from_str(&no_models).unwrap();
        assert!(s.agent_servers["crow"].default_config_options.model.is_none());
    }

    #[test]
    fn friendly_default_strips_registry_prefix() {
        assert_eq!(friendly_default("openai/gpt-4o"), "gpt-4o");
        assert_eq!(friendly_default("qwen3.6-plus"), "qwen3.6-plus");
    }

    fn sample_init_config() -> InitConfig {
        let mut mcp_servers = IndexMap::new();
        mcp_servers.insert(
            "crow-mcp".into(),
            McpEntry {
                transport: "stdio".into(),
                command: "/usr/local/bin/crow-mcp".into(),
                args: vec![],
            },
        );
        let mut providers = IndexMap::new();
        providers.insert(
            "dashscope".into(),
            ProviderEntry {
                base_url: "https://coding-intl.dashscope.aliyuncs.com/v1".into(),
                api_key: "${LLM_DASHSCOPE_API_KEY}".into(),
            },
        );
        let mut models = IndexMap::new();
        models.insert(
            "qwen3.6-plus".into(),
            ModelEntry {
                provider: "dashscope".into(),
                model: "qwen3.6-plus".into(),
            },
        );
        InitConfig {
            mcp_servers,
            memory_port: 27697,
            providers,
            models,
            max_compact_tokens: 190000,
            max_retries_per_step: 3,
        }
    }

    #[test]
    fn init_yaml_layout_matches_v1() {
        let yaml = serde_yaml::to_string(&sample_init_config()).unwrap();
        assert!(yaml.contains("mcpServers:"));
        assert!(yaml.contains("MAX_COMPACT_TOKENS: 190000"));
        assert!(yaml.contains("max_retries_per_step: 3"));
        assert!(yaml.contains("${LLM_DASHSCOPE_API_KEY}"));
        // mcpServers first, matching v1 key order
        assert!(yaml.starts_with("mcpServers:"));
    }

    #[test]
    fn init_yaml_loads_through_config_loader() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join("config.yaml"),
            serde_yaml::to_string(&sample_init_config()).unwrap(),
        )
        .unwrap();
        let cfg = crate::config::Config::load(Some(dir.path()), None).unwrap();
        assert_eq!(cfg.models.len(), 1);
        assert_eq!(cfg.max_compact_tokens, 190000);
        assert!(cfg.mcp_servers.contains_key("crow-mcp"));
        let (name, model) = cfg.default_model().unwrap();
        assert_eq!(name, "qwen3.6-plus");
        assert_eq!(cfg.provider_for(model).unwrap().base_url.as_deref(),
                   Some("https://coding-intl.dashscope.aliyuncs.com/v1"));
    }
}
