//! Compaction — summarize conversation history to reduce context window.
//!
//! Port of Python crow-cli/agent/compact.py.
//! Creates a new agent record with same session_id, incremented agent_idx.
//! Nothing is ever deleted.

use crate::config::Config;
use crow_memory_sdk::MemoryClient;
use crate::session::{self, AgentSession};

const MAX_OUTPUT_TOKENS: u32 = 30000;

const COMPACTION_PROMPT: &str = r#"Please summarize the entire conversation up to this point.
Include:
- What the user asked for
- What you attempted and the results
- What files were created/modified
- Current state of the work
- Any errors encountered
- What still needs to be done

Be thorough and detailed. This summary will replace the conversation history, so include everything a new agent would need to continue the work seamlessly."#;

/// Compact the conversation by summarizing it into a single message.
/// Returns the new session with compacted history.
pub async fn compact(
    old_session: &AgentSession,
    store: &MemoryClient,
    llm: &async_openai_thinking::Client<async_openai_thinking::config::OpenAIConfig>,
    config: &Config,
) -> anyhow::Result<AgentSession> {
    let original_session_id = &old_session.session_id;
    let original_agent_idx = old_session.agent_idx;

    tracing::info!(
        "Compacting agent {} ({} messages)...",
        old_session.agent_id,
        old_session.messages.len()
    );

    // 1. Fill missing tool responses on the last assistant message
    let mut messages = fill_missing_tool_responses(&old_session.messages);

    // 2. Guard against user+user
    if messages.last().and_then(|m| m.get("role")).and_then(|r| r.as_str()) == Some("user") {
        messages.push(serde_json::json!({
            "role": "assistant",
            "content": "Ready to compact. Calling no tools.",
        }));
    }

    // 3. Append compaction prompt
    messages.push(serde_json::json!({
        "role": "user",
        "content": COMPACTION_PROMPT,
    }));

    // 4. Send to LLM (non-streaming, tool_choice=none)
    use async_openai_thinking::types::chat::{
        ChatCompletionRequestMessage, ChatCompletionToolChoiceOption,
        CreateChatCompletionRequestArgs, ToolChoiceOptions,
    };

    let openai_msgs: Vec<ChatCompletionRequestMessage> = messages
        .iter()
        .filter_map(|m| json_to_openai_message(m))
        .collect();

    let req = CreateChatCompletionRequestArgs::default()
        .model(old_session.model_identifier.as_str())
        .messages(openai_msgs)
        .max_tokens(MAX_OUTPUT_TOKENS)
        .tool_choice(ChatCompletionToolChoiceOption::Mode(ToolChoiceOptions::None))
        .build()?;

    let response = llm.chat().create(req).await?;
    let summary = response
        .choices
        .first()
        .and_then(|c| c.message.content.as_deref())
        .unwrap_or("(compaction failed — empty summary)")
        .to_string();

    tracing::info!("Compaction summary: {} chars", summary.len());

    // 5. Create new agent record: same session_id, next agent_idx
    let new_agent_idx = original_agent_idx + 1;
    let tools_json = serde_json::to_value(&old_session.tools).unwrap_or_default();

    let mut new_session = session::make_agent_session(
        config,
        store,
        &tools_json,
        &old_session.model_identifier,
        &old_session.cwd,
        Some(original_session_id),
        Some(new_agent_idx),
    )
    .await?;

    // 6. Add summary + last messages as user message
    let last_msgs = last_messages(old_session, 20, 300);
    let new_prompt = format!("{summary}\n\nLast messages:\n\n{last_msgs}");
    new_session
        .add_message(
            store,
            serde_json::json!({"role": "user", "content": new_prompt}),
            None,
        )
        .await;

    tracing::info!(
        "Compacted: {} -> {}, {} messages -> {}",
        old_session.agent_id,
        new_session.agent_id,
        old_session.messages.len(),
        new_session.messages.len()
    );

    Ok(new_session)
}

