//! Isolated tests for ACP v2 tool call content model.
//!
//! Verifies: ToolCallUpdate lifecycle (Pending → InProgress → Completed),
//! Diff content (structured changes + git patch), Terminal content
//! (TerminalUpdate + TerminalOutputChunk + Terminal reference),
//! and ToolCallContentChunk streaming.
//!
//! This is a sandbox — a minimal agent that emits known tool call updates,
//! and a client that verifies every update on the wire.

use std::path::PathBuf;
use std::sync::Arc;

use agent_client_protocol::{
    Agent, Client, ConnectTo, Error, Responder, V2ConnectionTo,
    schema::{ProtocolVersion, v2 as acp},
};
use tokio::sync::{Mutex, mpsc::unbounded_channel};

// ---------------------------------------------------------------------------
// Minimal v2 agent that emits tool call content
// ---------------------------------------------------------------------------

#[derive(Clone)]
struct ToolAgent {
    sessions: Arc<Mutex<Vec<String>>>,
}

impl ToolAgent {
    fn new() -> Self {
        Self {
            sessions: Arc::new(Mutex::new(Vec::new())),
        }
    }
}

fn send_update(
    conn: &V2ConnectionTo<Client>,
    session_id: &acp::SessionId,
    update: acp::SessionUpdate,
) -> Result<(), Error> {
    conn.send_notification(acp::UpdateSessionNotification::new(
        session_id.clone(),
        update,
    ))
}

/// Emit a full edit tool call lifecycle with Diff content.
fn emit_edit_tool_call(
    conn: &V2ConnectionTo<Client>,
    sid: &acp::SessionId,
) -> Result<(), Error> {
    let tc_id = "call_edit_001";

    // 1. Create: title + kind + status=pending
    send_update(
        conn,
        sid,
        acp::SessionUpdate::ToolCallUpdate(
            acp::ToolCallUpdate::new(tc_id)
                .title("edit(src/main.rs)")
                .kind(acp::ToolKind::Edit)
                .status(acp::ToolCallStatus::Pending),
        ),
    )?;

    // 2. InProgress + raw_input
    send_update(
        conn,
        sid,
        acp::SessionUpdate::ToolCallUpdate(
            acp::ToolCallUpdate::new(tc_id)
                .status(acp::ToolCallStatus::InProgress)
                .raw_input(serde_json::json!({
                    "file_path": "/home/user/src/main.rs",
                    "old_string": "fn main() {}",
                    "new_string": "fn main() { println!(\"hello\"); }"
                })),
        ),
    )?;

    // 3. Stream a Diff content chunk
    let diff = acp::Diff::patch(
        "--- a/src/main.rs\n+++ b/src/main.rs\n@@ -1 +1 @@\n-fn main() {}\n+fn main() { println!(\"hello\"); }\n",
        vec![acp::DiffChange::modify("/home/user/src/main.rs")
            .file_type(acp::DiffFileType::Text)],
    );
    send_update(
        conn,
        sid,
        acp::SessionUpdate::ToolCallContentChunk(acp::ToolCallContentChunk::new(
            tc_id,
            acp::ToolCallContent::Diff(diff),
        )),
    )?;

    // 4. Completed + content (full replacement) + raw_output
    let final_diff = acp::Diff::patch(
        "--- a/src/main.rs\n+++ b/src/main.rs\n@@ -1 +1 @@\n-fn main() {}\n+fn main() { println!(\"hello\"); }\n",
        vec![acp::DiffChange::modify("/home/user/src/main.rs")
            .file_type(acp::DiffFileType::Text)],
    );
    send_update(
        conn,
        sid,
        acp::SessionUpdate::ToolCallUpdate(
            acp::ToolCallUpdate::new(tc_id)
                .status(acp::ToolCallStatus::Completed)
                .content(vec![acp::ToolCallContent::Diff(final_diff)])
                .raw_output(serde_json::json!({"success": true})),
        ),
    )?;

    Ok(())
}

