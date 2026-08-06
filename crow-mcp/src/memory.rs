//! Memory tools — query-only LanceDB access (list_sessions, query_memory,
//! query_session).

use crate::CrowMcpServer;
use rmcp::{
    ErrorData as McpError, handler::server::wrapper::Parameters, model::*, schemars, tool,
    tool_router,
};

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct ListSessionsParams {
    /// Max sessions to return (default 50, hard cap 200)
    #[serde(default = "default_session_limit")]
    pub limit: usize,
    /// Pagination offset
    #[serde(default)]
    pub offset: usize,
}

fn default_session_limit() -> usize { 50 }

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct QueryMemoryParams {
    /// Search term (required)
    pub query: String,
    /// Max matches (default 20, hard cap 200)
    #[serde(default = "default_query_limit")]
    pub limit: usize,
    /// Only messages with this role: "user", "assistant", "tool" or "system"
    #[serde(default)]
    pub role: Option<String>,
}

fn default_query_limit() -> usize { 20 }

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct QuerySessionParams {
    /// The session ID to read (required)
    pub session_id: String,
    /// Optional search term within the session
    #[serde(default)]
    pub query: Option<String>,
    /// Max messages to return (default 20)
    #[serde(default = "default_query_limit")]
    pub limit: usize,
    /// Only messages with this role: "user", "assistant", "tool" or "system"
    #[serde(default)]
    pub role: Option<String>,
}

const KNOWN_ROLES: &[&str] = &["user", "assistant", "tool", "system"];

fn validate_role(role: Option<&str>) -> Result<(), McpError> {
    match role {
        Some(r) if !KNOWN_ROLES.contains(&r) => Err(McpError::invalid_params(
            format!("unknown role '{r}'; expected one of: {}", KNOWN_ROLES.join(", ")),
            None,
        )),
        _ => Ok(()),
    }
}

#[tool_router(router = memory_router, vis = "pub")]
impl CrowMcpServer {
    /// List agent sessions, most-recently-active first.
    #[tool(description = "List agent sessions ordered by most recent activity. Returns session IDs, timestamps, message counts.")]
    async fn list_sessions(
        &self,
        Parameters(params): Parameters<ListSessionsParams>,
    ) -> Result<CallToolResult, McpError> {
        let limit = params.limit.min(200);
        let sessions = self.memory.list_sessions(limit, params.offset).await
            .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;

        let out: Vec<serde_json::Value> = sessions.iter().map(|s| serde_json::json!({
            "session_id": s.session_id,
            "last_activity": s.last_activity,
            "message_count": s.message_count,
            "agent_count": s.agent_count,
            "cwd": s.cwd,
            "model": s.model_identifier,
        })).collect();

        Ok(CallToolResult::success(vec![ContentBlock::text(
            serde_json::to_string_pretty(&out).unwrap(),
        )]))
    }

    /// Semantic search across all sessions.
    #[tool(description = "Semantic search across all session history. Finds which sessions discussed something. Returns matching messages with session context. Optional role filter narrows to user/assistant/tool/system messages.")]
    async fn query_memory(
        &self,
        Parameters(params): Parameters<QueryMemoryParams>,
    ) -> Result<CallToolResult, McpError> {
        validate_role(params.role.as_deref())?;
        let limit = params.limit.min(200);
        let results = self
            .memory
            .search_messages(&params.query, limit, params.role.as_deref())
            .await
            .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;

        // Build agent_id → session_id map for context
        let agents = self.memory.list_agents(None).await
            .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;
        let agent_to_sess: std::collections::HashMap<&str, &str> = agents
            .iter()
            .map(|a| (a.agent_id.as_str(), a.session_id.as_str()))
            .collect();

        let out: Vec<serde_json::Value> = results.iter().map(|m| {
            let session_id = agent_to_sess.get(m.agent_id.as_str()).copied().unwrap_or("unknown");
            serde_json::json!({
                "session_id": session_id,
                "agent_id": m.agent_id,
                "role": m.role,
                "created_at": m.created_at,
                "data": m.data,
            })
        }).collect();

        Ok(CallToolResult::success(vec![ContentBlock::text(
            serde_json::to_string_pretty(&out).unwrap(),
        )]))
    }

    /// Read or search within a single session.
    #[tool(description = "Read or search a single session's conversation history. Without query: returns recent messages. With query: keyword search within the session. Optional role filter narrows to user/assistant/tool/system messages.")]
    async fn query_session(
        &self,
        Parameters(params): Parameters<QuerySessionParams>,
    ) -> Result<CallToolResult, McpError> {
        validate_role(params.role.as_deref())?;
        // Find all agents in this session
        let agents = self.memory.list_agents(Some(&params.session_id)).await
            .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;

        if agents.is_empty() {
            return Ok(CallToolResult::success(vec![ContentBlock::text(format!(
                "No agents found for session '{}'",
                params.session_id
            ))]));
        }

        // With a role filter, fetch the whole history so truncation happens
        // AFTER filtering (the store scan reads all rows regardless).
        let fetch_limit = if params.role.is_some() { usize::MAX } else { params.limit };
        let mut all_messages: Vec<crow_memory_sdk::MessageRecord> = Vec::new();
        for agent in &agents {
            let msgs = self.memory
                .query_messages_by_agent(&agent.agent_id, true, fetch_limit, params.role.as_deref())
                .await
                .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;
            all_messages.extend(msgs);
        }

        // Sort by id (chronological)
        all_messages.sort_by_key(|m| m.id);

        // If query given, filter by keyword match on data (simple fallback)
        if let Some(q) = &params.query {
            let q_lower = q.to_lowercase();
            all_messages.retain(|m| {
                m.data.to_string().to_lowercase().contains(&q_lower)
            });
        }

        all_messages.truncate(params.limit);

        let out: Vec<serde_json::Value> = all_messages.iter().map(|m| serde_json::json!({
            "id": m.id,
            "agent_id": m.agent_id,
            "role": m.role,
            "created_at": m.created_at,
            "data": m.data,
        })).collect();

        Ok(CallToolResult::success(vec![ContentBlock::text(
            serde_json::to_string_pretty(&out).unwrap(),
        )]))
    }
}
