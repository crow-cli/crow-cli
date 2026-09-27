//! Protocol negotiation: one `initialize` that both stacks can answer.
//!
//! The peer tells you what it speaks. Config is a cache of that answer at best
//! and a lie at worst, so crow asks instead of declaring: a single UNION
//! `initialize` goes out — v2's `protocolVersion: 2`, `info` and `capabilities`
//! alongside v1's `clientInfo` and `clientCapabilities` — and the version in the
//! response picks the stack. Neither schema denies unknown fields and each
//! version reads only its own keys, so the same bytes work in both directions.
//!
//! The probe IS the connection. It runs on the live [`Channel`] the winning
//! stack then adopts, which is why this is hand-rolled rather than delegated to
//! [`Client::protocol_connector`]: the connector starts the v2 implementation
//! and, on a v1 answer, drops the connection and calls the agent factory again.
//! That costs a second spawned process for every v1 agent, and it cannot work at
//! all for an attach endpoint, where the "factory" is a dup'd fd or a socket the
//! peer already accepted and the peer has already eaten one `initialize`.
//!
//! [`Client::protocol_connector`]: agent_client_protocol::Client::protocol_connector

use std::collections::VecDeque;
use std::time::Duration;

use futures::channel::mpsc::{UnboundedReceiver, UnboundedSender};
use futures::StreamExt;
use serde_json::Value;

use agent_client_protocol::schema::v1::{
    InitializeResponse as V1InitializeResponse, RequestId, Response as RpcResponse,
};
use agent_client_protocol::schema::v2::{self, InitializeResponse as V2InitializeResponse};
use agent_client_protocol::schema::ProtocolVersion;
use agent_client_protocol::{
    Channel, Error as AcpError, RawJsonRpcMessage, TransportBatch, TransportBatchEntry,
    TransportFrame,
};

/// The probe's request id. The adopted stack starts its own counter at zero, so
/// the peer sees this id twice in a row; JSON-RPC only asks that ids be unique
/// among *outstanding* requests, and crow-cli's client does exactly this.
const PROBE_ID: RequestId = RequestId::Number(0);

/// Which protocol the peer chose.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Protocol {
    V1,
    V2,
}

impl Protocol {
    /// The harness-badge tag for the negotiated stack.
    pub(crate) fn tag(self) -> &'static str {
        match self {
            Protocol::V1 => "acp",
            Protocol::V2 => "acp2",
        }
    }

    /// The key the agent's identity travels under in that version's response.
    fn info_key(self) -> &'static str {
        match self {
            Protocol::V1 => "agentInfo",
            Protocol::V2 => "info",
        }
    }
}

/// What the peer said it speaks, plus the raw `initialize` result.
#[derive(Debug)]
pub(crate) struct Negotiated {
    pub(crate) protocol: Protocol,
    /// v1 and v2 responses are different shapes — `agentInfo`/`agentCapabilities`
    /// against `info`/`capabilities` — so each stack deserializes its own.
    pub(crate) init: Value,
}

impl Negotiated {
    /// The agent's display name, from whichever shape carried it.
    pub(crate) fn agent_name(&self) -> String {
        self.init
            .get(self.protocol.info_key())
            .and_then(|info| info.get("name"))
            .and_then(Value::as_str)
            .map(str::to_owned)
            .unwrap_or_else(|| "acp".into())
    }

    /// A stable label for the negotiated connection: name plus badge tag.
    pub(crate) fn describe(&self) -> String {
        format!("{} {}", self.agent_name(), self.protocol.tag())
    }

    /// The `initialize` result as the v1 stack reads it.
    pub(crate) fn v1(&self) -> Result<V1InitializeResponse, AcpError> {
        self.expect(Protocol::V1)?;
        serde_json::from_value(self.init.clone()).map_err(|error| {
            AcpError::new(
                -32602,
                format!("agent initialize response is not v1: {error}"),
            )
        })
    }

    /// The `initialize` result as the v2 stack reads it.
    pub(crate) fn v2(&self) -> Result<V2InitializeResponse, AcpError> {
        self.expect(Protocol::V2)?;
        serde_json::from_value(self.init.clone()).map_err(|error| {
            AcpError::new(
                -32602,
                format!("agent initialize response is not v2: {error}"),
            )
        })
    }