/// Fill missing tool responses for the last assistant message with tool_calls.
///
/// Also used on resume: an abrupt death (Ctrl+C / kill) can leave tool_calls
/// without responses, which no provider accepts on the next request.
pub fn fill_missing_tool_responses(messages: &[serde_json::Value]) -> Vec<serde_json::Value> {
    let mut result = messages.to_vec();

    // Walk backwards to find last assistant with tool_calls
    for i in (0..messages.len()).rev() {
        let msg = &messages[i];
        if msg.get("role").and_then(|r| r.as_str()) != Some("assistant") {
            continue;
        }
        let Some(tool_calls) = msg.get("tool_calls").and_then(|t| t.as_array()) else {
            continue;
        };

        let call_ids: Vec<String> = tool_calls
            .iter()
            .filter_map(|tc| tc.get("id").and_then(|id| id.as_str()).map(String::from))
            .collect();

        // Scan trailing tool responses
        let mut response_ids = std::collections::HashSet::new();
        for j in (i + 1)..messages.len() {
            if messages[j].get("role").and_then(|r| r.as_str()) == Some("tool") {
                if let Some(tcid) = messages[j]
                    .get("tool_call_id")
                    .and_then(|id| id.as_str())
                {
                    response_ids.insert(tcid.to_string());
                }
            }
        }

        let mut missing: Vec<&String> = call_ids
            .iter()
            .filter(|id| !response_ids.contains(*id))
            .collect();
        missing.sort();

        // Insert right after the trailing tool responses of THIS assistant
        // message (before any later user/assistant message), so the repaired
        // history stays a valid OpenAI sequence even when the dangling tail
        // isn't the last thing stored.
        let mut insert_at = i + 1;
        while insert_at < result.len()
            && result[insert_at].get("role").and_then(|r| r.as_str()) == Some("tool")
        {
            insert_at += 1;
        }
        for tool_call_id in missing {
            result.insert(
                insert_at,
                serde_json::json!({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": "Tool call was interrupted due to context compaction. Please retry if still needed.",
                }),
            );
            insert_at += 1;
        }
        break;
    }

    result
}

/// Format last N messages as a readable string for the compacted context.
fn last_messages(session: &AgentSession, n_messages: usize, max_chars: usize) -> String {
    let start = session.messages.len().saturating_sub(n_messages);
    let mut parts = Vec::new();

    for msg in &session.messages[start..] {
        let role = msg.get("role").and_then(|r| r.as_str()).unwrap_or("");
        match role {
            "user" => {
                parts.push("USER:".to_string());
                parts.push(unroll_content(msg.get("content"), max_chars * 10));
            }
            "assistant" => {
                parts.push("ASSISTANT:".to_string());
                parts.push(unroll_content(msg.get("content"), max_chars));
                if let Some(tcs) = msg.get("tool_calls").and_then(|t| t.as_array()) {
                    for tc in tcs {
                        if let Some(f) = tc.get("function") {
                            let name = f.get("name").and_then(|n| n.as_str()).unwrap_or("");
                            let args = f.get("arguments").and_then(|a| a.as_str()).unwrap_or("");
                            parts.push(format!("TOOL — {name}:"));
                            let truncated: String = args.chars().take(max_chars).collect();
                            parts.push(truncated);
                        }
                    }
                }
            }
            "tool" => {
                parts.push("TOOL RESULT:".to_string());
                parts.push(unroll_content(msg.get("content"), max_chars));
            }
            _ => {}
        }
    }
    parts.join("\n")
}

fn unroll_content(content: Option<&serde_json::Value>, max_chars: usize) -> String {
    let text = match content {
        Some(serde_json::Value::String(s)) => s.clone(),
        Some(serde_json::Value::Array(arr)) => arr
            .iter()
            .filter_map(|b| {
                if b.get("type").and_then(|t| t.as_str()) == Some("text") {
                    b.get("text").and_then(|t| t.as_str()).map(String::from)
                } else {
                    None
                }
            })
            .collect::<Vec<_>>()
            .join(" "),
        _ => String::new(),
    };
    text.chars().take(max_chars).collect()
}

