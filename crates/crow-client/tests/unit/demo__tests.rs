use super::*;
use std::sync::mpsc;

/// Collect all Rpc events from a finished demo turn.
fn collect(prompt: &str) -> Vec<(String, Value)> {
    let (tx, rx) = mpsc::channel();
    run_demo_turn(tx, "s-test".to_string(), prompt.to_string());
    let mut out = Vec::new();
    // Sender is moved into the thread; channel closes when it finishes.
    while let Ok(ev) = rx.recv_timeout(Duration::from_secs(5)) {
        if let AppEvent::Rpc { method, params } = ev {
            out.push((method, params));
        }
    }
    out
}

fn event_type(params: &Value) -> &str {
    params["event"]["type"].as_str().unwrap_or("")
}

#[test]
fn first_running_last_idle() {
    let events = collect("show me main");
    let (first_m, first_p) = &events[0];
    assert_eq!(first_m, "session.status");
    assert_eq!(first_p["status"], "running");
    let (last_m, last_p) = events.last().unwrap();
    assert_eq!(last_m, "session.status");
    assert_eq!(last_p["status"], "idle");
}

#[test]
fn tool_call_precedes_tool_result() {
    let events = collect("show me main");
    let call = events
        .iter()
        .position(|(m, p)| m == "session.event" && event_type(p) == "tool/call")
        .expect("tool/call emitted");
    let result = events
        .iter()
        .position(|(m, p)| m == "session.event" && event_type(p) == "tool/result")
        .expect("tool/result emitted");
    assert!(call < result, "tool/call must precede tool/result");
}

#[test]
fn error_prompt_ends_turn_with_error() {
    let events = collect("trigger an error please");
    let (_, end) = events
        .iter()
        .find(|(m, p)| m == "session.event" && event_type(p) == "turn/end")
        .expect("turn/end emitted");
    assert_eq!(end["event"]["data"]["reason"]["kind"], "error");
}

/// The 'diff' variation emits crow-cli's v2 subtool shape: ONE upsert that is
/// the call's first appearance, its artifact and its completion together, and
/// the parser has to read it as a card AND a result -- in that order, since
/// the result is what closes the cell.
#[test]
fn diff_prompt_emits_one_v2_upsert_that_parses_to_a_card_and_a_result() {
    let events = collect("show me the diff");
    let (_, params) = events
        .iter()
        .find(|(m, p)| {
            m == "session/update" && p["update"]["sessionUpdate"] == "tool_call_update"
        })
        .expect("a v2 tool_call_update");
    let block = &params["update"]["content"][0];
    assert_eq!(block["type"], "diff");
    assert_eq!(block["patch"]["format"], "git_patch");
    assert_eq!(
        block["changes"][0]["path"], "/work/crow/src/transcript.rs",
        "changes[].path is the real path, not the patch header's a/ b/"
    );
    let parsed = crate::events::parse_notification("session/update", params);
    assert!(
        matches!(
            &parsed[..],
            [
                crate::events::UiEvent::ToolCall { diff: Some(_), .. },
                crate::events::UiEvent::ToolResult { is_error: false, .. }
            ]
        ),
        "got {parsed:?}"
    );
}
