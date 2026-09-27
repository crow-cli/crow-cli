use super::*;
use serde_json::json;

#[test]
fn session_status_running_and_idle() {
    let ev = parse_notification(
        "session.status",
        &json!({"sessionId": "s1", "status": "running"}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::SessionStatus {
            session: "s1".into(),
            running: true
        }]
    );

    let ev = parse_notification(
        "session.status",
        &json!({"sessionId": "s1", "status": "idle"}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::SessionStatus {
            session: "s1".into(),
            running: false
        }]
    );
}

#[test]
fn subagent_started_and_finished() {
    let ev = parse_notification(
        "subagent.started",
        &json!({"parentSessionId": "p", "childSessionId": "c"}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::SubagentStarted {
            parent: "p".into(),
            child: "c".into()
        }]
    );

    let ev = parse_notification("subagent.finished", &json!({"childSessionId": "c"}));
    assert_eq!(
        ev,
        vec![UiEvent::SubagentFinished {
            child: "c".into(),
            failed: false,
        }]
    );
}

#[test]
fn standard_acp_nonterminal_tool_updates_refresh_the_existing_request() {
    let updates = parse_notification(
        "session/update",
        &json!({
            "sessionId": "parent",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call-1",
                "title": "Subagent: inspect renderer",
                "status": "in_progress",
                "rawInput": {"task": "inspect renderer"}
            }
        }),
    );
    assert_eq!(
        updates,
        vec![UiEvent::ToolCall {
            session: "parent".into(),
            call_id: "call-1".into(),
            name: "Subagent: inspect renderer".into(),
            arguments: r#"{"task":"inspect renderer"}"#.into(),
            diff: None,
        }]
    );
}

#[test]
fn a_tool_call_that_rides_content_instead_of_raw_input_is_still_readable() {
    // crow-cli's kernel tool sends no rawInput at all: the code rides the
    // call's `content`, wrapped the way ACP wraps every tool-call content
    // entry, and the completion repeats it ahead of the output.
    let fence = "```python\nprint(6 * 7)\n```";
    let started = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "turn/call_1",
                "title": "execute",
                "kind": "execute",
                "status": "pending",
                "content": [{"type": "content", "content": {"type": "text", "text": fence}}]
            }
        }),
    );
    assert_eq!(
        started,
        vec![UiEvent::ToolCall {
            session: "s".into(),
            call_id: "turn/call_1".into(),
            name: "execute".into(),
            arguments: fence.into(),
            diff: None,
        }]
    );

    let finished = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "turn/call_1",
                "status": "completed",
                "content": [
                    {"type": "content", "content": {"type": "text", "text": fence}},
                    {"type": "content", "content": {"type": "text", "text": "42"}}
                ]
            }
        }),
    );
    assert_eq!(
        finished,
        vec![UiEvent::ToolResult {
            session: "s".into(),
            call_id: "turn/call_1".into(),
            is_error: false,
            text: format!("{fence}\n42"),
            error: None,
        }]
    );
}

#[test]
fn raw_input_wins_over_content_and_a_null_one_is_no_answer() {
    let both = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "c",
                "title": "fs",
                "status": "pending",
                "rawInput": {"mode": "read"},
                "content": [{"type": "content", "content": {"type": "text", "text": "ignored"}}]
            }
        }),
    );
    assert_eq!(both[0], UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c".into(),
        name: "fs".into(),
        arguments: r#"{"mode":"read"}"#.into(),
        diff: None,
    });

    // An explicit null is an absent field, not the string "null".
    let nulled = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "c",
                "title": "fs",
                "status": "pending",
                "rawInput": null
            }
        }),
    );
    assert_eq!(nulled[0], UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c".into(),
        name: "fs".into(),
        arguments: String::new(),
        diff: None,
    });
}

#[test]
fn turn_start_and_end() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "turn/start", "data": {"turn": 3}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::TurnStart {
            session: "s".into(),
            turn: 3
        }]
    );

    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "turn/end", "data": {"reason": {"kind": "completed"}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::TurnEnd {
            session: "s".into(),
            kind: "completed".into()
        }]
    );

    // Missing reason -> default kind "unknown"; missing turn -> 0.
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "turn/end", "data": {}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::TurnEnd {
            session: "s".into(),
            kind: "unknown".into()
        }]
    );
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "turn/start", "data": {}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::TurnStart {
            session: "s".into(),
            turn: 0
        }]
    );
}

#[test]
fn text_and_reasoning_deltas() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "assistant/chunk",
                "data": {"chunk": {"type": "text-delta", "text": "hi"}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::TextDelta {
            session: "s".into(),
            text: "hi".into()
        }]
    );

    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "assistant/chunk",
                "data": {"chunk": {"type": "reasoning-delta", "text": "hmm"}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::ReasoningDelta {
            session: "s".into(),
            text: "hmm".into()
        }]
    );
}

#[test]
fn silent_chunk_types_emit_nothing() {
    for t in ["block-end", "tool-call-delta", "finish"] {
        let ev = parse_notification(
            "session.event",
            &json!({"sessionId": "s", "event": {"type": "assistant/chunk",
                    "data": {"chunk": {"type": t}}}}),
        );
        assert!(ev.is_empty(), "chunk type {t} should emit nothing");
    }
}

