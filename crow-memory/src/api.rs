//! HTTP API surface for the memory server. Every route takes
//! `State(Arc<MemoryStore>)`; wire types come from crow-memory-types.
//! Append-only: create + read/search, no update, no delete.

use std::sync::Arc;

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use crow_memory_types::{
    AddMessageRequest, AddMessageResponse, AgentRecord, CreateAgentRequest, ErrorResponse,
    LookupPromptRequest, LookupPromptResponse, MaxAgentIdxResponse, MessageRecord, PromptRecord,
    SearchMessagesRequest, SessionInfo,
};

use crate::store::MemoryStore;

pub struct ApiError(StatusCode, String);

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.0, Json(ErrorResponse { error: self.1 })).into_response()
    }
}

impl From<anyhow::Error> for ApiError {
    fn from(e: anyhow::Error) -> Self {
        ApiError(StatusCode::INTERNAL_SERVER_ERROR, format!("{e:#}"))
    }
}

fn not_found(what: &str) -> ApiError {
    ApiError(StatusCode::NOT_FOUND, format!("{what} not found"))
}

pub fn router(store: Arc<MemoryStore>) -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/v1/prompts/lookup", post(lookup_prompt))
        .route("/v1/prompts/{id}", get(get_prompt))
        .route("/v1/agents", post(create_agent).get(list_agents))
        .route("/v1/agents/{agent_id}", get(get_agent))
        .route("/v1/agents/{agent_id}/messages", get(load_messages))
        .route(
            "/v1/agents/{agent_id}/messages/query",
            get(query_messages),
        )
        .route("/v1/max-agent-idx", get(max_agent_idx))
        .route("/v1/messages", post(add_message))
        .route("/v1/messages/search", post(search_messages))
        .route("/v1/sessions", get(list_sessions))
        .route("/v1/sessions/by-cwd", get(sessions_by_cwd))
        .with_state(store)
}

async fn healthz() -> Json<serde_json::Value> {
    Json(serde_json::json!({ "ok": true }))
}

// ---- prompts ----

async fn lookup_prompt(
    State(s): State<Arc<MemoryStore>>,
    Json(req): Json<LookupPromptRequest>,
) -> Result<Json<LookupPromptResponse>, ApiError> {
    let prompt_id = s.lookup_or_create_prompt(&req.template, &req.name).await?;
    Ok(Json(LookupPromptResponse { prompt_id }))
}

async fn get_prompt(
    State(s): State<Arc<MemoryStore>>,
    Path(id): Path<String>,
) -> Result<Json<PromptRecord>, ApiError> {
    s.get_prompt(&id).await?.map(Json).ok_or_else(|| not_found("prompt"))
}

// ---- agents ----

async fn create_agent(
    State(s): State<Arc<MemoryStore>>,
    Json(req): Json<CreateAgentRequest>,
) -> Result<StatusCode, ApiError> {
    s.create_agent(
        &req.agent_id,
        &req.session_id,
        req.agent_idx,
        &req.cwd,
        &req.prompt_id,
        &req.prompt_args,
        &req.system_prompt,
        &req.tool_definitions,
        &req.request_params,
        &req.model_identifier,
    )
    .await?;
    Ok(StatusCode::CREATED)
}

async fn get_agent(
    State(s): State<Arc<MemoryStore>>,
    Path(agent_id): Path<String>,
) -> Result<Json<AgentRecord>, ApiError> {
    s.get_agent(&agent_id)
        .await?
        .map(Json)
        .ok_or_else(|| not_found("agent"))
}

#[derive(serde::Deserialize)]
struct ListAgentsQuery {
    session_id: Option<String>,
}

async fn list_agents(
    State(s): State<Arc<MemoryStore>>,
    Query(q): Query<ListAgentsQuery>,
) -> Result<Json<Vec<AgentRecord>>, ApiError> {
    Ok(Json(s.list_agents(q.session_id.as_deref()).await?))
}

#[derive(serde::Deserialize)]
struct MaxIdxQuery {
    session_id: String,
}

async fn max_agent_idx(
    State(s): State<Arc<MemoryStore>>,
    Query(q): Query<MaxIdxQuery>,
) -> Result<Json<MaxAgentIdxResponse>, ApiError> {
    Ok(Json(MaxAgentIdxResponse {
        max_idx: s.get_max_agent_idx(&q.session_id).await?,
    }))
}

// ---- messages ----

async fn add_message(
    State(s): State<Arc<MemoryStore>>,
    Json(req): Json<AddMessageRequest>,
) -> Result<Json<AddMessageResponse>, ApiError> {
    let id = s
        .add_message(&req.agent_id, &req.message, req.usage.as_ref())
        .await?;
    Ok(Json(AddMessageResponse { id }))
}

async fn load_messages(
    State(s): State<Arc<MemoryStore>>,
    Path(agent_id): Path<String>,
) -> Result<Json<Vec<serde_json::Value>>, ApiError> {
    Ok(Json(s.load_messages(&agent_id).await?))
}

#[derive(serde::Deserialize)]
struct QueryMessagesQuery {
    #[serde(default)]
    order_asc: bool,
    #[serde(default = "default_query_limit")]
    limit: usize,
    role: Option<String>,
}

fn default_query_limit() -> usize {
    20
}

async fn query_messages(
    State(s): State<Arc<MemoryStore>>,
    Path(agent_id): Path<String>,
    Query(q): Query<QueryMessagesQuery>,
) -> Result<Json<Vec<MessageRecord>>, ApiError> {
    Ok(Json(
        s.query_messages_by_agent(&agent_id, q.order_asc, q.limit, q.role.as_deref())
            .await?,
    ))
}

async fn search_messages(
    State(s): State<Arc<MemoryStore>>,
    Json(req): Json<SearchMessagesRequest>,
) -> Result<Json<Vec<MessageRecord>>, ApiError> {
    Ok(Json(
        s.search_messages(&req.query, req.limit, req.role.as_deref())
            .await?,
    ))
}

// ---- sessions ----

#[derive(serde::Deserialize)]
struct ListSessionsQuery {
    #[serde(default = "default_session_limit")]
    limit: usize,
    #[serde(default)]
    offset: usize,
}

fn default_session_limit() -> usize {
    50
}

async fn list_sessions(
    State(s): State<Arc<MemoryStore>>,
    Query(q): Query<ListSessionsQuery>,
) -> Result<Json<Vec<SessionInfo>>, ApiError> {
    Ok(Json(s.list_sessions(q.limit, q.offset).await?))
}

#[derive(serde::Deserialize)]
struct ByCwdQuery {
    cwd: String,
}

async fn sessions_by_cwd(
    State(s): State<Arc<MemoryStore>>,
    Query(q): Query<ByCwdQuery>,
) -> Result<Json<Vec<SessionInfo>>, ApiError> {
    Ok(Json(s.get_sessions_by_cwd(&q.cwd).await?))
}
