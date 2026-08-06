//! The react loop: LLM ↔ MCP tool execution cycle.
//!
//! Port of Python crow-cli/agent/react.py with:
//! - Cancellation via CancellationToken
//! - Message persistence via the crow-memory service (MemoryClient)
//! - Compaction when token threshold exceeded
//! - ACP v2 tool call content (Diff, Terminal, Content)
//! - History recording for session/resume replay

use std::collections::HashMap;
use std::sync::Arc;

use async_openai_thinking::types::chat::{
    ChatCompletionMessageToolCall, ChatCompletionRequestMessage,
    ChatCompletionTools, CreateChatCompletionRequestArgs,
};
use futures::StreamExt;
use rmcp::model::CallToolRequestParams;
use rmcp::service::{RoleClient, RunningService};
use tokio_util::sync::CancellationToken;

use agent_client_protocol::schema::v2 as acp;

use crate::compact;
use crate::config::Config;
use crow_memory_sdk::MemoryClient;
use crate::session::AgentSession;

type McpClient = Arc<RunningService<RoleClient, crate::agent::McpHandler>>;

/// Run the react loop for one prompt turn.
///
/// Returns the stop reason. Records whole-message upserts in `history`
/// for session/resume replay. Uses `msg_counter` for unique message IDs.
#[allow(clippy::too_many_arguments)]
pub async fn react_loop(
    updates: &tokio::sync::broadcast::Sender<acp::SessionUpdate>,
    session_id: &acp::SessionId,
    config: &Config,
    llm: &async_openai_thinking::Client<async_openai_thinking::config::OpenAIConfig>,
    mcp_clients: &[McpClient],
    session: &mut AgentSession,
    store: &MemoryClient,
    tools: &[ChatCompletionTools],
    history: &mut Vec<acp::SessionUpdate>,
    msg_counter: &mut u64,
    cancel: CancellationToken,
    msg_rx: &mut tokio::sync::mpsc::Receiver<String>,
    progress_rx: &mut tokio::sync::mpsc::UnboundedReceiver<rmcp::model::ProgressNotificationParam>,
) -> anyhow::Result<acp::StopReason> {
    let mut turn = 0u32;
    // 12.5: optional OpenAI request/response JSONL trace (CROW_LLM_TRACE).
    let trace = crate::llm::trace_path(&config.config_dir);
    loop {
        if turn >= 50_000 {
            break;
        }
        turn += 1;

        // Build OpenAI messages from session history
        let messages: Vec<ChatCompletionRequestMessage> = session
            .messages
            .iter()
            .filter_map(|m| crate::compact::json_to_openai_message(m))
            .collect();

        let mut req = CreateChatCompletionRequestArgs::default();
        req.model(session.model_identifier.as_str())
            .messages(messages)
            .temperature(config.temperature)
            .max_tokens(config.max_tokens)
            .parallel_tool_calls(true);

        if !tools.is_empty() {
            req.tools(tools.to_vec());
        }

        if cancel.is_cancelled() {
            return Ok(acp::StopReason::Cancelled);
        }

        // Retry transient provider errors (alibaba endpoint intermittently
        // rejects valid requests with validator errors from bad replicas).
        let request = req.build()?;
        if let Some(tp) = &trace {
            crate::llm::trace_append(
                tp,
                serde_json::json!({
                    "type": "request",
                    "ts": chrono::Utc::now().to_rfc3339(),
                    "session": session_id.to_string(),
                    "turn": turn,
                    "body": request,
                }),
            );
        }
        let mut attempt = 0u32;
        let mut stream = loop {
            attempt += 1;
            match llm.chat().create_stream(request.clone()).await {
                Ok(s) => break s,
                Err(e) if attempt < 3 => {
                    tracing::warn!("LLM call failed (attempt {attempt}): {e} — retrying");
                    tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                }
                Err(e) => return Err(e.into()),
            }
        };

        let mut content: Vec<String> = Vec::new();
        let mut thinking: Vec<String> = Vec::new();
        let mut tc_accum: HashMap<u32, (String, String, String)> = HashMap::new();
        let mut usage: Option<serde_json::Value> = None;
        let mut soft_cancelled = false;

        // Agent message ID for this turn (allocated up front)
        *msg_counter += 1;
        let agent_msg_id = format!("msg-{msg_counter}");
        let thought_msg_id = format!("thought-{msg_counter}");

        loop {
            tokio::select! {
                _ = cancel.cancelled() => {
                    tracing::info!("React loop cancelled mid-stream");
                    session.add_assistant_response(
                        store, &thinking, &content, &[], None,
                    ).await;
                    return Ok(acp::StopReason::Cancelled);
                }
                // Soft cancel mid-stream: safe to interrupt LLM (no side effects).
                // Save partial content, inject new message, re-enter loop.
                injected = msg_rx.recv() => {
                    if let Some(msg) = injected {
                        tracing::info!("Soft cancel mid-stream: injecting new context");
                        // Save partial assistant response
                        session.add_assistant_response(
                            store, &thinking, &content, &[], None,
                        ).await;
                        // Inject new user message
                        let user_msg = serde_json::json!({"role": "user", "content": msg});
                        session.add_message(store, user_msg, None).await;
                        // Drain any additional queued messages
                        while let Ok(extra) = msg_rx.try_recv() {
                            let extra_msg = serde_json::json!({"role": "user", "content": extra});
                            session.add_message(store, extra_msg, None).await;
                        }
                        soft_cancelled = true;
                        // Break inner stream loop → re-enter outer react loop
                        break;
                    }
                }
                chunk = stream.next() => {
                    let Some(chunk) = chunk else { break };
                    let chunk = chunk?;

                    if let Some(u) = &chunk.usage {
                        usage = Some(serde_json::json!({
                            "prompt_tokens": u.prompt_tokens,
                            "completion_tokens": u.completion_tokens,
                            "total_tokens": u.total_tokens,
                        }));
                    }

                    let Some(choice) = chunk.choices.first() else { continue };
                    let delta = &choice.delta;

                    // Reasoning / thinking (async-openai fork)
                    if let Some(reasoning) = delta.reasoning_content.as_deref() {
                        if !reasoning.is_empty() {
                            thinking.push(reasoning.to_string());
                            send_update(
                                updates,
                                session_id,
                                acp::SessionUpdate::AgentThoughtChunk(acp::ContentChunk::new(
                                    acp::ContentBlock::Text(acp::TextContent::new(reasoning)),
                                    thought_msg_id.as_str(),
                                )),
                            )?;
                        }
                    }

                    // Content
                    if let Some(text) = delta.content.as_deref() {
                        if !text.is_empty() {
                            content.push(text.to_string());
                            send_update(
                                updates,
                                session_id,
                                acp::SessionUpdate::AgentMessageChunk(acp::ContentChunk::new(
                                    acp::ContentBlock::Text(acp::TextContent::new(text)),
                                    agent_msg_id.as_str(),
                                )),
                            )?;
                        }
                    }

                    // Tool calls accumulation (keyed by index — see openai-streaming-tools skill)
                    if let Some(calls) = &delta.tool_calls {
                        for call in calls {
                            tracing::debug!(
                                "tc delta: idx={} id={:?} fn_name={:?} fn_args={:?}",
                                call.index,
                                call.id,
                                call.function.as_ref().and_then(|f| f.name.as_deref()),
                                call.function.as_ref().and_then(|f| f.arguments.as_deref().map(|a| &a[..a.len().min(60)])),
                            );
                            let entry = tc_accum.entry(call.index).or_default();
                            // NOTE: qwen/alibaba sends id="" / name="" (empty strings,
                            // not null) on continuation deltas — only overwrite when
                            // non-empty or the accumulated value gets blanked.
                            if let Some(id) = &call.id {
                                if !id.is_empty() {
                                    entry.0 = id.clone();
                                }
                            }
                            if let Some(f) = &call.function {
                                if let Some(name) = &f.name {
                                    if !name.is_empty() {
                                        entry.1 = name.clone();
                                    }
                                }
                                if let Some(args) = &f.arguments {
                                    entry.2.push_str(args);
                                }
                            }
                        }
                    }
                }
            }
        }

        // Assemble tool calls (sorted by index for deterministic order)
        let mut tool_calls: Vec<ChatCompletionMessageToolCall> = Vec::new();
        let mut tool_call_json: Vec<serde_json::Value> = Vec::new();
        let mut indices: Vec<u32> = tc_accum.keys().copied().collect();
        indices.sort();
        tracing::debug!("tc_accum: {} entries, indices={:?}", indices.len(), indices);
        for idx in indices {
            let (id, name, arguments) = tc_accum.remove(&idx).unwrap();
            let arguments = repair_json_args(&arguments);
            // Coerce stringified values to the schema's declared types BEFORE
            // persistence + execution, so stored history, the ACP raw_input
            // display, and the MCP call all agree.
            let arguments = match serde_json::from_str::<serde_json::Value>(&arguments) {
                Ok(mut v) => {
                    coerce_args_to_schema(&mut v, tool_schema(tools, &name));
                    v.to_string()
                }
                Err(_) => arguments,
            };

            tool_calls.push(ChatCompletionMessageToolCall {
                id: id.clone(),
                function: async_openai_thinking::types::chat::FunctionCall {
                    name: name.clone(),
                    arguments: arguments.clone(),
                },
            });
            tool_call_json.push(serde_json::json!({
                "id": id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }));
        }

        // Compaction check
        if let Some(tp) = &trace {
            crate::llm::trace_append(
                tp,
                serde_json::json!({
                    "type": "response",
                    "ts": chrono::Utc::now().to_rfc3339(),
                    "session": session_id.to_string(),
                    "turn": turn,
                    "thinking": thinking.join(""),
                    "content": content.join(""),
                    "tool_calls": tool_call_json,
                    "usage": usage,
                }),
            );
        }
        if let Some(u) = &usage {
            let total = u.get("total_tokens").and_then(|t| t.as_u64()).unwrap_or(0);
            if total > config.max_compact_tokens as u64 {
                tracing::info!("Token threshold crossed ({total}). Compacting...");
                send_update(
                    updates,
                    session_id,
                    acp::SessionUpdate::AgentMessageChunk(acp::ContentChunk::new(
                        acp::ContentBlock::Text(acp::TextContent::new(
                            &format!("\n\nCompaction threshold of {} reached — compacting...\n\n", config.max_compact_tokens),
                        )),
                        agent_msg_id.as_str(),
                    )),
                )?;

                session.add_assistant_response(
                    store, &thinking, &content, &tool_call_json, usage.clone(),
                ).await;

                let new_session = compact::compact(session, store, llm, config).await?;
                *session = new_session;
                continue;
            }
        }

        // Soft cancel mid-stream: skip EndTurn, re-enter outer loop with new context
        if soft_cancelled {
            continue;
        }

        // No tool calls → done. Record whole-message upsert for replay.
        if tool_calls.is_empty() {
            session
                .add_assistant_response(store, &thinking, &content, &[], usage)
                .await;

            let full_text = content.join("");
            if !full_text.is_empty() {
                let agent_msg = acp::SessionUpdate::AgentMessage(
                    acp::AgentMessage::new(agent_msg_id.as_str()).content(vec![
                        acp::ContentBlock::Text(acp::TextContent::new(&full_text)),
                    ]),
                );
                history.push(agent_msg);
            }

            return Ok(acp::StopReason::EndTurn);
        }

        // Persist assistant message with tool calls
        session
            .add_assistant_response(store, &thinking, &content, &tool_call_json, usage)
            .await;

        // Execute tools via MCP with v2 ToolCallUpdate lifecycle
        let mut tool_results: Vec<serde_json::Value> = Vec::new();
        let mut hard_cancelled = false;
        for tc in &tool_calls {
            // Hard cancel already landed: don't start further calls, but record
            // a synthetic result per call id so the persisted history stays a
            // valid OpenAI sequence (every tool_call needs a tool response).
            if hard_cancelled {
                let _ = send_update(
                    updates,
                    session_id,
                    acp::SessionUpdate::ToolCallUpdate(
                        acp::ToolCallUpdate::new(tc.id.as_str())
                            .title(format!("{}(...)", tc.function.name))
                            .kind(tool_kind(&tc.function.name))
                            .status(acp::ToolCallStatus::Failed)
                            .content(vec![acp::ToolCallContent::from(
                                acp::ContentBlock::Text(acp::TextContent::new("cancelled")),
                            )]),
                    ),
                );
                tool_results.push(serde_json::json!({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": "Error: cancelled",
                }));
                continue;
            }
            tracing::info!("tool: {}", tc.function.name);

            let args: serde_json::Value =
                serde_json::from_str(&tc.function.arguments).unwrap_or(serde_json::json!({}));

            // Create: title + kind + status=pending
            let _ = send_update(
                updates,
                session_id,
                acp::SessionUpdate::ToolCallUpdate(
                    acp::ToolCallUpdate::new(tc.id.as_str())
                        .title(format!("{}(...)", tc.function.name))
                        .kind(tool_kind(&tc.function.name))
                        .status(acp::ToolCallStatus::Pending)
                        .raw_input(args.clone()),
                ),
            );

            // InProgress
            let _ = send_update(
                updates,
                session_id,
                acp::SessionUpdate::ToolCallUpdate(
                    acp::ToolCallUpdate::new(tc.id.as_str())
                        .status(acp::ToolCallStatus::InProgress),
                ),
            );

            let tool_fut = call_tool(mcp_clients, &tc.function.name, args.clone(), &tc.id);
            tokio::pin!(tool_fut);
            let mut cancelled_here = false;
            let tool_result = loop {
                tokio::select! {
                    _ = cancel.cancelled() => {
                        tracing::info!("Hard cancel during tool: {}", tc.function.name);
                        cancelled_here = true;
                        break Err(anyhow::anyhow!("cancelled"));
                    }
                    result = &mut tool_fut => break result,
                    Some(p) = progress_rx.recv() => {
                        // Live terminal bytes: crow-mcp streams PTY chunks as
                        // progress notifications. NOTE: rmcp rewrites the
                        // outgoing progressToken with its own, so attribute by
                        // timing — exactly one tool call is in flight here and
                        // only crow-mcp's terminal tool emits progress
                        // messages.
                        if let Some(b64) = &p.message {
                            let _ = send_update(
                                updates,
                                session_id,
                                acp::SessionUpdate::TerminalOutputChunk(
                                    acp::TerminalOutputChunk::new(
                                        format!("term_{}", tc.id).as_str(),
                                        b64.as_str(),
                                    ),
                                ),
                            );
                        }
                    }
                }
            };
            if cancelled_here {
                hard_cancelled = true;
                let _ = send_update(
                    updates,
                    session_id,
                    acp::SessionUpdate::ToolCallUpdate(
                        acp::ToolCallUpdate::new(tc.id.as_str())
                            .status(acp::ToolCallStatus::Failed)
                            .content(vec![acp::ToolCallContent::from(
                                acp::ContentBlock::Text(acp::TextContent::new("cancelled")),
                            )]),
                    ),
                );
                tool_results.push(serde_json::json!({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": "Error: cancelled",
                }));
                continue;
            }
            match tool_result {
                Ok(result) => {
                    // Extract text and image content blocks
                    let mut text_parts: Vec<String> = Vec::new();
                    let mut content_blocks: Vec<serde_json::Value> = Vec::new();
                    let mut has_image = false;

                    for block in &result.content {
                        match block {
                            rmcp::model::ContentBlock::Text(t) => {
                                text_parts.push(t.text.to_string());
                                content_blocks.push(serde_json::json!({
                                    "type": "text",
                                    "text": t.text,
                                }));
                            }
                            rmcp::model::ContentBlock::Image(img) => {
                                has_image = true;
                                let data_url = format!("data:{};base64,{}", img.mime_type, img.data);
                                content_blocks.push(serde_json::json!({
                                    "type": "image_url",
                                    "image_url": {"url": data_url},
                                }));
                                text_parts.push(format!("[image: {}]", img.mime_type));
                            }
                            _ => {}
                        }
                    }

                    let text = text_parts.join("\n");

                    // terminal tool: lift raw PTY bytes into the ACP Terminal
                    // schema; `text` comes back cleaned (what the LLM sees).
                    let (text, term_payload) =
                        extract_terminal_payload(&tc.function.name, text, &args, &tc.id);

                    if let Some(tp) = &term_payload {
                        let mut tu = acp::TerminalUpdate::new(tp.terminal_id.as_str())
                            .command(tp.command.clone())
                            .output(acp::TerminalOutput::new(tp.raw_b64.clone()));
                        if let Some(cwd) = &tp.cwd {
                            tu = tu.cwd(acp::AbsolutePath::new(std::path::PathBuf::from(cwd)));
                        }
                        if let Some(code) = tp.exit_code {
                            tu = tu.exit_status(acp::TerminalExitStatus::new().exit_code(code));
                        }
                        let _ = send_update(
                            updates,
                            session_id,
                            acp::SessionUpdate::TerminalUpdate(tu),
                        );
                    }

                    // Build appropriate ToolCallContent based on tool type
                    let tool_content = match &term_payload {
                        Some(tp) => vec![acp::ToolCallContent::Terminal(acp::Terminal::new(
                            tp.terminal_id.as_str(),
                        ))],
                        None => build_tool_content(&tc.function.name, &text, &args),
                    };

                    // Completed + content + raw_output
                    let _ = send_update(
                        updates,
                        session_id,
                        acp::SessionUpdate::ToolCallUpdate(
                            acp::ToolCallUpdate::new(tc.id.as_str())
                                .status(acp::ToolCallStatus::Completed)
                                .content(tool_content)
                                .raw_output(serde_json::json!({"result": &text})),
                        ),
                    );

                    // Use multi-content format if images present, plain string otherwise
                    let tool_msg_content = if has_image {
                        serde_json::Value::Array(content_blocks)
                    } else {
                        serde_json::Value::String(text.clone())
                    };

                    tool_results.push(serde_json::json!({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_msg_content,
                    }));
                }
                Err(e) => {
                    let err_text = format!("Error: {e}");
                    let _ = send_update(
                        updates,
                        session_id,
                        acp::SessionUpdate::ToolCallUpdate(
                            acp::ToolCallUpdate::new(tc.id.as_str())
                                .status(acp::ToolCallStatus::Failed)
                                .content(vec![acp::ToolCallContent::from(
                                    acp::ContentBlock::Text(acp::TextContent::new(&err_text)),
                                )])
                                .raw_output(serde_json::json!({"error": &err_text})),
                        ),
                    );

                    tool_results.push(serde_json::json!({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": err_text,
                    }));
                }
            }
        }

        // Persist tool results
        session.add_tool_response(store, &tool_results).await;

        // Hard cancel: the persisted history is complete (assistant tool_calls
        // + one tool response per call). End the turn; do not re-enter the model.
        if hard_cancelled {
            return Ok(acp::StopReason::Cancelled);
        }

        // Soft cancel: check for injected messages. If present, add as user
        // message and re-enter the loop — the LLM sees the new context and
        // adjusts course without a hard cancel.
        while let Ok(injected) = msg_rx.try_recv() {
            tracing::info!("Soft cancel: injecting new user message mid-turn");
            let user_msg = serde_json::json!({"role": "user", "content": injected});
            session.add_message(store, user_msg, None).await;
        }
    }

    Ok(acp::StopReason::EndTurn)
}

