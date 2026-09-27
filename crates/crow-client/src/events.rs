//! Parsing of deepseek-harness SDK-runtime JSON-RPC notifications into UI events.

use serde_json::Value;

#[derive(Debug, Clone, PartialEq)]
pub enum UiEvent {
    SessionStatus {
        session: String,
        running: bool,
    },
    TurnStart {
        session: String,
        turn: u64,
    },
    TurnEnd {
        session: String,
        kind: String,
    },
    TextDelta {
        session: String,
        text: String,
    },
    ReasoningDelta {
        session: String,
        text: String,
    },
    /// A tool-call block started, but its streamed arguments are not yet a
    /// complete request. This is a presentation transition only: the later
    /// `ToolCall` remains the authoritative request event.
    ToolCallPreparing {
        session: String,
    },
    AssistantFinal {
        session: String,
        text: String,
        model: Option<String>,
    },
    ToolCall {
        session: String,
        call_id: String,
        name: String,
        arguments: String,
        diff: Option<ToolDiff>,
    },
    ToolResult {
        session: String,
        call_id: String,
        is_error: bool,
        text: String,
        error: Option<String>,
    },
    Usage {
        session: String,
        input: u64,
        output: u64,
        cached: u64,
        reasoning: u64,
    },
    /// Standard ACP `usage_update`: the context-window meter. `used`/`size`
    /// are absolute readings, not per-turn deltas, so this *replaces* the
    /// previous one rather than accumulating into `UsageTotals`.
    ContextUsage {
        session: String,
        used: u64,
        size: u64,
    },
    UserInjected {
        session: String,
        source: String,
        preview: String,
    },
    SubagentStarted {
        parent: String,
        child: String,
    },
    SubagentFinished {
        child: String,
        failed: bool,
    },
    /// ACP `user_message_chunk` (session/load replay needs user lines).
    UserMessage {
        session: String,
        text: String,
    },
    /// ACP `session_info_update` title.
    SessionTitle {
        session: String,
        title: String,
    },
    /// Structured adapter/runtime notice negotiated through ACP metadata.
    SessionNotice {
        session: String,
        severity: String,
        title: String,
        details: Option<String>,
    },
    /// Current model from the standard ACP session config snapshot.
    SessionModel {
        session: String,
        model: String,
    },
    /// ACP `plan` / `plan_update` snapshot (todo entries, not `plan/mode`).
    Plan {
        session: String,
        summary: String,
    },
    /// `plan/mode` — plan-mode collaboration state (last one wins).
    PlanMode {
        session: String,
        active: bool,
    },
    /// `sandbox/mode` — file policy: read-only | workspace-write | danger-full-access.
    SandboxMode {
        session: String,
        mode: String,
    },
    /// `approval/policy` — ask | never.
    ApprovalPolicy {
        session: String,
        policy: String,
    },
    /// `permission/preset` — bundled permission preset name.
    PermissionPreset {
        session: String,
        preset: String,
    },
    /// `agent-preset/selected` — agent composition preset (standard/code/…).
    AgentPreset {
        session: String,
        preset: String,
    },
    /// ACP `configOptions.effort.currentValue` — Host-owned reasoning default.
    ReasoningEffort {
        session: String,
        effort: String,
    },
    /// `approval/asked` — one pending approval request.
    ApprovalAsked {
        session: String,
        tool: String,
        reason: Option<String>,
    },
    /// `approval/decided` — its outcome.
    ApprovalDecided {
        session: String,
        outcome: String,
    },
    /// TUI extension theme update (not a session log event).
    Palette {
        pack: crate::theme::PalettePack,
        activate: bool,
    },
}

/// Parse a JSON-RPC notification into zero or more UI events.
/// Unknown methods and malformed payloads yield an empty vec; never panics.
pub fn parse_notification(method: &str, params: &Value) -> Vec<UiEvent> {
    match method {
        "session.status" => {
            let session = str_field(params, "sessionId");
            match params.get("status").and_then(Value::as_str) {
                Some(status) => vec![UiEvent::SessionStatus {
                    session,
                    running: status == "running",
                }],
                None => Vec::new(),
            }
        }
        "subagent.started" => vec![UiEvent::SubagentStarted {
            parent: str_field(params, "parentSessionId"),
            child: str_field(params, "childSessionId"),
        }],
        "subagent.finished" => vec![UiEvent::SubagentFinished {
            child: str_field(params, "childSessionId"),
            // Mirror the ACP path: the notification carries the child's
            // stop status — hardcoding success hid failed tasks.
            failed: params
                .get("status")
                .or_else(|| params.get("stopReason"))
                .and_then(Value::as_str)
                == Some("failed"),
        }],
        "session.event" => parse_session_event(params),
        "session/update" => parse_session_update(params),
        crate::ext::THEME_UPDATE => match crate::theme::parse_palette_notification(params) {
            Ok(Some(n)) => vec![UiEvent::Palette {
                pack: n.pack,
                activate: n.activate,
            }],
            _ => Vec::new(),
        },
        _ => Vec::new(),
    }
}

