//! crow-cli: AI agent CLI (Rust, ACP v2)
//!
//! Subcommands:
//!   crow-cli acp                   — run as ACP v2 agent over stdio
//!   crow-cli run [name] [prompt]   — run as client (name from client_settings.yaml)

mod agent;
mod client_settings;
mod compact;
mod config;
mod coolname;
mod daemon;
mod embeddings;
mod init;
mod llm;
mod react;
mod render;
mod session;

use std::os::unix::process::CommandExt as _;
use std::str::FromStr;

use agent_client_protocol::{AcpAgent, Channel, Client, ConnectTo, Stdio};
use clap::{Parser, Subcommand};
use client_settings::ClientSettings;

#[derive(Parser)]
#[command(
    name = "crow-cli",
    version,
    about = "crow-cli — scriptable ACP v2 CLI: run agents, chains, and terminals",
    after_help = "Examples:
  crow-cli init -y                           write config from LLM_*_API_KEY env vars
  crow-cli models                            list configured models (* = default)
  crow-cli run -m gpt-5 \"fix the test\"       one-shot prompt with an explicit model
  crow-cli run \"fix the failing test\"        one-shot prompt to the default agent
  crow-cli run verifier -p PROMPT.md       named chain from ~/.agents/crow/client_settings.yaml
  crow-cli run -j \"list files\" | jq .      JSON output: one line per session update
  crow-cli run -s <session-id> \"keep going\"  resume a session (append-only history)
  crow-cli daemon list                       declared daemons + state + MANAGED backend
  crow-cli daemon install ollama-mv          promote to a systemd user unit (boot persistence)
  crow-cli daemon status                     all daemons: port, pid, state, MANAGED backend
  crow-cli acp                             run as an ACP v2 agent over stdio

Configure agent servers and chains in ~/.agents/crow/client_settings.yaml.

Services: entries with a `port:` there are daemons. `crow-cli daemon
start|stop|restart|status` manage them directly (pidfile + log under the
config dir); `crow-cli daemon install <name>` promotes one to a systemd USER
UNIT (crow-<name>.service, Restart=always, logs via journalctl --user) and
start/stop/status then route through systemctl --user. `daemon uninstall`
reverts to the pidfile backend. Boot persistence needs linger:
  sudo loginctl enable-linger $USER"
)]
struct Cli {
    /// Configuration directory (default: ~/.agents/crow)
    #[arg(long, short = 'd', global = true)]
    config_dir: Option<std::path::PathBuf>,

    /// YAML file with config values to override (takes precedence over config.yaml)
    #[arg(long, short = 'o', global = true)]
    config_file: Option<std::path::PathBuf>,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Run as an ACP v2 agent over stdio (the ACP endpoint of crow), with
    /// --http as one resident multi-session agent over HTTP/SSE, or with
    /// --relay URL as a disposable stdio front for a resident daemon.
    Acp {
        /// Serve ACP over HTTP/SSE instead of stdio: one resident agent,
        /// sessions stay resident across connection drops (phase 13)
        #[arg(long)]
        http: bool,
        /// HTTP port (with --http)
        #[arg(long, default_value_t = 2769)]
        port: u16,
        /// HTTP bind address (with --http)
        #[arg(long, default_value = "127.0.0.1")]
        host: String,
        /// Relay mode: be a thin stdio ACP front for a resident daemon.
        /// Speaks ACP over stdio upstream, forwards everything to the
        /// daemon's `acp --http` endpoint. Sessions live in the daemon, so
        /// this process is disposable — kill it, respawn it, resume.
        #[arg(long)]
        relay: Option<String>,
    },
    /// Initialize Crow configuration (config.yaml, .env, system prompt) in
    /// the config directory. Scans LLM_*_API_KEY env vars with -y.
    Init {
        /// Non-interactive: take providers from LLM_*_API_KEY/LLM_*_BASE_URL
        /// env vars and overwrite existing config without asking.
        #[arg(short = 'y', long)]
        yes: bool,
    },
    /// Run as a client. The first word may name an agent server or chain from
    /// ~/.agents/crow/client_settings.yaml; the rest form the one-shot prompt.
    /// No prompt → interactive REPL on stdin.
    Run {
        /// [server-or-chain-name] [prompt words...]
        words: Vec<String>,
        /// Read the prompt from a file (e.g. PROMPT.md); words are appended
        #[arg(short = 'p', long = "prompt-file")]
        prompt_file: Option<std::path::PathBuf>,
        /// Resume an existing session by id (pairs with -p for delegation follow-ups)
        #[arg(short = 's', long = "session")]
        session: Option<String>,
        /// Machine output: every session update as a JSON line (jq-friendly,
        /// no ANSI). Fully scriptable — this is a CLI, not a TUI.
        #[arg(short = 'j', long)]
        json: bool,
        /// Agent to run: a name from client_settings.yaml (server or chain —
        /// see `crow-cli agents`) or a raw command string. The first prompt
        /// word still works as a name for convenience.
        #[arg(short = 'a', long)]
        agent: Option<String>,
        /// Model name or id for this session (see `crow-cli models`; overrides
        /// the config default and client_settings default_config_options)
        #[arg(short = 'm', long)]
        model: Option<String>,
        /// Fire-and-forget: spawn the run detached in the background, print
        /// the session id + log path immediately, and exit. The agent keeps
        /// working; follow up with `crow-cli run -s <id>` or query_session.
        #[arg(long)]
        headless: bool,
    },
    /// List models configured in config.yaml (first = default)
    Models {
        /// Output as a JSON array (scriptable)
        #[arg(short = 'j', long)]
        json: bool,
    },
    /// List agents (servers) and chains declared in client_settings.yaml
    #[command(after_help = AGENTS_HELP)]
    Agents {
        /// Output as JSON (scriptable)
        #[arg(short = 'j', long)]
        json: bool,
    },
    /// ACP auth surface: list advertised methods, log in, log out
    Auth {
        #[command(subcommand)]
        command: Option<AuthCommand>,
    },
    /// Manage agent-server daemons declared in client_settings.yaml.
    ///
    /// Two backends, one interface: entries with a `port:` are daemons.
    /// By default crow-cli runs them itself (detached spawn, pidfile in
    /// {config_dir}/run, log in {config_dir}/logs). `crow-cli daemon install
    /// <name>` promotes one to a systemd USER UNIT (~/.config/systemd/user/
    /// crow-<name>.service) with Restart=always and boot persistence — then
    /// start/stop/status route through systemctl --user. The MANAGED column
    /// in status/list shows which backend owns each daemon.
    ///
    /// Boot persistence needs linger: `sudo loginctl enable-linger $USER`
    /// (crow-cli warns on every install while it is off).
    Daemon {
        #[command(subcommand)]
        command: DaemonCommand,
    },
    /// Serve a client_settings agent (or chain) as a persistent ACP HTTP endpoint.
    ///
    /// Each HTTP connection spawns a fresh instance of the target (stdio
    /// subprocess(es)) and bridges ACP JSON-RPC over /acp — POST for requests,
    /// GET for SSE streams or a WebSocket upgrade, DELETE to hang up.
    /// Health probe: GET /health.
    Serve {
        /// Agent server or chain name from client_settings.yaml (or a raw command)
        name: String,
        /// Port to listen on
        #[arg(long, default_value_t = 2769)]
        port: u16,
        /// Bind address
        #[arg(long, default_value = "127.0.0.1")]
        host: String,
    },
}