#[test]
fn tool_call_block_start_exposes_hidden_argument_streaming() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "assistant/chunk",
        "data": {"chunk": {
            "type": "block-start",
            "blockType": "tool-call",
            "index": 1
        }}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::ToolCallPreparing {
            session: "s".into()
        }]
    );

    let text_block = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "assistant/chunk",
                "data": {"chunk": {"type": "block-start", "blockType": "text"}}}}),
    );
    assert!(text_block.is_empty());
}

#[test]
fn usage_with_cached_input_tokens() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "assistant/chunk",
                "data": {"chunk": {"type": "usage", "usage": {
                    "inputTokens": 10, "outputTokens": 20,
                    "cachedInputTokens": 5, "reasoningTokens": 7}}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::Usage {
            session: "s".into(),
            input: 10,
            output: 20,
            cached: 5,
            reasoning: 7
        }]
    );
}

#[test]
fn usage_with_cache_read_alternate_key_and_defaults() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "assistant/chunk",
                "data": {"chunk": {"type": "usage", "usage": {
                    "inputTokens": 1, "cacheReadInputTokens": 9}}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::Usage {
            session: "s".into(),
            input: 1,
            output: 0,
            cached: 9,
            reasoning: 0
        }]
    );
}

#[test]
fn usage_with_harness_cache_read_tokens() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "assistant/chunk",
                "data": {"chunk": {"type": "usage", "usage": {
                    "inputTokens": 1, "outputTokens": 2,
                    "cacheReadTokens": 9, "reasoningTokens": 3}}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::Usage {
            session: "s".into(),
            input: 1,
            output: 2,
            cached: 9,
            reasoning: 3
        }]
    );
}

#[test]
fn assistant_final_with_text_and_model() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "assistant/message",
                "data": {"message": {
                    "content": [
                        {"type": "text", "text": "hello "},
                        {"type": "tool-call", "text": "ignored"},
                        {"type": "text", "text": "world"}
                    ],
                    "source": {"model": "deepseek-v3"}}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::AssistantFinal {
            session: "s".into(),
            text: "hello world".into(),
            model: Some("deepseek-v3".into()),
        }]
    );
}

#[test]
fn assistant_final_fallback_to_data_and_always_emits() {
    // No "message" key: use data itself; empty content still emits.
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "assistant/message",
                "data": {"content": [], "source": {"model": 42}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::AssistantFinal {
            session: "s".into(),
            text: String::new(),
            model: None
        }]
    );
}

#[test]
fn tool_call_fields_and_defaults() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "tool/call",
                "data": {"callId": "c1", "name": "bash", "arguments": "{\"command\":\"ls\"}"}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::ToolCall {
            session: "s".into(),
            call_id: "c1".into(),
            name: "bash".into(),
            arguments: "{\"command\":\"ls\"}".into(),
            diff: None,
        }]
    );

    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "tool/call", "data": {}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::ToolCall {
            session: "s".into(),
            call_id: String::new(),
            name: String::new(),
            arguments: String::new(),
            diff: None,
        }]
    );
}

#[test]
fn tool_result_success_blocks() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "tool/result",
        "data": {"message": {"content": [
            {"type": "tool-result", "toolCallId": "c1", "content": [
                {"type": "text", "text": "line1"}]},
            {"type": "tool-result", "toolCallId": "c2", "isError": false, "content": [
                {"type": "text", "text": "line2"}]}
        ]}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::ToolResult {
            session: "s".into(),
            call_id: "c1".into(),
            is_error: false,
            text: "line1\nline2".into(),
            error: None,
        }]
    );
}

#[test]
fn tool_result_is_error_block_flag() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "tool/result",
        "data": {"message": {"content": [
            {"type": "tool-result", "toolCallId": "c1", "isError": true, "content": [
                {"type": "text", "text": "boom"}]}
        ]}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::ToolResult {
            session: "s".into(),
            call_id: "c1".into(),
            is_error: true,
            text: "boom".into(),
            error: None,
        }]
    );
}

#[test]
fn tool_result_error_field_forces_is_error() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "tool/result",
                "data": {
                    "message": {"content": [
                        {"type": "tool-result", "toolCallId": "c9", "content": []}
                    ]},
                    "error": {"name": "ToolTimeout", "code": "E_TIMEOUT"}}}}),
    );
    assert_eq!(
        ev,
        vec![UiEvent::ToolResult {
            session: "s".into(),
            call_id: "c9".into(),
            is_error: true,
            text: String::new(),
            error: Some("ToolTimeout (E_TIMEOUT)".into()),
        }]
    );
}

#[test]
fn user_message_user_kind_suppressed() {
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "user/message",
                "data": {"source": {"kind": "user"},
                         "content": [{"type": "text", "text": "typed by human"}]}}}),
    );
    assert!(ev.is_empty());

    // Missing kind also suppressed.
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "user/message",
                "data": {"content": [{"type": "text", "text": "x"}]}}}),
    );
    assert!(ev.is_empty());
}

#[test]
fn user_message_plugin_kind_preview_truncation() {
    // 200 multi-byte chars; preview must be first 160 chars, boundary-safe.
    let long: String = "é".repeat(200);
    let ev = parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "user/message",
                "data": {"source": {"kind": "plugin"},
                         "content": [{"type": "text", "text": long}]}}}),
    );
    let expected: String = "é".repeat(160);
    assert_eq!(
        ev,
        vec![UiEvent::UserInjected {
            session: "s".into(),
            source: "plugin".into(),
            preview: expected,
        }]
    );
}