/// Build the appropriate ToolCallContent for a completed tool.
///
/// - edit/write → Diff (structured change + git patch placeholder)
/// - edit → Diff (DiffChange::modify + git unified patch via `similar`)
/// - write → Diff (DiffChange::add + git unified patch)
/// - terminal → Terminal reference (with TerminalUpdate for output)
/// - everything else → Content (text block)
/// Raw PTY output lifted from the crow-mcp terminal tool result.
struct TerminalPayload {
    terminal_id: String,
    command: String,
    cwd: Option<String>,
    raw_b64: String,
    exit_code: Option<u32>,
}

/// For the `terminal` tool, pull `raw_bytes_b64` out of the JSON result and
/// return (cleaned text for the LLM, payload for the ACP Terminal schema).
fn extract_terminal_payload(
    tool_name: &str,
    text: String,
    args: &serde_json::Value,
    tool_call_id: &str,
) -> (String, Option<TerminalPayload>) {
    if tool_name != "terminal" {
        return (text, None);
    }
    let Ok(mut json) = serde_json::from_str::<serde_json::Value>(&text) else {
        return (text, None);
    };
    let Some(obj) = json.as_object_mut() else {
        return (text, None);
    };
    let Some(raw_b64) = obj
        .remove("raw_bytes_b64")
        .and_then(|v| v.as_str().map(String::from))
    else {
        return (text, None);
    };

    let exit_code = obj
        .get("exit_code")
        .and_then(|v| v.as_i64())
        .filter(|c| *c >= 0)
        .map(|c| c as u32);
    let cleaned = serde_json::to_string_pretty(&json).unwrap_or_else(|_| text.clone());
    let payload = TerminalPayload {
        terminal_id: format!("term_{tool_call_id}"),
        command: args
            .get("command")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        cwd: args
            .get("cwd")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .map(String::from)
            .or_else(|| std::env::current_dir().ok().map(|p| p.to_string_lossy().into_owned())),
        raw_b64,
        exit_code,
    };
    (cleaned, Some(payload))
}