#[derive(Subcommand)]
enum DaemonCommand {
    /// Start a daemon (detached; pidfile in {config_dir}/run, log in {config_dir}/logs)
    Start { name: String },
    /// Stop a running daemon (SIGTERM, then SIGKILL after 5s)
    Stop { name: String },
    /// Stop (if running) and start a daemon
    Restart { name: String },
    /// Show daemon status (all daemons when name is omitted)
    Status {
        name: Option<String>,
        #[arg(short = 'j', long)]
        json: bool,
    },
    /// List declared daemons and their state
    List {
        #[arg(short = 'j', long)]
        json: bool,
    },
    /// Install a systemd user unit for a daemon (crow-<name>.service):
    /// Restart=always (crash restart) + boot persistence (needs linger:
    /// `sudo loginctl enable-linger $USER`). While installed, start/stop/
    /// status route through systemd. Idempotent — reinstall rewrites + reloads.
    ///
    /// `ollama-mv` is special: when its binary is missing it is BUILT FROM
    /// SOURCE (forks cloned into {config_dir}/vendor, Go + cmake, CPU), and
    /// after startup the ColBERT embedding model is pulled + verified with a
    /// real embed call (`--no-verify` to skip).
    Install {
        name: String,
        /// Skip the embed call that pulls + verifies the embedding model
        /// (ollama-mv only)
        #[arg(long)]
        no_verify: bool,
    },
    /// Stop the daemon, remove its systemd user unit (logs kept)
    Uninstall { name: String },
}