    /// Refuse to read an answer as the version it was not given in.
    ///
    /// The shape alone cannot catch this: every field of v1's
    /// `InitializeResponse` defaults, so a v2 answer deserializes cleanly as a
    /// v1 one and the wrong stack gets a plausible empty response instead of an
    /// error. That is the silent half of the failure negotiation exists to
    /// prevent, so it is checked at the only place the two shapes meet.
    fn expect(&self, protocol: Protocol) -> Result<(), AcpError> {
        if self.protocol == protocol {
            return Ok(());
        }
        Err(AcpError::new(
            -32602,
            format!(
                "agent negotiated {} but was read as {}",
                self.protocol.tag(),
                protocol.tag()
            ),
        ))
    }
}

/// Frames the probe drained that were not its response. The adopter must replay
/// them ahead of the live stream, or the peer's own requests go unanswered.
pub(crate) type Buffered = VecDeque<TransportFrame>;

/// The v2 `initialize` crow sends.
///
/// v2's `ClientCapabilities` has no `fs` and no `terminal` — those client-side
/// services do not exist in v2 — so there is nothing to decline the way v1
/// declines them, and capabilities are advertised by presence alone.
///
/// Only `auth` is claimed, and only its login/logout half: `auth.terminal` is
/// left out because a v2 client has no terminal to run one in, and elicitation
/// is left out because the v2 stack has no handler for it. Advertising a
/// capability nobody services is how an agent ends up waiting on a request that
/// will never be answered. The v1 half of the union below still advertises
/// both, under the `clientCapabilities` key only v1 reads.
pub(crate) fn v2_initialize_request() -> v2::InitializeRequest {
    v2::InitializeRequest::new(
        ProtocolVersion::V2,
        v2::Implementation::new(env!("CARGO_PKG_NAME"), env!("CARGO_PKG_VERSION")),
    )
    .capabilities(v2::ClientCapabilities::new().auth(v2::AuthCapabilities::new()))
}

/// The union `initialize` params: v2's half verbatim, plus v1's identity and
/// capabilities under the keys only v1 reads.
///
/// `protocolVersion` stays 2. Asking for 2 is what makes a v2-capable peer
/// answer 2 instead of settling for 1; a v1-only peer answers the highest
/// version it has, which is the whole negotiation.
pub(crate) fn union_initialize_params() -> Value {
    let mut params = match serde_json::to_value(v2_initialize_request()) {
        Ok(Value::Object(map)) => map,
        _ => serde_json::Map::new(),
    };
    if let Ok(Value::Object(v1)) = serde_json::to_value(super::initialize_request()) {
        for (key, value) in v1 {
            if key != "protocolVersion" {
                params.entry(key).or_insert(value);
            }
        }
    }
    Value::Object(params)
}

/// Ask the peer which protocol it speaks, on the connection it will keep using.
///
/// Returns the negotiated version with the raw `initialize` result, plus any
/// frames that arrived before the answer. `deadline` bounds the wait: a spawn
/// endpoint's budget has to cover a cold `uv run`, which is minutes, not the
/// seconds a network round trip needs.
pub(crate) async fn negotiate(
    rx: &mut UnboundedReceiver<TransportFrame>,
    tx: &UnboundedSender<TransportFrame>,
    deadline: Duration,
) -> Result<(Negotiated, Buffered), AcpError> {
    let request =
        RawJsonRpcMessage::request("initialize".into(), union_initialize_params(), PROBE_ID)?;
    tx.unbounded_send(TransportFrame::Single(request))
        .map_err(|_| AcpError::new(-32000, "agent connection closed before initialize"))?;

    let mut buffered = Buffered::new();
    loop {
        let frame = tokio::time::timeout(deadline, rx.next())
            .await
            .map_err(|_| {
                AcpError::new(-32001, "agent did not answer initialize before the deadline")
            })?
            .ok_or_else(|| {
                AcpError::new(-32000, "agent closed the connection before answering initialize")
            })?;
        match scan(frame) {
            Scan::Answer(answer, leftover) => {
                buffered.extend(leftover);
                return answer.and_then(|init| {
                    let negotiated = classify(init)?;
                    Ok((negotiated, buffered))
                });
            }
            Scan::Other(frame) => buffered.push_back(frame),
        }
    }
}

