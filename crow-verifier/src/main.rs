//! crow-verifier: conductor proxy component.
//!
//! Sits between client and worker agent in a conductor chain:
//!   Client ←→ Conductor ←→ crow-verifier (proxy) ←→ Worker Agent
//!                                ↕ HTTP
//!                          Verifier Daemon (crow-server)
//!
//! The proxy:
//! 1. Forwards all messages transparently EXCEPT state_update:idle
//! 2. On idle: holds it, sends "query {SESSION-ID}" to verifier daemon
//! 3. Verifier daemon reads worker history via query_session, calls verdict tool
//! 4. Proxy reads verdict tool call from SSE stream
//! 5. pass → forward idle to client; fail → re-prompt worker with feedback
//!
//! Usage (via conductor):
//!   agent-client-protocol-conductor agent \
//!     "crow-verifier --verifier-url http://localhost:8081" \
//!     "crow-cli acp"

use std::sync::Arc;
use std::sync::atomic::{AtomicU32, Ordering};

use agent_client_protocol::{
    Agent, Client, Conductor, ConnectTo, Handled, Proxy,
    schema::v2 as acp,
};
use clap::Parser;
use tokio::sync::Mutex;

#[derive(Parser)]
#[command(name = "crow-verifier", version, about = "ACP verifier proxy component")]
struct Args {
    /// Verifier daemon URL (crow-server with verifier prompt)
    #[arg(long, default_value = "http://localhost:8081")]
    verifier_url: String,

    /// Max verification rounds before forwarding idle unconditionally
    #[arg(long, default_value = "3")]
    max_rounds: u32,
}

/// Verdict from the verifier daemon's tool call.
#[derive(Debug, serde::Deserialize)]
struct Verdict {
    pass: bool,
    #[serde(default)]
    feedback: String,
}

struct VerifierProxy {
    verifier_url: String,
    max_rounds: u32,
}

impl ConnectTo<Conductor> for VerifierProxy {
    async fn connect_to(
        self,
        conductor: impl ConnectTo<Proxy>,
    ) -> Result<(), agent_client_protocol::Error> {
        let verifier_url = self.verifier_url.clone();
        let max_rounds = self.max_rounds;

        // Track the worker's session ID + original task (captured from session/prompt)
        let session_id: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(None));
        let task: Arc<Mutex<String>> = Arc::new(Mutex::new(String::new()));
        let rounds = Arc::new(AtomicU32::new(0));

        Proxy.builder()
            // Capture session_id + task from session/prompt requests (client → agent)
            .on_receive_request_from(
                Client,
                {
                    let session_id = session_id.clone();
                    let task = task.clone();
                    async move |req: acp::PromptRequest,
                                responder,
                                cx| {
                        let sid = req.session_id.to_string();
                        *session_id.lock().await = Some(sid);
                        let text: Vec<String> = req
                            .prompt
                            .iter()
                            .filter_map(|b| match b {
                                acp::ContentBlock::Text(t) => Some(t.text.to_string()),
                                _ => None,
                            })
                            .collect();
                        *task.lock().await = text.join("\n");
                        // Forward to agent
                        cx.send_request_to(Agent, req)
                            .forward_response_to(responder)
                    }
                },
                agent_client_protocol::on_receive_request!(),
            )
            // Intercept session/update notifications from agent
            .on_receive_notification_from(
                Agent,
                {
                    let verifier_url = verifier_url.clone();
                    let session_id = session_id.clone();
                    let task = task.clone();
                    let rounds = rounds.clone();
                    async move |notif: acp::UpdateSessionNotification, cx| {
                        let is_idle = matches!(
                            &notif.update,
                            acp::SessionUpdate::StateUpdate(acp::StateUpdate::Idle(_))
                        );

                        if !is_idle {
                            // Forward non-idle updates to client
                            return cx
                                .send_notification_to(Client, notif)
                                .map(|_| Handled::Yes);
                        }

                        // --- Idle intercepted ---
                        let sid = session_id
                            .lock()
                            .await
                            .clone()
                            .unwrap_or_else(|| "unknown".into());
                        let task_text = task.lock().await.clone();
                        let round = rounds.fetch_add(1, Ordering::SeqCst) + 1;

                        if round > max_rounds {
                            tracing::warn!(
                                "max rounds ({max_rounds}) reached, forwarding idle"
                            );
                            return cx
                                .send_notification_to(Client, notif)
                                .map(|_| Handled::Yes);
                        }

                        tracing::info!(
                            session = %sid,
                            round = round,
                            "intercepted idle, calling verifier"
                        );

                        // Spawn verification so we don't block the dispatch loop
                        let cx2 = cx.clone();
                        let url = verifier_url.clone();
                        cx.spawn(async move {
                            match call_verifier(&url, &sid, &task_text).await {
                                Ok(Verdict {
                                    pass: true,
                                    feedback,
                                }) => {
                                    tracing::info!("verdict: PASS — forwarding idle");
                                    if !feedback.is_empty() {
                                        tracing::info!("verifier note: {feedback}");
                                    }
                                    let _ = cx2.send_notification_to(Client, notif);
                                }
                                Ok(Verdict {
                                    pass: false,
                                    feedback,
                                }) => {
                                    tracing::info!(
                                        "verdict: FAIL — re-prompting worker: {feedback}"
                                    );
                                    let reprompt = acp::PromptRequest::new(
                                        acp::SessionId::new(sid.as_str()),
                                        vec![acp::ContentBlock::Text(
                                            acp::TextContent::new(format!(
                                                "Verifier feedback — address this and continue: {feedback}"
                                            )),
                                        )],
                                    );
                                    let _ = cx2.send_request_to(Agent, reprompt);
                                }
                                Err(e) => {
                                    tracing::error!(
                                        "verifier call failed: {e} — forwarding idle"
                                    );
                                    let _ = cx2.send_notification_to(Client, notif);
                                }
                            }
                            Ok(())
                        })?;

                        Ok(Handled::Yes)
                    }
                },
                agent_client_protocol::on_receive_notification!(),
            )
            .connect_to(conductor)
            .await
    }
}