#[test]
fn unknown_method_and_unknown_event_type_yield_nothing() {
    assert!(parse_notification("nope.method", &json!({"sessionId": "s"})).is_empty());
    assert!(parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "weird/thing", "data": {}}})
    )
    .is_empty());
}

#[test]
fn tui_palette_notification_activates_ember() {
    let palette: Value =
        serde_json::from_str(include_str!("../../docs/fixtures/demo-skin.v0.json")).unwrap();
    let ev = parse_notification(
        crate::ext::THEME_UPDATE,
        &json!({"protocol": 0, "palette": palette, "activate": true}),
    );
    match &ev[..] {
        [UiEvent::Palette { pack, activate }] => {
            assert_eq!(pack.id, "ember");
            assert!(*activate);
            assert_eq!(
                pack.theme(crate::theme::Mode::Dark).brand,
                ratatui::style::Color::Rgb(247, 140, 60)
            );
        }
        other => panic!("expected Palette, got {other:?}"),
    }
}

#[test]
fn tui_palette_wrong_protocol_or_invalid_yields_nothing() {
    let palette: Value =
        serde_json::from_str(include_str!("../../docs/fixtures/demo-skin.v0.json")).unwrap();
    assert!(parse_notification(
        crate::ext::THEME_UPDATE,
        &json!({"protocol": 1, "palette": palette, "activate": true})
    )
    .is_empty());
    assert!(parse_notification(
        crate::ext::THEME_UPDATE,
        &json!({"protocol": 0, "palette": {"id": "x"}, "activate": true})
    )
    .is_empty());
}

#[test]
fn session_update_maps_chunks_tools_and_agent_option() {
    let ev = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "hi"}
            }
        }),
    );
    assert_eq!(
        ev,
        vec![UiEvent::TextDelta {
            session: "s".into(),
            text: "hi".into()
        }]
    );

    let ev = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "sessionUpdate": "current_mode_update",
            "currentModeId": "read-only"
        }),
    );
    assert!(ev
        .iter()
        .any(|e| matches!(e, UiEvent::PermissionPreset { preset, .. } if preset == "read-only")));

    let ev = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "update": {
                "sessionUpdate": "config_option_update",
                "configOptions": [
                    {"type": "select", "id": "mode", "category": "mode", "currentValue": "read-only", "options": []},
                    {"type": "select", "id": "agent", "currentValue": "studio", "options": [{"value": "studio", "name": "Studio"}]},
                    {"type": "select", "id": "effort", "currentValue": "max", "options": [{"value": "high", "name": "High"}, {"value": "max", "name": "Max"}]}
                ]
            }
        }),
    );
    assert_eq!(
        ev,
        vec![
            UiEvent::AgentPreset {
                session: "s".into(),
                preset: "studio".into()
            },
            UiEvent::ReasoningEffort {
                session: "s".into(),
                effort: "max".into()
            }
        ]
    );
}

#[test]
fn typed_acp_session_warning_is_a_notice_not_assistant_text() {
    let ev = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "update": {
                "sessionUpdate": "session_info_update",
                "_meta": {
                    "jetbrains": {"air": {
                        "version": 1,
                        "sessionFailure": {
                            "id": "s:notice:1",
                            "revision": 1,
                            "category": "unknown",
                            "severity": "warning",
                            "title": "Skill descriptions were shortened",
                            "details": "Disable unused skills or plugins.",
                            "actions": []
                        }
                    }}
                }
            }
        }),
    );

    assert_eq!(
        ev,
        vec![UiEvent::SessionNotice {
            session: "s".into(),
            severity: "warning".into(),
            title: "Skill descriptions were shortened".into(),
            details: Some("Disable unused skills or plugins.".into()),
        }]
    );
}

#[test]
fn config_options_report_the_session_model() {
    let events = config_option_events(
        "codex-session".into(),
        &json!([
            {
                "type": "select",
                "id": "model",
                "category": "model",
                "currentValue": "gpt-5.6-codex",
                "options": []
            }
        ]),
    );

    assert_eq!(
        events,
        vec![UiEvent::SessionModel {
            session: "codex-session".into(),
            model: "gpt-5.6-codex".into(),
        }]
    );
}

#[test]
fn config_options_report_semantic_reasoning_effort() {
    let events = config_option_events(
        "codex-session".into(),
        &json!([{
            "type": "select",
            "id": "reasoning_effort",
            "category": "thought_level",
            "currentValue": "high",
            "options": []
        }]),
    );

    assert_eq!(
        events,
        vec![UiEvent::ReasoningEffort {
            session: "codex-session".into(),
            effort: "high".into(),
        }]
    );
}

#[test]
fn context_usage_update_becomes_a_meter_not_a_token_breakdown() {
    let events = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "update": {
                "sessionUpdate": "usage_update",
                "used": 170,
                "size": 1000
            }
        }),
    );

    assert_eq!(
        events,
        vec![UiEvent::ContextUsage {
            session: "s".into(),
            used: 170,
            size: 1000
        }],
        "usage_update is context pressure; it must stay out of the per-turn token breakdown"
    );
}

#[test]
fn context_usage_update_without_a_ceiling_is_ignored() {
    let events = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "update": {
                "sessionUpdate": "usage_update",
                "used": 170
            }
        }),
    );

    assert!(events.is_empty(), "used without size is not a meter reading");
}