fn parse_session_event(params: &Value) -> Vec<UiEvent> {
    let session = str_field(params, "sessionId");
    let event = match params.get("event") {
        Some(e) => e,
        None => return Vec::new(),
    };
    let event_type = match event.get("type").and_then(Value::as_str) {
        Some(t) => t,
        None => return Vec::new(),
    };
    let data = event.get("data").unwrap_or(&Value::Null);

    match event_type {
        "turn/start" => {
            let turn = data.get("turn").and_then(Value::as_u64).unwrap_or(0);
            vec![UiEvent::TurnStart { session, turn }]
        }
        "turn/end" => {
            let kind = data
                .get("reason")
                .and_then(|r| r.get("kind"))
                .and_then(Value::as_str)
                .unwrap_or("unknown")
                .to_string();
            vec![UiEvent::TurnEnd { session, kind }]
        }
        "assistant/chunk" => parse_assistant_chunk(session, data),
        "plan/mode" => match data.get("active").and_then(Value::as_bool) {
            Some(active) => vec![UiEvent::PlanMode { session, active }],
            None => Vec::new(),
        },
        "sandbox/mode" => match data.get("mode").and_then(Value::as_str) {
            Some(mode) => vec![UiEvent::SandboxMode {
                session,
                mode: mode.to_string(),
            }],
            None => Vec::new(),
        },
        "approval/policy" => match data.get("policy").and_then(Value::as_str) {
            Some(policy) => vec![UiEvent::ApprovalPolicy {
                session,
                policy: policy.to_string(),
            }],
            None => Vec::new(),
        },
        "permission/preset" => match data.get("preset").and_then(Value::as_str) {
            Some(preset) => vec![UiEvent::PermissionPreset {
                session,
                preset: preset.to_string(),
            }],
            None => Vec::new(),
        },
        "agent-preset/selected" => match data.get("agentPreset").and_then(Value::as_str) {
            Some(preset) => vec![UiEvent::AgentPreset {
                session,
                preset: preset.to_string(),
            }],
            None => Vec::new(),
        },
        "approval/asked" => {
            let tool = data
                .get("toolName")
                .and_then(Value::as_str)
                .unwrap_or("tool")
                .to_string();
            let reason = data
                .get("reason")
                .and_then(Value::as_str)
                .map(|s| s.to_string());
            vec![UiEvent::ApprovalAsked {
                session,
                tool,
                reason,
            }]
        }
        "approval/decided" => {
            let outcome = match data.get("outcome") {
                Some(Value::String(s)) => s.clone(),
                Some(Value::Object(o)) => o
                    .get("kind")
                    .and_then(Value::as_str)
                    .unwrap_or("decided")
                    .to_string(),
                _ => "decided".to_string(),
            };
            vec![UiEvent::ApprovalDecided { session, outcome }]
        }
        "assistant/message" => {
            let msg = data.get("message").unwrap_or(data);
            let text = concat_text_blocks(msg.get("content").unwrap_or(&Value::Null));
            let model = msg
                .get("source")
                .and_then(|s| s.get("model"))
                .and_then(Value::as_str)
                .map(str::to_string);
            vec![UiEvent::AssistantFinal {
                session,
                text,
                model,
            }]
        }
        "tool/call" => vec![UiEvent::ToolCall {
            session,
            call_id: str_field(data, "callId"),
            name: str_field(data, "name"),
            arguments: str_field(data, "arguments"),
            diff: None,
        }],
        "tool/result" => parse_tool_result(session, data),
        "user/message" => parse_user_message(session, data),
        _ => Vec::new(),
    }
}

