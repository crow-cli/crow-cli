//! One foreground turn per session: the flag must be released when the turn
//! ends through the ERROR path, so the next prompt is accepted.
//!
//! Real CrowAgent over ACP v2 + real memory server (production path), dead
//! provider (`base_url: http://127.0.0.1:9`) so the react loop fails fast —
//! no live LLM needed. Before the RAII `ForegroundGuard`, a turn that died
//! before the explicit `store(false)` left the flag set and every future
//! prompt was rejected with "already has foreground work" until restart.

use agent_client_protocol::{
    Client, Error, V2ConnectionTo,
    schema::{ProtocolVersion, v2 as acp},
};
use crow_cli::agent::CrowAgent;
use crow_cli::config::Config;
use crow_memory_sdk::MemoryClient;

async fn spawn_client(path: &std::path::Path) -> MemoryClient {
    let store = crow_memory::MemoryStore::open(path, crow_memory::EmbedConfig::default())
        .await
        .unwrap();
    let app = crow_memory::router(std::sync::Arc::new(store));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    MemoryClient::connect(format!("http://{addr}"))
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn prompt_accepted_after_failed_turn_releases_foreground() {
    let tmp = tempfile::tempdir().unwrap();
    let store = spawn_client(tmp.path()).await;

    let sid = "fg-release";
    let agent_id = format!("{sid}-1");
    let prompt_id = store.lookup_or_create_prompt("sys", "t").await.unwrap();
    store
        .create_agent(
            &agent_id,
            sid,
            1,
            "/tmp",
            &prompt_id,
            &serde_json::json!({}),
            "system prompt",
            &serde_json::json!([]),
            &serde_json::json!({}),
            "test-model",
        )
        .await
        .unwrap();
    store
        .add_message(
            &agent_id,
            &serde_json::json!({"role": "user", "content": "hello"}),
            None,
        )
        .await
        .unwrap();

    // Dead provider: the react loop fails fast (connection refused) and the
    // turn ends through the ERROR path (agent.rs react-loop Err arm).
    let cfg_dir = tmp.path().join("cfg");
    std::fs::create_dir_all(&cfg_dir).unwrap();
    std::fs::write(
        cfg_dir.join("config.yaml"),
        "providers:\n  test:\n    base_url: http://127.0.0.1:9\n    api_key: k\nmodels:\n  test-model:\n    provider: test\n    model: test-model\n",
    )
    .unwrap();
    let config = Config::load(Some(&cfg_dir), None).unwrap();
    let agent = CrowAgent::new(config, std::sync::Arc::new(store));

    let (update_tx, mut update_rx) =
        tokio::sync::mpsc::unbounded_channel::<acp::UpdateSessionNotification>();

    Client
        .v2()
        .on_receive_notification(
            async move |update: acp::UpdateSessionNotification,
                        _connection: V2ConnectionTo<agent_client_protocol::Agent>| {
                update_tx.send(update).map_err(Error::into_internal_error)
            },
            agent_client_protocol::on_receive_notification!(),
        )
        .connect_with(agent, async move |connection| {
            connection
                .send_request(acp::InitializeRequest::new(
                    ProtocolVersion::V2,
                    acp::Implementation::new("test-client", "0.1.0"),
                ))
                .block_task()
                .await?;

            connection
                .send_request(acp::ResumeSessionRequest::new(
                    acp::SessionId::new(sid),
                    acp::AbsolutePath::new(std::path::PathBuf::from("/tmp")),
                ))
                .block_task()
                .await?;

            let prompt = |text: &str| {
                acp::PromptRequest::new(
                    acp::SessionId::new(sid),
                    vec![acp::ContentBlock::Text(acp::TextContent::new(text))],
                )
            };

            // Prompt #1: acked immediately; the turn then fails on the dead
            // provider and must release the foreground flag on its way out.
            connection
                .send_request(prompt("one"))
                .block_task()
                .await?;

            // Wait for the turn to end through the ERROR path: an "Error:"
            // chunk followed by Idle.
            let mut saw_error_chunk = false;
            loop {
                let update = tokio::time::timeout(
                    std::time::Duration::from_secs(30),
                    update_rx.recv(),
                )
                .await
                .expect("failed turn must reach Idle within 30s")
                .expect("update channel must stay open");
                match update.update {
                    acp::SessionUpdate::AgentMessageChunk(chunk) => {
                        if let acp::ContentBlock::Text(t) = &chunk.content {
                            if t.text.starts_with("Error:") {
                                saw_error_chunk = true;
                            }
                        }
                    }
                    acp::SessionUpdate::StateUpdate(acp::StateUpdate::Idle(_)) => break,
                    _ => {}
                }
            }
            assert!(saw_error_chunk, "turn must end through the error path");

            // Idle is emitted just before the guard drops; let the turn task
            // finish so the release is deterministic.
            tokio::time::sleep(std::time::Duration::from_millis(100)).await;

            // Prompt #2 must be ACCEPTED. Before the fix this was the brick:
            // the CAS failed and every prompt got "already has foreground
            // work" until process restart.
            if let Err(e) = connection
                .send_request(prompt("two"))
                .block_task()
                .await
            {
                let data = e
                    .data
                    .as_ref()
                    .and_then(|d| d.as_str())
                    .unwrap_or_default();
                panic!("prompt #2 must be accepted after a failed turn, got error: {data}");
            }
            Ok(())
        })
        .await
        .unwrap();
}