/// One array-content block → multimodal part for a user message.
/// Text and image_url blocks map 1:1; anything else is dropped.
fn user_content_part(
    block: &serde_json::Value,
) -> Option<async_openai_thinking::types::chat::ChatCompletionRequestUserMessageContentPart> {
    use async_openai_thinking::types::chat::*;
    match block.get("type").and_then(|t| t.as_str())? {
        "text" => Some(
            ChatCompletionRequestMessageContentPartText {
                text: block.get("text")?.as_str()?.to_string(),
            }
            .into(),
        ),
        "image_url" => Some(
            ChatCompletionRequestMessageContentPartImage {
                image_url: ImageUrl {
                    url: block.get("image_url")?.get("url")?.as_str()?.to_string(),
                    detail: None,
                },
            }
            .into(),
        ),
        _ => None,
    }
}

/// One array-content block → part for a tool message. Text and image_url
/// blocks map 1:1 (crow fork async-openai-thinking: tool parts accept
/// images — vision tool results); anything else is dropped.
fn tool_content_part(
    block: &serde_json::Value,
) -> Option<async_openai_thinking::types::chat::ChatCompletionRequestToolMessageContentPart> {
    use async_openai_thinking::types::chat::*;
    match block.get("type").and_then(|t| t.as_str())? {
        "text" => Some(
            ChatCompletionRequestMessageContentPartText {
                text: block.get("text")?.as_str()?.to_string(),
            }
            .into(),
        ),
        "image_url" => Some(
            ChatCompletionRequestMessageContentPartImage {
                image_url: ImageUrl {
                    url: block.get("image_url")?.get("url")?.as_str()?.to_string(),
                    detail: None,
                },
            }
            .into(),
        ),
        _ => None,
    }
}