#[test]
fn collaboration_config_update_restores_plan_mode_from_standard_acp() {
    let events = parse_notification(
        "session/update",
        &json!({
            "sessionId": "s",
            "update": {
                "sessionUpdate": "config_option_update",
                "configOptions": [{
                    "type": "select",
                    "id": "collaboration_mode",
                    "currentValue": "plan",
                    "options": [
                        {"value": "default", "name": "Default"},
                        {"value": "plan", "name": "Plan"}
                    ]
                }]
            }
        }),
    );

    assert_eq!(
        events,
        vec![UiEvent::PlanMode {
            session: "s".into(),
            active: true,
        }]
    );
}

#[test]
fn available_plan_command_keeps_its_standard_config_action() {
    let commands = skills_from_available_commands(&json!([{
        "name": "plan",
        "description": "Enter or leave plan mode",
        "input": { "hint": "on|off" },
        "_meta": {
            "commandAction": {
                "kind": "setConfigOption",
                "configId": "collaboration_mode",
                "value": "plan",
                "resetValue": "default"
            }
        }
    }]));

    assert_eq!(
        commands[0].config_action,
        Some(crate::bus::CommandConfigAction {
            config_id: "collaboration_mode".into(),
            value: "plan".into(),
            reset_value: Some("default".into()),
        })
    );
    assert_eq!(commands[0].input_hint.as_deref(), Some("on|off"));
}

#[test]
fn catalog_prefers_agent_id_and_flattens_groups() {
    let options = json!([
        {"type": "select", "id": "model", "category": "model", "options": [{"value": "deepseek/m1", "name": "M1"}]},
        {"type": "select", "id": "agent", "options": [
            {"group": "system", "name": "System", "options": [
                {"value": "studio", "name": "Studio", "description": "inspect"},
                {"value": "broken", "name": "Broken", "description": "Broken: missing yaml"}
            ]}
        ]}
    ]);
    let (models, presets, id) = catalog_from_config_options(&options);
    assert_eq!(id.as_deref(), Some("agent"));
    assert_eq!(models.len(), 1);
    assert_eq!(models[0].id, "m1");
    assert_eq!(presets.len(), 2);
    assert_eq!(presets[0].id, "studio");
    assert!(presets[1].broken);
}

#[test]
fn session_modes_read_available_and_current() {
    let modes = json!({
        "currentModeId": "workspace-write",
        "availableModes": [
            {"id": "read-only", "name": "Read only", "description": "no writes"},
            {"id": "workspace-write", "name": "Workspace write"}
        ]
    });
    let (list, current) = session_modes_from_value(&modes);
    assert_eq!(current.as_deref(), Some("workspace-write"));
    assert_eq!(list.len(), 2);
    assert_eq!(list[0].id, "read-only");
    assert_eq!(list[1].name, "Workspace write");
}

#[test]
fn malformed_payloads_yield_empty_vec() {
    // Non-object params.
    assert!(parse_notification("session.event", &json!("garbage")).is_empty());
    assert!(parse_notification("session.event", &json!(null)).is_empty());
    // Event missing type / wrong types.
    assert!(parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"data": {}}})
    )
    .is_empty());
    assert!(parse_notification(
        "session.event",
        &json!({"sessionId": 12, "event": {"type": 7}})
    )
    .is_empty());
    // session.status with non-string status.
    assert!(
        parse_notification("session.status", &json!({"sessionId": "s", "status": 1})).is_empty()
    );
    // assistant/chunk with missing chunk.
    assert!(parse_notification(
        "session.event",
        &json!({"sessionId": "s", "event": {"type": "assistant/chunk", "data": {}}})
    )
    .is_empty());
}

fn update_ev(session: &str, update: serde_json::Value) -> crate::bus::AppEvent {
    crate::bus::AppEvent::Rpc {
        method: "session/update".into(),
        params: json!({ "sessionId": session, "update": update }),
    }
}

fn text_chunk(session: &str, kind: &str, message: &str, text: &str) -> crate::bus::AppEvent {
    update_ev(
        session,
        json!({
            "sessionUpdate": kind,
            "content": { "type": "text", "text": text },
            "messageId": message,
        }),
    )
}

#[test]
fn adjacent_text_chunks_for_one_message_merge() {
    let mut events = vec![
        text_chunk("s1", "agent_message_chunk", "1:1", "hello "),
        text_chunk("s1", "agent_message_chunk", "1:1", "world"),
        text_chunk("s1", "agent_thought_chunk", "1:1", "thinking "),
        text_chunk("s1", "agent_thought_chunk", "1:1", "aloud"),
    ];
    coalesce_session_updates(&mut events);
    assert_eq!(events.len(), 2);
    let crate::bus::AppEvent::Rpc { params, .. } = &events[0] else {
        panic!("rpc")
    };
    assert_eq!(params["update"]["content"]["text"], "hello world");
    let crate::bus::AppEvent::Rpc { params, .. } = &events[1] else {
        panic!("rpc")
    };
    assert_eq!(params["update"]["content"]["text"], "thinking aloud");
}