fn build_tool_content(
    tool_name: &str,
    result_text: &str,
    args: &serde_json::Value,
) -> Vec<acp::ToolCallContent> {
    match tool_name {
        "edit" => {
            let file_path = args.get("file_path").and_then(|v| v.as_str()).unwrap_or("");
            let old_string = args.get("old_string").and_then(|v| v.as_str()).unwrap_or("");
            let new_string = args.get("new_string").and_then(|v| v.as_str()).unwrap_or("");

            if file_path.is_empty() || old_string.is_empty() {
                return vec![acp::ToolCallContent::from(
                    acp::ContentBlock::Text(acp::TextContent::new(result_text)),
                )];
            }

            let abs_path = ensure_absolute(file_path);
            let patch_text = unified_diff(file_path, old_string, new_string);
            let diff = acp::Diff::patch(
                patch_text,
                vec![acp::DiffChange::modify(abs_path.as_str())
                    .file_type(acp::DiffFileType::Text)],
            );
            vec![acp::ToolCallContent::Diff(diff)]
        }
        "write" => {
            let file_path = args.get("file_path").and_then(|v| v.as_str()).unwrap_or("");
            if file_path.is_empty() {
                return vec![acp::ToolCallContent::from(
                    acp::ContentBlock::Text(acp::TextContent::new(result_text)),
                )];
            }
            let abs_path = ensure_absolute(file_path);
            let content = args.get("content").and_then(|v| v.as_str()).unwrap_or("");
            let patch_text = unified_diff(file_path, "", content);
            let diff = acp::Diff::patch(
                patch_text,
                vec![acp::DiffChange::add(abs_path.as_str())
                    .file_type(acp::DiffFileType::Text)],
            );
            vec![acp::ToolCallContent::Diff(diff)]
        }
        _ => {
            vec![acp::ToolCallContent::from(
                acp::ContentBlock::Text(acp::TextContent::new(result_text)),
            )]
        }
    }
}