#[derive(Subcommand)]
enum AuthCommand {
    /// Print the advertised auth methods as JSON (derived from the
    /// ${VAR} api_key refs in config.yaml)
    List,
    /// Call auth/login on the default agent for one advertised method
    Login {
        /// Method id (provider name), see `crow-cli auth list`
        method_id: String,
        /// Secret to persist into the agent's .env; omit when the env var
        /// is already set
        #[arg(long)]
        value: Option<String>,
    },
    /// Call auth/logout on the default agent
    Logout,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("warn")),
        )
        .init();

    let cli = Cli::parse();

    // Config resolution: CLI flag > env var. The env vars are then (re)exported
    // so spawned `crow-cli acp` subprocesses inherit the same config.
    let config_dir = cli
        .config_dir
        .or_else(|| std::env::var_os("CROW_CONFIG_DIR").map(std::path::PathBuf::from));
    let config_file = cli
        .config_file
        .or_else(|| std::env::var_os("CROW_CONFIG_FILE").map(std::path::PathBuf::from));
    if let Some(d) = &config_dir {
        unsafe { std::env::set_var("CROW_CONFIG_DIR", d) };
    }
    if let Some(f) = &config_file {
        unsafe { std::env::set_var("CROW_CONFIG_FILE", f) };
    }

    match cli.command {
        Commands::Acp { http, port, host, relay } => {
            if let Some(url) = relay {
                if http {
                    anyhow::bail!("--relay and --http are mutually exclusive");
                }
                return run_relay(&url).await;
            }
            if http {
                tokio::select! {
                    result = run_agent_http(config_dir.as_deref(), config_file.as_deref(), host, port) => result,
                    _ = tokio::signal::ctrl_c() => {
                        tracing::info!("Ctrl+C received, shutting down agent");
                        Ok(())
                    }
                }
            } else {
                tokio::select! {
                    result = run_agent(config_dir.as_deref(), config_file.as_deref()) => result,
                    _ = tokio::signal::ctrl_c() => {
                        tracing::info!("Ctrl+C received, shutting down agent");
                        Ok(())
                    }
                }
            }
        }
        Commands::Init { yes } => init::run(config_dir.as_deref(), yes).await,
        Commands::Models { json } => {
            list_models(config_dir.as_deref(), config_file.as_deref(), json)
        }
        Commands::Agents { json } => list_agents(config_dir.as_deref(), json),
        Commands::Serve { name, port, host } => {
            tokio::select! {
                result = serve_command(name, host, port, config_dir.as_deref()) => result,
                _ = tokio::signal::ctrl_c() => {
                    eprintln!("\n· serve stopped");
                    Ok(())
                }
            }
        }
        Commands::Auth { command } => match command {
            None | Some(AuthCommand::List) => {
                let config =
                    config::Config::load(config_dir.as_deref(), config_file.as_deref())?;
                println!(
                    "{}",
                    serde_json::to_string_pretty(&agent::config_auth_methods(&config))?
                );
                Ok(())
            }
            Some(AuthCommand::Login { method_id, value }) => {
                let settings = ClientSettings::load(config_dir.as_deref())?;
                let dir = client_settings::config_dir_path(config_dir.as_deref())?;
                auth_call(default_target(&settings, &dir)?, AuthOp::Login { method_id, value }).await
            }
            Some(AuthCommand::Logout) => {
                let settings = ClientSettings::load(config_dir.as_deref())?;
                let dir = client_settings::config_dir_path(config_dir.as_deref())?;
                auth_call(default_target(&settings, &dir)?, AuthOp::Logout).await
            }
        },
        Commands::Daemon { command } => {
            let dir = client_settings::config_dir_path(config_dir.as_deref())?;
            let settings = ClientSettings::load(config_dir.as_deref())?;
            let daemon_cfg = |name: &str| -> anyhow::Result<&client_settings::AgentServerConfig> {
                settings
                    .agent_servers
                    .get(name)
                    .ok_or_else(|| anyhow::anyhow!("'{name}' not found in client_settings.yaml"))
            };
            match command {
                DaemonCommand::Start { name } => {
                    let pid = daemon::start(&dir, &name, daemon_cfg(&name)?)?;
                    println!("started {name} (pid {pid})");
                    Ok(())
                }
                DaemonCommand::Stop { name } => {
                    daemon::stop(&dir, &name)?;
                    println!("stopped {name}");
                    Ok(())
                }
                DaemonCommand::Restart { name } => {
                    if daemon::running_pid(&dir, &name).is_some() {
                        daemon::stop(&dir, &name)?;
                    }
                    let pid = daemon::start(&dir, &name, daemon_cfg(&name)?)?;
                    println!("restarted {name} (pid {pid})");
                    Ok(())
                }
                DaemonCommand::Status { name, json } => {
                    let statuses: Vec<daemon::Status> = match &name {
                        Some(n) => vec![daemon::status(&dir, n, daemon_cfg(n)?)],
                        None => settings
                            .agent_servers
                            .iter()
                            .filter(|(_, c)| c.port.is_some())
                            .map(|(n, c)| daemon::status(&dir, n, c))
                            .collect(),
                    };
                    print_statuses(&statuses, json);
                    Ok(())
                }
                DaemonCommand::List { json } => {
                    let statuses: Vec<daemon::Status> = settings
                        .agent_servers
                        .iter()
                        .filter(|(_, c)| c.port.is_some())
                        .map(|(n, c)| daemon::status(&dir, n, c))
                        .collect();
                    print_statuses(&statuses, json);
                    Ok(())
                }
                DaemonCommand::Install { name, no_verify } => {
                    if name == embeddings::SERVICE_NAME {
                        let mut s = ClientSettings::load(Some(&dir))?;
                        let cfg = embeddings::provision(&dir, &mut s)?;
                        let pid = daemon::install(&dir, &name, &cfg)?;
                        println!(
                            "installed {} (pid {pid}) — managed by systemd",
                            daemon::unit_name(&name)
                        );
                        if !no_verify {
                            embeddings::verify_embeddings(
                                cfg.port.unwrap_or(embeddings::PORT),
                            )
                            .await?;
                        }
                        return Ok(());
                    }
                    let pid = daemon::install(&dir, &name, daemon_cfg(&name)?)?;
                    println!(
                        "installed {} (pid {pid}) — managed by systemd",
                        daemon::unit_name(&name)
                    );
                    Ok(())
                }
                DaemonCommand::Uninstall { name } => {
                    daemon::uninstall(&name)?;
                    println!("uninstalled {}", daemon::unit_name(&name));
                    Ok(())
                }
            }
        }
        Commands::Run { words, prompt_file, session, json, agent, model, headless } => {
            run_command(words, prompt_file, session, json, agent, model, headless, config_dir.as_deref())
                .await
        }
    }
}

/// What `crow-cli run` connects to.
enum RunTarget {
    Single { agent: AcpAgent, model: Option<String> },
    /// Conductor proxy chain; the final component is the agent.
    Chain { components: Vec<AcpAgent>, model: Option<String> },
}

/// Resolve `crow-cli run` arguments against client_settings.yaml and go.
#[allow(clippy::too_many_arguments)]
async fn run_command(
    words: Vec<String>,
    prompt_file: Option<std::path::PathBuf>,
    resume_id: Option<String>,
    json: bool,
    agent_override: Option<String>,
    model: Option<String>,
    headless: bool,
    config_dir: Option<&std::path::Path>,
) -> anyhow::Result<()> {
    if headless {
        anyhow::ensure!(
            !words.is_empty() || prompt_file.is_some(),
            "--headless needs a prompt (words or -p file) — there is no stdin to read"
        );
        return run_headless(config_dir);
    }
    let settings = ClientSettings::load(config_dir)?;

    // Prompt: file contents first, trailing words appended.
    let mut prompt_parts: Vec<String> = Vec::new();
    if let Some(path) = &prompt_file {
        let text = std::fs::read_to_string(path)
            .map_err(|e| anyhow::anyhow!("{}: {e}", path.display()))?;
        prompt_parts.push(text);
    }

    // First word names a server/chain when it resolves; otherwise it's prompt text.
    let (name, rest) = match words.split_first() {
        Some((first, rest)) if agent_override.is_none() && settings.contains(first) => {
            (Some(first.as_str()), rest)
        }
        _ => (None, words.as_slice()),
    };
    prompt_parts.extend(rest.iter().cloned());
    let prompt = if prompt_parts.is_empty() {
        None
    } else {
        Some(prompt_parts.join(" "))
    };

    let dir = client_settings::config_dir_path(config_dir)?;
    // -a/--agent: a client_settings name resolves first; otherwise it's a raw
    // command string.
    let override_name = agent_override
        .as_ref()
        .filter(|c| settings.contains(c))
        .cloned();
    let mut target = if let Some(name) = &override_name {
        resolve_target(&settings, name, &dir)?
    } else if let Some(cmd) = agent_override {
        RunTarget::Single {
            agent: AcpAgent::from_str(&cmd)
                .map_err(|e| anyhow::anyhow!("failed to parse agent command: {e}"))?,
            model: None,
        }
    } else if let Some(name) = name {
        resolve_target(&settings, name, &dir)?
    } else {
        default_target(&settings, &dir)?
    };

    // --model overrides client_settings default_config_options.
    if let Some(m) = model {
        match &mut target {
            RunTarget::Single { model, .. } => *model = Some(m),
            RunTarget::Chain { model, .. } => *model = Some(m),
        }
    }

    let label = name
        .map(str::to_string)
        .or(override_name)
        .or_else(|| settings.default.clone())
        .unwrap_or_else(|| "agent".to_string());

    run_client(target, label, prompt, resume_id, json).await
}

