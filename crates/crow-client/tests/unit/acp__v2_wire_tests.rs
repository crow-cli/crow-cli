//! ACP v2 wire-shape pins.
//!
//! These exist because the hosted migration docs were AHEAD of every SDK
//! installed on this box, and because the crate this project pinned
//! (`agent-client-protocol` 2.0.0 → `agent-client-protocol-schema` 1.5.0)
//! carried a v2 module that was complete for the stable protocol but missing
//! two fields crow's own v2 agent emits. Each test pinned one of those facts so
//! a dependency bump would show up as a diff here rather than as a silently
//! changed wire.
//!
//! That is exactly what happened. The bump to 2.2.0 → schema 1.9.1 closed both
//! gaps, the two canaries fired on purpose, and the pins below now record the
//! shapes the SDK really has. They stay worth keeping: the next bump should
//! trip them again rather than quietly move the wire underneath the client.

use agent_client_protocol::schema::v2 as v2;
use agent_client_protocol::schema::MaybeUndefined;
use agent_client_protocol::schema::ProtocolVersion;
use agent_client_protocol::Client;
use serde_json::{json, Value};

/// The v2 `initialize` request this client sends: role-agnostic `info`
/// (required) + `capabilities`, and no v1 `clientInfo`/`clientCapabilities`.
/// One source of truth: the request the probe actually sends. A test-local copy
/// would keep passing after the real one drifted.
pub(crate) fn v2_initialize_request() -> v2::InitializeRequest {
    super::negotiate::v2_initialize_request()
}

#[test]
fn v2_initialize_request_carries_info_and_capabilities_only() {
    let value = serde_json::to_value(v2_initialize_request()).unwrap();
    let obj = value.as_object().unwrap();
    assert_eq!(obj.get("protocolVersion").and_then(Value::as_u64), Some(2));
    assert!(obj.get("info").is_some(), "v2 requires role-agnostic info");
    assert!(obj.get("capabilities").is_some());
    // v1-only spellings must not leak onto the v2 wire.
    assert!(obj.get("clientInfo").is_none());
    assert!(obj.get("clientCapabilities").is_none());
    // v2 removed the client fs + terminal execution surface entirely, so
    // there is nothing to decline and nothing to advertise.
    let caps = obj.get("capabilities").unwrap().as_object().unwrap();
    assert!(caps.get("fs").is_none());
    assert!(caps.get("terminal").is_none());
}

#[test]
fn v2_initialize_response_reads_capabilities_by_presence() {
    let response: v2::InitializeResponse = serde_json::from_value(json!({
        "protocolVersion": 2,
        "info": {"name": "crow-cli", "version": "0.2.0"},
        "capabilities": {"session": {"prompt": {"image": {}, "embeddedContext": {}}}},
        "authMethods": []
    }))
    .unwrap();
    assert_eq!(response.protocol_version, ProtocolVersion::V2);
    assert_eq!(response.info.name, "crow-cli");
    // v1 checked `promptCapabilities.image == true`; v2 checks presence.
    let image = response
        .capabilities
        .session
        .as_ref()
        .and_then(|session| session.prompt.as_ref())
        .and_then(|prompt| prompt.image.as_ref());
    assert!(image.is_some());

    let bare: v2::InitializeResponse = serde_json::from_value(json!({
        "protocolVersion": 2,
        "info": {"name": "x", "version": "1"},
        "capabilities": {}
    }))
    .unwrap();
    assert!(bare.capabilities.session.is_none());
}

