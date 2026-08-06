//! ollama-mv provisioning — build the multivector ollama fork from source,
//! pull the ColBERT embedding model, verify a real embed call.
//!
//! Driven by `crow-cli daemon install ollama-mv`: on a fresh machine the
//! forks are cloned into {config_dir}/vendor, built (Go + cmake, CPU-only),
//! declared in client_settings.yaml and installed as a systemd unit. The
//! "embeddings download" IS the first embed call — ollama pulls the model
//! on demand.

use std::collections::HashMap;
use std::path::Path;
use std::process::Command;
use std::time::Duration;

use anyhow::{anyhow, bail, Context};

use crate::client_settings::{AgentServerConfig, ClientSettings, ConfigOptions};

pub const SERVICE_NAME: &str = "ollama-mv";
pub const PORT: u16 = 11392;
pub const EMBED_MODEL: &str =
    "hf.co/LiquidAI/LFM2.5-ColBERT-350M-GGUF:LFM2.5-ColBERT-350M-BF16.gguf";

const OLLAMA_REPO: &str = "https://github.com/crow-cli/ollama.git";
const LLAMACPP_REPO: &str = "https://github.com/crow-cli/llama.cpp.git";

/// Built-in declaration for a fresh machine (no ollama-mv entry in
/// client_settings.yaml yet). Mirrors the hand-wired dev setup.
fn default_entry(config_dir: &Path) -> AgentServerConfig {
    let mut env = HashMap::new();
    env.insert("OLLAMA_HOST".into(), format!("127.0.0.1:{PORT}"));
    if let Some(home) = dirs::home_dir() {
        env.insert(
            "OLLAMA_MODELS".into(),
            home.join(".local/share/ollama-mv-models")
                .display()
                .to_string(),
        );
    }
    AgentServerConfig {
        kind: Some("custom".into()),
        command: config_dir.join("vendor/ollama/ollama").display().to_string(),
        args: vec!["serve".into()],
        env,
        default_config_options: ConfigOptions::default(),
        port: Some(PORT),
        requires: vec![],
    }
}

/// Ensure the ollama-mv entry exists (persisting the built-in default on a
/// fresh machine) and its binary is built. Returns the declaration.
pub fn provision(
    config_dir: &Path,
    settings: &mut ClientSettings,
) -> anyhow::Result<AgentServerConfig> {
    if !settings.agent_servers.contains_key(SERVICE_NAME) {
        let entry = default_entry(config_dir);
        settings.agent_servers.insert(SERVICE_NAME.into(), entry);
        settings
            .save(config_dir)
            .context("persisting ollama-mv entry to client_settings.yaml")?;
        eprintln!("declared ollama-mv in client_settings.yaml");
    }
    let cfg = settings.agent_servers[SERVICE_NAME].clone();

    if Path::new(&cfg.command).exists() {
        return Ok(cfg); // built already (dev tree or prior run) — idempotent
    }

    // Command path is dead (repo moved) or never built. Build into the
    // config dir and repoint the entry at the built binary — via surgical
    // text edit, so the user's yaml comments survive.
    let built = build_from_source(config_dir)?;
    let new_command = built.display().to_string();
    repoint_command(config_dir, SERVICE_NAME, &new_command)
        .context("repointing ollama-mv command in client_settings.yaml")?;
    let entry = settings.agent_servers.get_mut(SERVICE_NAME).expect("inserted above");
    entry.command = new_command.clone();
    eprintln!("repointed ollama-mv to {new_command}");
    Ok(entry.clone())
}

/// Replace an entry's `command:` value in client_settings.yaml WITHOUT a
/// serde round trip (comments + ordering survive).
fn repoint_command(config_dir: &Path, name: &str, new_command: &str) -> anyhow::Result<()> {
    let path = config_dir.join("client_settings.yaml");
    let text = std::fs::read_to_string(&path)?;
    let mut out = String::with_capacity(text.len());
    let mut entry_indent: Option<usize> = None;
    let mut replaced = false;
    for line in text.lines() {
        let trimmed = line.trim_start();
        let indent = line.len() - trimmed.len();
        if let Some(ei) = entry_indent {
            if !trimmed.is_empty() && indent <= ei {
                entry_indent = None; // dedented past the entry — block over
            }
        }
        if entry_indent.is_none() && trimmed == format!("{name}:") {
            entry_indent = Some(indent);
            out.push_str(line);
            out.push('\n');
            continue;
        }
        if entry_indent.is_some() && !replaced && trimmed.starts_with("command:") {
            out.push_str(&line[..indent]);
            out.push_str(&format!("command: {new_command}\n"));
            replaced = true;
            continue;
        }
        out.push_str(line);
        out.push('\n');
    }
    anyhow::ensure!(
        replaced,
        "no command: line found under '{name}' in {}",
        path.display()
    );
    std::fs::write(&path, out)?;
    Ok(())
}