#[test]
fn text_chunks_do_not_merge_across_messages_sessions_or_kinds() {
    let mut events = vec![
        text_chunk("s1", "agent_message_chunk", "1:1", "a"),
        text_chunk("s1", "agent_message_chunk", "1:2", "b"),
        text_chunk("s2", "agent_message_chunk", "1:2", "c"),
        text_chunk("s2", "agent_thought_chunk", "1:2", "d"),
    ];
    coalesce_session_updates(&mut events);
    assert_eq!(events.len(), 4);
}

#[test]
fn the_final_chunks_meta_survives_a_merge() {
    let mut events = vec![
        text_chunk("s1", "agent_message_chunk", "1:1", "body"),
        update_ev(
            "s1",
            json!({
                "sessionUpdate": "agent_message_chunk",
                "content": { "type": "text", "text": "" },
                "messageId": "1:1",
                "_meta": { "dsh": { "event": "assistant_message", "model": "deepseek-v4-flash" } },
            }),
        ),
    ];
    coalesce_session_updates(&mut events);
    assert_eq!(events.len(), 1);
    let crate::bus::AppEvent::Rpc { params, .. } = &events[0] else {
        panic!("rpc")
    };
    assert_eq!(params["update"]["content"]["text"], "body");
    assert_eq!(params["update"]["_meta"]["dsh"]["model"], "deepseek-v4-flash");
}

fn bare_tool_update(session: &str, call: &str, status: &str) -> crate::bus::AppEvent {
    update_ev(
        session,
        json!({
            "sessionUpdate": "tool_call_update",
            "toolCallId": call,
            "title": "bash ls",
            "status": status,
        }),
    )
}

#[test]
fn bare_tool_call_updates_keep_only_the_latest() {
    let mut events = vec![
        bare_tool_update("s1", "c1", "pending"),
        bare_tool_update("s1", "c1", "pending"),
        bare_tool_update("s1", "c1", "in_progress"),
        bare_tool_update("s1", "c2", "pending"),
    ];
    coalesce_session_updates(&mut events);
    assert_eq!(events.len(), 2);
    let crate::bus::AppEvent::Rpc { params, .. } = &events[0] else {
        panic!("rpc")
    };
    assert_eq!(params["update"]["status"], "in_progress");
    let crate::bus::AppEvent::Rpc { params, .. } = &events[1] else {
        panic!("rpc")
    };
    assert_eq!(params["update"]["toolCallId"], "c2");
}

#[test]
fn rich_tool_call_updates_are_never_dropped() {
    let mut events = vec![
        bare_tool_update("s1", "c1", "pending"),
        update_ev(
            "s1",
            json!({
                "sessionUpdate": "tool_call_update",
                "toolCallId": "c1",
                "status": "completed",
                "rawOutput": { "output": "ok", "isError": false },
            }),
        ),
        update_ev(
            "s1",
            json!({
                "sessionUpdate": "tool_call_update",
                "toolCallId": "c1",
                "_meta": { "terminal_output": { "terminal_id": "c1", "data": "chunk" } },
            }),
        ),
    ];
    coalesce_session_updates(&mut events);
    assert_eq!(events.len(), 3);
}

#[test]
fn non_update_events_pass_through_untouched() {
    let mut events = vec![
        text_chunk("s1", "agent_message_chunk", "1:1", "a"),
        update_ev("s1", json!({ "sessionUpdate": "tool_call", "toolCallId": "c1" })),
        text_chunk("s1", "agent_message_chunk", "1:1", "b"),
        crate::bus::AppEvent::Ui(UiEvent::TurnEnd {
            session: "s1".into(),
            kind: "end_turn".into(),
        }),
        text_chunk("s1", "agent_message_chunk", "1:1", "c"),
    ];
    coalesce_session_updates(&mut events);
    // The tool_call start and the TurnEnd break every run: nothing merges.
    assert_eq!(events.len(), 5);
}

#[test]
fn v2_whole_message_updates_repaint_a_replayed_transcript() {
    assert_eq!(
        v2_update(
            "premium-amethyst-anaconda-of-tenacity",
            json!({
                "sessionUpdate": "user_message",
                "messageId": "6e284e5302224f3eb739b46a67d4802b",
                "content": [{ "text": "write a 400 word essay about the sea", "type": "text" }],
            })
        ),
        vec![UiEvent::UserMessage {
            session: "premium-amethyst-anaconda-of-tenacity".into(),
            text: "write a 400 word essay about the sea".into(),
        }]
    );

    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "agent_thought",
                "messageId": "619713175e474dd783039a0a012fabf9",
                "content": [{ "text": "The user wants a 400-word essay.", "type": "text" }],
            })
        ),
        vec![UiEvent::ReasoningDelta {
            session: "s1".into(),
            text: "The user wants a 400-word essay.".into(),
        }]
    );

    let events = v2_update(
        "s1",
        json!({
            "sessionUpdate": "agent_message",
            "messageId": "58192eddf1204d629dcbe52501bc5f5d",
            "content": [{ "text": "PONG", "type": "text" }],
        })
    );
    assert_eq!(
        events,
        vec![UiEvent::AssistantFinal {
            session: "s1".into(),
            text: "PONG".into(),
            model: None,
        }],
        "a whole message is one finished cell, never a delta"
    );

    // A message split across blocks is one run of text: `concat_text_blocks`
    // joins with no separator (the blocks are fragments, not paragraphs), and a
    // non-text block contributes nothing.
    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "agent_message",
                "content": [
                    { "type": "text", "text": "PONG" },
                    { "type": "image", "data": "AAAA", "mimeType": "image/png" },
                    { "type": "text", "text": "!" },
                ],
            })
        ),
        vec![UiEvent::AssistantFinal {
            session: "s1".into(),
            text: "PONG!".into(),
            model: None,
        }]
    );

    // An empty message paints nothing: `AssistantFinal` with no text and no open
    // cell would push a blank bubble into the transcript.
    assert_eq!(
        v2_update("s1", json!({ "sessionUpdate": "agent_message", "content": [] })),
        Vec::<UiEvent>::new()
    );
}