#[test]
fn v2_session_update_fixtures_land_on_their_variants() {
    let cases: Vec<(&str, Value, &str)> = vec![
        ("running", json!({"sessionUpdate": "state_update", "state": "running"}), "StateUpdate"),
        ("idle", json!({"sessionUpdate": "state_update", "state": "idle", "stopReason": "end_turn"}), "StateUpdate"),
        (
            "requires_action",
            json!({"sessionUpdate": "state_update", "state": "requires_action"}),
            "StateUpdate",
        ),
        (
            "agent_message",
            json!({"sessionUpdate": "agent_message", "messageId": "m1",
                   "content": [{"type": "text", "text": "hi"}]}),
            "AgentMessage",
        ),
        (
            "user_message",
            json!({"sessionUpdate": "user_message", "messageId": "m2",
                   "content": [{"type": "text", "text": "hey"}]}),
            "UserMessage",
        ),
        (
            "agent_thought",
            json!({"sessionUpdate": "agent_thought", "messageId": "m3",
                   "content": [{"type": "text", "text": "hm"}]}),
            "AgentThought",
        ),
        (
            "agent_message_chunk",
            json!({"sessionUpdate": "agent_message_chunk", "messageId": "m4",
                   "content": {"type": "text", "text": "a"}}),
            "AgentMessageChunk",
        ),
        (
            "tool_call_update",
            json!({"sessionUpdate": "tool_call_update", "toolCallId": "c1",
                   "title": "Reading", "kind": "read", "status": "pending"}),
            "ToolCallUpdate",
        ),
        (
            "tool_call_content_chunk",
            json!({"sessionUpdate": "tool_call_content_chunk", "toolCallId": "c1",
                   "content": {"type": "content", "content": {"type": "text", "text": "ok"}}}),
            "ToolCallContentChunk",
        ),
        (
            "terminal_update",
            json!({"sessionUpdate": "terminal_update", "terminalId": "t1",
                   "command": "cargo test", "cwd": "/workspace",
                   "exitStatus": {"exitCode": 0}}),
            "TerminalUpdate",
        ),
        (
            "terminal_output_chunk",
            json!({"sessionUpdate": "terminal_output_chunk", "terminalId": "t1",
                   "data": "cGFzc2Vk"}),
            "TerminalOutputChunk",
        ),
        (
            "plan_update",
            json!({"sessionUpdate": "plan_update",
                   "plan": {"type": "items", "planId": "p1", "entries": [
                       {"content": "check", "priority": "high", "status": "pending"}]}}),
            "PlanUpdate",
        ),
        (
            "config_option_update",
            json!({"sessionUpdate": "config_option_update", "configOptions": [
                {"configId": "model", "name": "Model", "category": "model",
                 "type": "select", "currentValue": "a:b",
                 "options": [{"value": "a:b", "name": "B"}]}]}),
            "ConfigOptionUpdate",
        ),
        (
            "usage_update",
            json!({"sessionUpdate": "usage_update", "used": 10, "size": 100}),
            "UsageUpdate",
        ),
        (
            "session_info_update",
            json!({"sessionUpdate": "session_info_update", "title": "T"}),
            "SessionInfoUpdate",
        ),
        (
            "available_commands_update",
            json!({"sessionUpdate": "available_commands_update", "availableCommands": [
                {"name": "search", "description": "d", "input": {"type": "text", "hint": "q"}}]}),
            "AvailableCommandsUpdate",
        ),
    ];
    for (label, fixture, expected) in cases {
        let parsed: v2::SessionUpdate = serde_json::from_value(fixture.clone())
            .unwrap_or_else(|err| panic!("{label}: {err}"));
        let variant = format!("{parsed:?}");
        assert!(
            variant.starts_with(expected),
            "{label}: expected {expected}, got {variant}"
        );
    }
}

#[test]
fn v2_unknown_update_is_preserved_not_rejected() {
    let parsed: v2::SessionUpdate =
        serde_json::from_value(json!({"sessionUpdate": "_crow_widget", "n": 1})).unwrap();
    match parsed {
        v2::SessionUpdate::Other(other) => {
            assert_eq!(other.session_update, "_crow_widget");
            assert_eq!(other.fields.get("n").and_then(Value::as_u64), Some(1));
        }
        other => panic!("expected Other, got {other:?}"),
    }
}

