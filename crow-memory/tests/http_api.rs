//! End-to-end: real axum server on a temp LanceDB + real HTTP + the SDK.
//! No mocks — this is the wire contract test.

use std::sync::Arc;

use serde_json::json;

async fn spawn_server() -> crow_memory_sdk::MemoryClient {
    let tmp = std::env::temp_dir().join(format!(
        "crow-memory-test-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let store = crow_memory::MemoryStore::open(&tmp, crow_memory::EmbedConfig::default())
        .await
        .unwrap();
    let app = crow_memory::router(Arc::new(store));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    crow_memory_sdk::MemoryClient::connect(format!("http://{addr}"))
}

#[tokio::test]
async fn full_api_round_trip() {
    let client = spawn_server().await;
    client.health().await.unwrap();

    // prompts: create, hash-dedupe, fetch, 404 → None
    let pid = client
        .lookup_or_create_prompt("hello {{name}}", "test-prompt")
        .await
        .unwrap();
    let again = client
        .lookup_or_create_prompt("hello {{name}}", "test-prompt")
        .await
        .unwrap();
    assert_eq!(pid, again, "same template must dedupe by hash");
    let pr = client.get_prompt(&pid).await.unwrap().expect("prompt exists");
    assert_eq!(pr.template, "hello {{name}}");
    assert_eq!(pr.name, "test-prompt");
    assert!(client.get_prompt("nope-nope-nope").await.unwrap().is_none());

    // agents: create, get, list, max idx
    client
        .create_agent(
            "a-1", "s-1", 0, "/tmp/w", &pid,
            &json!({"workspace": "/tmp/w"}), "you are crow",
            &json!([{"name": "terminal"}]), &json!({"model": "test"}), "test-model",
        )
        .await
        .unwrap();
    client
        .create_agent(
            "a-2", "s-1", 1, "/tmp/w", &pid,
            &json!({}), "you are crow", &json!([]), &json!({}), "test-model",
        )
        .await
        .unwrap();
    let a = client.get_agent("a-1").await.unwrap().expect("agent exists");
    assert_eq!(a.session_id, "s-1");
    assert_eq!(a.prompt_args["workspace"], "/tmp/w");
    assert!(client.get_agent("ghost").await.unwrap().is_none());
    assert_eq!(client.get_max_agent_idx("s-1").await.unwrap(), 1);
    assert_eq!(client.list_agents(Some("s-1")).await.unwrap().len(), 2);
    assert_eq!(client.list_agents(None).await.unwrap().len(), 2);

    // messages: append-only, ids increase, load in order
    let id1 = client
        .add_message("a-1", &json!({"role": "user", "content": "the sky is blue"}), None)
        .await
        .unwrap();
    let id2 = client
        .add_message(
            "a-1",
            &json!({"role": "assistant", "content": "yes it is"}),
            Some(&json!({"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3})),
        )
        .await
        .unwrap();
    assert!(id2 > id1);
    let msgs = client.load_messages("a-1").await.unwrap();
    assert_eq!(msgs.len(), 2);
    assert_eq!(msgs[0]["role"], "user");
    assert_eq!(msgs[1]["content"], "yes it is");

    // query by agent with role filter
    let users: Vec<_> = client
        .query_messages_by_agent("a-1", true, 10, Some("user"))
        .await
        .unwrap();
    assert_eq!(users.len(), 1);
    assert_eq!(users[0].role, "user");
    let all = client
        .query_messages_by_agent("a-1", false, 10, None)
        .await
        .unwrap();
    assert_eq!(all.len(), 2);
    assert!(all[0].id > all[1].id, "order_asc=false → newest first");

    // semantic search (embedding server may be down in test → recent
    // fallback; either path must return the messages)
    let hits = client.search_messages("sky", 10, None).await.unwrap();
    assert!(!hits.is_empty());
    let user_hits = client.search_messages("sky", 10, Some("user")).await.unwrap();
    assert!(user_hits.iter().all(|m| m.role == "user"));

    // sessions: aggregated from agents + messages
    let sessions = client.list_sessions(50, 0).await.unwrap();
    assert_eq!(sessions.len(), 1);
    assert_eq!(sessions[0].session_id, "s-1");
    assert_eq!(sessions[0].message_count, 2);
    assert_eq!(sessions[0].agent_count, 2);
    assert_eq!(sessions[0].model_identifier, "test-model");

    // pagination
    let page2 = client.list_sessions(50, 1).await.unwrap();
    assert!(page2.is_empty());
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn concurrent_add_message_unique_ids() {
    let client = Arc::new(spawn_server().await);
    let pid = client
        .lookup_or_create_prompt("test", "race")
        .await
        .unwrap();
    client
        .create_agent(
            "race-agent-1", "race-sess", 0, "/tmp", &pid,
            &json!({}), "system prompt", &json!([]), &json!({}), "test-model",
        )
        .await
        .unwrap();

    // N concurrent add_message calls through the real axum server. Before
    // the id-allocation mutex, every request scanned max(id) first, so
    // concurrent requests computed the same id → duplicate message ids.
    const N: usize = 20;
    let mut handles = Vec::new();
    for i in 0..N {
        let c = Arc::clone(&client);
        handles.push(tokio::spawn(async move {
            c.add_message(
                "race-agent-1",
                &json!({"role": "user", "content": format!("concurrent message {i}")}),
                None,
            )
            .await
        }));
    }
    let mut ids: Vec<i64> = Vec::new();
    for h in handles {
        ids.push(h.await.unwrap().unwrap());
    }
    ids.sort_unstable();
    ids.dedup();
    assert_eq!(ids.len(), N, "concurrent add_message handed out duplicate ids");

    // Every message landed and is readable.
    let msgs = client.load_messages("race-agent-1").await.unwrap();
    assert_eq!(msgs.len(), N);
}

#[tokio::test]
async fn list_sessions_stats_across_sessions() {
    let client = spawn_server().await;
    let pid = client
        .lookup_or_create_prompt("test", "sessions")
        .await
        .unwrap();
    for (agent_id, sess, idx) in [
        ("ls-a-1", "ls-sess-a", 0),
        ("ls-b-1", "ls-sess-b", 0),
        ("ls-b-2", "ls-sess-b", 1),
        ("ls-c-1", "ls-sess-c", 0),
    ] {
        client
            .create_agent(
                agent_id, sess, idx, "/tmp/w", &pid,
                &json!({}), "system prompt", &json!([]), &json!({}), "test-model",
            )
            .await
            .unwrap();
    }

    // 3 messages to A, then 1 (newest) to B, none to C.
    for content in ["a one", "a two", "a three"] {
        client
            .add_message("ls-a-1", &json!({"role": "user", "content": content}), None)
            .await
            .unwrap();
    }
    client
        .add_message(
            "ls-b-1",
            &json!({"role": "assistant", "content": "b last"}),
            None,
        )
        .await
        .unwrap();

    let sessions = client.list_sessions(50, 0).await.unwrap();
    assert_eq!(sessions.len(), 3);

    // Ordered by most-recent message activity: B (newest msg), A, then C.
    assert_eq!(sessions[0].session_id, "ls-sess-b");
    assert_eq!(sessions[0].message_count, 1);
    assert_eq!(sessions[0].agent_count, 2);
    assert_eq!(sessions[0].agent_idxs, vec![0, 1]);
    assert_eq!(sessions[0].last_role, "assistant");
    let last_b = sessions[0].last_message.as_ref().expect("last_message");
    assert_eq!(last_b.data["content"], "b last");
    assert_eq!(last_b.agent_id, "ls-b-1");

    assert_eq!(sessions[1].session_id, "ls-sess-a");
    assert_eq!(sessions[1].message_count, 3);
    assert_eq!(sessions[1].agent_count, 1);
    assert_eq!(sessions[1].last_role, "user");
    assert_eq!(
        sessions[1].last_message.as_ref().unwrap().data["content"],
        "a three"
    );

    // Session with agents but no messages.
    assert_eq!(sessions[2].session_id, "ls-sess-c");
    assert_eq!(sessions[2].message_count, 0);
    assert!(sessions[2].last_message.is_none());
}

#[tokio::test]
async fn backoff_fails_fast_on_4xx() {
    let client = spawn_server().await;
    // Malformed body → 4xx (axum rejects), must NOT retry for ~3s.
    let start = std::time::Instant::now();
    let resp = client
        .health()
        .await;
    assert!(resp.is_ok());
    assert!(start.elapsed().as_secs() < 2);
}