/// Emit a full terminal tool call lifecycle with Terminal content.
fn emit_terminal_tool_call(
    conn: &V2ConnectionTo<Client>,
    sid: &acp::SessionId,
) -> Result<(), Error> {
    let tc_id = "call_term_001";
    let term_id = "term_001";

    // 1. Create: title + kind=Execute + status=InProgress
    send_update(
        conn,
        sid,
        acp::SessionUpdate::ToolCallUpdate(
            acp::ToolCallUpdate::new(tc_id)
                .title("terminal(cargo test)")
                .kind(acp::ToolKind::Execute)
                .status(acp::ToolCallStatus::InProgress)
                .raw_input(serde_json::json!({"command": "cargo test"})),
        ),
    )?;

    // 2. Terminal state upsert (command + cwd)
    send_update(
        conn,
        sid,
        acp::SessionUpdate::TerminalUpdate(
            acp::TerminalUpdate::new(term_id)
                .command("cargo test")
                .cwd("/home/user/project"),
        ),
    )?;

    // 3. Terminal output chunks (base64-encoded)
    use base64::Engine;
    let b64 = base64::engine::general_purpose::STANDARD;
    send_update(
        conn,
        sid,
        acp::SessionUpdate::TerminalOutputChunk(acp::TerminalOutputChunk::new(
            term_id,
            b64.encode(b"running 3 tests\n"),
        )),
    )?;
    send_update(
        conn,
        sid,
        acp::SessionUpdate::TerminalOutputChunk(acp::TerminalOutputChunk::new(
            term_id,
            b64.encode(b"test result: ok. 3 passed\n"),
        )),
    )?;

    // 4. Tool call content = Terminal reference + completed
    send_update(
        conn,
        sid,
        acp::SessionUpdate::ToolCallUpdate(
            acp::ToolCallUpdate::new(tc_id)
                .status(acp::ToolCallStatus::Completed)
                .content(vec![acp::ToolCallContent::Terminal(
                    acp::Terminal::new(term_id),
                )])
                .raw_output(serde_json::json!({"exit_code": 0})),
        ),
    )?;

    // 5. Terminal exit status (independent of tool call status)
    send_update(
        conn,
        sid,
        acp::SessionUpdate::TerminalUpdate(
            acp::TerminalUpdate::new(term_id)
                .exit_status(acp::TerminalExitStatus::new().exit_code(0)),
        ),
    )?;

    Ok(())
}