/// RULING 2's gap, closed by the 1.9.1 bump. `crow-cli acp2` emits `name` on
/// tool calls; schema 1.5.0 had no such field — it was `unstable_tool_call_name`
/// — so serde ignored the unknown key, the typed struct lost it, and `events.rs`
/// could only read it from the raw JSON crow forwards. 1.9.1 has the field with
/// no feature gate, as `MaybeUndefined<String>` under patch semantics (omitted
/// means unchanged, `null` clears, a string replaces).
///
/// crow still forwards `session/update` raw, and this pins that the reason is no
/// longer `name`: `SessionUpdate` is `#[non_exhaustive]` and its fields
/// deserialize through `DefaultOnError`, so a typed round trip drops any update
/// kind the pinned schema predates. Compaction is the live example — agent2
/// emits it unconditionally and there is no capability handshake in v2.
#[test]
fn v2_tool_call_name_is_typed_and_still_survives_raw_forwarding() {
    let fixture = json!({"sessionUpdate": "tool_call_update", "toolCallId": "c1",
                         "name": "execute", "title": "Running", "status": "in_progress"});
    let parsed: v2::SessionUpdate = serde_json::from_value(fixture.clone()).unwrap();
    let v2::SessionUpdate::ToolCallUpdate(tool_call) = parsed else {
        panic!("expected ToolCallUpdate");
    };
    assert_eq!(tool_call.tool_call_id.to_string(), "c1");
    // The typed field the 1.5.0 pin could not see.
    assert!(
        matches!(&tool_call.name, MaybeUndefined::Value(name) if name == "execute"),
        "schema 1.9.1 types ToolCallUpdate.name; got {:?}",
        tool_call.name
    );
    // It round-trips now, so re-serializing no longer drops it either.
    let serialized = serde_json::to_value(&tool_call).unwrap();
    assert_eq!(serialized.get("name").and_then(Value::as_str), Some("execute"));
    // Omission is patch semantics, not an error and not a clear.
    let bare: v2::SessionUpdate = serde_json::from_value(
        json!({"sessionUpdate": "tool_call_update", "toolCallId": "c1"}),
    )
    .unwrap();
    let v2::SessionUpdate::ToolCallUpdate(bare) = bare else {
        panic!("expected ToolCallUpdate");
    };
    assert!(bare.name.is_undefined());
    // And the raw params crow actually forwards keep it whatever the schema does.
    assert_eq!(fixture.get("name").and_then(Value::as_str), Some("execute"));
}

/// RULING 1, closed by the 1.9.1 bump. The hosted migration docs always said
/// the v2 `session/prompt` response carries a required `messageId`; Rust 1.5.0,
/// Rust 1.7.0 and Python alpha.3 all defined `PromptResponse` as `_meta` only.
/// 1.9.1 agrees with the docs — and with crow's own agent, which was already
/// sending the field (`agent2/agent.py` returns
/// `v2.PromptResponse(message_id=...)`), so the Rust client had been discarding
/// an id its agent supplied.
///
/// The response is still only an ACK. The stop reason arrives on `state_update:
/// idle`, never here, which is the fact `v2.rs::spawn_prompt` depends on when it
/// treats `Ok(_)` as "accepted" and waits for the board.
#[test]
fn v2_prompt_response_is_an_ack_requiring_message_id() {
    // "Required and non-null. Omission and explicit `null` are both invalid."
    assert!(serde_json::from_value::<v2::PromptResponse>(json!({})).is_err());
    assert!(serde_json::from_value::<v2::PromptResponse>(json!({"messageId": null})).is_err());

    let ack: v2::PromptResponse =
        serde_json::from_value(json!({"messageId": "msg_user_8f7a1"})).unwrap();
    assert_eq!(ack.message_id.to_string(), "msg_user_8f7a1");
    let value = serde_json::to_value(&ack).unwrap();
    assert!(value.get("stopReason").is_none(), "the outcome is not in the ack");
    // It round-trips now; the 1.5.0 pin asserted the opposite.
    assert_eq!(value.get("messageId").and_then(Value::as_str), Some("msg_user_8f7a1"));
}