fn ensure_absolute(path: &str) -> String {
    if path.starts_with('/') {
        path.to_string()
    } else {
        format!("/{}", path)
    }
}

/// Generate a git-style unified diff from old → new content using `similar`.
fn unified_diff(file_path: &str, old: &str, new: &str) -> String {
    use similar::{ChangeTag, TextDiff};

    // Strip leading / for the a/ b/ header (git convention)
    let display_path = file_path.strip_prefix('/').unwrap_or(file_path);
    let diff = TextDiff::from_lines(old, new);
    let mut patch = format!("--- a/{display_path}\n+++ b/{display_path}\n");

    for group in diff.grouped_ops(3) {
        let old_start = group.first().map(|op| op.old_range().start + 1).unwrap_or(1);
        let old_len: usize = group.iter().map(|op| op.old_range().len()).sum();
        let new_start = group.first().map(|op| op.new_range().start + 1).unwrap_or(1);
        let new_len: usize = group.iter().map(|op| op.new_range().len()).sum();

        patch.push_str(&format!(
            "@@ -{},{} +{},{} @@\n",
            old_start, old_len, new_start, new_len
        ));

        for op in &group {
            for change in diff.iter_changes(op) {
                let sign = match change.tag() {
                    ChangeTag::Delete => "-",
                    ChangeTag::Insert => "+",
                    ChangeTag::Equal => " ",
                };
                patch.push_str(sign);
                patch.push_str(change.value());
                if change.missing_newline() {
                    patch.push('\n');
                }
            }
        }
    }

    patch
}

