//! Append-only resume contract (demanded by dogfooding):
//!
//! On resume, the session must have the EXACT same history as before, plus
//! the things that happened since — no loss, no reorder, no duplication.
//! Compaction creates a new agent generation; resume must load the chain
//! head (highest agent_idx), never a stale generation. An abrupt death may
//! leave a dangling assistant tool_calls tail; resume repairs it without
//! touching the stored history.
//!
//! `resume_load` mirrors the agent.rs resume pipeline exactly:
//! list_agents -> pick_resume_agent -> query_messages_by_agent(asc) ->
//! fill_missing_tool_responses.

use crow_memory_sdk::MemoryClient;

/// Mirror of the agent.rs resume load pipeline.
async fn resume_load(
    store: &MemoryClient,
    sid: &str,
) -> (crow_memory_sdk::AgentRecord, Vec<serde_json::Value>) {
    let agents = store.list_agents(Some(sid)).await.unwrap();
    assert!(!agents.is_empty(), "no agent records for session {sid}");
    let rec = crow_cli::session::pick_resume_agent(&agents).clone();
    let rows = store
        .query_messages_by_agent(&rec.agent_id, true, 100_000, None, false)
        .await
        .unwrap();
    let stored: Vec<serde_json::Value> = rows.into_iter().map(|m| m.data).collect();
    let repaired = crow_cli::compact::fill_missing_tool_responses(&stored);
    (rec, repaired)
}

/// Real crow-memory axum server on a temp LanceDB + SDK client — the
/// production path, not an in-process shortcut.
async fn make_store() -> (tempfile::TempDir, MemoryClient, String) {
    let tmp = tempfile::tempdir().unwrap();
    let store =
        crow_memory::MemoryStore::open(tmp.path(), crow_memory::EmbedConfig::default())
            .await
            .unwrap();
    let app = crow_memory::router(std::sync::Arc::new(store));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    let client = MemoryClient::connect(format!("http://{addr}"));
    let prompt_id = client.lookup_or_create_prompt("system", "t").await.unwrap();
    (tmp, client, prompt_id)
}

async fn make_agent(store: &MemoryClient, sid: &str, agent_id: &str, idx: i64, prompt_id: &str) {
    store
        .create_agent(
            agent_id,
            sid,
            idx,
            "/tmp",
            prompt_id,
            &serde_json::json!({}),
            "system prompt",
            &serde_json::json!([]),
            &serde_json::json!({}),
            "test-model",
        )
        .await
        .unwrap();
}

fn user(text: &str) -> serde_json::Value {
    serde_json::json!({"role": "user", "content": text})
}
fn assistant(text: &str) -> serde_json::Value {
    serde_json::json!({"role": "assistant", "content": text})
}
fn system(text: &str) -> serde_json::Value {
    serde_json::json!({"role": "system", "content": text})
}

#[tokio::test]
async fn resume_history_is_exact_then_append_only() {
    let (_tmp, store, prompt_id) = make_store().await;
    let sid = "append-only-1";
    make_agent(&store, sid, "append-only-1-1", 1, &prompt_id).await;

    // Turn 1
    let turn1 = [
        system("You are a test agent."),
        user("hello"),
        assistant("hi there"),
    ];
    for m in &turn1 {
        store.add_message("append-only-1-1", m, None).await.unwrap();
    }

    // Resume #1: history is EXACTLY what was stored, in order.
    let (rec, loaded) = resume_load(&store, sid).await;
    assert_eq!(rec.agent_idx, 1);
    assert_eq!(loaded, turn1, "resume must load the exact stored history");

    // Turn 2 happens since.
    let turn2 = [user("what did I just say?"), assistant("you said hello")];
    for m in &turn2 {
        store.add_message("append-only-1-1", m, None).await.unwrap();
    }

    // Resume #2: exact prior history PLUS the new turns. Nothing lost,
    // reordered, or duplicated.
    let (rec, loaded) = resume_load(&store, sid).await;
    assert_eq!(rec.agent_idx, 1);
    let mut expected = turn1.to_vec();
    expected.extend_from_slice(&turn2);
    assert_eq!(loaded, expected, "resume must be append-only across turns");

    // Turn 3, then resume again — invariant holds inductively.
    let turn3 = [user("and then?"), assistant("and then you asked this")];
    for m in &turn3 {
        store.add_message("append-only-1-1", m, None).await.unwrap();
    }
    let (_, loaded) = resume_load(&store, sid).await;
    let mut expected = turn1.to_vec();
    expected.extend_from_slice(&turn2);
    expected.extend_from_slice(&turn3);
    assert_eq!(loaded, expected);
}

#[tokio::test]
async fn resume_message_ids_strictly_increase_across_resumes() {
    let (_tmp, store, prompt_id) = make_store().await;
    let sid = "append-only-ids";
    make_agent(&store, sid, "append-only-ids-1", 1, &prompt_id).await;

    let mut last_id = 0i64;
    for i in 0..3 {
        store
            .add_message("append-only-ids-1", &user(&format!("msg {i}")), None)
            .await
            .map(|id| {
                assert!(id > last_id, "message ids must strictly increase");
                last_id = id;
            })
            .unwrap();
        // Simulate death + resume between every append: the ids already on
        // disk must come back in the same strictly-increasing order.
        let rows = store
            .query_messages_by_agent("append-only-ids-1", true, 100_000, None, false)
            .await
            .unwrap();
        let ids: Vec<i64> = rows.iter().map(|r| r.id).collect();
        let mut sorted = ids.clone();
        sorted.sort();
        assert_eq!(ids, sorted, "resume order must match insertion order");
        assert!(ids.windows(2).all(|w| w[0] < w[1]), "no duplicate ids");
    }
}

