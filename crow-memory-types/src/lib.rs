//! Wire types for the crow-memory HTTP API.
//!
//! The SINGLE SOURCE OF TRUTH for the contract between the crow-memory
//! server (axum + LanceDB) and its clients — the python crow-memory-sdk
//! generates its pydantic models from this crate's JSON Schema
//! (`cargo run -p crow-memory-types --bin gen-schema`, then
//! `scripts/gen_wire_types.sh` in the python sdk). Append-only chat
//! history: create + read/search, no update, no delete.

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

/// Default crow-memory HTTP port: 27697 = CROWS on a phone keypad.
/// Below the Linux ephemeral range (32768+), unregistered in IANA.
pub const DEFAULT_MEMORY_PORT: u16 = 27697;

// ---- Records (read side) ---------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct PromptRecord {
    pub id: String,
    pub name: String,
    pub template: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct AgentRecord {
    pub agent_id: String,
    pub session_id: String,
    pub agent_idx: i64,
    pub cwd: String,
    pub prompt_id: String,
    pub prompt_args: serde_json::Value,
    pub system_prompt: String,
    pub tool_definitions: serde_json::Value,
    pub request_params: serde_json::Value,
    pub model_identifier: String,
    pub status: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct MessageRecord {
    pub id: i64,
    pub agent_id: String,
    pub created_at: String,
    pub data: serde_json::Value,
    pub role: String,
    /// Search relevance (lower = better, LanceDB `_distance`); only set on
    /// semantic search hits.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub score: Option<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct SessionInfo {
    pub session_id: String,
    pub last_activity: String,
    pub message_count: usize,
    pub agent_count: usize,
    pub last_role: String,
    pub cwd: String,
    pub model_identifier: String,
    /// Sorted distinct agent_idx values in this session.
    #[serde(default)]
    pub agent_idxs: Vec<i64>,
    /// The most recent message in the session, if any.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_message: Option<MessageRecord>,
}

// ---- Requests / responses (write side) -------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct LookupPromptRequest {
    pub template: String,
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct LookupPromptResponse {
    pub prompt_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct CreateAgentRequest {
    pub agent_id: String,
    pub session_id: String,
    pub agent_idx: i64,
    pub cwd: String,
    pub prompt_id: String,
    pub prompt_args: serde_json::Value,
    pub system_prompt: String,
    pub tool_definitions: serde_json::Value,
    pub request_params: serde_json::Value,
    pub model_identifier: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct AddMessageRequest {
    pub agent_id: String,
    pub message: serde_json::Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub usage: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct AddMessageResponse {
    pub id: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct SearchMessagesRequest {
    pub query: String,
    pub limit: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub role: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct MaxAgentIdxResponse {
    pub max_idx: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct ErrorResponse {
    pub error: String,
}

// ---- images ----

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct AddImageRequest {
    pub mime: String,
    /// Base64-encoded image bytes (RFC 4648 standard alphabet).
    pub data: String,
    pub w: i64,
    pub h: i64,
}

/// Image as served on the wire. Storage-side bytes live in the server's
/// `StoredImage`; here `data` is always base64.
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct ImageRecord {
    pub image_id: String,
    pub mime: String,
    /// Base64-encoded image bytes (RFC 4648 standard alphabet).
    pub data: String,
    pub w: i64,
    pub h: i64,
    pub created_at: String,
}

/// JSON Schema covering every wire type, `$defs` keyed by type name.
/// Single source of truth for client codegen (python pydantic).
pub fn wire_schema() -> serde_json::Value {
    let mut defs = serde_json::Map::new();

    macro_rules! add {
        ($($t:ty),* $(,)?) => {
            $(
                {
                    let name = std::any::type_name::<$t>()
                        .rsplit("::")
                        .next()
                        .unwrap();
                    let mut value =
                        serde_json::to_value(schemars::schema_for!($t)).unwrap();
                    let obj = value.as_object_mut().unwrap();
                    obj.remove("$schema");
                    let nested = obj.remove("$defs");
                    defs.insert(name.to_string(), value);
                    if let Some(serde_json::Value::Object(n)) = nested {
                        for (k, v) in n {
                            defs.entry(k).or_insert(v);
                        }
                    }
                }
            )*
        };
    }

    add!(
        PromptRecord,
        AgentRecord,
        MessageRecord,
        SessionInfo,
        LookupPromptRequest,
        LookupPromptResponse,
        CreateAgentRequest,
        AddMessageRequest,
        AddMessageResponse,
        SearchMessagesRequest,
        MaxAgentIdxResponse,
        ErrorResponse,
        AddImageRequest,
        ImageRecord,
    );

    serde_json::json!({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "crow-memory wire types",
        "description": "Generated from the crow-memory-types rust crate — do not edit by hand.",
        "$defs": serde_json::Value::Object(defs),
    })
}
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn schema_json_up_to_date() {
        // The committed schema.json is the artifact the python sdk generates
        // pydantic models from. If this fails, run:
        //   cargo run -p crow-memory-types --bin gen-schema crow-memory-types/schema.json
        let committed = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/schema.json"
        ))
        .expect("schema.json missing — run gen-schema");
        let generated =
            serde_json::to_string_pretty(&wire_schema()).unwrap() + "\n";
        assert_eq!(
            committed, generated,
            "schema.json drifted from the rust types — regenerate it"
        );
    }

    #[test]
    fn agent_record_round_trip() {
        let rec = AgentRecord {
            agent_id: "brave-fox-42".into(),
            session_id: "sess-1".into(),
            agent_idx: 3,
            cwd: "/home/u/src".into(),
            prompt_id: "p-1".into(),
            prompt_args: serde_json::json!({"workspace": "/home/u/src"}),
            system_prompt: "you are crow".into(),
            tool_definitions: serde_json::json!([{"name": "terminal"}]),
            request_params: serde_json::json!({"model": "qwen"}),
            model_identifier: "qwen3-max".into(),
            status: "active".into(),
            created_at: "2026-08-05T00:00:00Z".into(),
        };
        let json = serde_json::to_string(&rec).unwrap();
        let back: AgentRecord = serde_json::from_str(&json).unwrap();
        assert_eq!(back.agent_id, rec.agent_id);
        assert_eq!(back.agent_idx, 3);
        assert_eq!(back.prompt_args, rec.prompt_args);
    }

    #[test]
    fn message_record_round_trip() {
        let rec = MessageRecord {
            id: 17,
            agent_id: "a-1".into(),
            created_at: "2026-08-05T00:00:00Z".into(),
            data: serde_json::json!({"role": "user", "content": "hi"}),
            role: "user".into(),
            score: None,
        };
        let json = serde_json::to_string(&rec).unwrap();
        assert!(!json.contains("score"));
        let back: MessageRecord = serde_json::from_str(&json).unwrap();
        assert_eq!(back.id, 17);
        assert_eq!(back.data["role"], "user");
        let scored: MessageRecord =
            serde_json::from_str(r#"{"id":1,"agent_id":"a","created_at":"t","data":{},"role":"user","score":0.42}"#)
                .unwrap();
        assert_eq!(scored.score, Some(0.42));
    }

    #[test]
    fn add_message_usage_optional() {
        let no_usage: AddMessageRequest =
            serde_json::from_str(r#"{"agent_id":"a","message":{"role":"user"}}"#).unwrap();
        assert!(no_usage.usage.is_none());
        let json = serde_json::to_string(&no_usage).unwrap();
        assert!(!json.contains("usage"));
    }

    #[test]
    fn session_info_round_trip() {
        let s = SessionInfo {
            session_id: "s".into(),
            last_activity: "t".into(),
            message_count: 5,
            agent_count: 2,
            last_role: "assistant".into(),
            cwd: "/x".into(),
            model_identifier: "m".into(),
            agent_idxs: vec![0, 1],
            last_message: None,
        };
        let back: SessionInfo =
            serde_json::from_str(&serde_json::to_string(&s).unwrap()).unwrap();
        assert_eq!(back.message_count, 5);
        assert_eq!(back.agent_idxs, vec![0, 1]);
        // Old servers (no new fields) must still deserialize.
        let old: SessionInfo = serde_json::from_str(
            r#"{"session_id":"s","last_activity":"t","message_count":1,"agent_count":1,
                "last_role":"user","cwd":"/x","model_identifier":"m"}"#,
        )
        .unwrap();
        assert!(old.agent_idxs.is_empty());
        assert!(old.last_message.is_none());
    }
}