/// The default target: client_settings `default`, else our own ACP agent mode.
fn default_target(settings: &ClientSettings, config_dir: &std::path::Path) -> anyhow::Result<RunTarget> {
    if let Some(name) = settings.default.as_deref() {
        return resolve_target(settings, name, config_dir);
    }
    let exe = std::env::current_exe()?;
    Ok(RunTarget::Single {
        agent: AcpAgent::from_str(&format!("{} acp", exe.display()))
            .map_err(|e| anyhow::anyhow!("{e}"))?,
        model: None,
    })
}

/// Resolve a client_settings name to component command strings + model.
/// Unknown names are treated as raw agent command strings. Required daemons
/// (`requires:`) are auto-started on the way. Shared by `run` and `serve`.
fn resolve_commands(
    settings: &ClientSettings,
    name: &str,
    config_dir: &std::path::Path,
) -> anyhow::Result<(Vec<String>, Option<String>)> {
    let ensure_requires = |cfg: &client_settings::AgentServerConfig| -> anyhow::Result<()> {
        for r in &cfg.requires {
            daemon::ensure_running(config_dir, settings, r)?;
        }
        Ok(())
    };

    if let Some(chain) = settings.chains.get(name) {
        anyhow::ensure!(
            !chain.components.is_empty(),
            "chain '{name}' has no components"
        );
        let mut commands = Vec::new();
        let mut model = None;
        for c in &chain.components {
            if let Some(cfg) = settings.agent_servers.get(c) {
                ensure_requires(cfg)?;
                commands.push(ClientSettings::server_command(cfg));
                if cfg.default_config_options.model.is_some() {
                    model = cfg.default_config_options.model.clone();
                }
            } else {
                commands.push(c.clone());
            }
        }
        Ok((commands, model))
    } else if let Some(cfg) = settings.agent_servers.get(name) {
        ensure_requires(cfg)?;
        Ok((
            vec![ClientSettings::server_command(cfg)],
            cfg.default_config_options.model.clone(),
        ))
    } else {
        Ok((vec![name.to_string()], None))
    }
}

/// Resolve a name from client_settings.yaml to a run target. Unknown names
/// are treated as raw agent command strings. Required daemons (`requires:`)
/// are auto-started on the way.
fn resolve_target(
    settings: &ClientSettings,
    name: &str,
    config_dir: &std::path::Path,
) -> anyhow::Result<RunTarget> {
    let parse = |s: &str| {
        AcpAgent::from_str(s).map_err(|e| anyhow::anyhow!("agent '{s}': {e}"))
    };
    let (commands, model) = resolve_commands(settings, name, config_dir)?;
    let mut agents = Vec::with_capacity(commands.len());
    for c in &commands {
        agents.push(parse(c)?);
    }
    if agents.len() == 1 {
        Ok(RunTarget::Single {
            agent: agents.pop().unwrap(),
            model,
        })
    } else {
        Ok(RunTarget::Chain {
            components: agents,
            model,
        })
    }
}

fn print_statuses(statuses: &[daemon::Status], json: bool) {
    if json {
        println!(
            "{}",
            serde_json::to_string_pretty(statuses).expect("serialize")
        );
        return;
    }
    // Markdown table through the streamdown renderer (12.6).
    let mut md = String::from("| NAME | PORT | PID | MANAGED | STATE |\n|---|---|---|---|---|\n");
    for s in statuses {
        let state = match (s.running, s.healthy) {
            (false, _) => "stopped".to_string(),
            (true, Some(true)) => "running (healthy)".to_string(),
            (true, Some(false)) => "running (unhealthy)".to_string(),
            (true, None) => "running".to_string(),
        };
        md.push_str(&format!(
            "| {} | {} | {} | {} | {} |\n",
            md_cell(&s.name),
            md_cell(&s.port.map(|p| p.to_string()).unwrap_or_default()),
            md_cell(&s.pid.map(|p| p.to_string()).unwrap_or_default()),
            md_cell(&s.managed_by),
            md_cell(&state)
        ));
    }
    render::print_markdown(&md);
}

const AGENTS_HELP: &str = r#"Defining agents — ~/.agents/crow/client_settings.yaml:

  agent_servers:
    crow:                          # a stdio ACP agent (spawned per run)
      command: crow-cli
      args: [acp]
      default_config_options:
        model: qwen3.8-max-preview # model for `run` (see `crow-cli models`)
    my-daemon:                     # a long-running HTTP service
      command: /path/to/server
      args: ["--port", "8082"]
      env: { RUST_LOG: info }
      port: 8082                   # makes it a daemon: crow-cli daemon start/…
      requires: [ollama-mv]        # auto-started before this agent runs
  chains:
    verifier:                      # conductor proxy chain; LAST = the agent
      components: [crow-verifier, crow]
  default: crow                    # target for bare `crow-cli run`

Run them:  crow-cli run <name>            (or: crow-cli run -a <name>)
           crow-cli run -a 'cmd args…'    (raw command, no settings entry)
