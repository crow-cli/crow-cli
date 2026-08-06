//! Integration tests for the memory store — through the real axum server
//! + SDK client (the production path).

use crow_memory_sdk::MemoryClient;

/// Spin up a real crow-memory axum server on a temp LanceDB and return an
/// SDK client connected to it.
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

#[tokio::test]
async fn test_memory_store_crud() {
    let tmp = tempfile::tempdir().unwrap();
    let store = spawn_client(tmp.path()).await;

    // Create prompt
    let prompt_id = store
        .lookup_or_create_prompt("You are a test agent.", "test-prompt")
        .await
        .unwrap();
    assert!(!prompt_id.is_empty());

    // Lookup same prompt returns same id
    let prompt_id2 = store
        .lookup_or_create_prompt("You are a test agent.", "test-prompt")
        .await
        .unwrap();
    assert_eq!(prompt_id, prompt_id2);

    // Get prompt
    let prompt = store.get_prompt(&prompt_id).await.unwrap().unwrap();
    assert_eq!(prompt.template, "You are a test agent.");
    assert_eq!(prompt.name, "test-prompt");

    // Create agent
    store
        .create_agent(
            "test-session-1",
            "test-session",
            1,
            "/tmp",
            &prompt_id,
            &serde_json::json!({"workspace": "/tmp"}),
            "You are a test agent.",
            &serde_json::json!([]),
            &serde_json::json!({"temperature": 0.2}),
            "test-model",
        )
        .await
        .unwrap();

    // Get agent
    let agent = store.get_agent("test-session-1").await.unwrap().unwrap();
    assert_eq!(agent.session_id, "test-session");
    assert_eq!(agent.agent_idx, 1);
    assert_eq!(agent.model_identifier, "test-model");
    assert_eq!(agent.cwd, "/tmp");

    // Add messages
    let id1 = store
        .add_message(
            "test-session-1",
            &serde_json::json!({"role": "system", "content": "You are a test agent."}),
            None,
        )
        .await
        .unwrap();
    assert!(id1 > 0);

    let id2 = store
        .add_message(
            "test-session-1",
            &serde_json::json!({"role": "user", "content": "hello"}),
            None,
        )
        .await
        .unwrap();
    assert!(id2 > id1);

    let id3 = store
        .add_message(
            "test-session-1",
            &serde_json::json!({"role": "assistant", "content": "hi there"}),
            Some(&serde_json::json!({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})),
        )
        .await
        .unwrap();
    assert!(id3 > id2);

    // Load messages
    let msgs = store.load_messages("test-session-1").await.unwrap();
    assert_eq!(msgs.len(), 3);
    assert_eq!(msgs[0]["role"], "system");
    assert_eq!(msgs[1]["role"], "user");
    assert_eq!(msgs[1]["content"], "hello");
    assert_eq!(msgs[2]["role"], "assistant");

    // Query messages
    let queried = store
        .query_messages_by_agent("test-session-1", true, 10, None)
        .await
        .unwrap();
    assert_eq!(queried.len(), 3);
    assert_eq!(queried[0].role, "system");

    // Max agent idx
    let max_idx = store.get_max_agent_idx("test-session").await.unwrap();
    assert_eq!(max_idx, 1);

    // List agents
    let agents = store.list_agents(None).await.unwrap();
    assert_eq!(agents.len(), 1);
    let agents_filtered = store.list_agents(Some("test-session")).await.unwrap();
    assert_eq!(agents_filtered.len(), 1);
    let agents_empty = store.list_agents(Some("nonexistent")).await.unwrap();
    assert_eq!(agents_empty.len(), 0);

    // List sessions
    let sessions = store.list_sessions(10, 0).await.unwrap();
    assert_eq!(sessions.len(), 1);
    assert_eq!(sessions[0].session_id, "test-session");
    assert_eq!(sessions[0].message_count, 3);
}

#[tokio::test]
async fn test_message_role_filter() {
    let tmp = tempfile::tempdir().unwrap();
    let store = spawn_client(tmp.path()).await;

    let prompt_id = store.lookup_or_create_prompt("test", "role-filter").await.unwrap();
    store
        .create_agent(
            "role-sess-1",
            "role-sess",
            1,
            "/tmp",
            &prompt_id,
            &serde_json::json!({}),
            "system prompt",
            &serde_json::json!([]),
            &serde_json::json!({}),
            "model",
        )
        .await
        .unwrap();

    for (role, content) in [
        ("user", "what is the capital of france"),
        ("assistant", "Paris is the capital of France"),
        ("tool", "{\"output\": \"paris verified\"}"),
        ("user", "thanks, now tell me about lyon"),
        ("assistant", "Lyon is a city in France"),
    ] {
        store
            .add_message(
                "role-sess-1",
                &serde_json::json!({"role": role, "content": content}),
                None,
            )
            .await
            .unwrap();
    }

    // query_messages_by_agent: role pre-filter in the SQL predicate
    let users = store
        .query_messages_by_agent("role-sess-1", true, 100, Some("user"))
        .await
        .unwrap();
    assert_eq!(users.len(), 2);
    assert!(users.iter().all(|m| m.role == "user"));

    let tools = store
        .query_messages_by_agent("role-sess-1", true, 100, Some("tool"))
        .await
        .unwrap();
    assert_eq!(tools.len(), 1);

    let all = store
        .query_messages_by_agent("role-sess-1", true, 100, None)
        .await
        .unwrap();
    assert_eq!(all.len(), 5);

    // search_messages: role filter applies to the vector path AND the
    // no-embedding fallback (recent_messages).
    let found = store.search_messages("france", 100, Some("assistant")).await.unwrap();
    assert_eq!(found.len(), 2);
    assert!(found.iter().all(|m| m.role == "assistant"));

    let found_none = store.search_messages("france", 100, None).await.unwrap();
    assert_eq!(found_none.len(), 5);
}

#[tokio::test]
async fn test_memory_store_compaction_agent() {
    let tmp = tempfile::tempdir().unwrap();
    let store = spawn_client(tmp.path()).await;

    let prompt_id = store
        .lookup_or_create_prompt("test", "test")
        .await
        .unwrap();

    // Create agent idx 1
    store
        .create_agent(
            "compact-session-1",
            "compact-session",
            1,
            "/tmp",
            &prompt_id,
            &serde_json::json!({}),
            "system prompt",
            &serde_json::json!([]),
            &serde_json::json!({}),
            "model",
        )
        .await
        .unwrap();

    // Create agent idx 2 (simulating compaction)
    store
        .create_agent(
            "compact-session-2",
            "compact-session",
            2,
            "/tmp",
            &prompt_id,
            &serde_json::json!({}),
            "system prompt",
            &serde_json::json!([]),
            &serde_json::json!({}),
            "model",
        )
        .await
        .unwrap();

    let max_idx = store.get_max_agent_idx("compact-session").await.unwrap();
    assert_eq!(max_idx, 2);

    let agents = store.list_agents(Some("compact-session")).await.unwrap();
    assert_eq!(agents.len(), 2);
}
