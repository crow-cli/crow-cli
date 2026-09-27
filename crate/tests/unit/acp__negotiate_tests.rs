//! The union probe, against scripted peers.
//!
//! A scripted peer here obeys the spec the way a real agent does: one that only
//! speaks v1 answers `protocolVersion: 1`, not the version the request asked
//! for. A peer that echoed 2 would make every test below pass against a client
//! that cannot actually talk to crow-cli.

use std::sync::{Arc, Mutex};
use std::time::Duration;

use agent_client_protocol::schema::v1::{RequestId, Response as RpcResponse};
use agent_client_protocol::{
    Channel, RawJsonRpcMessage, RawJsonRpcParams, TransportBatch, TransportBatchEntry,
    TransportFrame,
};
use futures::StreamExt;
use serde_json::{json, Value};

use super::{probe, Protocol};

/// The params of an `initialize` request, if that is what this frame is.
fn initialize_params(frame: &TransportFrame) -> Option<Value> {
    let TransportFrame::Single(RawJsonRpcMessage::Request(request)) = frame else {
        return None;
    };
    if request.method.as_ref() != "initialize" {
        return None;
    }
    match &request.params {
        Some(RawJsonRpcParams::Object(map)) => Some(Value::Object(map.clone())),
        Some(RawJsonRpcParams::Array(rows)) => Some(Value::Array(rows.clone())),
        None => Some(Value::Null),
    }
}

fn answer(result: Value) -> TransportFrame {
    TransportFrame::Single(RawJsonRpcMessage::response(
        RequestId::Number(0),
        Ok(result),
    ))
}

fn refusal(code: i32, message: &str) -> TransportFrame {
    TransportFrame::Single(RawJsonRpcMessage::response(
        RequestId::Number(0),
        Err(agent_client_protocol::Error::new(code, message.to_string())),
    ))
}

fn v1_answer() -> Value {
    json!({
        "protocolVersion": 1,
        "agentCapabilities": { "loadSession": true },
        "agentInfo": { "name": "stub-v1", "version": "0.0.1" },
        "authMethods": []
    })
}

fn v2_answer() -> Value {
    json!({
        "protocolVersion": 2,
        "capabilities": { "session": { "prompt": {} } },
        "info": { "name": "stub-v2", "version": "0.0.1" },
        "authMethods": []
    })
}

/// Spawn a scripted peer on the agent half of a duplex channel. It waits for
/// the probe's `initialize`, records what it was asked, then sends `replies` in
/// order. `hold` keeps its half open afterwards: a peer that drops immediately
/// turns "did not answer" into "closed the connection", which is a different
/// failure and gets its own test.
fn scripted_peer(
    replies: Vec<TransportFrame>,
    hold: bool,
) -> (Channel, Arc<Mutex<Option<Value>>>) {
    let (client, agent) = Channel::duplex();
    let seen = Arc::new(Mutex::new(None));
    let recorded = Arc::clone(&seen);
    tokio::spawn(async move {
        let Channel { mut rx, tx } = agent;
        while let Some(frame) = rx.next().await {
            if let Some(params) = initialize_params(&frame) {
                *recorded.lock().unwrap() = Some(params);
                break;
            }
        }
        for reply in replies {
            if tx.unbounded_send(reply).is_err() {
                return;
            }
        }
        if !hold {
            return;
        }
        // Keep the sender alive. Dropping it closes the client's half, which
        // turns "did not answer" into "closed the connection" — a different
        // failure, with its own test.
        let _keep_open = tx;
        while rx.next().await.is_some() {}
    });
    (client, seen)
}