async fn call_tool(
    clients: &[McpClient],
    name: &str,
    arguments: serde_json::Value,
    tool_call_id: &str,
) -> anyhow::Result<rmcp::model::CallToolResult> {
    let mut params = CallToolRequestParams::new(name.to_string());
    if let serde_json::Value::Object(map) = arguments {
        params = params.with_arguments(map);
    }
    // Attach a progressToken (= tool call id) so streaming MCP servers
    // (crow-mcp terminal) can push live output chunks as progress
    // notifications while the call is in flight.
    params.meta = Some(rmcp::model::Meta::with_progress_token(
        rmcp::model::ProgressToken(rmcp::model::NumberOrString::String(
            tool_call_id.into(),
        )),
    ));

    for client in clients {
        match client.peer().call_tool(params.clone()).await {
            Ok(result) => return Ok(result),
            Err(_) => continue,
        }
    }

    anyhow::bail!("tool '{name}' not found on any MCP server")
}

fn send_update(
    updates: &tokio::sync::broadcast::Sender<acp::SessionUpdate>,
    _session_id: &acp::SessionId,
    update: acp::SessionUpdate,
) -> Result<(), agent_client_protocol::Error> {
    // 14.1: publish to the per-session fan-out; attached connections pump
    // these to clients. No receivers = no live connection right now, which
    // is fine — the turn survives and history has the whole messages.
    let _ = updates.send(update);
    Ok(())
}