fn parse_session_update(params: &Value) -> Vec<UiEvent> {
    let root_session = str_field(params, "sessionId");
    let update = params.get("update").unwrap_or(params);
    let session = root_session;
    let kind = update
        .get("sessionUpdate")
        .and_then(Value::as_str)
        .unwrap_or("");
    match kind {
        "agent_message_chunk" => {
            let text = acp_text_content(update.get("content"));
            if text.is_empty() {
                Vec::new()
            } else {
                vec![UiEvent::TextDelta { session, text }]
            }
        }
        "agent_thought_chunk" => {
            let text = acp_text_content(update.get("content"));
            if text.is_empty() {
                Vec::new()
            } else {
                vec![UiEvent::ReasoningDelta { session, text }]
            }
        }
        "user_message_chunk" | "user_message" => {
            let text = acp_text_content(update.get("content"));
            if text.is_empty() {
                Vec::new()
            } else {
                vec![UiEvent::UserMessage { session, text }]
            }
        }
        // v2 sends a whole message where v1 sends a run of chunks. `content` is
        // an array of blocks rather than one block, which `acp_text_content`
        // already reads. Landing on `AssistantFinal` rather than a delta is what
        // makes both orders work: with no open cell it creates the finished one,
        // and after chunks it supersedes the buffer instead of appending a
        // second copy of the same sentence to it.
        "agent_message" => {
            let text = acp_text_content(update.get("content"));
            if text.is_empty() {
                Vec::new()
            } else {
                vec![UiEvent::AssistantFinal {
                    session,
                    text,
                    model: None,
                }]
            }
        }
        "agent_thought" => {
            let text = acp_text_content(update.get("content"));
            if text.is_empty() {
                Vec::new()
            } else {
                vec![UiEvent::ReasoningDelta { session, text }]
            }
        }
        // The v2 stack owns this one: `state_update` is how a turn ends now
        // that `PromptResponse` is an empty acknowledgement, and `acp::v2`
        // settles its turn board off the idle before this parser ever sees it.
        // Emitting `SessionStatus`/`TurnEnd` here too would report every turn
        // twice — and agent2 re-emits idle every thirty seconds as a heartbeat.
        "state_update" => Vec::new(),
        // Terminal bytes have two audiences and only one of them is the
        // transcript. `terminal_output_chunk` is base64 PTY output for a human
        // watching a terminal pane; the model's copy of the same run arrives as
        // `tool_call_update.raw_output`, which the arm above already paints.
        // crow has no terminal pane, so painting the PTY stream into the
        // transcript would be showing one thing twice.
        "terminal_update" | "terminal_output_chunk" | "tool_call_content_chunk" => Vec::new(),
        "session_info_update" => {
            if let Some(failure) = update
                .get("_meta")
                .and_then(|meta| meta.get("jetbrains"))
                .and_then(|jetbrains| jetbrains.get("air"))
                .and_then(|air| air.get("sessionFailure"))
            {
                let title = failure
                    .get("title")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .trim();
                if !title.is_empty() {
                    return vec![UiEvent::SessionNotice {
                        session,
                        severity: failure
                            .get("severity")
                            .and_then(Value::as_str)
                            .unwrap_or("error")
                            .to_string(),
                        title: title.to_string(),
                        details: failure
                            .get("details")
                            .and_then(Value::as_str)
                            .map(str::trim)
                            .filter(|details| !details.is_empty())
                            .map(str::to_string),
                    }];
                }
            }
            let title = update
                .get("title")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim();
            if title.is_empty() {
                Vec::new()
            } else {
                vec![UiEvent::SessionTitle {
                    session,
                    title: title.to_string(),
                }]
            }
        }
        "plan" | "plan_update" => {
            let summary = plan_summary(update);
            if summary.is_empty() && update.get("entries").and_then(Value::as_array).is_none() {
                Vec::new()
            } else {
                vec![UiEvent::Plan { session, summary }]
            }
        }
        "plan_removed" => vec![UiEvent::Plan {
            session,
            summary: String::new(),
        }],
        "tool_call" => vec![acp_tool_call(session, update)],
        "tool_call_update" => {
            let status = first_str(update, &["status"]);
            // A v1 agent patches the artifact (its diff block) in on a later
            // update; the card must not wait for a title to ride it.
            let diff = acp_tool_diff(update);
            let named = update.get("title").is_some()
                || update.get("kind").is_some()
                || update.get("rawInput").is_some()
                || update.get("raw_input").is_some();
            if status == "completed" || status == "failed" {
                // v2 has no create: `tool_call_update` IS the upsert, and
                // crow-cli puts a drained subtool row -- an edit's diff among
                // them -- on the wire in ONE of them, first sight of the id
                // and its completion together. Reading only the result half
                // left such a cell to be born in the transcript's fallback:
                // nameless, titled with a call id, and the diff block dropped
                // on the floor. So the card half rides along whenever the
                // update carries an identity -- first, because the result
                // half is what closes the cell.
                let mut out: Vec<UiEvent> = Vec::new();
                if named || diff.is_some() {
                    out.push(acp_tool_call(session.clone(), update));
                }
                out.extend(acp_tool_result(session, update));
                out
            } else if ((status == "pending" || status == "in_progress") && named) || diff.is_some()
            {
                vec![acp_tool_call(session, update)]
            } else {
                Vec::new()
            }
        }
        "current_mode_update" => {
            let mode = first_str(update, &["currentModeId", "current_mode_id"]);
            if mode.is_empty() {
                Vec::new()
            } else {
                vec![
                    UiEvent::PermissionPreset {
                        session: session.clone(),
                        preset: mode.clone(),
                    },
                    UiEvent::SandboxMode { session, mode },
                ]
            }
        }
        "config_option_update" => {
            let options = update
                .get("configOptions")
                .or_else(|| update.get("config_options"));
            options
                .map(|options| config_option_events(session, options))
                .unwrap_or_default()
        }
        // Standard ACP `usage_update` reports context-window pressure as
        // `used`/`size`. This used to be dropped on the assumption that turn
        // totals always arrive on `PromptResponse.usage` — but an agent that
        // never fills that field (crow-cli sends `usage_update` and nothing
        // else) then reports no tokens at all, and the meter stays empty.
        "usage_update" => match (u64_field(update, "used"), u64_field(update, "size")) {
            (Some(used), Some(size)) => vec![UiEvent::ContextUsage {
                session,
                used,
                size,
            }],
            _ => Vec::new(),
        },
        _ => Vec::new(),
    }
}