/// Probe a live channel and hand it back ready for the winning stack.
///
/// This is `crow-cli run`'s `_dispatch` in Rust: one spawn, one `initialize`,
/// and the handshaked connection goes to whichever client the answer selects
/// instead of being spawned a second time by it.
pub(crate) async fn probe(
    channel: Channel,
    deadline: Duration,
) -> Result<(Negotiated, Channel), AcpError> {
    let Channel { mut rx, tx } = channel;
    let (negotiated, buffered) = negotiate(&mut rx, &tx, deadline).await?;
    Ok((negotiated, adopt(rx, tx, buffered)))
}

/// Hand the probed connection to the stack that won it.
///
/// A peer that sent nothing but the initialize answer — the common case — gets
/// its original channel back untouched, so the streaming path pays no extra hop.
/// A peer that batched the answer, printed a non-JSON banner, or opened with a
/// request of its own gets a relay that replays what the probe drained first.
pub(crate) fn adopt(
    rx: UnboundedReceiver<TransportFrame>,
    tx: UnboundedSender<TransportFrame>,
    mut buffered: Buffered,
) -> Channel {
    if buffered.is_empty() {
        return Channel { rx, tx };
    }
    let (client_side, relay_side) = Channel::duplex();
    let Channel {
        rx: from_client,
        tx: to_client,
    } = relay_side;
    tokio::spawn(async move {
        let mut rx = rx;
        while let Some(frame) = buffered.pop_front() {
            if to_client.unbounded_send(frame).is_err() {
                return;
            }
        }
        while let Some(frame) = rx.next().await {
            if to_client.unbounded_send(frame).is_err() {
                return;
            }
        }
    });
    tokio::spawn(async move {
        let mut from_client = from_client;
        while let Some(frame) = from_client.next().await {
            if tx.unbounded_send(frame).is_err() {
                return;
            }
        }
    });
    client_side
}

/// One frame's contribution to the probe: the answer, or "not mine, keep it".
enum Scan {
    Answer(Result<Value, AcpError>, Option<TransportFrame>),
    Other(TransportFrame),
}

fn scan(frame: TransportFrame) -> Scan {
    match frame {
        TransportFrame::Single(message) => match answer_of(&message) {
            Some(answer) => Scan::Answer(answer, None),
            None => Scan::Other(TransportFrame::Single(message)),
        },
        // Malformed wire input is retained for relays: a banner printed ahead of
        // the JSON-RPC stream must reach the adopter unchanged.
        TransportFrame::Malformed { .. } => Scan::Other(frame),
        TransportFrame::Batch(batch) => {
            let mut rest = Vec::with_capacity(batch.len());
            let mut found = None;
            for entry in batch.into_entries() {
                let hit = match &entry {
                    TransportBatchEntry::Message(message) if found.is_none() => answer_of(message),
                    _ => None,
                };
                match hit {
                    Some(answer) => found = Some(answer),
                    None => rest.push(entry),
                }
            }
            let leftover = TransportBatch::from_entries(rest).map(TransportFrame::Batch);
            match found {
                Some(answer) => Scan::Answer(answer, leftover),
                // Nothing was consumed, so the rebuild is the original batch, and
                // a batch is structurally non-empty.
                None => Scan::Other(leftover.expect("a batch carries at least one entry")),
            }
        }
    }
}

fn answer_of(message: &RawJsonRpcMessage) -> Option<Result<Value, AcpError>> {
    let RawJsonRpcMessage::Response(response) = message else {
        return None;
    };
    match response {
        RpcResponse::Result { id, result } if *id == PROBE_ID => Some(Ok(result.clone())),
        RpcResponse::Error { id, error } if *id == PROBE_ID => Some(Err(AcpError::new(
            i32::from(error.code.clone()),
            format!("initialize: {}", error.message),
        ))),
        _ => None,
    }
}

fn classify(init: Value) -> Result<Negotiated, AcpError> {
    match init.get("protocolVersion").and_then(Value::as_u64) {
        Some(1) => Ok(Negotiated {
            protocol: Protocol::V1,
            init,
        }),
        Some(2) => Ok(Negotiated {
            protocol: Protocol::V2,
            init,
        }),
        Some(other) => Err(AcpError::new(
            -32602,
            format!("agent negotiated protocolVersion {other}; crow speaks 1 and 2"),
        )),
        None => Err(AcpError::new(
            -32602,
            "agent answered initialize without a protocolVersion",
        )),
    }
}

#[cfg(test)]
#[path = "../../tests/unit/acp__negotiate_tests.rs"]
mod tests;