/// Convert a JSON message dict to an async-openai ChatCompletionRequestMessage.
///
/// Array content (multimodal tool results, image user messages) survives:
/// user and tool messages become multimodal requests (text + image parts);
/// assistant messages unroll to text parts (assistant content never carries
/// images — only text + tool_calls).
pub fn json_to_openai_message(
    msg: &serde_json::Value,
) -> Option<async_openai_thinking::types::chat::ChatCompletionRequestMessage> {
    use async_openai_thinking::types::chat::*;

    let role = msg.get("role")?.as_str()?;
    let content = msg.get("content");

    match role {
        "system" | "developer" => {
            let mut builder = ChatCompletionRequestSystemMessageArgs::default();
            builder.content(unroll_content(content, usize::MAX));
            Some(builder.build().ok()?.into())
        }
        "user" => {
            let mut builder = ChatCompletionRequestUserMessageArgs::default();
            match content {
                Some(serde_json::Value::Array(arr)) => {
                    let parts: Vec<ChatCompletionRequestUserMessageContentPart> =
                        arr.iter().filter_map(user_content_part).collect();
                    if parts.is_empty() {
                        builder.content("");
                    } else {
                        builder.content(parts);
                    }
                }
                _ => {
                    builder.content(content.and_then(|c| c.as_str()).unwrap_or(""));
                }
            }
            Some(builder.build().ok()?.into())
        }
        "assistant" => {
            let mut builder = ChatCompletionRequestAssistantMessageArgs::default();
            match content {
                Some(serde_json::Value::String(s)) => {
                    builder.content(s.as_str());
                }
                Some(serde_json::Value::Array(_)) => {
                    let text = unroll_content(content, usize::MAX);
                    if !text.is_empty() {
                        builder.content(text);
                    }
                }
                _ => {}
            }
            if let Some(tcs) = msg.get("tool_calls").and_then(|t| t.as_array()) {
                let tool_calls: Vec<ChatCompletionMessageToolCalls> = tcs
                    .iter()
                    .filter_map(|tc| {
                        let id = tc.get("id")?.as_str()?;
                        let f = tc.get("function")?;
                        let name = f.get("name")?.as_str()?;
                        let arguments = f.get("arguments")?.as_str()?;
                        Some(ChatCompletionMessageToolCalls::Function(
                            ChatCompletionMessageToolCall {
                                id: id.to_string(),
                                function: FunctionCall {
                                    name: name.to_string(),
                                    arguments: arguments.to_string(),
                                },
                            },
                        ))
                    })
                    .collect();
                if !tool_calls.is_empty() {
                    builder.tool_calls(tool_calls);
                }
            }
            Some(builder.build().ok()?.into())
        }
        "tool" => {
            let tool_call_id = msg.get("tool_call_id")?.as_str()?;
            let mut builder = ChatCompletionRequestToolMessageArgs::default();
            builder.tool_call_id(tool_call_id);
            match content {
                Some(serde_json::Value::Array(arr)) => {
                    let parts: Vec<ChatCompletionRequestToolMessageContentPart> =
                        arr.iter().filter_map(tool_content_part).collect();
                    if parts.is_empty() {
                        builder.content("");
                    } else {
                        builder.content(parts);
                    }
                }
                _ => {
                    builder.content(unroll_content(content, usize::MAX));
                }
            }
            Some(builder.build().ok()?.into())
        }
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fill_missing_no_tool_calls() {
        let msgs = vec![
            serde_json::json!({"role": "user", "content": "hi"}),
            serde_json::json!({"role": "assistant", "content": "hello"}),
        ];
        let result = fill_missing_tool_responses(&msgs);
        assert_eq!(result.len(), 2);
    }

    #[test]
    fn fill_missing_all_responded() {
        let msgs = vec![
            serde_json::json!({"role": "assistant", "content": "", "tool_calls": [
                {"id": "tc1", "function": {"name": "terminal", "arguments": "{}"}}
            ]}),
            serde_json::json!({"role": "tool", "tool_call_id": "tc1", "content": "ok"}),
        ];
        let result = fill_missing_tool_responses(&msgs);
        assert_eq!(result.len(), 2);
    }

    #[test]
    fn fill_missing_adds_response() {
        let msgs = vec![
            serde_json::json!({"role": "assistant", "content": "", "tool_calls": [
                {"id": "tc1", "function": {"name": "terminal", "arguments": "{}"}},
                {"id": "tc2", "function": {"name": "read", "arguments": "{}"}}
            ]}),
            serde_json::json!({"role": "tool", "tool_call_id": "tc1", "content": "ok"}),
        ];
        let result = fill_missing_tool_responses(&msgs);
        assert_eq!(result.len(), 3);
        assert_eq!(result[2]["tool_call_id"], "tc2");
        assert!(result[2]["content"].as_str().unwrap().contains("compaction"));
    }

    #[test]
    fn json_to_openai_system() {
        let msg = serde_json::json!({"role": "system", "content": "you are helpful"});
        let result = json_to_openai_message(&msg);
        assert!(result.is_some());
    }

    #[test]
    fn json_to_openai_user() {
        let msg = serde_json::json!({"role": "user", "content": "hello"});
        let result = json_to_openai_message(&msg);
        assert!(result.is_some());
    }

    #[test]
    fn json_to_openai_tool() {
        let msg = serde_json::json!({"role": "tool", "tool_call_id": "tc1", "content": "result"});
        let result = json_to_openai_message(&msg);
        assert!(result.is_some());
    }

    #[test]
    fn json_to_openai_assistant_with_tool_calls() {
        let msg = serde_json::json!({
            "role": "assistant",
            "content": "let me check",
            "tool_calls": [{"id": "tc1", "function": {"name": "terminal", "arguments": "{}"}}]
        });
        let result = json_to_openai_message(&msg);
        assert!(result.is_some());
    }

    #[test]
    fn json_to_openai_unknown_role() {
        let msg = serde_json::json!({"role": "alien", "content": "????"});
        assert!(json_to_openai_message(&msg).is_none());
    }

    /// Regression: array content with an image must survive conversion —
    /// pre-fix, any non-string content was silently dropped (message became
    /// an empty string), eating images out of the API request.
    #[test]
    fn json_to_openai_user_multimodal() {
        use async_openai_thinking::types::chat::*;
        let msg = serde_json::json!({
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
            ],
        });
        let result = json_to_openai_message(&msg).expect("multimodal user message converts");
        let ChatCompletionRequestMessage::User(user) = result else {
            panic!("expected user message");
        };
        let ChatCompletionRequestUserMessageContent::Array(parts) = user.content else {
            panic!("expected array content, got {:?}", user.content);
        };
        assert_eq!(parts.len(), 2);
        match &parts[0] {
            ChatCompletionRequestUserMessageContentPart::Text(t) => {
                assert_eq!(t.text, "what is this?")
            }
            p => panic!("expected text part, got {p:?}"),
        }
        match &parts[1] {
            ChatCompletionRequestUserMessageContentPart::ImageUrl(i) => {
                assert_eq!(i.image_url.url, "data:image/png;base64,QUJD")
            }
            p => panic!("expected image part, got {p:?}"),
        }
    }

    /// Tool results with array content (the react.rs image path) keep BOTH
    /// text and image parts — the image must reach the LLM, not just the
    /// `[image: ...]` marker.
    #[test]
    fn json_to_openai_tool_array_content() {
        use async_openai_thinking::types::chat::*;
        let msg = serde_json::json!({
            "role": "tool",
            "tool_call_id": "tc1",
            "content": [
                {"type": "text", "text": "[image: image/png]"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
            ],
        });
        let result = json_to_openai_message(&msg).expect("tool message converts");
        let ChatCompletionRequestMessage::Tool(tool) = result else {
            panic!("expected tool message");
        };
        let ChatCompletionRequestToolMessageContent::Array(parts) = tool.content else {
            panic!("expected array content, got {:?}", tool.content);
        };
        assert_eq!(parts.len(), 2);
        match &parts[0] {
            ChatCompletionRequestToolMessageContentPart::Text(t) => {
                assert_eq!(t.text, "[image: image/png]")
            }
            p => panic!("expected text part, got {p:?}"),
        }
        match &parts[1] {
            ChatCompletionRequestToolMessageContentPart::ImageUrl(i) => {
                assert_eq!(i.image_url.url, "data:image/png;base64,QUJD")
            }
            p => panic!("expected image part, got {p:?}"),
        }
    }

    /// Regression for the exact vision-tool failure: read_image_file returns
    /// ONLY an image block (no text parts). Pre-fix, unroll_content kept only
    /// text parts → the tool message arrived at the LLM as empty content and
    /// the model saw nothing. The image part must survive on its own.
    #[test]
    fn json_to_openai_tool_image_only() {
        use async_openai_thinking::types::chat::*;
        let msg = serde_json::json!({
            "role": "tool",
            "tool_call_id": "tc1",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}},
            ],
        });
        let result = json_to_openai_message(&msg).expect("tool message converts");
        let ChatCompletionRequestMessage::Tool(tool) = result else {
            panic!("expected tool message");
        };
        let ChatCompletionRequestToolMessageContent::Array(parts) = tool.content else {
            panic!("expected array content, got {:?}", tool.content);
        };
        assert_eq!(parts.len(), 1);
        match &parts[0] {
            ChatCompletionRequestToolMessageContentPart::ImageUrl(i) => {
                assert_eq!(i.image_url.url, "data:image/jpeg;base64,QUJD")
            }
            p => panic!("expected image part, got {p:?}"),
        }
    }
}