fn acp_text_content(content: Option<&Value>) -> String {
    let Some(content) = content else {
        return String::new();
    };
    if let Some(text) = content.get("text").and_then(Value::as_str) {
        return text.to_string();
    }
    concat_text_blocks(content)
}

/// A diff content block off a tool call: what a write/edit changed.
///
/// ACP v2 sends `DiffToolCallContent` -- structured `changes` (the path and
/// the add/modify/delete operation) plus a renderable `patch` -- and v1 sent
/// whole `oldText`/`newText`. Either is enough to draw the change; the patch
/// is preferred because it is what the agent actually computed.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct ToolDiff {
    pub path: String,
    /// v2 `patch.text`, a unified git patch.
    pub patch: Option<String>,
    /// v1 whole-file texts, when the agent sent those instead.
    pub old_text: Option<String>,
    pub new_text: Option<String>,
}

/// The first diff block in a tool call's `content` array, if any.
fn acp_tool_diff(update: &Value) -> Option<ToolDiff> {
    for block in update.get("content").and_then(Value::as_array)? {
        if block.get("type").and_then(Value::as_str) != Some("diff") {
            continue;
        }
        let path = block
            .get("changes")
            .and_then(Value::as_array)
            .and_then(|c| c.iter().find_map(|ch| ch.get("path").and_then(Value::as_str)))
            .or_else(|| block.get("path").and_then(Value::as_str))
            .unwrap_or_default()
            .to_string();
        let patch = block
            .get("patch")
            .and_then(|p| p.get("text"))
            .and_then(Value::as_str)
            .map(str::to_string);
        let old_text = block.get("oldText").and_then(Value::as_str).map(str::to_string);
        let new_text = block.get("newText").and_then(Value::as_str).map(str::to_string);
        if patch.is_some() || old_text.is_some() || new_text.is_some() {
            return Some(ToolDiff {
                path,
                patch,
                old_text,
                new_text,
            });
        }
    }
    None
}

fn acp_tool_call(session: String, update: &Value) -> UiEvent {
    let diff = acp_tool_diff(update);
    // A diff card titles itself -- `📄 path (+N, -M)` -- and the wire title of
    // a call carrying one is that same path spelled out again ("edit:
    // /abs/path"), so the header wants the artifact's kind instead: "edit".
    let name = if diff.is_some() {
        first_str(update, &["kind", "toolName", "title"])
    } else {
        first_str(update, &["title", "kind", "toolName"])
    };
    UiEvent::ToolCall {
        session,
        call_id: first_str(update, &["toolCallId", "tool_call_id"]),
        name,
        diff,
        arguments: update
            .get("rawInput")
            .or_else(|| update.get("raw_input"))
            .filter(|raw| !raw.is_null())
            .map(Value::to_string)
            // An agent that fills no `rawInput` still says what it is about to
            // run: ACP lets the command ride the call's `content`, and crow-cli
            // fences the kernel cell there. Reading only `rawInput` left such a
            // cell with a name and nothing else — no command, no output.
            .or_else(|| update.get("content").map(tool_content_text))
            .filter(|text| !text.is_empty())
            .unwrap_or_default(),
    }
}

fn acp_tool_result(session: String, update: &Value) -> Option<UiEvent> {
    let status = first_str(update, &["status"]);
    if status != "completed" && status != "failed" {
        return None;
    }
    Some(UiEvent::ToolResult {
        session,
        call_id: first_str(update, &["toolCallId", "tool_call_id"]),
        is_error: status == "failed",
        text: acp_tool_output_text(update),
        error: None,
    })
}

