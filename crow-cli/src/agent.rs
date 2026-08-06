//! ACP v2 agent — crow-cli wired with Agent.v2().
//!
//! Implements the full v2 prompt lifecycle (§4 of the acp-v2 skill):
//! UserMessage → Running → work → Idle → PromptResponse ack.
//! Foreground work enforcement, history recording for resume replay,
//! session/list and session/resume handlers.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use agent_client_protocol::{
    Agent, Client, ConnectTo, Responder, V2ConnectionTo,
    schema::v2 as acp,
};
use async_openai_thinking::types::chat::ChatCompletionTools;
use rmcp::service::{RoleClient, RunningService};
use rmcp::transport::TokioChildProcess;
use tokio::sync::Mutex;
use tokio_util::sync::CancellationToken;

use crate::config::Config;
use crate::llm;
use crow_memory_sdk::MemoryClient;
use crate::react;
use crate::session::{self, AgentSession};

/// MCP client handler — receives server→client notifications. Progress
/// notifications carry crow-mcp's live terminal byte chunks (base64 in
/// `message`, keyed by the request progressToken); the react loop relays them
/// to the ACP client as `terminal_output_chunk` updates while the tool runs.
pub struct McpHandler {
    pub progress_tx: tokio::sync::mpsc::UnboundedSender<rmcp::model::ProgressNotificationParam>,
}

impl rmcp::handler::client::ClientHandler for McpHandler {
    fn on_progress(
        &self,
        params: rmcp::model::ProgressNotificationParam,
        _context: rmcp::service::NotificationContext<rmcp::RoleClient>,
    ) -> impl std::future::Future<Output = ()> + rmcp::service::MaybeSendFuture + '_ {
        let _ = self.progress_tx.send(params);
        std::future::ready(())
    }
}

type McpClient = Arc<RunningService<RoleClient, McpHandler>>;

#[derive(Clone)]
pub struct CrowAgent {
    config: Arc<Config>,
    store: Arc<MemoryClient>,
    state: Arc<Mutex<AgentState>>,
    /// Foreground cancel token per session id. Kept OUTSIDE `state`: the
    /// prompt handler holds the state lock for the entire turn (react loop
    /// borrows the session), so the cancel handler must not depend on it —
    /// otherwise cancels only land after the work already finished.
    cancel_tokens: Arc<std::sync::Mutex<HashMap<String, CancellationToken>>>,
}
struct AgentState {
    sessions: HashMap<String, Arc<SessionInner>>,
}

/// Session entry: the attach points that must work WHILE a turn holds the
/// exclusive state (14.1 — resume mid-turn subscribes to the fan-out), plus
/// the exclusive state the turn borrows for its whole react loop.
struct SessionInner {
    /// Session update fan-out. The turn publishes here; every attached
    /// connection runs a pump that forwards to its client. Cloning/subscribing
    /// needs no lock, so reconnects attach mid-turn.
    update_tx: tokio::sync::broadcast::Sender<acp::SessionUpdate>,
    /// True while a prompt turn is in flight. v2 requires one foreground
    /// prompt per session — reject new prompts while this is set. Atomic so
    /// the check never waits on the turn's lock.
    foreground: std::sync::atomic::AtomicBool,
    state: tokio::sync::Mutex<SessionState>,
}

struct SessionState {
    session: AgentSession,
    mcp_clients: Vec<McpClient>,
    tools: Vec<ChatCompletionTools>,
    llm: async_openai_thinking::Client<async_openai_thinking::config::OpenAIConfig>,
    cancel: CancellationToken,
    /// Monotonic counter for agent-owned message IDs.
    msg_counter: u64,
    /// Recorded whole-message upserts for session/resume replay.
    history: Vec<acp::SessionUpdate>,
    /// Soft cancel: send a message here to inject it into the react loop
    /// after the current tool finishes. The loop re-enters with this as
    /// new user context instead of continuing the old turn.
    msg_tx: tokio::sync::mpsc::Sender<String>,
    msg_rx: tokio::sync::mpsc::Receiver<String>,
    /// MCP progress notifications (live terminal bytes) from our MCP servers.
    progress_rx: tokio::sync::mpsc::UnboundedReceiver<rmcp::model::ProgressNotificationParam>,
}