/// Call the verifier daemon over ACP HTTP (9.7: rust-sdk HttpClient + v2
/// session API instead of hand-rolled reqwest+SSE). Updates arrive typed
/// through the notification handler; we drain them until the verdict tool
/// call shows up (or the verifier turn ends without one).
async fn call_verifier(
    base_url: &str,
    worker_session_id: &str,
    task: &str,
) -> anyhow::Result<Verdict> {
    use agent_client_protocol::schema::MaybeUndefined;
    use agent_client_protocol::{Error, V2ConnectionTo};
    use agent_client_protocol_http::HttpClient;

    let (update_tx, mut update_rx) =
        tokio::sync::mpsc::unbounded_channel::<acp::UpdateSessionNotification>();

    let prompt = format!(
        "query {worker_session_id}\n\nOriginal task given to the worker:\n{task}\n\n\
         Call query_session to read the worker history, verify the task was actually \
         completed (check files on disk with the terminal tool when relevant), \
         then call the verdict tool."
    );

    let http = HttpClient::new(base_url)
        .map_err(|e| anyhow::anyhow!("verifier URL '{base_url}': {e}"))?;

    agent_client_protocol::Client
        .v2()
        .on_receive_notification(
            async move |update: acp::UpdateSessionNotification,
                        _cx: V2ConnectionTo<Agent>| {
                update_tx.send(update).map_err(Error::into_internal_error)
            },
            agent_client_protocol::on_receive_notification!(),
        )
        .connect_with(http, async move |connection| {
            connection
                .send_request(acp::InitializeRequest::new(
                    agent_client_protocol::schema::ProtocolVersion::V2,
                    acp::Implementation::new("crow-verifier", env!("CARGO_PKG_VERSION")),
                ))
                .block_task()
                .await?;

            let opened = connection
                .build_session(std::path::PathBuf::from("/tmp"))
                .start_session()
                .block_task()
                .await?;
            let (session, _) = opened.into_parts();

            // The ack — the real output flows in as session/update events.
            session.send_prompt(prompt).block_task().await?;

            let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(120);
            loop {
                let now = tokio::time::Instant::now();
                if now >= deadline {
                    return Err(Error::internal_error()
                        .data("no verdict tool call found in verifier output (timeout)"));
                }
                let update = match tokio::time::timeout(deadline - now, update_rx.recv()).await {
                    Ok(Some(update)) => update,
                    Ok(None) => {
                        return Err(Error::internal_error()
                            .data("verifier connection closed before a verdict"))
                    }
                    Err(_) => continue,
                };

                match update.update {
                    acp::SessionUpdate::ToolCallUpdate(tc) => {
                        // Wire shape: name lives in the title "verdict(...)",
                        // args in raw_input.
                        let MaybeUndefined::Value(title) = &tc.title else {
                            continue;
                        };
                        if title.split('(').next().unwrap_or("") != "verdict" {
                            continue;
                        }
                        let MaybeUndefined::Value(args) = &tc.raw_input else {
                            continue;
                        };
                        tracing::info!("verdict tool call found: {args}");
                        return serde_json::from_value(args.clone())
                            .map_err(|e| Error::internal_error().data(e.to_string()));
                    }
                    acp::SessionUpdate::StateUpdate(acp::StateUpdate::Idle(_)) => {
                        return Err(Error::internal_error()
                            .data("verifier turn ended without a verdict tool call"));
                    }
                    _ => {}
                }
            }
        })
        .await
        .map_err(|e| anyhow::anyhow!("{e}"))
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .with_writer(std::io::stderr)
        .with_ansi(false)
        .init();

    let args = Args::parse();

    let proxy = VerifierProxy {
        verifier_url: args.verifier_url,
        max_rounds: args.max_rounds,
    };

    // The conductor connects to us via stdio
    let stdio = agent_client_protocol::Stdio::new();
    proxy.connect_to(stdio).await?;

    Ok(())
}