fn acp_tool_output_text(update: &Value) -> String {
    if let Some(data) = update
        .get("_meta")
        .and_then(|m| m.get("terminal_output"))
        .and_then(|t| t.get("data"))
        .and_then(Value::as_str)
    {
        if !data.is_empty() {
            return data.to_string();
        }
    }
    if let Some(raw) = update.get("rawOutput").or_else(|| update.get("raw_output")) {
        if let Some(s) = raw.as_str() {
            return s.to_string();
        }
        if let Some(s) = raw.get("output").and_then(Value::as_str) {
            return s.to_string();
        }
        return raw.to_string();
    }
    if let Some(content) = update.get("content") {
        return tool_content_text(content);
    }
    String::new()
}

/// Text of an ACP tool call's `content` array.
///
/// Each entry is a tagged union — `{"type":"content","content":{…}}` wraps an
/// ordinary content block, alongside the `diff` and `terminal` variants — so
/// the text sits one level deeper than the blocks `concat_text_blocks` reads
/// out of a message chunk. Entries that skip the wrapper are read anyway.
fn tool_content_text(content: &Value) -> String {
    let Some(blocks) = content.as_array() else {
        return String::new();
    };
    let mut out: Vec<String> = Vec::new();
    for block in blocks {
        let inner = match block.get("type").and_then(Value::as_str) {
            Some("content") => block.get("content"),
            _ => Some(block),
        };
        let Some(inner) = inner else { continue };
        if inner.get("type").and_then(Value::as_str) != Some("text") {
            continue;
        }
        if let Some(text) = inner.get("text").and_then(Value::as_str) {
            if !text.is_empty() {
                out.push(text.to_owned());
            }
        }
    }
    out.join("\n")
}

fn plan_summary(update: &Value) -> String {
    let entries = update
        .get("entries")
        .or_else(|| update.get("plan").and_then(|p| p.get("entries")))
        .and_then(Value::as_array);
    if let Some(entries) = entries {
        let parts: Vec<String> = entries
            .iter()
            .filter_map(|entry| {
                let content = entry.get("content").and_then(Value::as_str)?;
                let status = entry.get("status").and_then(Value::as_str).unwrap_or("");
                if status.is_empty() {
                    Some(content.to_string())
                } else {
                    Some(format!("{content} [{status}]"))
                }
            })
            .collect();
        return parts.join(" · ");
    }
    update
        .get("plan")
        .and_then(|p| p.get("content"))
        .and_then(Value::as_str)
        .or_else(|| update.get("content").and_then(Value::as_str))
        .unwrap_or("")
        .to_string()
}

fn first_str(v: &Value, keys: &[&str]) -> String {
    for key in keys {
        let s = str_field(v, key);
        if !s.is_empty() {
            return s;
        }
    }
    String::new()
}

/// Flatten ACP select options, including `{ group, options }` rows.
pub fn flatten_select_options(options: &Value) -> Vec<(String, String, String)> {
    let mut out = Vec::new();
    let Some(arr) = options.as_array() else {
        return out;
    };
    for item in arr {
        if let Some(nested) = item.get("options") {
            out.extend(flatten_select_options(nested));
            continue;
        }
        let Some(value) = item.get("value").and_then(Value::as_str) else {
            continue;
        };
        let name = item
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or(value)
            .to_string();
        let description = item
            .get("description")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        out.push((value.to_string(), name, description));
    }
    out
}

/// A config option's identifier.
///
/// v1 calls it `id`; v2 renamed it `configId` and the old key is gone, not
/// aliased. Both spellings reach this parser, because a v2 `session/new`
/// response and a v2 `config_option_update` are forwarded raw.
pub fn config_id_of(option: &Value) -> Option<&str> {
    option
        .get("configId")
        .or_else(|| option.get("config_id"))
        .or_else(|| option.get("id"))
        .and_then(Value::as_str)
}

/// The extra composition select, if the agent advertised one.
/// Prefers `agent` / `preset` / `agent-preset`; else the first uncategorized
/// select that is not mode/model/effort.
pub fn composition_option<'a>(options: &'a Value) -> Option<&'a Value> {
    let arr = options.as_array()?;
    let named = arr.iter().find(|option| {
        matches!(
            config_id_of(option),
            Some("agent" | "preset" | "agent-preset")
        )
    });
    if named.is_some() {
        return named;
    }
    arr.iter().find(|option| {
        option.get("type").and_then(Value::as_str) == Some("select")
            && option.get("category").and_then(Value::as_str).is_none()
            && !matches!(
                config_id_of(option),
                Some("mode" | "model" | "effort" | "collaboration_mode")
            )
    })
}

fn composition_current_value(options: Option<&Value>) -> Option<String> {
    let options = options?;
    let option = composition_option(options)?;
    option
        .get("currentValue")
        .or_else(|| option.get("current_value"))
        .and_then(Value::as_str)
        .map(str::to_string)
}