impl SessionState {
    fn next_msg_id(&mut self) -> String {
        self.msg_counter += 1;
        format!("msg-{}", self.msg_counter)
    }

    fn record(&mut self, update: acp::SessionUpdate) {
        self.history.push(update);
    }
}

impl CrowAgent {
    pub fn new(config: Config, store: Arc<MemoryClient>) -> Self {
        Self {
            config: Arc::new(config),
            store,
            state: Arc::new(Mutex::new(AgentState {
                sessions: HashMap::new(),
            })),
            cancel_tokens: Arc::new(std::sync::Mutex::new(HashMap::new())),
        }
    }

    async fn setup_mcp(
        &self,
    ) -> (
        Vec<McpClient>,
        Vec<ChatCompletionTools>,
        tokio::sync::mpsc::UnboundedReceiver<rmcp::model::ProgressNotificationParam>,
    ) {
        let mut clients = Vec::new();
        let (progress_tx, progress_rx) = tokio::sync::mpsc::unbounded_channel();

        for (name, cfg) in &self.config.mcp_servers {
            let Some(command) = &cfg.command else {
                continue;
            };

            let mut cmd = tokio::process::Command::new(command);
            if let Some(args) = &cfg.args {
                cmd.args(args);
            }
            if let Some(env) = &cfg.env {
                cmd.envs(env);
            }

            let Ok(transport) = TokioChildProcess::builder(cmd).spawn() else {
                tracing::warn!("failed to spawn MCP '{name}'");
                continue;
            };

            match rmcp::service::serve_client(
                McpHandler {
                    progress_tx: progress_tx.clone(),
                },
                transport.0,
            )
            .await
            {
                Ok(client) => {
                    tracing::info!("connected MCP '{name}'");
                    clients.push(Arc::new(client));
                }
                Err(e) => tracing::warn!("MCP '{name}' init failed: {e}"),
            }
        }

        use async_openai_thinking::types::chat::{ChatCompletionTool, FunctionObject};
        let mut tools = Vec::new();
        for client in &clients {
            if let Ok(mcp_tools) = client.peer().list_all_tools().await {
                for t in mcp_tools {
                    tools.push(ChatCompletionTools::Function(ChatCompletionTool {
                        function: FunctionObject {
                            name: t.name.to_string(),
                            description: t.description.as_ref().map(|d| d.to_string()),
                            parameters: Some(
                                serde_json::to_value(&t.input_schema).unwrap_or_default(),
                            ),
                            strict: None,
                        },
                    }));
                }
            }
        }

        tracing::info!("{} tools from {} MCP servers", tools.len(), clients.len());
        (clients, tools, progress_rx)
    }
}

fn send_update(
    conn: &V2ConnectionTo<Client>,
    session_id: &acp::SessionId,
    update: acp::SessionUpdate,
) -> Result<(), agent_client_protocol::Error> {
    conn.send_notification(acp::UpdateSessionNotification::new(
        session_id.clone(),
        update,
    ))
}

/// 14.1: forward a session's update fan-out to one connection for as long as
/// that connection lives. The turn task publishes to the broadcast channel
/// independently of any connection, so its work keeps running when the
/// connection drops; a fresh connection just attaches another pump.
fn spawn_pump(
    connection: &V2ConnectionTo<Client>,
    session_id: acp::SessionId,
    mut rx: tokio::sync::broadcast::Receiver<acp::SessionUpdate>,
) {
    let conn = connection.clone();
    let sid = session_id.to_string();
    let _ = connection.spawn(async move {
        tracing::info!("pump attached for {sid}");
        loop {
            match rx.recv().await {
                Ok(update) => {
                    if let Err(e) = send_update(&conn, &session_id, update) {
                        tracing::warn!("pump for {sid}: send failed: {e}");
                        break;
                    }
                }
                Err(tokio::sync::broadcast::error::RecvError::Lagged(n)) => {
                    tracing::debug!("pump for {sid}: lagged {n} updates");
                }
                Err(tokio::sync::broadcast::error::RecvError::Closed) => {
                    tracing::info!("pump for {sid}: channel closed");
                    break;
                }
            }
        }
        Ok(())
    });
}

