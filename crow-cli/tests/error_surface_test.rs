//! Stop swallowing errors: resume load failures and persist failures must
//! stay visible.
//!
//! Both tests run against the REAL crow-memory axum server + SDK client
//! (production path). The failure is induced for real by deleting the
//! messages table's Lance directory on disk: reads and writes on that table
//! then fail with 500 (not retried by the SDK — immediate), while the agents
//! table keeps working. No mocks.

use crow_cli::session::AgentSession;
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

/// Real failure: nuke the messages table on disk. The store keeps serving
/// agents/prompts, but every messages read/write 500s.
fn break_messages_table(path: &std::path::Path) {
    std::fs::remove_dir_all(path.join("messages.lance")).unwrap();
}

async fn make_agent(store: &MemoryClient, sid: &str, agent_id: &str) {
    let prompt_id = store.lookup_or_create_prompt("sys", "t").await.unwrap();
    store
        .create_agent(
            agent_id,
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
}

fn session(agent_id: &str) -> AgentSession {
    AgentSession {
        agent_id: agent_id.to_string(),
        session_id: agent_id.to_string(),
        agent_idx: 1,
        cwd: "/tmp".to_string(),
        messages: Vec::new(),
        model_identifier: "test-model".to_string(),
        tools: serde_json::json!([]),
        request_params: serde_json::json!({}),
        prompt_id: String::new(),
        prompt_args: serde_json::json!({}),
        failed_persists: 0,
    }
}

// ---- Fix 3: resume load failure must propagate, never become empty ----

#[tokio::test]
async fn resume_load_returns_repaired_history() {
    let tmp = tempfile::tempdir().unwrap();
    let store = spawn_client(tmp.path()).await;
    make_agent(&store, "err-surf-1", "err-surf-1-1").await;
    store
        .add_message(
            "err-surf-1-1",
            &serde_json::json!({"role": "user", "content": "hello"}),
            None,
        )
        .await
        .unwrap();

    let loaded = crow_cli::session::load_resume_messages(&store, "err-surf-1-1")
        .await
        .unwrap();
    assert_eq!(loaded.len(), 1);
    assert_eq!(loaded[0]["content"], "hello");
}

#[tokio::test]
async fn resume_load_failure_is_an_error_not_empty_history() {
    let tmp = tempfile::tempdir().unwrap();
    let store = spawn_client(tmp.path()).await;
    make_agent(&store, "err-surf-2", "err-surf-2-1").await;
    store
        .add_message(
            "err-surf-2-1",
            &serde_json::json!({"role": "user", "content": "hello"}),
            None,
        )
        .await
        .unwrap();

    break_messages_table(tmp.path());

    // The agent record still loads (agents table intact) — this is exactly
    // the resume scenario: session found, message load fails.
    assert!(store.list_agents(Some("err-surf-2")).await.is_ok());
    // The load must FAIL, not launder into an amnesiac empty history.
    let err = crow_cli::session::load_resume_messages(&store, "err-surf-2-1")
        .await
        .unwrap_err();
    assert!(
        err.to_string().contains("memory server error"),
        "real store error must propagate, got: {err}"
    );
}

// ---- Fix 3, end-to-end: the real CrowAgent must refuse the resume ----

/// The full ACP v2 path: real CrowAgent, real memory server, broken messages
/// table. `session/resume` must come back as an ACP error response — not a
/// successful resume onto an empty (amnesiac) history.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn resume_over_acp_aborts_when_message_load_fails() {
    use agent_client_protocol::{
        Client, Error,
        schema::{ProtocolVersion, v2 as acp},
    };
    use crow_cli::agent::CrowAgent;
    use crow_cli::config::Config;

    let tmp = tempfile::tempdir().unwrap();
    let store = spawn_client(tmp.path()).await;
    make_agent(&store, "resume-acp-fail", "resume-acp-fail-1").await;
    store
        .add_message(
            "resume-acp-fail-1",
            &serde_json::json!({"role": "user", "content": "hello"}),
            None,
        )
        .await
        .unwrap();
    break_messages_table(tmp.path());

    // Config with one model so resolve_model succeeds (the failure must come
    // from the message load, not model resolution).
    let cfg_dir = tmp.path().join("cfg");
    std::fs::create_dir_all(&cfg_dir).unwrap();
    std::fs::write(
        cfg_dir.join("config.yaml"),
        "providers:\n  test:\n    base_url: http://127.0.0.1:9\n    api_key: k\nmodels:\n  test-model:\n    provider: test\n    model: test-model\n",
    )
    .unwrap();
    let config = Config::load(Some(&cfg_dir), None).unwrap();
    let agent = CrowAgent::new(config, std::sync::Arc::new(store));

    Client
        .v2()
        .connect_with(agent, async move |connection| {
            let init = connection
                .send_request(acp::InitializeRequest::new(
                    ProtocolVersion::V2,
                    acp::Implementation::new("test-client", "0.1.0"),
                ))
                .block_task()
                .await?;
            assert_eq!(init.protocol_version, ProtocolVersion::V2);

            let resume = connection
                .send_request(acp::ResumeSessionRequest::new(
                    acp::SessionId::new("resume-acp-fail"),
                    acp::AbsolutePath::new(std::path::PathBuf::from("/tmp")),
                ))
                .block_task()
                .await;

            match resume {
                Ok(_) => panic!("resume must fail when the message load fails"),
                Err(e) => {
                    assert_eq!(e.code, Error::internal_error().code);
                    let data = e
                        .data
                        .as_ref()
                        .and_then(|d| d.as_str())
                        .unwrap_or_default()
                        .to_string();
                    assert!(
                        data.contains("failed to load session history"),
                        "error must carry the load failure, got: {data}"
                    );
                }
            }
            Ok(())
        })
        .await
        .unwrap();
}

// ---- Fix 4: failed persists are tracked, not silently dropped ----

#[tokio::test]
async fn add_message_tracks_failed_persists() {
    let tmp = tempfile::tempdir().unwrap();
    let store = spawn_client(tmp.path()).await;
    make_agent(&store, "err-surf-3", "err-surf-3-1").await;

    let mut session = session("err-surf-3-1");

    // Healthy store: persists, counter stays 0.
    session
        .add_message(
            &store,
            serde_json::json!({"role": "user", "content": "one"}),
            None,
        )
        .await;
    assert_eq!(session.failed_persists, 0);
    assert_eq!(session.messages.len(), 1);

    break_messages_table(tmp.path());

    // Broken store: message stays in memory, counter records the loss.
    session
        .add_message(
            &store,
            serde_json::json!({"role": "user", "content": "two"}),
            None,
        )
        .await;
    session
        .add_message(
            &store,
            serde_json::json!({"role": "user", "content": "three"}),
            None,
        )
        .await;
    assert_eq!(session.failed_persists, 2, "both failed persists must be counted");
    assert_eq!(session.messages.len(), 3, "in-memory history is intact");

    // The DB really is behind: only message "one" made it.
    let rows = store
        .query_messages_by_agent("err-surf-3-1", true, 100, None, false)
        .await;
    assert!(rows.is_err(), "table is broken — reads must fail too");
}