fn collaboration_mode_active(options: Option<&Value>) -> Option<bool> {
    let option = options?
        .as_array()?
        .iter()
        .find(|option| config_id_of(option) == Some("collaboration_mode"))?;
    option
        .get("currentValue")
        .or_else(|| option.get("current_value"))
        .and_then(Value::as_str)
        .map(|value| value == "plan")
}

/// Resolve the standard semantic reasoning-effort option while retaining the
/// legacy literal `effort` id used by older ACP agents.
pub fn reasoning_effort_option(options: &Value) -> Option<&Value> {
    let entries = options.as_array()?;
    entries
        .iter()
        .find(|option| {
            option.get("category").and_then(Value::as_str) == Some("thought_level")
        })
        .or_else(|| {
            entries
                .iter()
                .find(|option| config_id_of(option) == Some("effort"))
        })
}

/// Fold a complete ACP `configOptions` snapshot into the client-facing facts
/// that drive existing composer chrome. Used for both setup responses and
/// later `config_option_update` notifications.
pub fn config_option_events(session: String, options: &Value) -> Vec<UiEvent> {
    let mut events = Vec::new();
    if let Some(model) = options.as_array().and_then(|entries| {
        entries
            .iter()
            .find(|option| config_id_of(option) == Some("model"))
            .and_then(|option| {
                option
                    .get("currentValue")
                    .or_else(|| option.get("current_value"))
                    .and_then(Value::as_str)
            })
    }) {
        events.push(UiEvent::SessionModel {
            session: session.clone(),
            model: model.to_string(),
        });
    }
    if let Some(active) = collaboration_mode_active(Some(options)) {
        events.push(UiEvent::PlanMode {
            session: session.clone(),
            active,
        });
    }
    if let Some(preset) = composition_current_value(Some(options)) {
        events.push(UiEvent::AgentPreset {
            session: session.clone(),
            preset,
        });
    }
    if let Some(effort) = reasoning_effort_option(options).and_then(|option| {
        option
            .get("currentValue")
            .or_else(|| option.get("current_value"))
            .and_then(Value::as_str)
    }) {
        events.push(UiEvent::ReasoningEffort {
            session,
            effort: effort.to_string(),
        });
    }
    events
}

/// Models + composition choices from ACP `configOptions`.
pub fn catalog_from_config_options(
    options: &Value,
) -> (
    Vec<crate::bus::CatalogModel>,
    Vec<crate::bus::CatalogPreset>,
    Option<String>,
) {
    let mut models = Vec::new();
    if let Some(arr) = options.as_array() {
        if let Some(model) = arr
            .iter()
            .find(|o| config_id_of(o) == Some("model"))
        {
            for (id, name, _) in
                flatten_select_options(model.get("options").unwrap_or(&Value::Null))
            {
                let (provider, model_id) = match id.split_once('/') {
                    Some((p, m)) => (p.to_string(), m.to_string()),
                    None => (String::new(), id.clone()),
                };
                models.push(crate::bus::CatalogModel {
                    provider,
                    id: model_id,
                    name,
                    vision: false,
                });
            }
        }
    }
    let composition = composition_option(options);
    let composition_id = composition
        .and_then(config_id_of)
        .map(str::to_string);
    let mut presets = Vec::new();
    if let Some(option) = composition {
        for (id, name, description) in
            flatten_select_options(option.get("options").unwrap_or(&Value::Null))
        {
            let broken = description.starts_with("Broken:");
            presets.push(crate::bus::CatalogPreset {
                id,
                name,
                description,
                broken,
            });
        }
    }
    (models, presets, composition_id)
}

/// ACP session modes (`session/new.modes` / `availableModes`).
pub fn session_modes_from_value(modes: &Value) -> (Vec<crate::bus::CatalogPreset>, Option<String>) {
    let current = first_str(modes, &["currentModeId", "current_mode_id"]);
    let current = if current.is_empty() {
        None
    } else {
        Some(current)
    };
    let mut out = Vec::new();
    let Some(arr) = modes
        .get("availableModes")
        .or_else(|| modes.get("available_modes"))
        .and_then(Value::as_array)
    else {
        return (out, current);
    };
    for mode in arr {
        let Some(id) = mode.get("id").and_then(|v| match v {
            Value::String(s) => Some(s.clone()),
            other => other.as_str().map(str::to_string),
        }) else {
            continue;
        };
        out.push(crate::bus::CatalogPreset {
            name: mode
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or(&id)
                .to_string(),
            description: mode
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            id,
            broken: false,
        });
    }
    (out, current)
}