Manage daemons:  crow-cli daemon start|stop|restart|status|list
                 crow-cli daemon install <name>   (systemd: boot + self-heal)"#;

/// List agents (servers) and chains from client_settings.yaml.
/// Escape a value for a markdown table cell (12.6).
fn md_cell(s: impl std::fmt::Display) -> String {
    s.to_string().replace('|', "\\|")
}

fn list_agents(config_dir: Option<&std::path::Path>, json: bool) -> anyhow::Result<()> {
    let settings = ClientSettings::load(config_dir)?;
    anyhow::ensure!(
        !settings.agent_servers.is_empty() || !settings.chains.is_empty(),
        "no agents declared in {}",
        client_settings::config_dir_path(config_dir)?
            .join("client_settings.yaml")
            .display()
    );
    let default = settings.default.clone().unwrap_or_default();
    if json {
        let servers: Vec<serde_json::Value> = settings
            .agent_servers
            .iter()
            .map(|(name, c)| {
                serde_json::json!({
                    "name": name,
                    "kind": if c.port.is_some() { "daemon" } else { "agent" },
                    "command": c.command,
                    "args": c.args,
                    "port": c.port,
                    "requires": c.requires,
                    "default": *name == default,
                })
            })
            .collect();
        let chains: Vec<serde_json::Value> = settings
            .chains
            .iter()
            .map(|(name, c)| serde_json::json!({"name": name, "components": c.components}))
            .collect();
        println!(
            "{}",
            serde_json::json!({"agents": servers, "chains": chains, "default": default})
        );
        return Ok(());
    }
    // Markdown table through the streamdown renderer (12.6).
    let mut md = String::from("|   | NAME | KIND | PORT | HOW |\n|---|---|---|---|---|\n");
    for (name, c) in &settings.agent_servers {
        // Backticks: a bare `*` cell is eaten by the markdown inline parser.
        let mark = if *name == default { "`*`" } else { "" };
        let kind = if c.port.is_some() { "daemon" } else { "agent" };
        // Basename keeps the table human-readable; -j has the full paths.
        let bin = std::path::Path::new(&c.command)
            .file_name()
            .map(|f| f.to_string_lossy().into_owned())
            .unwrap_or_else(|| c.command.clone());
        let how = if c.args.is_empty() {
            bin
        } else {
            format!("{} {}", bin, c.args.join(" "))
        };
        md.push_str(&format!(
            "| {mark} | {} | {kind} | {} | {} |\n",
            md_cell(name),
            md_cell(&c.port.map(|p| p.to_string()).unwrap_or_default()),
            md_cell(&how)
        ));
    }
    for (name, c) in &settings.chains {
        // Backticks: a bare `*` cell is eaten by the markdown inline parser.
        let mark = if *name == default { "`*`" } else { "" };
        md.push_str(&format!(
            "| {mark} | {} | chain | | chain: {} |\n",
            md_cell(name),
            md_cell(&c.components.join(" → "))
        ));
    }
    render::print_markdown(&md);
    Ok(())
}

/// List models configured in config.yaml (first entry is the default).
fn list_models(    config_dir: Option<&std::path::Path>,
    config_file: Option<&std::path::Path>,
    json: bool,
) -> anyhow::Result<()> {
    let config = config::Config::load(config_dir, config_file)?;
    anyhow::ensure!(
        !config.models.is_empty(),
        "no models configured in {}",
        config.config_dir.join("config.yaml").display()
    );
    if json {
        let out: Vec<serde_json::Value> = config
            .models
            .iter()
            .enumerate()
            .map(|(i, (name, m))| {
                serde_json::json!({
                    "name": name,
                    "provider": m.provider,
                    "model": m.model,
                    "default": i == 0,
                })
            })
            .collect();
        println!("{}", serde_json::to_string_pretty(&out)?);
        return Ok(());
    }
    // Markdown table through the streamdown renderer (12.6).
    let mut md = String::from("|   | MODEL | PROVIDER / MODEL |\n|---|---|---|\n");
    for (i, (name, m)) in config.models.iter().enumerate() {
        // Backticks: a bare `*` cell is eaten by the markdown inline parser.
        let mark = if i == 0 { "`*`" } else { "" };
        md.push_str(&format!(
            "| {mark} | {} | {}/{} |\n",
            md_cell(name),
            md_cell(&m.provider),
            md_cell(&m.model)
        ));
    }
    md.push_str("\n`*` = default. Override per-run: `crow-cli run -m <name-or-id> \"...\"`");
    render::print_markdown(&md);
    Ok(())
}

/// Serve a resolved target as a persistent ACP HTTP endpoint (9.6). Each HTTP
/// connection gets a FRESH component instance (spawned stdio subprocess(es)):
/// single agents bridge directly, chains go through an embedded conductor.
async fn serve_command(
    name: String,
    host: String,
    port: u16,
    config_dir: Option<&std::path::Path>,
) -> anyhow::Result<()> {
    use agent_client_protocol::DynConnectTo;
    use agent_client_protocol_conductor::{CommandLineComponents, ConductorImpl};
    use agent_client_protocol_http::AcpHttpServer;

    let settings = ClientSettings::load(config_dir)?;
    let dir = client_settings::config_dir_path(config_dir)?;
    let (commands, _) = resolve_commands(&settings, &name, &dir)?;

    // Validate once up front; the factory rebuilds agents per connection.
    let mut configs = Vec::with_capacity(commands.len());
    for c in &commands {
        configs.push(
            AcpAgent::from_str(c)
                .map_err(|e| anyhow::anyhow!("agent '{c}': {e}"))?
                .config()
                .clone(),
        );
    }

    let server = AcpHttpServer::new(move || -> DynConnectTo<Client> {
        let agents: Vec<AcpAgent> = configs.iter().map(|c| AcpAgent::new(c.clone())).collect();
        if agents.len() == 1 {
            DynConnectTo::new(agents.into_iter().next().unwrap())
        } else {
            DynConnectTo::new(ConductorImpl::new_agent(
                "crow-cli-serve",
                CommandLineComponents(agents),
            ))
        }
    });

    let addr = format!("{host}:{port}");
    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .map_err(|e| anyhow::anyhow!("bind {addr}: {e}"))?;
    eprintln!("· serving '{name}' over ACP HTTP on http://{addr}/acp  (health: /health)");
    axum::serve(listener, server.into_router())
        .await
        .map_err(|e| anyhow::anyhow!("serve: {e}"))?;
    Ok(())
}