impl ConnectTo<Client> for CrowAgent {
    async fn connect_to(
        self,
        client: impl ConnectTo<Agent>,
    ) -> Result<(), agent_client_protocol::Error> {
        Agent
            .v2()
            .name("crow-cli")
            // ---- initialize ----
            .on_receive_request(
                {
                    let agent = self.clone();
                    async move |req: acp::InitializeRequest,
                                responder: Responder<acp::InitializeResponse>,
                                _: V2ConnectionTo<Client>| {
                        responder.respond(
                            acp::InitializeResponse::new(
                                req.protocol_version,
                                acp::Implementation::new("crow-cli", env!("CARGO_PKG_VERSION")),
                            )
                            .capabilities(
                                acp::AgentCapabilities::new()
                                    .session(acp::SessionCapabilities::new()),
                            )
                            .auth_methods(config_auth_methods(&agent.config)),
                        )
                    }
                },
                agent_client_protocol::on_receive_request!(),
            )
            // ---- auth/login ----
            .on_receive_request(
                {
                    let agent = self.clone();
                    async move |req: acp::LoginAuthRequest,
                                responder: Responder<acp::LoginAuthResponse>,
                                _: V2ConnectionTo<Client>| {
                        let method = req.method_id.to_string();
                        let Some(var) = agent.config.api_key_env_refs.get(&method).cloned()
                        else {
                            return responder.respond_with_error(
                                agent_client_protocol::Error::internal_error()
                                    .data(format!("unknown auth method '{method}'")),
                            );
                        };
                        // Client-supplied key → persist to {config_dir}/.env
                        if let Some(val) = req
                            .meta
                            .as_ref()
                            .and_then(|m| m.get("value"))
                            .and_then(|v| v.as_str())
                        {
                            if let Err(e) =
                                write_env_var(&agent.config.config_dir, &var, val)
                            {
                                return responder.respond_with_error(
                                    agent_client_protocol::Error::internal_error()
                                        .data(e.to_string()),
                                );
                            }
                            unsafe { std::env::set_var(&var, val) };
                        }
                        match std::env::var(&var) {
                            Ok(v) if !v.is_empty() => {
                                responder.respond(acp::LoginAuthResponse::new())
                            }
                            _ => responder.respond_with_error(
                                agent_client_protocol::Error::internal_error().data(format!(
                                    "{var} is not set; provide it via _meta.value or the environment"
                                )),
                            ),
                        }
                    }
                },
                agent_client_protocol::on_receive_request!(),
            )
            // ---- auth/logout ----
            .on_receive_request(
                {
                    let agent = self.clone();
                    async move |_req: acp::LogoutAuthRequest,
                                responder: Responder<acp::LogoutAuthResponse>,
                                _: V2ConnectionTo<Client>| {
                        for var in agent.config.api_key_env_refs.values() {
                            remove_env_var_file(&agent.config.config_dir, var);
                            unsafe { std::env::remove_var(var) };
                        }
                        responder.respond(acp::LogoutAuthResponse::new())
                    }
                },
                agent_client_protocol::on_receive_request!(),
            )
            // ---- session/new ----
            .on_receive_request(
                {
                    let agent = self.clone();
                    async move |req: acp::NewSessionRequest,
                                responder: Responder<acp::NewSessionResponse>,
                                connection: V2ConnectionTo<Client>| {
                        let cwd = req.cwd.0.display().to_string();

                        // Model selection rides in NewSessionRequest._meta.model
                        let req_model = req
                            .meta
                            .as_ref()
                            .and_then(|m| m.get("model"))
                            .and_then(|v| v.as_str());
                        let (model_cfg, provider) = match llm::resolve_model(&agent.config, req_model) {
                            Ok(m) => m,
                            Err(e) => {
                                return responder.respond_with_error(
                                    agent_client_protocol::Error::internal_error()
                                        .data(format!("config: {e}")),
                                );
                            }
                        };

                        let llm_client = llm::make_client(provider);
                        let model_id = model_cfg.model.clone();
                        let (mcp_clients, tools, progress_rx) = agent.setup_mcp().await;

                        let tools_json = serde_json::to_value(
                            tools.iter().map(|t| serde_json::to_value(t).unwrap_or_default()).collect::<Vec<_>>()
                        ).unwrap_or_default();

                        let agent_session = match session::make_agent_session(
                            &agent.config,
                            &agent.store,
                            &tools_json,
                            &model_id,
                            &cwd,
                            None,
                            None,
                        )
                        .await
                        {
                            Ok(s) => s,
                            Err(e) => {
                                return responder.respond_with_error(
                                    agent_client_protocol::Error::internal_error()
                                        .data(format!("session: {e}")),
                                );
                            }
                        };

                        let session_id = acp::SessionId::new(agent_session.session_id.clone());
                        let sid_key = agent_session.session_id.clone();

                        let (update_tx, update_rx) = tokio::sync::broadcast::channel(4096);
                        agent.state.lock().await.sessions.insert(
                            sid_key,
                            Arc::new(SessionInner {
                                update_tx,
                                foreground: std::sync::atomic::AtomicBool::new(false),
                                state: tokio::sync::Mutex::new({
                                    let (msg_tx, msg_rx) = tokio::sync::mpsc::channel(16);
                                    SessionState {
                                        session: agent_session,
                                        mcp_clients,
                                        tools,
                                        llm: llm_client,
                                        cancel: CancellationToken::new(),
                                        msg_counter: 0,
                                        history: Vec::new(),
                                        msg_tx,
                                        msg_rx,
                                        progress_rx,
                                    }
                                }),
                            }),
                        );
                        spawn_pump(&connection, session_id.clone(), update_rx);

                        responder.respond(acp::NewSessionResponse::new(session_id))
                    }
                },
                agent_client_protocol::on_receive_request!(),
            )
            // ---- session/list ----
            .on_receive_request(
                {
                    let agent = self.clone();
                    async move |_req: acp::ListSessionsRequest,
                                responder: Responder<acp::ListSessionsResponse>,
                                _: V2ConnectionTo<Client>| {
                        let infos = match agent.store.list_sessions(50, 0).await {
                            Ok(sessions) => sessions
                                .into_iter()
                                .map(|s| {
                                    acp::SessionInfo::new(
                                        acp::SessionId::new(s.session_id),
                                        PathBuf::from(if s.cwd.is_empty() { "/tmp" } else { &s.cwd }),
                                    )
                                })
                                .collect(),
                            Err(e) => {
                                tracing::warn!("list_sessions: {e}");
                                Vec::new()
                            }
                        };
                        responder.respond(acp::ListSessionsResponse::new(infos))
                    }
                },
                agent_client_protocol::on_receive_request!(),
            )
            // ---- session/resume ----
            .on_receive_request(
                {
                    let agent = self.clone();
                    async move |req: acp::ResumeSessionRequest,
                                responder: Responder<acp::ResumeSessionResponse>,
                                connection: V2ConnectionTo<Client>| {
                        let sid_key = req.session_id.to_string();
                        let session_id = req.session_id.clone();
                        let cwd = req.cwd.0.display().to_string();
                        let wants_replay = req.replay_from.is_some();

                        // If session is already in memory, attach (and replay
                        // when idle). Must NOT block on the session lock: an
                        // in-flight turn holds it for its whole react loop —
                        // subscribe lock-free and take the live tail (14.1).
                        let inner = {
                            let state = agent.state.lock().await;
                            state.sessions.get(&sid_key).cloned()
                        };
                        if let Some(inner) = inner {
                            // Subscribe BEFORE replay so updates emitted mid-replay
                            // are not missed — if a turn is in flight, its tail
                            // arrives live on the pump.
                            let rx = inner.update_tx.subscribe();
                            match inner.state.try_lock() {
                                Ok(s) => {
                                    tracing::info!(
                                        "resume {sid_key}: in-memory fast path ({} history updates)",
                                        s.history.len()
                                    );
                                    if wants_replay {
                                        for update in &s.history {
                                            let _ = send_update(&connection, &session_id, update.clone());
                                        }
                                    }
                                }
                                Err(_) => {
                                    tracing::info!(
                                        "resume {sid_key}: attaching mid-turn (live tail only)"
                                    );
                                }
                            }
                            spawn_pump(&connection, session_id.clone(), rx);
                            return responder.respond(acp::ResumeSessionResponse::new());
                        }

                        // Otherwise, load from LanceDB and rebuild
                        let agents = match agent.store.list_agents(Some(&sid_key)).await {
                            Ok(a) if !a.is_empty() => a,
                            _ => {
                                return responder.respond_with_error(
                                    agent_client_protocol::Error::invalid_params()
                                        .data(format!("session not found: {sid_key}")),
                                );
                            }
                        };
                        let agent_record = session::pick_resume_agent(&agents);
                        tracing::info!("resume {sid_key}: rebuilding from LanceDB");

                        // Resume with the model the session was created with.
                        let saved_model = agent_record.model_identifier.clone();
                        let (_model_cfg, provider) = match llm::resolve_model(&agent.config, Some(saved_model.as_str()))
                            .or_else(|_| llm::resolve_model(&agent.config, None))
                        {
                            Ok(m) => m,
                            Err(e) => {
                                return responder.respond_with_error(
                                    agent_client_protocol::Error::internal_error()
                                        .data(format!("config: {e}")),
                                );
                            }
                        };

                        let llm_client = llm::make_client(provider);
                        let (mcp_clients, tools, progress_rx) = agent.setup_mcp().await;

                        // Load messages from LanceDB — the CURRENT generation
                        // only (compaction chain head). Repair the tail: an
                        // abrupt death (Ctrl+C / kill) can leave an assistant
                        // message whose tool_calls never got responses, which
                        // is an invalid OpenAI sequence on the next request.
                        let messages = match agent.store
                            .query_messages_by_agent(&agent_record.agent_id, true, 100_000, None)
                            .await
                        {
                            Ok(m) => crate::compact::fill_missing_tool_responses(
                                &m.into_iter().map(|m| m.data).collect::<Vec<_>>(),
                            ),
                            Err(_) => Vec::new(),
                        };

                        let agent_session = AgentSession {
                            agent_id: agent_record.agent_id.clone(),
                            session_id: sid_key.clone(),
                            agent_idx: agent_record.agent_idx,
                            cwd: cwd.clone(),
                            model_identifier: agent_record.model_identifier.clone(),
                            messages,
                            tools: agent_record.tool_definitions.clone(),
                            request_params: agent_record.request_params.clone(),
                            prompt_id: agent_record.prompt_id.clone(),
                            prompt_args: agent_record.prompt_args.clone(),
                        };

                        // Replay history from stored messages
                        if wants_replay {
                            let mut counter = 0u64;
                            for msg in &agent_session.messages {
                                counter += 1;
                                let mid = format!("msg-{counter}");
                                let role = msg.get("role").and_then(|r| r.as_str()).unwrap_or("");
                                let content_text = msg.get("content")
                                    .and_then(|c| c.as_str())
                                    .unwrap_or("")
                                    .to_string();
                                if content_text.is_empty() {
                                    continue;
                                }
                                let update = match role {
                                    "user" => acp::SessionUpdate::UserMessage(
                                        acp::UserMessage::new(mid.as_str()).content(vec![
                                            acp::ContentBlock::Text(acp::TextContent::new(&content_text)),
                                        ]),
                                    ),
                                    "assistant" => acp::SessionUpdate::AgentMessage(
                                        acp::AgentMessage::new(mid.as_str()).content(vec![
                                            acp::ContentBlock::Text(acp::TextContent::new(&content_text)),
                                        ]),
                                    ),
                                    _ => continue,
                                };
                                let _ = send_update(&connection, &session_id, update);
                            }
                        }

                        let msg_counter = agent_session.messages.len() as u64;

                        let (update_tx, update_rx) = tokio::sync::broadcast::channel(4096);
                        agent.state.lock().await.sessions.insert(
                            sid_key,
                            Arc::new(SessionInner {
                                update_tx,
                                foreground: std::sync::atomic::AtomicBool::new(false),
                                state: tokio::sync::Mutex::new({
                                    let (msg_tx, msg_rx) = tokio::sync::mpsc::channel(16);
                                    SessionState {
                                        session: agent_session,
                                        mcp_clients,
                                        tools,
                                        llm: llm_client,
                                        cancel: CancellationToken::new(),
                                        msg_counter,
                                        history: Vec::new(),
                                        msg_tx,
                                        msg_rx,
                                        progress_rx,
                                    }
                                }),
                            }),
                        );
                        spawn_pump(&connection, session_id.clone(), update_rx);

                        responder.respond(acp::ResumeSessionResponse::new())
                    }
                },
                agent_client_protocol::on_receive_request!(),
            )
            // ---- prompt ----
            .on_receive_request(
                {
                    let agent = self.clone();
                    async move |req: acp::PromptRequest,
                                responder: Responder<acp::PromptResponse>,
                                _connection: V2ConnectionTo<Client>| {
                        let session_id = req.session_id.clone();
                        let sid_key = session_id.to_string();

                        // Foreground work enforcement: one prompt per session.
                        // Atomic CAS so this never waits on an in-flight turn's
                        // lock (14.1).
                        let inner = {
                            let state = agent.state.lock().await;
                            state.sessions.get(&sid_key).cloned()
                        };
                        let Some(inner) = inner else {
                            return responder.respond_with_error(
                                agent_client_protocol::Error::invalid_params()
                                    .data(format!("session not found: {sid_key}")),
                            );
                        };
                        if inner
                            .foreground
                            .compare_exchange(
                                false,
                                true,
                                std::sync::atomic::Ordering::AcqRel,
                                std::sync::atomic::Ordering::Acquire,
                            )
                            .is_err()
                        {
                            return responder.respond_with_error(
                                agent_client_protocol::Error::internal_error()
                                    .data(format!(
                                        "session `{sid_key}` already has foreground work"
                                    )),
                            );
                        }

                        let user_text: String = req
                            .prompt
                            .iter()
                            .filter_map(|b| match b {
                                acp::ContentBlock::Text(t) => Some(t.text.to_string()),
                                _ => None,
                            })
                            .collect::<Vec<_>>()
                            .join("\n");

                        // Ack immediately (v2: prompt response = "accepted")
                        responder.respond(acp::PromptResponse::new())?;

                        let agent = agent.clone();
                        // 14.1: detach the turn from the connection. It publishes to
                        // the session's fan-out (update_tx) and keeps running after a
                        // client disconnect; pumps on live connections forward updates.
                        let sid_watch = sid_key.clone();
                        let handle = tokio::spawn(async move {
                            // Cancel token + user message under the per-session
                            // lock (brief section — no LLM calls).
                            let (cancel, user_msg_id) = {
                                let mut s = inner.state.lock().await;
                                s.cancel = CancellationToken::new();
                                agent
                                    .cancel_tokens
                                    .lock()
                                    .unwrap()
                                    .insert(sid_key.clone(), s.cancel.clone());

                                // UserMessage with unique ID
                                let mid = s.next_msg_id();
                                let user_update = acp::SessionUpdate::UserMessage(
                                    acp::UserMessage::new(mid.as_str()).content(vec![
                                        acp::ContentBlock::Text(acp::TextContent::new(&user_text)),
                                    ]),
                                );
                                let _ = inner.update_tx.send(user_update.clone());
                                s.record(user_update);

                                // Running
                                let _ = inner.update_tx.send(acp::SessionUpdate::StateUpdate(
                                    acp::StateUpdate::Running(acp::RunningStateUpdate::new()),
                                ));

                                // Persist user message to LanceDB
                                let user_msg = serde_json::json!({
                                    "role": "user",
                                    "content": user_text,
                                });
                                s.session
                                    .add_message(&agent.store, user_msg, None)
                                    .await;

                                (s.cancel.clone(), mid)
                            };
                            let _ = user_msg_id;

                            // Run react loop — holds the per-session lock for
                            // the whole turn; a resume mid-turn subscribes to
                            // update_tx lock-free instead of waiting here (14.1).
                            let stop = {
                                let mut guard = inner.state.lock().await;
                                let s = &mut *guard;
                                match react::react_loop(
                                    &inner.update_tx,
                                    &session_id,
                                    &agent.config,
                                    &s.llm,
                                    &s.mcp_clients,
                                    &mut s.session,
                                    &agent.store,
                                    &s.tools,
                                    &mut s.history,
                                    &mut s.msg_counter,
                                    cancel,
                                    &mut s.msg_rx,
                                    &mut s.progress_rx,
                                )
                                .await
                                {
                                    Ok(stop) => stop,
                                    Err(e) => {
                                        tracing::error!("react loop failed: {e:#}");
                                        // Surface the failure to the client — a silent
                                        // EndTurn looks like an empty model reply.
                                        let _ = inner.update_tx.send(
                                            acp::SessionUpdate::AgentMessageChunk(
                                                acp::ContentChunk::new(
                                                    acp::ContentBlock::Text(
                                                        acp::TextContent::new(format!(
                                                            "Error: {e:#}"
                                                        )),
                                                    ),
                                                    "error",
                                                ),
                                            ),
                                        );
                                        acp::StopReason::EndTurn
                                    }
                                }
                            };

                            // Idle + clear foreground
                            let _ = inner.update_tx.send(acp::SessionUpdate::StateUpdate(
                                acp::StateUpdate::Idle(
                                    acp::IdleStateUpdate::new().stop_reason(stop),
                                ),
                            ));

                            inner
                                .foreground
                                .store(false, std::sync::atomic::Ordering::Release);
                        });
                        // Surface a silent death (panic) of the detached turn.
                        tokio::spawn(async move {
                            if let Err(e) = handle.await {
                                tracing::error!("turn task for {sid_watch} died: {e}");
                            }
                        });
                        Ok(())
                    }
                },
                agent_client_protocol::on_receive_request!(),
            )
            // ---- cancel ----
            .on_receive_notification(
                {
                    let agent = self.clone();
                    async move |notif: acp::CancelSessionNotification,
                                _: V2ConnectionTo<Client>| {
                        let sid = notif.session_id.to_string();
                        tracing::info!("cancel: {sid}");
                        // NB: do NOT take the state lock here — the prompt
                        // handler holds it for the whole turn, so a cancel
                        // through `state` would only land after the work
                        // already finished. The token registry is separate.
                        if let Some(tok) =
                            agent.cancel_tokens.lock().unwrap().get(&sid).cloned()
                        {
                            tok.cancel();
                        }
                        Ok(())
                    }
                },
                agent_client_protocol::on_receive_notification!(),
            )
            // ---- session/close ----
            .on_receive_request(
                {
                    let agent = self.clone();
                    async move |req: acp::CloseSessionRequest,
                                responder: Responder<acp::CloseSessionResponse>,
                                _: V2ConnectionTo<Client>| {
                        let sid = req.session_id.to_string();
                        tracing::info!("close: {sid}");
                        // Cancel an in-flight turn: it no longer blocks this
                        // handler (per-session lock, 14.1), so stop it here.
                        if let Some(tok) = agent.cancel_tokens.lock().unwrap().remove(&sid) {
                            tok.cancel();
                        }
                        agent.state.lock().await.sessions.remove(&sid);
                        responder.respond(acp::CloseSessionResponse::new())
                    }
                },
                agent_client_protocol::on_receive_request!(),
            )
            .connect_to(client)
            .await
    }
}