#[test]
fn v2_idle_state_update_carries_the_stop_reason_and_usage() {
    let parsed: v2::SessionUpdate = serde_json::from_value(json!({
        "sessionUpdate": "state_update",
        "state": "idle",
        "stopReason": "cancelled",
        "usage": {"totalTokens": 7, "inputTokens": 3, "outputTokens": 4,
                  "thoughtTokens": 1, "cachedReadTokens": 2}
    }))
    .unwrap();
    let v2::SessionUpdate::StateUpdate(v2::StateUpdate::Idle(idle)) = parsed else {
        panic!("expected an idle state update");
    };
    assert!(matches!(idle.stop_reason, Some(v2::StopReason::Cancelled)));
    let usage = idle.usage.expect("unstable_end_turn_token_usage is enabled");
    assert_eq!(usage.total_tokens, 7);
    assert_eq!(usage.input_tokens, 3);
    assert_eq!(usage.output_tokens, 4);
    assert_eq!(usage.thought_tokens, Some(1));
    assert_eq!(usage.cached_read_tokens, Some(2));
}

/// The landmine behind the fixture above. v2's `Usage.total_tokens` is
/// REQUIRED (v1's turn usage never asked for it), and `IdleStateUpdate.usage`
/// is wrapped in `DefaultOnError` — so an agent that omits `totalTokens` does
/// not produce a parse error, it silently produces `usage: None` and the token
/// meter just stays empty. `crow-cli acp2` is safe here: its
/// `agent2/emitter.py::usage_model` always fills `total_tokens`, falling back
/// to `input + output`. Any other v2 agent needs the same care, and a missing
/// meter is the only symptom.
#[test]
fn v2_idle_usage_without_total_tokens_silently_vanishes() {
    let parsed: v2::SessionUpdate = serde_json::from_value(json!({
        "sessionUpdate": "state_update",
        "state": "idle",
        "stopReason": "end_turn",
        "usage": {"inputTokens": 3, "outputTokens": 4}
    }))
    .unwrap();
    let v2::SessionUpdate::StateUpdate(v2::StateUpdate::Idle(idle)) = parsed else {
        panic!("expected an idle state update");
    };
    assert!(matches!(idle.stop_reason, Some(v2::StopReason::EndTurn)));
    assert!(idle.usage.is_none(), "DefaultOnError swallowed it, as documented");
}

#[test]
fn v2_permission_request_separates_prompt_copy_from_tool_state() {
    let parsed: v2::RequestPermissionRequest = serde_json::from_value(json!({
        "sessionId": "s1",
        "title": "Run this script?",
        "description": "wants to execute scripts/setup.sh",
        "subject": {"type": "command", "command": "cargo test", "cwd": "/workspace"},
        "options": [{"optionId": "allow", "name": "Allow once", "kind": "allow_once"}]
    }))
    .unwrap();
    assert_eq!(parsed.title, "Run this script?");
    assert!(parsed.subject.is_some());
    assert_eq!(parsed.options.len(), 1);
}

/// Compile-time proof that the pinned crate still exposes the entry point crow's
/// v2 stack is actually built on.
///
/// `without_acp_version_guard` is load-bearing, not cosmetic. It is the only way
/// to get a v2-speaking connection whose callbacks receive a raw `ConnectionTo`,
/// and crow needs exactly that because `negotiate::probe` consumes the
/// `initialize` round trip at the transport layer before any connection exists.
/// Build the v2 stack on `Client::v2()` instead and the connection never leaves
/// `Uninitialized`, so every request is rejected with "ACP initialization must
/// complete before ... can be used". If a future SDK drops or renames the escape
/// hatch this stops compiling — which is the point of pinning it here.
///
/// The other two still exist and crow deliberately uses neither: `Client::v2()`
/// hands back a `V2ConnectionTo` that cannot convert back to the type v1 uses,
/// which would split `control::run_version_neutral` in two, and
/// `Client::protocol_connector()` re-spawns the agent on a v1 answer. Both
/// reasons are written out in `negotiate.rs`.
#[test]
fn v2_client_entry_points_exist() {
    let _builder = Client
        .builder()
        .without_acp_version_guard()
        .name(env!("CARGO_PKG_NAME"));
    let _v2_builder = Client.v2().name(env!("CARGO_PKG_NAME"));
    let _connector = Client.protocol_connector();
}