/// Relay mode: thin stdio ACP front for a resident daemon. A conductor in
/// agent mode with zero proxies — upstream speaks ACP over stdio (what an
/// IDE spawns), downstream is an HTTP client to `crow-cli acp --http`. All
/// state lives in the daemon; this process is disposable.
async fn run_relay(url: &str) -> anyhow::Result<()> {
    use agent_client_protocol_conductor::{AgentOnly, ConductorImpl};
    use agent_client_protocol_http::HttpClient;

    let http = HttpClient::new(url).map_err(|e| anyhow::anyhow!("relay: {e}"))?;
    let conductor = ConductorImpl::new_agent("crow-relay", AgentOnly(http));
    tracing::info!("relay: stdio -> {url}");
    conductor
        .run(Stdio::new())
        .await
        .map_err(|e| anyhow::anyhow!("relay: {e}"))
}

/// Run as ACP v2 agent over stdio.
async fn run_agent(
    config_dir: Option<&std::path::Path>,
    config_file: Option<&std::path::Path>,
) -> anyhow::Result<()> {
    let config = config::Config::load(config_dir, config_file)?;
    if !config.is_configured() {
        anyhow::bail!("no LLM providers/models configured in ~/.agents/crow/config.yaml");
    }

    let store = std::sync::Arc::new(crow_memory_sdk::MemoryClient::connect(&config.memory_url));
    let crow = agent::CrowAgent::new(config, store);
    crow.connect_to(Stdio::new()).await?;
    Ok(())
}

/// 13.2: run as ONE resident multi-session ACP v2 agent over HTTP/SSE.
/// Every connection gets a clone of the same CrowAgent (cheap: all-Arc
/// state), so sessions stay resident across connection drops and resume is
/// the fast in-memory path.
async fn run_agent_http(
    config_dir: Option<&std::path::Path>,
    config_file: Option<&std::path::Path>,
    host: String,
    port: u16,
) -> anyhow::Result<()> {
    use agent_client_protocol::DynConnectTo;
    use agent_client_protocol_http::AcpHttpServer;

    let config = config::Config::load(config_dir, config_file)?;
    if !config.is_configured() {
        anyhow::bail!("no LLM providers/models configured in ~/.agents/crow/config.yaml");
    }

    let store = std::sync::Arc::new(crow_memory_sdk::MemoryClient::connect(&config.memory_url));
    let crow = agent::CrowAgent::new(config, store);

    let server = AcpHttpServer::new(move || DynConnectTo::new(crow.clone()));

    let addr = format!("{host}:{port}");
    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .map_err(|e| anyhow::anyhow!("bind {addr}: {e}"))?;
    eprintln!("· serving crow ACP agent on http://{addr}/acp  (health: /health)");
    axum::serve(listener, server.into_router())
        .await
        .map_err(|e| anyhow::anyhow!("serve: {e}"))?;
    Ok(())
}

/// Run as client against the resolved target.
async fn run_client(
    target: RunTarget,
    label: String,
    one_shot: Option<String>,
    resume_id: Option<String>,
    json: bool,
) -> anyhow::Result<()> {
    let model = match &target {
        RunTarget::Single { model, .. } => model.clone(),
        RunTarget::Chain { model, .. } => model.clone(),
    };

    let result = match target {
        RunTarget::Single { agent, .. } => {
            run_session(agent, label, one_shot, resume_id, json, model).await
        }
        RunTarget::Chain { components, .. } => {
            // Embedded conductor: client ↔ in-memory channel ↔ proxy chain.
            use agent_client_protocol_conductor::{CommandLineComponents, ConductorImpl};
            let (client_end, conductor_end) = Channel::duplex();
            tokio::spawn(async move {
                let conductor =
                    ConductorImpl::new_agent("crow-cli", CommandLineComponents(components));
                if let Err(e) = conductor.run(conductor_end).await {
                    tracing::error!("conductor exited: {e}");
                }
            });
            run_session(client_end, label, one_shot, resume_id, json, model).await
        }
    };

    if let Err(e) = result {
        if json {
            println!("{}", serde_json::json!({ "error": e.to_string() }));
        } else {
            eprintln!("error: {e}");
        }
        std::process::exit(1);
    }
    Ok(())
}