/// One ACP EnvVar auth method per provider whose api_key is a `${VAR}` ref.
pub fn config_auth_methods(config: &Config) -> Vec<acp::AuthMethod> {
    config
        .api_key_env_refs
        .iter()
        .map(|(provider, var)| {
            acp::AuthMethod::EnvVar(
                acp::AuthMethodEnvVar::new(
                    acp::AuthMethodId::new(std::sync::Arc::from(provider.as_str())),
                    format!("{provider} API key"),
                    vec![acp::AuthEnvVar::new(var.clone()).secret(true)],
                )
                .description(format!("Sets {var} for the '{provider}' provider")),
            )
        })
        .collect()
}

/// Persist KEY=VALUE to {config_dir}/.env (replacing any existing KEY line).
fn write_env_var(config_dir: &std::path::Path, key: &str, value: &str) -> anyhow::Result<()> {
    let path = config_dir.join(".env");
    let mut lines: Vec<String> = std::fs::read_to_string(&path)
        .unwrap_or_default()
        .lines()
        .filter(|l| !l.starts_with(&format!("{key}=")))
        .map(str::to_string)
        .collect();
    lines.push(format!("{key}={value}"));
    std::fs::write(path, lines.join("\n") + "\n")?;
    Ok(())
}

/// Remove KEY from {config_dir}/.env if the file exists.
fn remove_env_var_file(config_dir: &std::path::Path, key: &str) {
    let path = config_dir.join(".env");
    let Ok(content) = std::fs::read_to_string(&path) else {
        return;
    };
    let lines: Vec<&str> = content
        .lines()
        .filter(|l| !l.starts_with(&format!("{key}=")))
        .collect();
    let _ = std::fs::write(path, lines.join("\n") + "\n");
}