/// Slash entries from `available_commands_update`.
pub fn skills_from_available_commands(commands: &Value) -> Vec<crate::bus::SkillInfo> {
    let mut out = Vec::new();
    let Some(arr) = commands.as_array() else {
        return out;
    };
    for command in arr {
        let Some(name) = command.get("name").and_then(Value::as_str) else {
            continue;
        };
        out.push(crate::bus::SkillInfo {
            name: name.to_string(),
            description: command
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            input_hint: command
                .pointer("/input/hint")
                .and_then(Value::as_str)
                .map(str::to_string),
            config_action: command_config_action(command),
            client_command: command_client_action(command),
        });
    }
    out
}

fn command_client_action(command: &Value) -> bool {
    [command.get("metadata"), command.get("_meta")]
        .into_iter()
        .flatten()
        .filter_map(|carrier| carrier.get("commandAction"))
        .any(|action| action.get("kind").and_then(Value::as_str) == Some("clientCommand"))
}

fn command_config_action(command: &Value) -> Option<crate::bus::CommandConfigAction> {
    for carrier in [command.get("metadata"), command.get("_meta")]
        .into_iter()
        .flatten()
    {
        let action = carrier.get("commandAction")?;
        if action.get("kind").and_then(Value::as_str) != Some("setConfigOption") {
            continue;
        }
        let config_id = action.get("configId")?.as_str()?;
        let value = action.get("value")?.as_str()?;
        let reset_value = action
            .get("resetValue")
            .and_then(Value::as_str)
            .map(str::to_string);
        return Some(crate::bus::CommandConfigAction {
            config_id: config_id.to_string(),
            value: value.to_string(),
            reset_value,
        });
    }
    None
}

fn parse_assistant_chunk(session: String, data: &Value) -> Vec<UiEvent> {
    let chunk = match data.get("chunk") {
        Some(c) => c,
        None => return Vec::new(),
    };
    match chunk.get("type").and_then(Value::as_str) {
        Some("text-delta") => vec![UiEvent::TextDelta {
            session,
            text: str_field(chunk, "text"),
        }],
        Some("reasoning-delta") => vec![UiEvent::ReasoningDelta {
            session,
            text: str_field(chunk, "text"),
        }],
        Some("block-start")
            if chunk.get("blockType").and_then(Value::as_str) == Some("tool-call") =>
        {
            vec![UiEvent::ToolCallPreparing { session }]
        }
        Some("usage") => {
            let usage = chunk.get("usage").unwrap_or(&Value::Null);
            let cached = u64_field(usage, "cacheReadTokens")
                .or_else(|| u64_field(usage, "cachedInputTokens"))
                .or_else(|| u64_field(usage, "cacheReadInputTokens"))
                .unwrap_or(0);
            vec![UiEvent::Usage {
                session,
                input: u64_field(usage, "inputTokens").unwrap_or(0),
                output: u64_field(usage, "outputTokens").unwrap_or(0),
                cached,
                reasoning: u64_field(usage, "reasoningTokens").unwrap_or(0),
            }]
        }
        _ => Vec::new(),
    }
}

fn parse_tool_result(session: String, data: &Value) -> Vec<UiEvent> {
    let empty: Vec<Value> = Vec::new();
    let blocks = data
        .get("message")
        .and_then(|m| m.get("content"))
        .and_then(Value::as_array)
        .unwrap_or(&empty);

    let mut is_error = false;
    let mut call_id = String::new();
    let mut have_call_id = false;
    let mut texts: Vec<String> = Vec::new();

    for block in blocks {
        if block.get("type").and_then(Value::as_str) != Some("tool-result") {
            continue;
        }
        if block.get("isError").and_then(Value::as_bool) == Some(true) {
            is_error = true;
        }
        if !have_call_id {
            call_id = str_field(block, "toolCallId");
            have_call_id = true;
        }
        texts.push(concat_text_blocks(
            block.get("content").unwrap_or(&Value::Null),
        ));
    }

    let mut error = None;
    if let Some(err) = data.get("error") {
        if !err.is_null() {
            let name = str_field(err, "name");
            let code = match err.get("code") {
                Some(Value::String(s)) => s.clone(),
                Some(Value::Number(n)) => n.to_string(),
                _ => String::new(),
            };
            error = Some(format!("{name} ({code})"));
            is_error = true;
        }
    }

    vec![UiEvent::ToolResult {
        session,
        call_id,
        is_error,
        text: texts.join("\n"),
        error,
    }]
}

fn parse_user_message(session: String, data: &Value) -> Vec<UiEvent> {
    let kind = match data
        .get("source")
        .and_then(|s| s.get("kind"))
        .and_then(Value::as_str)
    {
        Some(k) => k,
        None => return Vec::new(),
    };
    if kind == "user" {
        return Vec::new();
    }
    let full = concat_text_blocks(data.get("content").unwrap_or(&Value::Null));
    let preview: String = full.chars().take(160).collect();
    vec![UiEvent::UserInjected {
        session,
        source: kind.to_string(),
        preview,
    }]
}

