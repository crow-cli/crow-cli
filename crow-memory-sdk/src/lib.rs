//! crow-memory-sdk — reqwest client for the crow-memory HTTP server.
//!
//! Same method surface as the old in-process MemoryStore, minus open/path:
//! `MemoryClient::connect(url)`. Requests carry a 30s timeout — a wedge
//! detector, not a latency budget: a server that accepts TCP but never
//! answers must error, not hang the agent. Connection failures, timeouts
//! and 502/503/504 retry with exponential backoff (v1 lesson: a service
//! blip with no backoff killed the whole experiment). 4xx and 500 fail
//! fast — 500s from the store are not retried so non-idempotent writes
//! never double-apply.

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
const DEFAULT_REQUEST_TIMEOUT: Duration = Duration::from_secs(30);

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
        Self::connect_with_timeout(base_url, DEFAULT_REQUEST_TIMEOUT)
    }

    /// Like `connect`, with an explicit per-request timeout.
    pub fn connect_with_timeout(base_url: impl Into<String>, timeout: Duration) -> Self {
        Self {
            http: reqwest::Client::builder()
                .timeout(timeout)
                .build()
                .expect("reqwest client builds"),
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

    // ---- images ----

    pub async fn add_image(
        &self,
        image_id: &str,
        mime: &str,
        data: &[u8],
        w: i64,
        h: i64,
    ) -> anyhow::Result<()> {
        let resp = self
            .send_raw(
                Method::PUT,
                &format!("/v1/images/{image_id}"),
                &[],
                Some(&AddImageRequest {
                    mime: mime.to_string(),
                    data: base64_encode(data),
                    w,
                    h,
                }),
            )
            .await?;
        check_success(resp).await.map(|_| ())
    }

    pub async fn get_image(&self, image_id: &str) -> anyhow::Result<Option<ImageRecord>> {
        let r: ImageResponse = match self
            .send_opt(Method::GET, &format!("/v1/images/{image_id}"), &[])
            .await?
        {
            Some(r) => r,
            None => return Ok(None),
        };
        Ok(Some(ImageRecord {
            image_id: r.image_id,
            mime: r.mime,
            data: base64_decode(&r.data)?,
            w: r.w,
            h: r.h,
            created_at: r.created_at,
        }))
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

    /// Request with retry: connect errors, timeouts + 502/503/504 back off
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
                Err(e) if e.is_connect() || e.is_timeout() => {
                    let kind = if e.is_timeout() { "timeout" } else { "connect error" };
                    Some(format!("{kind}: {e}"))
                }
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

// ---- images wire types ------------------------------------------------------

#[derive(serde::Serialize)]
struct AddImageRequest {
    mime: String,
    /// Base64-encoded image bytes.
    data: String,
    w: i64,
    h: i64,
}

#[derive(serde::Deserialize)]
struct ImageResponse {
    image_id: String,
    mime: String,
    /// Base64-encoded image bytes.
    data: String,
    w: i64,
    h: i64,
    created_at: String,
}

/// One stored image (bytes + metadata).
#[derive(Debug, Clone)]
pub struct ImageRecord {
    pub image_id: String,
    pub mime: String,
    pub data: Vec<u8>,
    pub w: i64,
    pub h: i64,
    pub created_at: String,
}

// ---- base64 (RFC 4648 standard alphabet; no extra dependency) --------------

const B64_ALPHABET: &[u8; 64] =
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

fn base64_encode(data: &[u8]) -> String {
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b = [
            chunk[0],
            chunk.get(1).copied().unwrap_or(0),
            chunk.get(2).copied().unwrap_or(0),
        ];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        out.push(B64_ALPHABET[(n >> 18 & 63) as usize] as char);
        out.push(B64_ALPHABET[(n >> 12 & 63) as usize] as char);
        out.push(if chunk.len() > 1 {
            B64_ALPHABET[(n >> 6 & 63) as usize] as char
        } else {
            '='
        });
        out.push(if chunk.len() > 2 {
            B64_ALPHABET[(n & 63) as usize] as char
        } else {
            '='
        });
    }
    out
}

fn base64_decode(s: &str) -> anyhow::Result<Vec<u8>> {
    let bytes: Vec<u8> = s
        .bytes()
        .filter(|&b| !b.is_ascii_whitespace())
        .collect();
    let end = bytes.iter().position(|&b| b == b'=').unwrap_or(bytes.len());
    let data = &bytes[..end];
    if bytes[end..].iter().any(|&b| b != b'=') {
        anyhow::bail!("base64 padding only allowed at the end");
    }
    let val = |b: u8| -> anyhow::Result<u32> {
        match b {
            b'A'..=b'Z' => Ok((b - b'A') as u32),
            b'a'..=b'z' => Ok((b - b'a' + 26) as u32),
            b'0'..=b'9' => Ok((b - b'0' + 52) as u32),
            b'+' => Ok(62),
            b'/' => Ok(63),
            _ => anyhow::bail!("invalid base64 character: {}", b as char),
        }
    };
    let mut out = Vec::with_capacity(data.len() * 3 / 4);
    for chunk in data.chunks(4) {
        if chunk.len() == 1 {
            anyhow::bail!("invalid base64 length");
        }
        let mut n = 0u32;
        for (i, &b) in chunk.iter().enumerate() {
            n |= val(b)? << (18 - 6 * i);
        }
        out.push((n >> 16) as u8);
        if chunk.len() > 2 {
            out.push((n >> 8) as u8);
        }
        if chunk.len() > 3 {
            out.push(n as u8);
        }
    }
    Ok(out)
}