#[cfg(test)]
mod auth_tests {
    use super::*;

    fn config_with_refs(refs: &[(&str, &str)]) -> Config {
        let mut api_key_env_refs = indexmap::IndexMap::new();
        for (p, v) in refs {
            api_key_env_refs.insert(p.to_string(), v.to_string());
        }
        Config {
            config_dir: std::path::PathBuf::from("/tmp"),
            api_key_env_refs,
            providers: indexmap::IndexMap::new(),
            models: indexmap::IndexMap::new(),
            mcp_servers: indexmap::IndexMap::new(),
            memory_url: "http://127.0.0.1:27697".into(),
            max_tokens: 1,
            temperature: 0.0,
            max_compact_tokens: 1,
            system_prompt: String::new(),
        }
    }

    #[test]
    fn auth_methods_advertise_env_vars() {
        let methods = config_auth_methods(&config_with_refs(&[("alibaba", "ALIBABA_API_KEY")]));
        assert_eq!(methods.len(), 1);
        let acp::AuthMethod::EnvVar(m) = &methods[0] else { panic!() };
        assert_eq!(m.method_id.to_string(), "alibaba");
        assert_eq!(m.name, "alibaba API key");
        assert_eq!(m.vars.len(), 1);
        assert_eq!(m.vars[0].name, "ALIBABA_API_KEY");
        assert!(m.vars[0].secret);
    }

    #[test]
    fn env_file_write_and_remove_round_trip() {
        let dir = tempfile::tempdir().unwrap();
        write_env_var(dir.path(), "FOO_KEY", "v1").unwrap();
        write_env_var(dir.path(), "FOO_KEY", "v2").unwrap();
        write_env_var(dir.path(), "OTHER", "x").unwrap();
        let content = std::fs::read_to_string(dir.path().join(".env")).unwrap();
        assert!(content.contains("FOO_KEY=v2") && content.contains("OTHER=x"));
        assert!(!content.contains("v1"));
        remove_env_var_file(dir.path(), "FOO_KEY");
        let content = std::fs::read_to_string(dir.path().join(".env")).unwrap();
        assert!(!content.contains("FOO_KEY") && content.contains("OTHER=x"));
    }
}
