//! Wire types for the crow-memory HTTP API.
//!
//! The contract between the crow-memory server (axum + LanceDB) and
//! crow-memory-sdk (reqwest client). Append-only chat history: create +
//! read/search, no update, no delete.

use serde::{Deserialize, Serialize};

/// Default crow-memory HTTP port: 27697 = CROWS on a phone keypad.
/// Below the Linux ephemeral range (32768+), unregistered in IANA.
pub const DEFAULT_MEMORY_PORT: u16 = 27697;

// ---- Records (read side) ---------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptRecord {
    pub id: String,
    pub name: String,
    pub template: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MessageRecord {
    pub id: i64,
    pub agent_id: String,
    pub created_at: String,
    pub data: serde_json::Value,
    pub role: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionInfo {
    pub session_id: String,
    pub last_activity: String,
    pub message_count: usize,
    pub agent_count: usize,
    pub last_role: String,
    pub cwd: String,
    pub model_identifier: String,
}

// ---- Requests / responses (write side) -------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LookupPromptRequest {
    pub template: String,
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LookupPromptResponse {
    pub prompt_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AddMessageRequest {
    pub agent_id: String,
    pub message: serde_json::Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub usage: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AddMessageResponse {
    pub id: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchMessagesRequest {
    pub query: String,
    pub limit: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub role: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MaxAgentIdxResponse {
    pub max_idx: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorResponse {
    pub error: String,
}

#[cfg(test)]
mod tests {
    use super::*;

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
        };
        let back: MessageRecord =
            serde_json::from_str(&serde_json::to_string(&rec).unwrap()).unwrap();
        assert_eq!(back.id, 17);
        assert_eq!(back.data["role"], "user");
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
        };
        let back: SessionInfo =
            serde_json::from_str(&serde_json::to_string(&s).unwrap()).unwrap();
        assert_eq!(back.message_count, 5);
    }
}