impl ConnectTo<Client> for ToolAgent {
    async fn connect_to(
        self,
        client: impl ConnectTo<Agent>,
    ) -> Result<(), Error> {
        Agent
            .v2()
            .name("tool-test-agent")
            .on_receive_request(
                async |req: acp::InitializeRequest,
                       responder: Responder<acp::InitializeResponse>,
                       _: V2ConnectionTo<Client>| {
                    responder.respond(
                        acp::InitializeResponse::new(
                            req.protocol_version,
                            acp::Implementation::new("tool-test-agent", "0.1.0"),
                        )
                        .capabilities(
                            acp::AgentCapabilities::new()
                                .session(acp::SessionCapabilities::new()),
                        ),
                    )
                },
                agent_client_protocol::on_receive_request!(),
            )
            .on_receive_request(
                {
                    let agent = self.clone();
                    async move |req: acp::NewSessionRequest,
                                responder: Responder<acp::NewSessionResponse>,
                                _: V2ConnectionTo<Client>| {
                        let sid = "tool-test-session-1".to_string();
                        agent.sessions.lock().await.push(sid.clone());
                        responder.respond(acp::NewSessionResponse::new(acp::SessionId::new(sid)))
                    }
                },
                agent_client_protocol::on_receive_request!(),
            )
            .on_receive_request(
                async |req: acp::PromptRequest,
                       responder: Responder<acp::PromptResponse>,
                       connection: V2ConnectionTo<Client>| {
                    let sid = req.session_id.clone();
                    responder.respond(acp::PromptResponse::new())?;

                    let conn = connection.clone();
                    connection.spawn(async move {
                        // UserMessage
                        let _ = send_update(
                            &conn,
                            &sid,
                            acp::SessionUpdate::UserMessage(
                                acp::UserMessage::new("user-1").content(vec![
                                    acp::ContentBlock::Text(acp::TextContent::new("edit main.rs then run tests")),
                                ]),
                            ),
                        );

                        // Running
                        let _ = send_update(
                            &conn,
                            &sid,
                            acp::SessionUpdate::StateUpdate(acp::StateUpdate::Running(
                                acp::RunningStateUpdate::new(),
                            )),
                        );

                        // Edit tool call with Diff content
                        let _ = emit_edit_tool_call(&conn, &sid);

                        // Terminal tool call with Terminal content
                        let _ = emit_terminal_tool_call(&conn, &sid);

                        // Final agent message
                        let _ = send_update(
                            &conn,
                            &sid,
                            acp::SessionUpdate::AgentMessageChunk(acp::ContentChunk::new(
                                acp::ContentBlock::Text(acp::TextContent::new(
                                    "Done. Edited main.rs and all 3 tests pass.",
                                )),
                                "msg-1",
                            )),
                        );

                        // Idle
                        let _ = send_update(
                            &conn,
                            &sid,
                            acp::SessionUpdate::StateUpdate(acp::StateUpdate::Idle(
                                acp::IdleStateUpdate::new().stop_reason(acp::StopReason::EndTurn),
                            )),
                        );

                        Ok(())
                    })
                },
                agent_client_protocol::on_receive_request!(),
            )
            .on_receive_request(
                async |req: acp::ListSessionsRequest,
                       responder: Responder<acp::ListSessionsResponse>,
                       _: V2ConnectionTo<Client>| {
                    responder.respond(acp::ListSessionsResponse::new(vec![
                        acp::SessionInfo::new(
                            acp::SessionId::new("tool-test-session-1"),
                            PathBuf::from("/tmp"),
                        ),
                    ]))
                },
                agent_client_protocol::on_receive_request!(),
            )
            .on_receive_request(
                async |_req: acp::CloseSessionRequest,
                       responder: Responder<acp::CloseSessionResponse>,
                       _: V2ConnectionTo<Client>| {
                    responder.respond(acp::CloseSessionResponse::new())
                },
                agent_client_protocol::on_receive_request!(),
            )
            .connect_to(client)
            .await
    }
}

// ---------------------------------------------------------------------------
// Client-side test
// ---------------------------------------------------------------------------

#[derive(Debug)]
enum TestEvent {
    Update(Box<acp::UpdateSessionNotification>),
    PromptAccepted,
}