/// Concatenate the `.text` of blocks with `type == "text"` in a content array.
fn concat_text_blocks(content: &Value) -> String {
    let mut out = String::new();
    if let Some(blocks) = content.as_array() {
        for block in blocks {
            if block.get("type").and_then(Value::as_str) == Some("text") {
                if let Some(t) = block.get("text").and_then(Value::as_str) {
                    out.push_str(t);
                }
            }
        }
    }
    out
}

fn str_field(v: &Value, key: &str) -> String {
    v.get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

fn u64_field(v: &Value, key: &str) -> Option<u64> {
    v.get(key).and_then(Value::as_u64)
}

/// Coalesce a burst of drained bus events before they reach `App::handle`.
///
/// ACP agents may stream session updates at extreme rates — an agent's
/// `session/load` replay can re-emit every historical delta of a long session
/// (a 10k-event log became 258k notifications / 1.4 GB, melting the UI loop
/// for minutes; issue #94 freeze). Deltas are append-only and tool-call
/// updates are state-replacing, so merging adjacent ones is lossless for the
/// final transcript:
///
/// - consecutive text chunks (`agent_message_chunk` / `agent_thought_chunk`)
///   for the same session and message are concatenated; a trailing `_meta`
///   (model attribution on the final chunk) is preserved;
/// - consecutive *bare* `tool_call_update`s for the same session and call
///   keep only the latest state. Updates carrying `content`, `rawOutput`,
///   or `_meta` (diff blocks, terminal streams) are never dropped.
///
/// `tool_call` (turn start of a call) is a different kind and never merges,
/// so the tool start/result frame boundary in the drain loop is untouched.
pub fn coalesce_session_updates(events: &mut Vec<crate::bus::AppEvent>) {
    use crate::bus::AppEvent;
    if events.len() < 2 {
        return;
    }
    let mut out: Vec<AppEvent> = Vec::with_capacity(events.len());
    for ev in events.drain(..) {
        if let (
            Some(AppEvent::Rpc {
                method: prev_method,
                params: prev_params,
            }),
            AppEvent::Rpc { method, params },
        ) = (out.last_mut(), &ev)
        {
            if prev_method == "session/update" && method == "session/update" {
                match merge_update(prev_params, params) {
                    MergeOutcome::Merged => continue,
                    MergeOutcome::Keep => {}
                }
            }
        }
        out.push(ev);
    }
    *events = out;
}

enum MergeOutcome {
    Merged,
    Keep,
}

fn merge_update(prev: &mut Value, new: &Value) -> MergeOutcome {
    let same_str = |a: &Value, b: &Value, key: &str| a.get(key).and_then(Value::as_str) == b.get(key).and_then(Value::as_str);
    if !same_str(prev, new, "sessionId") {
        return MergeOutcome::Keep;
    }
    let (Some(prev_update), Some(new_update)) = (prev.get_mut("update"), new.get("update")) else {
        return MergeOutcome::Keep;
    };
    if !same_str(prev_update, new_update, "sessionUpdate") {
        return MergeOutcome::Keep;
    }
    let kind = new_update
        .get("sessionUpdate")
        .and_then(Value::as_str)
        .unwrap_or_default();
    match kind {
        "agent_message_chunk" | "agent_thought_chunk" => {
            if !same_str(prev_update, new_update, "messageId") {
                return MergeOutcome::Keep;
            }
            let Some(new_text) = new_update.pointer("/content/text").and_then(Value::as_str) else {
                return MergeOutcome::Keep;
            };
            match prev_update.pointer_mut("/content/text") {
                Some(Value::String(buf)) => buf.push_str(new_text),
                _ => return MergeOutcome::Keep,
            }
            // The final chunk of a message carries the model attribution.
            if let Some(meta) = new_update.get("_meta") {
                prev_update["_meta"] = meta.clone();
            }
            MergeOutcome::Merged
        }
        "tool_call_update" => {
            if !same_str(prev_update, new_update, "toolCallId") {
                return MergeOutcome::Keep;
            }
            let bare = |u: &Value| {
                u.get("content").is_none() && u.get("rawOutput").is_none() && u.get("_meta").is_none()
            };
            if !bare(prev_update) || !bare(new_update) {
                return MergeOutcome::Keep;
            }
            *prev_update = new_update.clone();
            MergeOutcome::Merged
        }
        _ => MergeOutcome::Keep,
    }
}

#[cfg(test)]
#[path = "../tests/unit/events__tests.rs"]
mod tests;

#[cfg(test)]
#[path = "../tests/unit/events__mode_event_tests.rs"]
mod mode_event_tests;