fn build_from_source(config_dir: &Path) -> anyhow::Result<std::path::PathBuf> {
    let go = find_go()?;
    let vendor = config_dir.join("vendor");
    let ollama = vendor.join("ollama");
    let llamcpp = vendor.join("llama.cpp");

    if !ollama.join(".git").exists() {
        eprintln!("cloning {OLLAMA_REPO}");
        run(Command::new("git")
            .args(["clone", "--depth", "1", OLLAMA_REPO])
            .arg(&ollama))?;
    }
    let pinned = std::fs::read_to_string(ollama.join("LLAMA_CPP_VERSION"))
        .context("reading vendor/ollama/LLAMA_CPP_VERSION")?
        .trim()
        .to_string();
    if !llamcpp.join(".git").exists() {
        eprintln!("cloning {LLAMACPP_REPO} @ {pinned}");
        run(Command::new("git")
            .args(["clone", "--depth", "1", "--branch", &pinned, LLAMACPP_REPO])
            .arg(&llamcpp))?;
    } else {
        let at = Command::new("git")
            .args(["describe", "--tags", "--exact-match"])
            .current_dir(&llamcpp)
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
            .unwrap_or_default();
        if at != pinned {
            let d = llamcpp.display();
            bail!(
                "vendor/llama.cpp is at '{at}' but vendor/ollama pins '{pinned}':\n  \
                 git -C {d} fetch --depth 1 origin tag {pinned} && git -C {d} checkout {pinned}"
            );
        }
    }

    eprintln!("configuring cmake (CPU-only, offline llama.cpp)");
    run(Command::new("cmake")
        .env("OLLAMA_LLAMA_CPP_SOURCE", &llamcpp)
        .arg("-B")
        .arg("build")
        .arg("-S")
        .arg(".")
        .arg("-DCMAKE_BUILD_TYPE=Release")
        .arg(format!("-DGO_EXECUTABLE={go}"))
        .current_dir(&ollama))?;
    let jobs = std::thread::available_parallelism()
        .map(|n| n.get().min(8))
        .unwrap_or(8);
    eprintln!("building ollama-mv (--parallel {jobs}) — this takes a while");
    run(Command::new("cmake")
        .env("OLLAMA_LLAMA_CPP_SOURCE", &llamcpp)
        .arg("--build")
        .arg("build")
        .arg("--parallel")
        .arg(jobs.to_string())
        .current_dir(&ollama))?;

    let binary = ollama.join("ollama");
    if !binary.exists() {
        bail!("build finished but {} is missing", binary.display());
    }
    eprintln!("built {}", binary.display());
    Ok(binary)
}

fn find_go() -> anyhow::Result<String> {
    if let Ok(g) = std::env::var("GO") {
        return Ok(g);
    }
    if let Some(home) = dirs::home_dir() {
        let g = home.join(".local/go/bin/go");
        if g.exists() {
            return Ok(g.display().to_string());
        }
    }
    if Command::new("go")
        .arg("version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
    {
        return Ok("go".into());
    }
    bail!("no Go toolchain found — install Go (https://go.dev/dl/) or set GO=/path/to/go")
}

fn run(cmd: &mut Command) -> anyhow::Result<()> {
    let desc = format!("{cmd:?}");
    let status = cmd
        .status()
        .with_context(|| format!("spawning: {desc}"))?;
    if !status.success() {
        bail!("command failed: {desc}");
    }
    Ok(())
}

/// Pull (on first call) + verify the ColBERT model with a real embed.
/// Same semantics as scripts/embeddings.sh: generous per-call timeout,
/// retries while the runner cold-loads / the model downloads.
pub async fn verify_embeddings(port: u16) -> anyhow::Result<()> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(120))
        .build()?;
    let url = format!("http://127.0.0.1:{port}/api/embed");
    let body = serde_json::json!({
        "model": EMBED_MODEL,
        "input": "crow warmup",
        "colbert": true,
    });
    for attempt in 1..=24u32 {
        match client.post(&url).json(&body).send().await {
            Ok(r) if r.status().is_success() => {
                if r.text().await.unwrap_or_default().contains("embeddings") {
                    eprintln!("embeddings: OK (http://127.0.0.1:{port})");
                    return Ok(());
                }
            }
            Ok(r) => eprintln!("embed attempt {attempt}: HTTP {}", r.status()),
            Err(e) => eprintln!("embed attempt {attempt}: {e}"),
        }
        tokio::time::sleep(Duration::from_secs(5)).await;
    }
    Err(anyhow!(
        "embeddings: FAILED after 24 attempts — check the ollama-mv log"
    ))
}