fn asked(seen: &Arc<Mutex<Option<Value>>>) -> Value {
    seen.lock().unwrap().clone().expect("the peer saw an initialize")
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_v1_only_peer_answers_one_and_lands_on_the_v1_stack() {
    let (client, seen) = scripted_peer(vec![answer(v1_answer())], true);
    let (negotiated, _channel) = probe(client, Duration::from_secs(5)).await.unwrap();
    assert!(matches!(negotiated.protocol, Protocol::V1));
    assert_eq!(negotiated.agent_name(), "stub-v1");
    assert_eq!(negotiated.describe(), "stub-v1 acp");
    // The v1 stack adopts this instead of re-initializing.
    let init = negotiated.v1().unwrap();
    assert!(init.agent_capabilities.load_session);
    assert!(negotiated.v2().is_err(), "a v1 answer is not a v2 answer");

    // The union asks for 2 — that is what makes a v2-capable peer answer 2
    // instead of settling for 1 — while carrying v1's half under the keys
    // only v1 reads.
    let params = asked(&seen);
    assert_eq!(params["protocolVersion"].as_u64(), Some(2));
    assert!(params["info"]["name"].is_string(), "v2 requires info");
    assert!(params["clientInfo"]["name"].is_string(), "v1 reads clientInfo");
    let caps = &params["clientCapabilities"];
    assert_eq!(caps["fs"]["readTextFile"].as_bool(), Some(true));
    assert_eq!(caps["fs"]["writeTextFile"].as_bool(), Some(true));
    // Load-bearing the other way round from crow-cli: crow HAS a terminal
    // broker (acp_term.rs), so it advertises one. crow-cli declines it to make
    // the agent fall through to its own MCP supply.
    assert_eq!(caps["terminal"].as_bool(), Some(true));
    // v2 has no fs and no terminal capability, so its half must not grow one.
    assert!(params["capabilities"].get("fs").is_none());
    assert!(params["capabilities"].get("terminal").is_none());
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_v2_peer_answers_two_and_lands_on_the_v2_stack() {
    let (client, _seen) = scripted_peer(vec![answer(v2_answer())], true);
    let (negotiated, _channel) = probe(client, Duration::from_secs(5)).await.unwrap();
    assert!(matches!(negotiated.protocol, Protocol::V2));
    assert_eq!(negotiated.describe(), "stub-v2 acp2");
    let init = negotiated.v2().unwrap();
    assert!(init.capabilities.session.is_some());
    assert!(negotiated.v1().is_err(), "a v2 answer is not a v1 answer");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_banner_printed_before_the_answer_reaches_the_adopter() {
    // Non-JSON noise ahead of the stream is a real agent behaviour (a Python
    // warning, a uv progress line). It is `Malformed` on purpose and is
    // retained for relays, so it must survive the probe unchanged.
    let banner = TransportFrame::Malformed {
        raw: "warning: something went to stdout\n".into(),
        error: agent_client_protocol::Error::new(-32700, "parse error"),
    };
    let (client, _seen) = scripted_peer(vec![banner, answer(v2_answer())], true);
    let (negotiated, mut channel) = probe(client, Duration::from_secs(5)).await.unwrap();
    assert!(matches!(negotiated.protocol, Protocol::V2));
    let replayed = channel.rx.next().await.expect("the banner is replayed");
    assert!(
        matches!(&replayed, TransportFrame::Malformed { raw, .. } if raw.starts_with("warning:")),
        "the banner must reach the adopter verbatim, got {replayed:?}"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_request_the_peer_opened_with_is_not_eaten_by_the_probe() {
    // An agent that asks the client something before it answers initialize
    // (a fs/read_text_file during startup, say) must still get its answer:
    // the probe drains frames looking for one id and has to hand the rest back.
    let request = TransportFrame::Single(
        RawJsonRpcMessage::request(
            "fs/read_text_file".into(),
            json!({ "path": "/tmp/x" }),
            RequestId::Number(7),
        )
        .unwrap(),
    );
    let (client, _seen) = scripted_peer(vec![request, answer(v1_answer())], true);
    let (negotiated, mut channel) = probe(client, Duration::from_secs(5)).await.unwrap();
    assert!(matches!(negotiated.protocol, Protocol::V1));
    let replayed = channel.rx.next().await.expect("the peer's request is replayed");
    let TransportFrame::Single(RawJsonRpcMessage::Request(inner)) = replayed else {
        panic!("expected the peer's request, got {replayed:?}");
    };
    assert_eq!(inner.method.as_ref(), "fs/read_text_file");
    assert_eq!(inner.id, RequestId::Number(7));
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn an_answer_batched_with_other_traffic_is_split_not_dropped() {
    let batch = TransportBatch::from_entries(vec![
        TransportBatchEntry::message(
            RawJsonRpcMessage::notification(
                "session/update".into(),
                json!({ "sessionId": "s", "update": { "sessionUpdate": "agent_message_chunk" } }),
            )
            .unwrap(),
        ),
        TransportBatchEntry::message(RawJsonRpcMessage::response(
            RequestId::Number(0),
            Ok(v2_answer()),
        )),
    ])
    .map(TransportFrame::Batch)
    .expect("a batch of two is a batch");
    let (client, _seen) = scripted_peer(vec![batch], true);
    let (negotiated, mut channel) = probe(client, Duration::from_secs(5)).await.unwrap();
    assert!(matches!(negotiated.protocol, Protocol::V2));
    let leftover = channel.rx.next().await.expect("the rest of the batch is replayed");
    let TransportFrame::Batch(rest) = leftover else {
        panic!("expected the leftover batch, got {leftover:?}");
    };
    assert_eq!(rest.len(), 1, "only the answer was consumed");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_refusal_carries_the_agents_own_words() {
    // This is the exact failure that started the negotiation work: a v2 agent
    // handed a v1-shaped initialize answers -32602 for the missing `info`. An
    // error the client invents would hide it.
    let (client, _seen) = scripted_peer(
        vec![refusal(
            -32602,
            "Field required: info",
        )],
        true,
    );
    let err = probe(client, Duration::from_secs(5)).await.unwrap_err();
    let message = err.to_string();
    assert!(message.contains("info"), "the agent's message is lost: {message}");
    assert!(message.contains("initialize"), "the failing request is unnamed: {message}");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_version_this_client_does_not_speak_is_refused_by_number() {
    let (client, _seen) = scripted_peer(
        vec![answer(json!({ "protocolVersion": 3, "info": { "name": "from-the-future" } }))],
        true,
    );
    let err = probe(client, Duration::from_secs(5)).await.unwrap_err();
    let message = err.to_string();
    assert!(message.contains('3'), "the offered version is not named: {message}");
    assert!(message.contains("1 and 2"), "what crow speaks is not stated: {message}");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn an_answer_without_a_version_is_refused() {
    let (client, _seen) =
        scripted_peer(vec![answer(json!({ "info": { "name": "no-version" } }))], true);
    let err = probe(client, Duration::from_secs(5)).await.unwrap_err();
    assert!(
        err.to_string().contains("protocolVersion"),
        "the missing field is not named: {err}"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_peer_that_hangs_up_is_an_error_not_a_hang() {
    // `hold: false` drops the agent's sender after replying with nothing.
    let (client, _seen) = scripted_peer(vec![], false);
    let err = probe(client, Duration::from_secs(5)).await.unwrap_err();
    assert!(
        err.to_string().contains("closed the connection"),
        "a dead peer must say so: {err}"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_silent_peer_times_out_instead_of_hanging() {
    // A spawn budget, not a round-trip budget: `uv run` cold-starting an agent
    // takes longer than a network hop, so the deadline has to be generous and
    // still finite.
    let (client, _seen) = scripted_peer(vec![], true);
    let err = probe(client, Duration::from_millis(50)).await.unwrap_err();
    assert!(
        err.to_string().contains("deadline"),
        "a silent peer must say so: {err}"
    );
}

#[test]
fn the_probe_reuses_id_zero_and_the_stack_may_reuse_it_too() {
    // JSON-RPC only asks that ids be unique among OUTSTANDING requests. The
    // probe's id is settled before the adopted stack sends anything, so the
    // stack starting its own counter at zero is legal — and is what crow-cli's
    // client does. Pinning it here keeps a future "fix" from turning one
    // harmless repeat into a mismatched-response bug.
    let frame = RawJsonRpcMessage::request(
        "initialize".into(),
        super::union_initialize_params(),
        super::PROBE_ID,
    )
    .unwrap();
    let value = serde_json::to_value(frame).unwrap();
    assert_eq!(value["id"].as_i64(), Some(0));
    assert_eq!(value["method"].as_str(), Some("initialize"));
    // The response id must match, or the probe would never recognize its own
    // answer and would wait out the deadline against a healthy agent.
    let reply = RawJsonRpcMessage::response(RequestId::Number(0), Ok(v2_answer()));
    assert_eq!(reply.response_id(), Some(&RequestId::Number(0)));
    let RpcResponse::Result { id, .. } = reply_as_response(&reply) else {
        panic!("a response is a response");
    };
    assert_eq!(id, &RequestId::Number(0));
}

fn reply_as_response(frame: &RawJsonRpcMessage) -> &RpcResponse<Value> {
    match frame {
        RawJsonRpcMessage::Response(response) => response,
        _ => panic!("not a response"),
    }
}
