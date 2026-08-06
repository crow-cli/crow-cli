//! crow-server: ACP v2 agent served over HTTP/SSE.
//!
//! Usage:
//!   crow-server                    — serve on 0.0.0.0:8080
//!   crow-server --port 3000        — custom port
//!   crow-server -d ~/.agents/crow         — custom config dir
//!   crow-server -o overlay.yaml    — config overlay

use std::sync::Arc;

use clap::Parser;

#[derive(Parser)]
#[command(name = "crow-server", version, about = "crow ACP agent server (HTTP/SSE)")]
struct Cli {
    /// Configuration directory (default: ~/.agents/crow)
    #[arg(long, short = 'd')]
    config_dir: Option<std::path::PathBuf>,

    /// YAML file with config values to override
    #[arg(long, short = 'o')]
    config_file: Option<std::path::PathBuf>,

    /// Port to listen on
    #[arg(long, short = 'p', default_value = "8080")]
    port: u16,

    /// Bind address
    #[arg(long, default_value = "0.0.0.0")]
    bind: String,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let cli = Cli::parse();

    let config = crow_cli::config::Config::load(
        cli.config_dir.as_deref(),
        cli.config_file.as_deref(),
    )?;
    if !config.is_configured() {
        anyhow::bail!("no LLM providers/models configured in ~/.agents/crow/config.yaml");
    }

    let store = Arc::new(crow_memory_sdk::MemoryClient::connect(&config.memory_url));

    let config = Arc::new(config);

    let server = agent_client_protocol_http::AcpHttpServer::new({
        let config = config.clone();
        let store = store.clone();
        move || {
            crow_cli::agent::CrowAgent::new(
                (*config).clone(),
                store.clone(),
            )
        }
    })
    .with_options(
        agent_client_protocol_http::ServerOptions::default(),
    );

    let router = server.into_router();

    let addr = format!("{}:{}", cli.bind, cli.port);
    tracing::info!("crow-server listening on {addr}");
    println!("crow-server listening on http://{addr}/acp");

    let listener = tokio::net::TcpListener::bind(&addr).await?;

    // Graceful shutdown on Ctrl+C
    axum::serve(listener, router)
        .with_graceful_shutdown(async {
            tokio::signal::ctrl_c().await.ok();
            tracing::info!("shutting down");
        })
        .await?;

    Ok(())
}
