//! crow-memory-sdk — reqwest client for the crow-memory HTTP server.
//!
//! Same method surface as the old in-process MemoryStore, minus open/path:
//! `MemoryClient::connect(url)`. Connection failures and 502/503/504 retry
//! with exponential backoff (v1 lesson: a service blip with no backoff
//! killed the whole experiment). 4xx and 500 fail fast — 500s from the
//! store are not retried so non-idempotent writes never double-apply.

use std::time::Duration;

use anyhow::Context;
use crow_memory_types::{
    AddMessageRequest, AddMessageResponse, CreateAgentRequest, ErrorResponse, LookupPromptRequest,
    LookupPromptResponse, MaxAgentIdxResponse, SearchMessagesRequest,
};
use reqwest::Method;
use serde::{de::DeserializeOwned, Serialize};

pub use crow_memory_types::{
    AgentRecord, MessageRecord, PromptRecord, SessionInfo, DEFAULT_MEMORY_PORT,
};

const MAX_RETRIES: u32 = 5;
const BASE_BACKOFF_MS: u64 = 100;
const MAX_BACKOFF_MS: u64 = 2000;

/// Default crow-memory server URL. Honors `CROW_MEMORY_PORT` (set it in
/// `{config_dir}/.env` or container env — docker-compose friendly), else
/// `DEFAULT_MEMORY_PORT` (27697 — CROWS on a phone keypad).
pub fn default_memory_url() -> String {
    let port = std::env::var("CROW_MEMORY_PORT")
        .ok()
        .and_then(|s| s.parse::<u16>().ok())
        .unwrap_or(DEFAULT_MEMORY_PORT);
    format!("http://127.0.0.1:{port}")
}

pub struct MemoryClient {
    http: reqwest::Client,
    base_url: String,
}

impl MemoryClient {
    /// Lazy connect — no I/O until the first call.
    /// `base_url` e.g. `http://127.0.0.1:27697`.
    pub fn connect(base_url: impl Into<String>) -> Self {
        Self {
            http: reqwest::Client::new(),
            base_url: base_url.into().trim_end_matches('/').to_string(),
        }
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub async fn health(&self) -> anyhow::Result<()> {
        let _: serde_json::Value = self.send(Method::GET, "/healthz", &[], None::<&()>).await?;
        Ok(())
    }

    // ---- prompts ----

    pub async fn lookup_or_create_prompt(
        &self,
        template: &str,
        name: &str,
    ) -> anyhow::Result<String> {
        let r: LookupPromptResponse = self
            .send(
                Method::POST,
                "/v1/prompts/lookup",
                &[],
                Some(&LookupPromptRequest {
                    template: template.to_string(),
                    name: name.to_string(),
                }),
            )
            .await?;
        Ok(r.prompt_id)
    }

    pub async fn get_prompt(&self, prompt_id: &str) -> anyhow::Result<Option<PromptRecord>> {
        self.send_opt(Method::GET, &format!("/v1/prompts/{prompt_id}"), &[])
            .await
    }

    // ---- agents ----

    #[allow(clippy::too_many_arguments)]
    pub async fn create_agent(
        &self,
        agent_id: &str,
        session_id: &str,
        agent_idx: i64,
        cwd: &str,
        prompt_id: &str,
        prompt_args: &serde_json::Value,
        system_prompt: &str,
        tool_definitions: &serde_json::Value,
        request_params: &serde_json::Value,
        model_identifier: &str,
    ) -> anyhow::Result<()> {
        let resp = self
            .send_raw(
                Method::POST,
                "/v1/agents",
                &[],
                Some(&CreateAgentRequest {
                    agent_id: agent_id.to_string(),
                    session_id: session_id.to_string(),
                    agent_idx,
                    cwd: cwd.to_string(),
                    prompt_id: prompt_id.to_string(),
                    prompt_args: prompt_args.clone(),
                    system_prompt: system_prompt.to_string(),
                    tool_definitions: tool_definitions.clone(),
                    request_params: request_params.clone(),
                    model_identifier: model_identifier.to_string(),
                }),
            )
            .await?;
        check_success(resp).await.map(|_| ())
    }

    pub async fn get_agent(&self, agent_id: &str) -> anyhow::Result<Option<AgentRecord>> {
        self.send_opt(Method::GET, &format!("/v1/agents/{agent_id}"), &[])
            .await
    }

    pub async fn list_agents(
        &self,
        session_id: Option<&str>,
    ) -> anyhow::Result<Vec<AgentRecord>> {
        let mut query: Vec<(&str, String)> = Vec::new();
        if let Some(s) = session_id {
            query.push(("session_id", s.to_string()));
        }
        self.send(Method::GET, "/v1/agents", &query, None::<&()>).await
    }

    pub async fn get_max_agent_idx(&self, session_id: &str) -> anyhow::Result<i64> {
        let r: MaxAgentIdxResponse = self
            .send(
                Method::GET,
                "/v1/max-agent-idx",
                &[("session_id", session_id.to_string())],
                None::<&()>,
            )
            .await?;
        Ok(r.max_idx)
    }

    // ---- messages ----

    pub async fn add_message(
        &self,
        agent_id: &str,
        message: &serde_json::Value,
        usage: Option<&serde_json::Value>,
    ) -> anyhow::Result<i64> {
        let r: AddMessageResponse = self
            .send(
                Method::POST,
                "/v1/messages",
                &[],
                Some(&AddMessageRequest {
                    agent_id: agent_id.to_string(),
                    message: message.clone(),
                    usage: usage.cloned(),
                }),
            )
            .await?;
        Ok(r.id)
    }

    pub async fn load_messages(
        &self,
        agent_id: &str,
    ) -> anyhow::Result<Vec<serde_json::Value>> {
        self.send(
            Method::GET,
            &format!("/v1/agents/{agent_id}/messages"),
            &[],
            None::<&()>,
        )
        .await
    }

    pub async fn query_messages_by_agent(
        &self,
        agent_id: &str,
        order_asc: bool,
        limit: usize,
        role: Option<&str>,
    ) -> anyhow::Result<Vec<MessageRecord>> {
        let mut query: Vec<(&str, String)> = vec![
            ("order_asc", order_asc.to_string()),
            ("limit", limit.to_string()),
        ];
        if let Some(r) = role {
            query.push(("role", r.to_string()));
        }
        self.send(
            Method::GET,
            &format!("/v1/agents/{agent_id}/messages/query"),
            &query,
            None::<&()>,
        )
        .await
    }

    pub async fn search_messages(
        &self,
        query: &str,
        limit: usize,
        role: Option<&str>,
    ) -> anyhow::Result<Vec<MessageRecord>> {
        self.send(
            Method::POST,
            "/v1/messages/search",
            &[],
            Some(&SearchMessagesRequest {
                query: query.to_string(),
                limit,
                role: role.map(str::to_string),
            }),
        )
        .await
    }

    // ---- sessions ----

    pub async fn list_sessions(
        &self,
        limit: usize,
        offset: usize,
    ) -> anyhow::Result<Vec<SessionInfo>> {
        self.send(
            Method::GET,
            "/v1/sessions",
            &[
                ("limit", limit.to_string()),
                ("offset", offset.to_string()),
            ],
            None::<&()>,
        )
        .await
    }

    pub async fn get_sessions_by_cwd(&self, cwd: &str) -> anyhow::Result<Vec<SessionInfo>> {
        self.send(
            Method::GET,
            "/v1/sessions/by-cwd",
            &[("cwd", cwd.to_string())],
            None::<&()>,
        )
        .await
    }

    // ---- plumbing ----

    async fn send<B: Serialize, R: DeserializeOwned>(
        &self,
        method: Method,
        path: &str,
        query: &[(&str, String)],
        body: Option<&B>,
    ) -> anyhow::Result<R> {
        let resp = self.send_raw(method, path, query, body).await?;
        parse_body(resp).await
    }

    /// GET that maps 404 → None.
    async fn send_opt<R: DeserializeOwned>(
        &self,
        method: Method,
        path: &str,
        query: &[(&str, String)],
    ) -> anyhow::Result<Option<R>> {
        let resp = self
            .send_raw::<()>(method, path, query, None)
            .await?;
        if resp.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }
        Ok(Some(parse_body(resp).await?))
    }