/// The turn does not end when `session/prompt` returns: v2's `PromptResponse`
/// is `{}`, and the idle `state_update` is the only end-of-turn signal. The
/// `acp::v2` stack settles its turn board off that notification before this
/// parser sees it, so parsing it into `SessionStatus`/`TurnEnd` as well would
/// report every turn twice — and agent2 re-emits idle every thirty seconds as
/// a heartbeat for a parked session, which would read as a turn ending.
#[test]
fn v2_state_update_belongs_to_the_stack_not_the_parser() {
    for update in [
        json!({ "sessionUpdate": "state_update", "state": "running" }),
        json!({ "sessionUpdate": "state_update", "state": "idle" }),
        json!({
            "sessionUpdate": "state_update",
            "state": "idle",
            "stopReason": "end_turn",
            "usage": { "totalTokens": 7661, "inputTokens": 7632, "outputTokens": 29 },
        }),
        json!({ "sessionUpdate": "state_update", "state": "idle", "stopReason": "cancelled" }),
        // The provider-failure path: v2's prompt response cannot carry
        // `stopReason: "error"`, so agent2 puts it on the idle instead.
        json!({ "sessionUpdate": "state_update", "state": "idle", "stopReason": "error" }),
    ] {
        assert_eq!(
            v2_update("s1", update.clone()),
            Vec::<UiEvent>::new(),
            "state_update {update} must not reach the transcript"
        );
    }
}

/// Terminal bytes have two audiences and only one of them is the transcript.
/// `terminal_output_chunk` is base64 PTY output for a human watching a
/// terminal pane; the model's copy of the same run arrives as
/// `tool_call_update.raw_output`. crow has no terminal pane, so painting
/// the PTY stream would be showing one thing twice.
#[test]
fn v2_terminal_updates_are_claimed_but_not_painted() {
    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "terminal_update",
                "terminalId": "term_79d4d32778c74087b3522bc369dcad67/call_4d5f7d16aa7643d8a7f2bac0",
                "command": "print(\"ok\")",
                "cwd": "/tmp/v2smoke",
            })
        ),
        Vec::<UiEvent>::new()
    );
    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "terminal_output_chunk",
                "terminalId": "term_1",
                "data": "b2sK",
            })
        ),
        Vec::<UiEvent>::new()
    );
    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "tool_call_content_chunk",
                "toolCallId": "call_1",
                "content": { "type": "content", "content": { "type": "text", "text": "ok" } },
            })
        ),
        Vec::<UiEvent>::new()
    );
}

/// A v2 agent sent no `tool_call` at all in the live capture: the first thing
/// it said about the call was a `tool_call_update` carrying `title`, `kind` and
/// `rawInput`. Updates are patches, so an update for an id nobody announced has
/// to CREATE the call or the tool cell never opens. The completion is a second
/// patch whose `rawOutput` is an object, not a string.
#[test]
fn a_v2_tool_call_arrives_as_its_own_first_update() {
    let call_id = "79d4d32778c74087b3522bc369dcad67/call_4d5f7d16aa7643d8a7f2bac0";
    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "tool_call_update",
                "toolCallId": call_id,
                "title": "execute",
                "kind": "execute",
                "status": "in_progress",
                "rawInput": { "code": "print(\"ok\")" },
            })
        ),
        vec![UiEvent::ToolCall {
            session: "s1".into(),
            call_id: call_id.into(),
            name: "execute".into(),
            arguments: r#"{"code":"print(\"ok\")"}"#.into(),
            diff: None,
        }],
        "no preceding tool_call: the in_progress patch opens the cell"
    );

    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "tool_call_update",
                "toolCallId": call_id,
                "status": "completed",
                "content": [{ "terminalId": format!("term_{call_id}"), "type": "terminal" }],
                "rawOutput": { "output": "ok", "exit_code": null },
            })
        ),
        vec![UiEvent::ToolResult {
            session: "s1".into(),
            call_id: call_id.into(),
            is_error: false,
            text: "ok".into(),
            error: None,
        }],
        "the terminal content block is not text; rawOutput.output is"
    );

    // A patch that repeats nothing but the status must not invent a second cell.
    assert_eq!(
        v2_update(
            "s1",
            json!({ "sessionUpdate": "tool_call_update", "toolCallId": call_id, "status": "in_progress" })
        ),
        Vec::<UiEvent>::new()
    );
}

fn v2_update(session: &str, update: serde_json::Value) -> Vec<UiEvent> {
    parse_notification("session/update", &json!({ "sessionId": session, "update": update }))
}