#[tokio::test]
async fn resume_after_compaction_loads_chain_head_only() {
    let (_tmp, store, prompt_id) = make_store().await;
    let sid = "compact-chain";

    // Generation 1: long history.
    make_agent(&store, sid, "compact-chain-1", 1, &prompt_id).await;
    for i in 0..6 {
        store
            .add_message("compact-chain-1", &user(&format!("old {i}")), None)
            .await
            .unwrap();
    }

    // Generation 2: compaction (summary seed).
    make_agent(&store, sid, "compact-chain-2", 2, &prompt_id).await;
    let gen2_seed = [
        system("You are a test agent."),
        user("# Conversation Summary\nold stuff happened"),
        assistant("ok, continuing"),
    ];
    for m in &gen2_seed {
        store.add_message("compact-chain-2", m, None).await.unwrap();
    }

    // Generation 3: a second compaction.
    make_agent(&store, sid, "compact-chain-3", 3, &prompt_id).await;
    let gen3_seed = [
        system("You are a test agent."),
        user("# Conversation Summary\nolder stuff happened"),
    ];
    for m in &gen3_seed {
        store.add_message("compact-chain-3", m, None).await.unwrap();
    }

    // Resume picks the chain head (idx 3), NOT a stale generation, and loads
    // only that generation's messages.
    let (rec, loaded) = resume_load(&store, sid).await;
    assert_eq!(rec.agent_id, "compact-chain-3");
    assert_eq!(rec.agent_idx, 3);
    assert_eq!(loaded, gen3_seed);

    // Append-only still holds on the head generation after resume.
    let new_turn = [user("next"), assistant("done")];
    for m in &new_turn {
        store.add_message("compact-chain-3", m, None).await.unwrap();
    }
    let (rec, loaded) = resume_load(&store, sid).await;
    assert_eq!(rec.agent_idx, 3);
    let mut expected = gen3_seed.to_vec();
    expected.extend_from_slice(&new_turn);
    assert_eq!(loaded, expected);
}

#[tokio::test]
async fn resume_repairs_dangling_tool_calls_idempotently() {
    let (_tmp, store, prompt_id) = make_store().await;
    let sid = "dangling-tail";
    make_agent(&store, sid, "dangling-tail-1", 1, &prompt_id).await;

    let tool_call_msg = serde_json::json!({
        "role": "assistant",
        "content": null,
        "tool_calls": [
            {"id": "call_a", "type": "function",
             "function": {"name": "terminal", "arguments": "{}"}},
            {"id": "call_b", "type": "function",
             "function": {"name": "terminal", "arguments": "{}"}},
        ],
    });
    let prefix = [system("sys"), user("do two things"), tool_call_msg.clone()];
    for m in &prefix {
        store.add_message("dangling-tail-1", m, None).await.unwrap();
    }
    // Only call_a got a response before the client died.
    store
        .add_message(
            "dangling-tail-1",
            &serde_json::json!({"role": "tool", "tool_call_id": "call_a", "content": "ok"}),
            None,
        )
        .await
        .unwrap();

    // Resume repairs the tail: stored prefix untouched, exactly one synthetic
    // response for call_b appended.
    let (_, loaded) = resume_load(&store, sid).await;
    assert_eq!(loaded.len(), prefix.len() + 2, "prefix + tool_a + synthetic tool_b");
    assert_eq!(&loaded[..3], &prefix, "stored history must be untouched");
    assert_eq!(loaded[3]["tool_call_id"], "call_a");
    assert_eq!(loaded[4]["role"], "tool");
    assert_eq!(loaded[4]["tool_call_id"], "call_b");

    // Idempotent: repairing an already-repaired load changes nothing.
    let repaired_again = crow_cli::compact::fill_missing_tool_responses(&loaded);
    assert_eq!(repaired_again, loaded, "repair must be idempotent");

    // The repair is load-time only — nothing was persisted. A fresh resume
    // sees the same stored history and repairs it identically.
    let (_, loaded2) = resume_load(&store, sid).await;
    assert_eq!(loaded2, loaded);

    // After resume the agent persists the NEXT turn; append-only still holds
    // and the repair does not duplicate.
    store
        .add_message("dangling-tail-1", &user("keep going"), None)
        .await
        .unwrap();
    let (_, loaded3) = resume_load(&store, sid).await;
    assert_eq!(loaded3.last().unwrap()["content"], "keep going");
    let tool_b_count = loaded3
        .iter()
        .filter(|m| m["role"] == "tool" && m["tool_call_id"] == "call_b")
        .count();
    assert_eq!(tool_b_count, 1, "synthetic repair must not duplicate");
}