async fn next_update(
    rx: &mut tokio::sync::mpsc::UnboundedReceiver<TestEvent>,
) -> acp::UpdateSessionNotification {
    match rx.recv().await.expect("agent should still be alive") {
        TestEvent::Update(u) => *u,
        other => panic!("expected update, got {other:?}"),
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn v2_tool_call_content_lifecycle() {
    let (tx, mut rx) = unbounded_channel::<TestEvent>();
    let update_tx = tx.clone();

    Client
        .v2()
        .on_receive_notification(
            async move |update: acp::UpdateSessionNotification,
                        _: V2ConnectionTo<Agent>| {
                update_tx
                    .send(TestEvent::Update(Box::new(update)))
                    .map_err(Error::into_internal_error)
            },
            agent_client_protocol::on_receive_notification!(),
        )
        .connect_with(ToolAgent::new(), async move |connection| {
            // Initialize
            let init = connection
                .send_request(acp::InitializeRequest::new(
                    ProtocolVersion::V2,
                    acp::Implementation::new("test-client", "0.1.0"),
                ))
                .block_task()
                .await?;
            assert_eq!(init.protocol_version, ProtocolVersion::V2);

            // New session
            let opened = connection
                .build_session(PathBuf::from("/tmp"))
                .start_session()
                .block_task()
                .await?;
            let (session, _) = opened.into_parts();

            // Send prompt
            session
                .send_prompt("edit main.rs then run tests")
                .on_receiving_result({
                    let tx = tx.clone();
                    async move |result| {
                        assert_eq!(result?, acp::PromptResponse::new());
                        tx.send(TestEvent::PromptAccepted)
                            .map_err(Error::into_internal_error)
                    }
                })?;

            // PromptAccepted
            assert!(matches!(
                rx.recv().await.unwrap(),
                TestEvent::PromptAccepted
            ));

            // 1. UserMessage
            let u = next_update(&mut rx).await;
            assert!(matches!(u.update, acp::SessionUpdate::UserMessage(_)));

            // 2. StateUpdate::Running
            let u = next_update(&mut rx).await;
            assert!(matches!(
                u.update,
                acp::SessionUpdate::StateUpdate(acp::StateUpdate::Running(_))
            ));

            // === EDIT TOOL CALL ===

            // 3. ToolCallUpdate: create (pending)
            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::ToolCallUpdate(tc) => {
                    assert_eq!(tc.tool_call_id.to_string(), "call_edit_001");
                    assert_eq!(tc.title.value().unwrap(), "edit(src/main.rs)");
                    assert_eq!(*tc.kind.value().unwrap(), acp::ToolKind::Edit);
                    assert_eq!(*tc.status.value().unwrap(), acp::ToolCallStatus::Pending);
                }
                other => panic!("expected ToolCallUpdate, got {other:?}"),
            }

            // 4. ToolCallUpdate: in_progress + raw_input
            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::ToolCallUpdate(tc) => {
                    assert_eq!(tc.tool_call_id.to_string(), "call_edit_001");
                    assert_eq!(*tc.status.value().unwrap(), acp::ToolCallStatus::InProgress);
                    let input = tc.raw_input.value().unwrap();
                    assert_eq!(input["file_path"], "/home/user/src/main.rs");
                    // title/kind should be UNCHANGED (patch semantics)
                    assert!(tc.title.is_undefined());
                    assert!(tc.kind.is_undefined());
                }
                other => panic!("expected ToolCallUpdate, got {other:?}"),
            }

            // 5. ToolCallContentChunk: Diff
            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::ToolCallContentChunk(chunk) => {
                    assert_eq!(chunk.tool_call_id.to_string(), "call_edit_001");
                    match &chunk.content {
                        acp::ToolCallContent::Diff(diff) => {
                            assert_eq!(diff.changes.len(), 1);
                            let patch = diff.patch.as_ref().unwrap();
                            assert_eq!(patch.format, acp::DiffPatchFormat::GitPatch);
                            assert!(patch.text.contains("-fn main() {}"));
                            assert!(patch.text.contains("+fn main() { println!"));
                            // Verify structured change
                            match &diff.changes[0].operation {
                                acp::DiffChangeOperation::Modify(m) => {
                                    assert_eq!(m.path.0.to_str().unwrap(), "/home/user/src/main.rs");
                                }
                                other => panic!("expected Modify, got {other:?}"),
                            }
                        }
                        other => panic!("expected Diff content, got {other:?}"),
                    }
                }
                other => panic!("expected ToolCallContentChunk, got {other:?}"),
            }

            // 6. ToolCallUpdate: completed + content replacement + raw_output
            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::ToolCallUpdate(tc) => {
                    assert_eq!(tc.tool_call_id.to_string(), "call_edit_001");
                    assert_eq!(*tc.status.value().unwrap(), acp::ToolCallStatus::Completed);
                    let content = tc.content.value().unwrap();
                    assert_eq!(content.len(), 1);
                    assert!(matches!(&content[0], acp::ToolCallContent::Diff(_)));
                    assert_eq!(tc.raw_output.value().unwrap()["success"], true);
                }
                other => panic!("expected ToolCallUpdate, got {other:?}"),
            }

            // === TERMINAL TOOL CALL ===

            // 7. ToolCallUpdate: create (in_progress)
            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::ToolCallUpdate(tc) => {
                    assert_eq!(tc.tool_call_id.to_string(), "call_term_001");
                    assert_eq!(*tc.kind.value().unwrap(), acp::ToolKind::Execute);
                    assert_eq!(*tc.status.value().unwrap(), acp::ToolCallStatus::InProgress);
                }
                other => panic!("expected ToolCallUpdate, got {other:?}"),
            }

            // 8. TerminalUpdate: command + cwd
            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::TerminalUpdate(tu) => {
                    assert_eq!(tu.terminal_id.to_string(), "term_001");
                    assert_eq!(tu.command.value().unwrap(), "cargo test");
                    assert_eq!(
                        tu.cwd.value().unwrap().0.to_str().unwrap(),
                        "/home/user/project"
                    );
                }
                other => panic!("expected TerminalUpdate, got {other:?}"),
            }

            // 9. TerminalOutputChunk x2
            use base64::Engine;
            let b64 = base64::engine::general_purpose::STANDARD;

            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::TerminalOutputChunk(chunk) => {
                    assert_eq!(chunk.terminal_id.to_string(), "term_001");
                    let decoded = b64.decode(&chunk.data).unwrap();
                    assert_eq!(String::from_utf8(decoded).unwrap(), "running 3 tests\n");
                }
                other => panic!("expected TerminalOutputChunk, got {other:?}"),
            }

            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::TerminalOutputChunk(chunk) => {
                    let decoded = b64.decode(&chunk.data).unwrap();
                    assert_eq!(String::from_utf8(decoded).unwrap(), "test result: ok. 3 passed\n");
                }
                other => panic!("expected TerminalOutputChunk, got {other:?}"),
            }

            // 10. ToolCallUpdate: completed + Terminal reference
            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::ToolCallUpdate(tc) => {
                    assert_eq!(tc.tool_call_id.to_string(), "call_term_001");
                    assert_eq!(*tc.status.value().unwrap(), acp::ToolCallStatus::Completed);
                    let content = tc.content.value().unwrap();
                    assert_eq!(content.len(), 1);
                    match &content[0] {
                        acp::ToolCallContent::Terminal(t) => {
                            assert_eq!(t.terminal_id.to_string(), "term_001");
                        }
                        other => panic!("expected Terminal content, got {other:?}"),
                    }
                }
                other => panic!("expected ToolCallUpdate, got {other:?}"),
            }

            // 11. TerminalUpdate: exit status
            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::TerminalUpdate(tu) => {
                    assert_eq!(tu.terminal_id.to_string(), "term_001");
                    let exit = tu.exit_status.value().unwrap();
                    assert_eq!(exit.exit_code, Some(0));
                }
                other => panic!("expected TerminalUpdate, got {other:?}"),
            }

            // === FINAL MESSAGE ===

            // 12. AgentMessageChunk
            let u = next_update(&mut rx).await;
            match &u.update {
                acp::SessionUpdate::AgentMessageChunk(chunk) => {
                    match &chunk.content {
                        acp::ContentBlock::Text(t) => {
                            assert!(t.text.contains("all 3 tests pass"));
                        }
                        other => panic!("expected text, got {other:?}"),
                    }
                }
                other => panic!("expected AgentMessageChunk, got {other:?}"),
            }

            // 13. StateUpdate::Idle
            let u = next_update(&mut rx).await;
            assert!(matches!(
                u.update,
                acp::SessionUpdate::StateUpdate(acp::StateUpdate::Idle(ref idle))
                    if idle.stop_reason == Some(acp::StopReason::EndTurn)
            ));

            // Session list
            let sessions = connection
                .send_request(acp::ListSessionsRequest::new())
                .block_task()
                .await?;
            assert_eq!(sessions.sessions.len(), 1);

            Ok(())
        })
        .await
        .unwrap();
}