/// crow-cli's v2 subtool drain puts a drained row on the wire in ONE upsert:
/// first sight of the id, its diff artifact and its completion together. The
/// card half has to ride with the result half, and first, or the cell is born
/// in the transcript's nameless fallback and the diff is dropped on the floor.
#[test]
fn a_v2_diff_upsert_opens_the_card_and_completes_it() {
    let patch = "--- a/tmp/x.py\n+++ b/tmp/x.py\n@@ -1 +1 @@\n-a\n+b\n";
    let updates = v2_update(
        "s1",
        json!({
            "sessionUpdate": "tool_call_update",
            "toolCallId": "turn-1/call_sub7",
            "title": "edit: /tmp/x.py",
            "kind": "edit",
            "status": "completed",
            "rawInput": { "file_path": "/tmp/x.py", "old_string": "a", "new_string": "b" },
            "locations": [{ "path": "/tmp/x.py" }],
            "content": [{
                "type": "diff",
                "changes": [{ "path": "/tmp/x.py", "fileType": "text", "operation": "modify" }],
                "patch": { "format": "git_patch", "text": patch },
            }],
        }),
    );
    assert_eq!(
        updates.len(),
        2,
        "one upsert, two events: {updates:?}"
    );
    match &updates[0] {
        UiEvent::ToolCall {
            call_id,
            name,
            arguments,
            diff,
            ..
        } => {
            assert_eq!(call_id, "turn-1/call_sub7");
            assert_eq!(
                name, "edit",
                "the card titles itself with the path, so the header wants the kind"
            );
            assert!(
                arguments.contains("old_string"),
                "the raw input still rides along: {arguments}"
            );
            let d = diff.as_ref().expect("the diff block is the artifact");
            assert_eq!(
                d.path, "/tmp/x.py",
                "changes[].path is the real path, not the header's a/ b/"
            );
            assert_eq!(d.patch.as_deref(), Some(patch));
        }
        other => panic!("expected the card half, got {other:?}"),
    }
    assert!(
        matches!(&updates[1], UiEvent::ToolResult { call_id, is_error: false, .. }
            if call_id == "turn-1/call_sub7"),
        "and the result half closes it: {:?}",
        updates[1]
    );
}

/// v1 sent no patch: both whole texts, and the client did the diffing. It
/// patched the artifact in on an `in_progress` update, before the completion.
#[test]
fn a_v1_diff_block_carries_both_whole_texts() {
    let updates = v2_update(
        "s1",
        json!({
            "sessionUpdate": "tool_call_update",
            "toolCallId": "call_1",
            "status": "in_progress",
            "content": [{ "type": "diff", "path": "/tmp/x.py", "oldText": "a\n", "newText": "b\n" }],
        }),
    );
    match updates.as_slice() {
        [UiEvent::ToolCall { diff: Some(d), .. }] => {
            assert_eq!(d.path, "/tmp/x.py");
            assert_eq!(d.patch, None, "v1 computed nothing for us");
            assert_eq!(d.old_text.as_deref(), Some("a\n"));
            assert_eq!(d.new_text.as_deref(), Some("b\n"));
        }
        other => panic!("expected one card patch, got {other:?}"),
    }
}

/// `usage_update` is the only token signal crow-cli's v2 agent sends mid-turn,
/// and it reports context pressure as `used`/`size` rather than a breakdown.
#[test]
fn v2_usage_update_fills_the_context_meter() {
    assert_eq!(
        v2_update("s1", json!({ "sessionUpdate": "usage_update", "used": 7615, "size": 180000 })),
        vec![UiEvent::ContextUsage {
            session: "s1".into(),
            used: 7615,
            size: 180000,
        }]
    );
}

/// The live v2 turn: a chunk stream whose `content` is a single block object,
/// not an array. This is the shape that has to keep working alongside the
/// whole-message variants above.
#[test]
fn v2_live_chunks_carry_a_single_content_block() {
    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "agent_message_chunk",
                "messageId": "58192eddf1204d629dcbe52501bc5f5d",
                "content": { "text": "PONG", "type": "text" },
            })
        ),
        vec![UiEvent::TextDelta {
            session: "s1".into(),
            text: "PONG".into(),
        }]
    );
    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "agent_thought_chunk",
                "messageId": "9619c3e162414ecb844f72f6a7acd8d1",
                "content": { "text": " user wants", "type": "text" },
            })
        ),
        vec![UiEvent::ReasoningDelta {
            session: "s1".into(),
            text: " user wants".into(),
        }]
    );
    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "session_info_update",
                "title": "reply with exactly: PONG",
            })
        ),
        vec![UiEvent::SessionTitle {
            session: "s1".into(),
            title: "reply with exactly: PONG".into(),
        }]
    );
}


// ---------------------------------------------------------------------------
// v2 renamed the config-option key: `id` became `configId`. One reader
// (`config_id_of`) now serves both spellings, so both have to stay pinned —
// the v2 rename is what left the model catalog, the composition picker and the
// effort selector empty on a live v2 connection.
// ---------------------------------------------------------------------------

/// The verbatim `configOptions` from a real `crow-cli acp2` `session/new`.
fn v2_config_options() -> serde_json::Value {
    json!([{
        "configId": "model",
        "name": "Model",
        "category": "model",
        "type": "select",
        "currentValue": "bonsai:bonsai-2",
        "options": [
            { "value": "bonsai:bonsai-2", "name": "bonsai-2", "description": "bonsai-2" },
            { "value": "alibaba:qwen3.8-max", "name": "qwen3.8-max", "description": "qwen3.8-max" },
        ],
    }])
}