    /// Request with retry: connect errors + 502/503/504 back off
    /// exponentially; everything else returns immediately.
    async fn send_raw<B: Serialize>(
        &self,
        method: Method,
        path: &str,
        query: &[(&str, String)],
        body: Option<&B>,
    ) -> anyhow::Result<reqwest::Response> {
        let url = format!("{}{}", self.base_url, path);
        let mut attempt: u32 = 0;
        loop {
            let mut req = self.http.request(method.clone(), &url);
            if !query.is_empty() {
                req = req.query(query);
            }
            if let Some(b) = body {
                req = req.json(b);
            }
            let retryable = match req.send().await {
                Ok(resp) => {
                    let st = resp.status();
                    if matches!(
                        st,
                        reqwest::StatusCode::BAD_GATEWAY
                            | reqwest::StatusCode::SERVICE_UNAVAILABLE
                            | reqwest::StatusCode::GATEWAY_TIMEOUT
                    ) {
                        Some(format!("HTTP {st}"))
                    } else {
                        return Ok(resp);
                    }
                }
                Err(e) if e.is_connect() => Some(format!("{e}")),
                Err(e) => {
                    return Err(anyhow::Error::new(e))
                        .context(format!("memory server request failed: {url}"))
                }
            };
            if attempt >= MAX_RETRIES {
                anyhow::bail!(
                    "memory server unreachable after {} retries: {} ({url})",
                    MAX_RETRIES,
                    retryable.unwrap_or_default()
                );
            }
            attempt += 1;
            let backoff = (BASE_BACKOFF_MS.saturating_mul(1 << attempt)).min(MAX_BACKOFF_MS);
            tracing::warn!(
                "memory server unavailable ({}); retry {attempt}/{MAX_RETRIES} in {backoff}ms",
                retryable.unwrap_or_default()
            );
            tokio::time::sleep(Duration::from_millis(backoff)).await;
        }
    }
}

async fn check_success(resp: reqwest::Response) -> anyhow::Result<reqwest::Response> {
    let st = resp.status();
    if st.is_success() {
        return Ok(resp);
    }
    let body = resp.text().await.unwrap_or_default();
    let msg = serde_json::from_str::<ErrorResponse>(&body)
        .map(|e| e.error)
        .unwrap_or(body);
    anyhow::bail!("memory server error {st}: {msg}")
}

async fn parse_body<R: DeserializeOwned>(resp: reqwest::Response) -> anyhow::Result<R> {
    let resp = check_success(resp).await?;
    Ok(resp.json().await?)
}