/// Verify Diff serialization matches the wire format.
#[test]
fn diff_serialization() {
    let diff = acp::Diff::patch(
        "--- a/f.rs\n+++ b/f.rs\n@@ -1 +1 @@\n-old\n+new\n",
        vec![
            acp::DiffChange::modify("/abs/f.rs").file_type(acp::DiffFileType::Text),
        ],
    );
    let json = serde_json::to_value(&diff).unwrap();
    assert_eq!(json["patch"]["format"], "git_patch");
    assert!(json["patch"]["text"].as_str().unwrap().contains("-old"));
    assert_eq!(json["changes"][0]["operation"], "modify");
    assert_eq!(json["changes"][0]["path"], "/abs/f.rs");
    assert_eq!(json["changes"][0]["fileType"], "text");
}

/// Verify Terminal serialization matches the wire format.
#[test]
fn terminal_serialization() {
    let term = acp::Terminal::new("term_42");
    let json = serde_json::to_value(&term).unwrap();
    assert_eq!(json["terminalId"], "term_42");

    let update = acp::TerminalUpdate::new("term_42")
        .command("ls -la")
        .cwd("/tmp")
        .exit_status(acp::TerminalExitStatus::new().exit_code(0));
    let json = serde_json::to_value(&update).unwrap();
    assert_eq!(json["terminalId"], "term_42");
    assert_eq!(json["command"], "ls -la");
    assert_eq!(json["cwd"], "/tmp");
    assert_eq!(json["exitStatus"]["exitCode"], 0);
}

