//! crow-mcp: MCP server exposing terminal + edit + read + write tools over stdio.
//!
//! Spawned by crow-cli agent as a child process per config.yaml mcpServers.

mod edit;
mod fs;
mod memory;
mod terminal;
mod verdict;
mod vision;
mod web;

use std::sync::Arc;

use rmcp::{
    handler::server::ServerHandler, tool_handler, ServiceExt, transport::stdio,
};
use tokio::sync::Mutex;

/// Shared state for the MCP server.
struct ServerState {
    terminal_mgr: terminal::TerminalManager,
}

#[derive(Clone)]
pub struct CrowMcpServer {
    state: Arc<Mutex<ServerState>>,
    memory: Arc<crow_memory_sdk::MemoryClient>,
}

// ---------------------------------------------------------------------------
// Tool implementations live in per-tool modules: terminal.rs, edit.rs,
// fs.rs, memory.rs, verdict.rs, vision.rs, web.rs. Each declares a
// #[tool_router]; tool_router() below combines them all.
// ---------------------------------------------------------------------------

impl CrowMcpServer {
    pub fn new(memory: Arc<crow_memory_sdk::MemoryClient>) -> Self {
        Self {
            state: Arc::new(Mutex::new(ServerState {
                terminal_mgr: terminal::TerminalManager::new(),
            })),
            memory,
        }
    }

    pub fn tool_router() -> rmcp::handler::server::router::tool::ToolRouter<Self> {
        Self::terminal_router() + Self::edit_router() + Self::fs_router() + Self::memory_router() + Self::verdict_router() + Self::vision_router() + Self::web_router()
    }
}

#[tool_handler(router = Self::tool_router())]
impl ServerHandler for CrowMcpServer {}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("warn")),
        )
        .with_writer(std::io::stderr)
        .with_ansi(false)
        .init();

    tracing::info!("crow-mcp server starting");

    // Connect to the crow-memory HTTP server (URL from env or default).
    // Lazy connect: if the server is down, memory tools retry per call
    // with backoff — no silent fallback store to hide the outage.
    let memory_url = std::env::var("CROW_MEMORY_URL")
        .unwrap_or_else(|_| crow_memory_sdk::default_memory_url());
    let client = crow_memory_sdk::MemoryClient::connect(&memory_url);
    match client.health().await {
        Ok(()) => tracing::info!("memory server: {memory_url}"),
        Err(e) => tracing::warn!(
            "memory server unavailable at {memory_url}: {e} — memory tools will retry per call"
        ),
    }
    let memory = Arc::new(client);

    let service = CrowMcpServer::new(memory).serve(stdio()).await.inspect_err(|e| {
        tracing::error!("serving error: {e:?}");
    })?;

    service.waiting().await?;
    Ok(())
}