/// 12.5: fire-and-forget run. Re-exec ourselves with `--headless` stripped and
/// `--json` forced (machine-parseable session line), detached with stdio into
/// a log file; print session id + pid + log path once the child reports the
/// session, then exit — the child keeps working. Log naming follows the v1
/// convention: `logs/crow-cli-{session_id}.log` (renamed from a temp name
/// once the session id is known).
fn run_headless(config_dir: Option<&std::path::Path>) -> anyhow::Result<()> {
    let exe = std::env::current_exe()?;
    let mut args: Vec<String> = std::env::args()
        .skip(1)
        .filter(|a| a != "--headless")
        .collect();
    if !args.iter().any(|a| a == "--json" || a == "-j") {
        let pos = args
            .iter()
            .position(|a| a == "run")
            .ok_or_else(|| anyhow::anyhow!("--headless only works with `run`"))?;
        args.insert(pos + 1, "--json".into());
    }

    let dir = client_settings::config_dir_path(config_dir)?;
    std::fs::create_dir_all(dir.join("logs"))?;
    let ts = chrono::Utc::now().format("%Y%m%d-%H%M%S");
    let log_path = dir
        .join("logs")
        .join(format!("headless-{ts}-{}.log", std::process::id()));
    let log = std::fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
    let err = log.try_clone()?;

    let child = std::process::Command::new(&exe)
        .args(&args)
        .stdin(std::process::Stdio::null())
        .stdout(log)
        .stderr(err)
        .process_group(0)
        .spawn()?;
    let pid = child.id();

    // The child prints {"session":{"id":...}} as its first JSON line once the
    // session exists. First session/new pays MCP connect costs — poll 60s.
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(60);
    loop {
        if !daemon::alive(pid) {
            anyhow::bail!(
                "headless run exited during startup — see {}",
                log_path.display()
            );
        }
        if let Ok(contents) = std::fs::read_to_string(&log_path) {
            if let Some(line) = contents
                .lines()
                .find(|l| l.trim_start().starts_with('{'))
            {
                if let Ok(v) = serde_json::from_str::<serde_json::Value>(line) {
                    if v.get("session").is_some() {
                        // v1 convention: logs/crow-cli-{session_id}.log —
                        // rename now that the id is known (the child's open fd
                        // follows the inode).
                        let id = v["session"]["id"]
                            .as_str()
                            .ok_or_else(|| anyhow::anyhow!("session line missing id"))?;
                        let final_path =
                            dir.join("logs").join(format!("crow-cli-{id}.log"));
                        std::fs::rename(&log_path, &final_path)?;
                        println!(
                            "{}",
                            serde_json::json!({
                                "session": v["session"],
                                "pid": pid,
                                "log": final_path.display().to_string(),
                            })
                        );
                        return Ok(());
                    }
                }
            }
        }
        if std::time::Instant::now() > deadline {
            anyhow::bail!("no session id within 60s — see {}", log_path.display());
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
}

/// Client session loop over any agent-side endpoint (spawned AcpAgent or an
/// in-memory channel into the embedded conductor).
#[derive(Debug, Clone, PartialEq)]
enum TurnState {
    Idle,
    Running,
}

/// How a turn ended (drives REPL vs exit).
enum TurnEnd {
    /// Agent finished on its own.
    Idle,
    /// Ctrl+C cancelled the active work; the agent persisted its state.
    Cancelled,
    /// Ctrl+C while idle — the human wants out.
    Quit,
}

/// Wait out the current turn. Ctrl+C mid-turn sends `session/cancel` and
/// waits (bounded) for the agent's idle so partial work is persisted —
/// abrupt process death is what loses history. Ctrl+C while idle quits.
/// A second Ctrl+C during the persistence wait aborts immediately.
async fn wait_turn<L: agent_client_protocol::role::HasPeer<agent_client_protocol::Agent>>(
    session: &agent_client_protocol::V2Session<L>,
    mut rx: tokio::sync::watch::Receiver<TurnState>,
) -> Result<TurnEnd, agent_client_protocol::Error> {
    loop {
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {
                if *rx.borrow() == TurnState::Idle {
                    return Ok(TurnEnd::Quit);
                }
                let _ = session.cancel_active_work();
                eprintln!("\x1b[2m^C — cancelling; waiting for the agent to persist its state...\x1b[0m");
                let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(30);
                loop {
                    if *rx.borrow() == TurnState::Idle {
                        return Ok(TurnEnd::Cancelled);
                    }
                    tokio::select! {
                        _ = tokio::signal::ctrl_c() => return Ok(TurnEnd::Cancelled),
                        r = tokio::time::timeout_at(deadline, rx.changed()) => {
                            match r {
                                Ok(Ok(())) => {}
                                Ok(Err(e)) => {
                                    return Err(agent_client_protocol::Error::internal_error()
                                        .data(e.to_string()))
                                }
                                Err(_) => return Ok(TurnEnd::Cancelled),
                            }
                        }
                    }
                }
            }
            r = rx.changed() => {
                r.map_err(|e| agent_client_protocol::Error::internal_error().data(e.to_string()))?;
                if *rx.borrow() == TurnState::Idle {
                    return Ok(TurnEnd::Idle);
                }
            }
        }
    }
}

async fn run_session(
    endpoint: impl ConnectTo<Client>,
    label: String,
    one_shot: Option<String>,
    resume_id: Option<String>,
    json: bool,
    model: Option<String>,
) -> Result<(), agent_client_protocol::Error> {
    use agent_client_protocol::schema::{ProtocolVersion, v2 as acp};
    use tokio::sync::watch;

    let (state_tx, state_rx) = watch::channel(TurnState::Idle);
    let renderer = std::sync::Arc::new(std::sync::Mutex::new(render::CliRenderer::new()));

    Client
        .v2()
        .name("crow-cli")
        .on_receive_notification(
            {
                let state_tx = state_tx.clone();
                let renderer = renderer.clone();
                async move |notification: acp::UpdateSessionNotification,
                            _connection: agent_client_protocol::V2ConnectionTo<
                    agent_client_protocol::Agent,
                >| {
                    if json {
                        // One JSON object per line — pipe through jq.
                        if let Ok(json) = serde_json::to_string(&notification.update) {
                            println!("{json}");
                            use std::io::Write;
                            let _ = std::io::stdout().flush();
                        }
                    } else {
                        renderer.lock().unwrap().handle_update(&notification.update);
                    }

                    if let acp::SessionUpdate::StateUpdate(su) = &notification.update {
                        match su {
                            acp::StateUpdate::Running(_) => { let _ = state_tx.send(TurnState::Running); }
                            acp::StateUpdate::Idle(idle) => {
                                if let Some(r) = &idle.stop_reason { tracing::info!("stop: {r:?}"); }
                                let _ = state_tx.send(TurnState::Idle);
                            }
                            _ => {}
                        }
                    }
                    Ok(())
                }
            },
            agent_client_protocol::on_receive_notification!(),
        )
        .connect_with(endpoint, async move |connection| {
            let init = connection
                .send_request(acp::InitializeRequest::new(
                    ProtocolVersion::V2,
                    acp::Implementation::new("crow-cli", env!("CARGO_PKG_VERSION")),
                ))
                .block_task()
                .await?;
            tracing::info!("connected: {} v{}", init.info.name, init.info.version);

            let session = if let Some(sid) = &resume_id {
                // session/resume — continue an existing session by id; ask the
                // agent to replay the whole conversation so the human sees it.
                let cwd = std::env::current_dir().map_err(|e| {
                    agent_client_protocol::Error::internal_error().data(e.to_string())
                })?;
                let req = acp::ResumeSessionRequest::new(sid.as_str(), cwd).replay_from(
                    acp::ReplayFrom::Start(acp::ReplayFromStart::new()),
                );
                connection
                    .resume_session_from(req)
                    .block_task()
                    .await?
                    .into_session()
            } else {
                // Model selection rides in NewSessionRequest._meta.model.
                let builder = match &model {
                    Some(m) => {
                        let cwd = std::env::current_dir().map_err(|e| {
                            agent_client_protocol::Error::internal_error().data(e.to_string())
                        })?;
                        let mut meta = serde_json::Map::new();
                        meta.insert("model".into(), serde_json::json!(m));
                        connection
                            .build_session_from(acp::NewSessionRequest::new(cwd).meta(meta))
                    }
                    None => connection.build_session_cwd()?,
                };
                builder.start_session().block_task().await?.into_session()
            };

            let sid = session.session_id().to_string();

            if json {
                println!(
                    "{}",
                    serde_json::json!({
                        "session": {
                            "id": sid,
                            "agent": label,
                        }
                    })
                );
                use std::io::Write;
                let _ = std::io::stdout().flush();
            } else {
                // The session id is crucial information — it feeds `run -s`.
                eprintln!("\x1b[2m· session {sid} · {label}\x1b[0m");
            }

            match one_shot {
                Some(prompt) => {
                    let _ = state_tx.send(TurnState::Running);
                    session.send_prompt(&prompt).block_task().await?;
                    wait_turn(&session, state_rx.clone()).await?;
                }
                None => {
                    use tokio::io::{AsyncBufReadExt, BufReader};
                    let mut lines = BufReader::new(tokio::io::stdin()).lines();
                    loop {
                        if json {
                            eprint!("> ");
                        } else {
                            eprint!("\x1b[1m> \x1b[0m");
                        }
                        use std::io::Write;
                        let _ = std::io::stderr().flush();
                        // Ctrl+C at the prompt exits the REPL.
                        let line = tokio::select! {
                            _ = tokio::signal::ctrl_c() => None,
                            l = lines.next_line() => l.map_err(|e| agent_client_protocol::Error::internal_error().data(e.to_string()))?,
                        };
                        let Some(line) = line else { break };
                        let line = line.trim().to_string();
                        if line.is_empty() { continue; }
                        if line == "exit" || line == "quit" { break; }

                        let _ = state_tx.send(TurnState::Running);
                        session.send_prompt(&line).block_task().await?;
                        // Ctrl+C mid-turn cancels + persists, then we're back
                        // at the prompt; only a Quit (^C while idle) leaves.
                        if matches!(wait_turn(&session, state_rx.clone()).await?, TurnEnd::Quit) {
                            break;
                        }
                    }
                }
            }

            if !json {
                eprintln!("\x1b[2m⟳ continue: crow-cli run -s {sid}\x1b[0m");
            }
            session.close().block_task().await?;
            Ok(())
        })
        .await
}

/// Auth operation to run against the resolved agent.
enum AuthOp {
    Login { method_id: String, value: Option<String> },
    Logout,
}

/// Run an auth op against the target (same endpoint plumbing as `run`).
async fn auth_call(target: RunTarget, op: AuthOp) -> anyhow::Result<()> {
    let result = match target {
        RunTarget::Single { agent, .. } => auth_session(agent, op).await,
        RunTarget::Chain { components, .. } => {
            use agent_client_protocol_conductor::{CommandLineComponents, ConductorImpl};
            let (client_end, conductor_end) = Channel::duplex();
            tokio::spawn(async move {
                let conductor =
                    ConductorImpl::new_agent("crow-cli", CommandLineComponents(components));
                if let Err(e) = conductor.run(conductor_end).await {
                    tracing::error!("conductor exited: {e}");
                }
            });
            auth_session(client_end, op).await
        }
    };
    if let Err(e) = result {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
    Ok(())
}

/// Connect, initialize, then issue auth/login or auth/logout.
async fn auth_session(
    endpoint: impl ConnectTo<Client>,
    op: AuthOp,
) -> Result<(), agent_client_protocol::Error> {
    use agent_client_protocol::schema::{ProtocolVersion, v2 as acp};
    Client
        .v2()
        .name("crow-cli")
        .connect_with(endpoint, async move |connection| {
            let init = connection
                .send_request(acp::InitializeRequest::new(
                    ProtocolVersion::V2,
                    acp::Implementation::new("crow-cli", env!("CARGO_PKG_VERSION")),
                ))
                .block_task()
                .await?;
            tracing::info!("connected: {} v{}", init.info.name, init.info.version);

            match op {
                AuthOp::Login { method_id, value } => {
                    let mut req = acp::LoginAuthRequest::new(acp::AuthMethodId::new(
                        std::sync::Arc::from(method_id.as_str()),
                    ));
                    if let Some(v) = value {
                        let mut meta = serde_json::Map::new();
                        meta.insert("value".into(), serde_json::json!(v));
                        req = req.meta(meta);
                    }
                    connection.send_request(req).block_task().await?;
                    println!("logged in: {method_id}");
                }
                AuthOp::Logout => {
                    connection
                        .send_request(acp::LogoutAuthRequest::new())
                        .block_task()
                        .await?;
                    println!("logged out");
                }
            }
            Ok(())
        })
        .await
}