#[test]
fn config_id_of_reads_the_v2_key_first_and_falls_back_to_v1() {
    assert_eq!(config_id_of(&json!({ "configId": "model" })), Some("model"));
    assert_eq!(config_id_of(&json!({ "config_id": "model" })), Some("model"));
    assert_eq!(config_id_of(&json!({ "id": "model" })), Some("model"));
    assert_eq!(config_id_of(&json!({ "name": "Model" })), None);
    // A v2 option that also carries a stray `id` keeps its `configId`.
    assert_eq!(
        config_id_of(&json!({ "configId": "model", "id": "something-else" })),
        Some("model")
    );
}

#[test]
fn v2_config_options_still_feed_the_catalog_and_the_model_line() {
    let options = v2_config_options();

    assert_eq!(
        config_option_events("s1".into(), &options),
        vec![UiEvent::SessionModel {
            session: "s1".into(),
            model: "bonsai:bonsai-2".into(),
        }],
        "a v2 snapshot has to name the current model"
    );

    let (models, presets, composition_id) = catalog_from_config_options(&options);
    assert_eq!(
        models
            .iter()
            .map(|m| (m.provider.as_str(), m.id.as_str(), m.name.as_str()))
            .collect::<Vec<_>>(),
        vec![
            ("", "bonsai:bonsai-2", "bonsai-2"),
            ("", "alibaba:qwen3.8-max", "qwen3.8-max"),
        ],
        "colon-form ids carry their provider inside the id"
    );
    // `category: "model"` is what keeps the model select out of the composition
    // picker; without it every v2 agent would offer its models as presets.
    assert!(presets.is_empty(), "the model select is not a composition");
    assert_eq!(composition_id, None);
}

#[test]
fn the_v1_config_option_spelling_still_works_through_the_same_reader() {
    let options = json!([
        {
            "id": "model",
            "name": "Model",
            "type": "select",
            "currentValue": "gpt-5",
            "options": [{ "value": "gpt-5", "name": "GPT-5", "description": "gpt-5" }],
        },
        {
            "id": "agent",
            "name": "Agent",
            "type": "select",
            "currentValue": "code",
            "options": [
                { "value": "code", "name": "Code", "description": "code agent" },
                { "value": "chat", "name": "Chat", "description": "Broken: no model" },
            ],
        },
        {
            "id": "effort",
            "name": "Effort",
            "category": "thought_level",
            "type": "select",
            "currentValue": "high",
            "options": [{ "value": "high", "name": "High", "description": "high" }],
        },
    ]);

    assert_eq!(
        config_option_events("s1".into(), &options),
        vec![
            UiEvent::SessionModel {
                session: "s1".into(),
                model: "gpt-5".into()
            },
            UiEvent::AgentPreset {
                session: "s1".into(),
                preset: "code".into()
            },
            UiEvent::ReasoningEffort {
                session: "s1".into(),
                effort: "high".into()
            },
        ]
    );

    let (models, presets, composition_id) = catalog_from_config_options(&options);
    assert_eq!(models.len(), 1);
    assert_eq!(composition_id.as_deref(), Some("agent"));
    assert_eq!(
        presets
            .iter()
            .map(|p| (p.id.as_str(), p.broken))
            .collect::<Vec<_>>(),
        vec![("code", false), ("chat", true)]
    );
    assert_eq!(
        reasoning_effort_option(&options).and_then(config_id_of),
        Some("effort")
    );
}

/// v2 spells the same snapshot with `configId` everywhere; the composition and
/// effort picks have to survive the rename too, not just the model one.
#[test]
fn v2_config_options_name_the_composition_and_the_effort() {
    let options = json!([
        {
            "configId": "agent",
            "name": "Agent",
            "type": "select",
            "currentValue": "code",
            "options": [{ "value": "code", "name": "Code", "description": "code agent" }],
        },
        {
            "configId": "effort",
            "name": "Effort",
            "category": "thought_level",
            "type": "select",
            "currentValue": "low",
            "options": [{ "value": "low", "name": "Low", "description": "low" }],
        },
    ]);
    assert_eq!(
        config_option_events("s1".into(), &options),
        vec![
            UiEvent::AgentPreset {
                session: "s1".into(),
                preset: "code".into()
            },
            UiEvent::ReasoningEffort {
                session: "s1".into(),
                effort: "low".into()
            },
        ]
    );
    assert_eq!(
        composition_option(&options).and_then(config_id_of),
        Some("agent")
    );
    let (_, _, composition_id) = catalog_from_config_options(&options);
    assert_eq!(composition_id.as_deref(), Some("agent"));
}

/// A `config_option_update` notification is the mid-session spelling of the
/// same snapshot, and it is what a v2 agent sends after
/// `session/set_config_option`.
#[test]
fn v2_config_option_update_notification_reports_the_new_model() {
    assert_eq!(
        v2_update(
            "s1",
            json!({
                "sessionUpdate": "config_option_update",
                "configOptions": [{
                    "configId": "model",
                    "name": "Model",
                    "category": "model",
                    "type": "select",
                    "currentValue": "alibaba:qwen3.8-max",
                    "options": [],
                }],
            })
        ),
        vec![UiEvent::SessionModel {
            session: "s1".into(),
            model: "alibaba:qwen3.8-max".into(),
        }]
    );
}