/// Validate and repair JSON arguments from LLM tool calls.
fn repair_json_args(args: &str) -> String {
    if serde_json::from_str::<serde_json::Value>(args).is_ok() {
        return args.to_string();
    }
    let mut repaired = args.to_string();
    let open_brackets = repaired.matches('[').count();
    let close_brackets = repaired.matches(']').count();
    if open_brackets > close_brackets {
        repaired.push_str(&"]".repeat(open_brackets - close_brackets));
    }
    let open_braces = repaired.matches('{').count();
    let close_braces = repaired.matches('}').count();
    if open_braces > close_braces {
        repaired.push_str(&"}".repeat(open_braces - close_braces));
    }
    if serde_json::from_str::<serde_json::Value>(&repaired).is_ok() {
        return repaired;
    }
    "{}".to_string()
}

/// Look up a tool's declared JSON schema (function parameters) by name.
fn tool_schema<'a>(
    tools: &'a [ChatCompletionTools],
    name: &str,
) -> Option<&'a serde_json::Value> {
    tools.iter().find_map(|t| match t {
        ChatCompletionTools::Function(f) if f.function.name == name => {
            f.function.parameters.as_ref()
        }
        _ => None,
    })
}

/// Coerce stringified arguments into the types declared by the tool schema.
///
/// Some models (qwen/alibaba) emit numbers and booleans as JSON strings —
/// `"timeout": "30"` against a schema that says integer. MCP passes arguments
/// through untouched and the server's typed deserialization rejects them
/// ("invalid type: string \"30\", expected u64"). We hold the schema, so cast:
/// a string value whose property is declared integer/number/boolean is parsed
/// into that type when parseable. Top-level properties only — our tool
/// schemas are flat. Unparseable values are left alone so the server error
/// reaches the model verbatim.
fn coerce_args_to_schema(args: &mut serde_json::Value, schema: Option<&serde_json::Value>) {
    let Some(props) = schema
        .and_then(|s| s.get("properties"))
        .and_then(|p| p.as_object())
    else {
        return;
    };
    let Some(obj) = args.as_object_mut() else {
        return;
    };
    for (key, value) in obj.iter_mut() {
        if !value.is_string() {
            continue;
        }
        let Some(prop) = props.get(key) else { continue };
        // "type": "integer" or "type": ["integer", "null"]
        let wants = |t: &str| {
            prop.get("type").is_some_and(|ty| {
                ty.as_str() == Some(t)
                    || ty
                        .as_array()
                        .is_some_and(|arr| arr.iter().any(|v| v.as_str() == Some(t)))
            })
        };
        let s = value.as_str().unwrap().trim();
        if wants("integer") {
            if let Ok(n) = s.parse::<i64>() {
                *value = serde_json::json!(n);
            }
        } else if wants("number") {
            if let Ok(n) = s.parse::<f64>() {
                *value = serde_json::json!(n);
            }
        } else if wants("boolean") {
            match s.to_ascii_lowercase().as_str() {
                "true" => *value = serde_json::json!(true),
                "false" => *value = serde_json::json!(false),
                _ => {}
            }
        }
    }
}

