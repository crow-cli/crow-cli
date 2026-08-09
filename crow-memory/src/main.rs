//! crow-memory server binary: axum + LanceDB + embeddings, single writer.
//!
//! Reads `memory_path` + `embedding` from the crow config.yaml (same file
//! crow-cli uses); clients talk to this server via the python crow-memory-sdk.

use std::path::PathBuf;
use std::sync::Arc;

use clap::Parser;

#[derive(Parser)]
#[command(name = "crow-memory", about = "crow memory HTTP server (LanceDB single writer)")]
struct Cli {
    /// Config file with memory_path + embedding sections (default:
    /// ~/.agents/crow/config.yaml)
    #[arg(long)]
    config: Option<PathBuf>,
    /// HTTP port (overrides $CROW_MEMORY_PORT and config `memory_port`)
    #[arg(long)]
    port: Option<u16>,
    /// Bind address
    #[arg(long, default_value = "127.0.0.1")]
    host: String,
}

/// Subset of the crow config.yaml this server cares about. Unknown keys
/// (providers, models, mcpServers, …) are ignored.
#[derive(Default, serde::Deserialize)]
struct ConfigFile {
    memory_path: Option<String>,
    /// Server HTTP port; clients derive memory_url from it when memory_url
    /// is unset, so one knob moves server + clients together.
    memory_port: Option<u16>,
    #[serde(default)]
    embedding: Option<crow_memory::EmbedConfig>,
}

fn expand_tilde(p: &str) -> PathBuf {
    match p.strip_prefix("~/") {
        Some(rest) => dirs::home_dir()
            .map(|h| h.join(rest))
            .unwrap_or_else(|| PathBuf::from(p)),
        None => PathBuf::from(p),
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .with_writer(std::io::stderr)
        .init();

    let cli = Cli::parse();

    let config_path = cli.config.unwrap_or_else(|| {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".agents/crow/config.yaml")
    });

    // Same convention as crow-cli: ports/secrets live in {config_dir}/.env.
    if let Some(dir) = config_path.parent() {
        let env_file = dir.join(".env");
        if env_file.exists() {
            dotenvy::from_path(&env_file).ok();
        }
    }

    let raw: ConfigFile = if config_path.exists() {
        serde_yaml::from_str(&std::fs::read_to_string(&config_path)?)?
    } else {
        tracing::warn!("config {} not found; using defaults", config_path.display());
        ConfigFile::default()
    };

    // Port precedence: --port flag > $CROW_MEMORY_PORT (docker/.env) >
    // config.yaml memory_port > DEFAULT_MEMORY_PORT (27697, "CROWS").
    let port = cli
        .port
        .or_else(|| std::env::var("CROW_MEMORY_PORT").ok().and_then(|s| s.parse().ok()))
        .or(raw.memory_port)
        .unwrap_or(crow_memory_types::DEFAULT_MEMORY_PORT);

    let memory_path = raw
        .memory_path
        .map(|p| expand_tilde(&p))
        .unwrap_or_else(|| {
            dirs::home_dir()
                .unwrap_or_else(|| PathBuf::from("."))
                .join(".agents/crow/memory.lance")
        });
    let embed_config = raw.embedding.unwrap_or_else(crow_memory::EmbedConfig::from_env);

    tracing::info!("opening LanceDB at {}", memory_path.display());
    let store = crow_memory::MemoryStore::open(&memory_path, embed_config).await?;
    let app = crow_memory::router(Arc::new(store));

    let addr = format!("{}:{}", cli.host, port);
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    tracing::info!("crow-memory serving on http://{addr}");
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            tokio::signal::ctrl_c().await.ok();
            tracing::info!("Ctrl+C received, shutting down");
        })
        .await?;
    Ok(())
}