/// Verify ToolCallUpdate patch semantics: omitted fields don't serialize.
#[test]
fn tool_call_update_patch_semantics() {
    // First update: create with title + kind + status
    let create = acp::ToolCallUpdate::new("tc1")
        .title("read(foo.rs)")
        .kind(acp::ToolKind::Read)
        .status(acp::ToolCallStatus::Pending);
    let json = serde_json::to_value(&create).unwrap();
    assert_eq!(json["toolCallId"], "tc1");
    assert_eq!(json["title"], "read(foo.rs)");
    assert_eq!(json["kind"], "read");
    assert_eq!(json["status"], "pending");
    // raw_input should NOT be present (undefined)
    assert!(json.get("rawInput").is_none());
    assert!(json.get("content").is_none());

    // Second update: only status changes
    let patch = acp::ToolCallUpdate::new("tc1")
        .status(acp::ToolCallStatus::InProgress);
    let json = serde_json::to_value(&patch).unwrap();
    assert_eq!(json["toolCallId"], "tc1");
    assert_eq!(json["status"], "in_progress");
    // title/kind should NOT be present (undefined = no change)
    assert!(json.get("title").is_none());
    assert!(json.get("kind").is_none());
}

/// Verify ToolCallContentChunk serialization.
#[test]
fn tool_call_content_chunk_serialization() {
    let chunk = acp::ToolCallContentChunk::new(
        "tc1",
        acp::ToolCallContent::from(acp::ContentBlock::Text(acp::TextContent::new("hello"))),
    );
    let json = serde_json::to_value(&chunk).unwrap();
    assert_eq!(json["toolCallId"], "tc1");
    assert_eq!(json["content"]["type"], "content");
    assert_eq!(json["content"]["content"]["type"], "text");
    assert_eq!(json["content"]["content"]["text"], "hello");
}

/// Verify TerminalOutputChunk base64 encoding.
#[test]
fn terminal_output_chunk_base64() {
    use base64::Engine;
    let b64 = base64::engine::general_purpose::STANDARD;
    let data = b64.encode(b"hello world\n");
    let chunk = acp::TerminalOutputChunk::new("term_1", data.clone());
    let json = serde_json::to_value(&chunk).unwrap();
    assert_eq!(json["terminalId"], "term_1");
    assert_eq!(json["data"], data);
    // Verify round-trip
    let decoded = b64.decode(json["data"].as_str().unwrap()).unwrap();
    assert_eq!(decoded, b"hello world\n");
}