/// Map tool name to ACP ToolKind for client UI.
fn tool_kind(name: &str) -> acp::ToolKind {
    match name {
        "terminal" => acp::ToolKind::Execute,
        "read" => acp::ToolKind::Read,
        "write" | "edit" => acp::ToolKind::Edit,
        "web_search" => acp::ToolKind::Search,
        "web_fetch" => acp::ToolKind::Fetch,
        _ => acp::ToolKind::Other,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repair_valid_json() {
        assert_eq!(repair_json_args(r#"{"key": "value"}"#), r#"{"key": "value"}"#);
    }

    #[test]
    fn repair_missing_brace() {
        assert_eq!(repair_json_args(r#"{"key": "value""#), r#"{"key": "value"}"#);
    }

    #[test]
    fn repair_missing_bracket() {
        assert_eq!(repair_json_args(r#"{"arr": [1, 2"#), r#"{"arr": [1, 2]}"#);
    }

    #[test]
    fn repair_garbage() {
        assert_eq!(repair_json_args("not json at all"), "{}");
    }

    #[test]
    fn repair_empty() {
        assert_eq!(repair_json_args(""), "{}");
    }

    // ---- schema type coercion (qwen sends "30" for an integer param) ----

    fn terminal_tool() -> ChatCompletionTools {
        use async_openai_thinking::types::chat::{ChatCompletionTool, FunctionObject};
        ChatCompletionTools::Function(ChatCompletionTool {
            function: FunctionObject {
                name: "terminal".to_string(),
                description: None,
                parameters: Some(serde_json::json!({
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": ["string", "null"]},
                        "timeout": {"type": ["integer", "null"], "format": "uint64"}
                    },
                    "required": ["command"]
                })),
                strict: None,
            },
        })
    }

    #[test]
    fn coerce_reindeer_timeout_string_to_int() {
        // The exact dangerous-reindeer failure: timeout "30" vs Option<u64>.
        let tools = vec![terminal_tool()];
        let mut args = serde_json::json!({"command": "echo hi", "timeout": "30"});
        coerce_args_to_schema(&mut args, tool_schema(&tools, "terminal"));
        assert!(args["timeout"].is_number(), "timeout must be a number, got {:?}", args["timeout"]);
        assert_eq!(args["timeout"], serde_json::json!(30));
        // string param stays a string
        assert_eq!(args["command"], serde_json::json!("echo hi"));
    }

    #[test]
    fn coerce_plain_integer_type() {
        let schema = serde_json::json!({"type":"object","properties":{"n":{"type":"integer"}}});
        let mut args = serde_json::json!({"n": "42"});
        coerce_args_to_schema(&mut args, Some(&schema));
        assert_eq!(args["n"], serde_json::json!(42));
    }

    #[test]
    fn coerce_number_and_boolean() {
        let schema = serde_json::json!({"type":"object","properties":{
            "f":{"type":"number"}, "flag":{"type":"boolean"}
        }});
        let mut args = serde_json::json!({"f": "2.5", "flag": "true"});
        coerce_args_to_schema(&mut args, Some(&schema));
        assert_eq!(args["f"], serde_json::json!(2.5));
        assert_eq!(args["flag"], serde_json::json!(true));
    }

    #[test]
    fn coerce_leaves_correct_types_alone() {
        let tools = vec![terminal_tool()];
        let mut args = serde_json::json!({"command": "x", "timeout": 30});
        coerce_args_to_schema(&mut args, tool_schema(&tools, "terminal"));
        assert_eq!(args["timeout"], serde_json::json!(30));
    }

    #[test]
    fn coerce_unparseable_string_left_alone() {
        // "abc" can't parse to i64 — leave it so the server error reaches the model.
        let tools = vec![terminal_tool()];
        let mut args = serde_json::json!({"command": "x", "timeout": "abc"});
        coerce_args_to_schema(&mut args, tool_schema(&tools, "terminal"));
        assert_eq!(args["timeout"], serde_json::json!("abc"));
    }

    #[test]
    fn coerce_no_schema_is_noop() {
        let mut args = serde_json::json!({"timeout": "30"});
        coerce_args_to_schema(&mut args, None);
        assert_eq!(args["timeout"], serde_json::json!("30"));
    }

    #[test]
    fn tool_schema_lookup_by_name() {
        let tools = vec![terminal_tool()];
        assert!(tool_schema(&tools, "terminal").is_some());
        assert!(tool_schema(&tools, "nope").is_none());
    }
}
