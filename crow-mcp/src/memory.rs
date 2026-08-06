//! Memory tools — query-only LanceDB access (list_sessions, query_memory,
//! query_session). Full v1 parity: content modes, search types, context
//! windows, markdown tables/transcripts with excerpts, scores and agent tags.

use crate::CrowMcpServer;
use rmcp::{
    ErrorData as McpError, handler::server::wrapper::Parameters, model::*, schemars, tool,
    tool_router,
};
use serde_json::Value;
use std::collections::{BTreeSet, HashMap};

// ---- Content modes / search types ------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, serde::Deserialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ContentMode {
    #[default]
    Conversation,
    WithThinking,
    WithTools,
    Full,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, serde::Deserialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum SearchType {
    #[default]
    Semantic,
    Keyword,
    Both,
}

/// Role filter per content mode (None = no filter).
fn mode_roles(mode: ContentMode) -> Option<&'static [&'static str]> {
    match mode {
        ContentMode::Conversation | ContentMode::WithThinking => Some(&["user", "assistant"]),
        ContentMode::WithTools => Some(&["user", "assistant", "tool"]),
        ContentMode::Full => None,
    }
}

// ---- Params ----------------------------------------------------------------

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct ListSessionsParams {
    /// Max sessions to return (default 50, hard cap 200).
    #[serde(default = "default_session_limit")]
    pub limit: usize,
    /// Pagination offset.
    #[serde(default)]
    pub offset: usize,
}

fn default_session_limit() -> usize {
    50
}

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct QueryMemoryParams {
    /// Search term (required).
    pub query: String,
    /// ContentMode controlling which message types match and display.
    #[serde(default)]
    pub mode: ContentMode,
    /// "semantic" (default, ColBERT MaxSim) or "both". Pure "keyword" is not
    /// supported across all sessions — use query_session for keyword search
    /// within a session.
    #[serde(default)]
    pub search_type: SearchType,
    /// Max matches (default 20, hard cap 200).
    #[serde(default = "default_query_limit")]
    pub limit: usize,
    /// Pagination offset.
    #[serde(default)]
    pub offset: usize,
}

fn default_query_limit() -> usize {
    20
}

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct QuerySessionParams {
    /// The session to read (required).
    pub session_id: String,
    /// Optional search term. None = browse recent messages.
    #[serde(default)]
    pub query: Option<String>,
    /// Optional — narrow to one agent. Default None = all agents.
    #[serde(default)]
    pub agent_idx: Option<i64>,
    /// ContentMode controlling what message types to show.
    #[serde(default)]
    pub mode: ContentMode,
    /// "desc" (default) = newest-first (tail); "asc" = oldest-first (head).
    #[serde(default = "default_order")]
    pub order: String,
    /// Messages around each search match (like grep -C). Search only.
    #[serde(default)]
    pub context: usize,
    /// ISO datetime — only messages after this time.
    #[serde(default)]
    pub after: Option<String>,
    /// ISO datetime — only messages before this time.
    #[serde(default)]
    pub before: Option<String>,
    /// Max messages. Browse default = 1 (the tail); search default = 20.
    /// Hard cap 200.
    #[serde(default)]
    pub limit: Option<usize>,
    /// Pagination offset (into the past when order="desc").
    #[serde(default)]
    pub offset: usize,
    /// "semantic" (default), "keyword", or "both". Search only.
    #[serde(default)]
    pub search_type: SearchType,
}

fn default_order() -> String {
    "desc".into()
}

// ---- Formatting helpers (ports of the v1 Python helpers) -------------------

/// Extract all searchable text from a message data dict.
fn extract_searchable_text(data: &Value) -> String {
    let mut parts: Vec<String> = Vec::new();
    match data.get("role").and_then(|r| r.as_str()).unwrap_or("") {
        "user" => match data.get("content") {
            Some(Value::Array(blocks)) => {
                for b in blocks {
                    if b.get("type").and_then(|t| t.as_str()) == Some("text") {
                        if let Some(t) = b.get("text").and_then(|t| t.as_str()) {
                            parts.push(t.to_string());
                        }
                    }
                }
            }
            Some(Value::String(s)) => parts.push(s.clone()),
            _ => {}
        },
        "assistant" => {
            if let Some(c) = data.get("content").and_then(|c| c.as_str()) {
                if !c.is_empty() {
                    parts.push(c.to_string());
                }
            }
            if let Some(rc) = data.get("reasoning_content").and_then(|c| c.as_str()) {
                if !rc.is_empty() {
                    parts.push(rc.to_string());
                }
            }
            if let Some(tcs) = data.get("tool_calls").and_then(|t| t.as_array()) {
                for tc in tcs {
                    let f = tc.get("function");
                    if let Some(n) = f.and_then(|f| f.get("name")).and_then(|n| n.as_str()) {
                        parts.push(n.to_string());
                    }
                    if let Some(a) = f.and_then(|f| f.get("arguments")).and_then(|a| a.as_str())
                    {
                        parts.push(a.to_string());
                    }
                }
            }
        }
        "tool" => {
            if let Some(c) = data.get("content").and_then(|c| c.as_str()) {
                parts.push(c.to_string());
            }
            if let Some(id) = data.get("tool_call_id").and_then(|i| i.as_str()) {
                parts.push(id.to_string());
            }
        }
        _ => {}
    }
    parts.join(" ")
}

/// Extract the primary display text from a message.
fn extract_display_text(data: &Value) -> String {
    match data.get("role").and_then(|r| r.as_str()).unwrap_or("") {
        "user" => match data.get("content") {
            Some(Value::Array(blocks)) => {
                let texts: Vec<&str> = blocks
                    .iter()
                    .filter(|b| b.get("type").and_then(|t| t.as_str()) == Some("text"))
                    .filter_map(|b| b.get("text").and_then(|t| t.as_str()))
                    .collect();
                texts.join(" ")
            }
            Some(Value::String(s)) => s.clone(),
            _ => String::new(),
        },
        "assistant" | "tool" => data
            .get("content")
            .and_then(|c| c.as_str())
            .unwrap_or("")
            .to_string(),
        _ => String::new(),
    }
}

/// Format a single message for display. Returns None if skipped.
/// `ts` = HH:MM:SS, `aidx` = agent index (transcript tags).
fn format_message(data: &Value, mode: ContentMode, ts: &str, aidx: Option<i64>) -> Option<String> {
    let prefix = match (!ts.is_empty(), aidx) {
        (true, Some(a)) => format!("**[{ts} · a{a}]** "),
        (true, None) => format!("**[{ts}]** "),
        (false, Some(a)) => format!("**[a{a}]** "),
        (false, None) => String::new(),
    };
    let role = data.get("role").and_then(|r| r.as_str()).unwrap_or("");

    if role == "user" {
        let text = extract_display_text(data);
        if text.is_empty() {
            return None;
        }
        return Some(format!("{prefix}**USER**\n{text}"));
    }

    if role == "assistant" {
        let mut lines: Vec<String> = Vec::new();
        if matches!(mode, ContentMode::WithThinking | ContentMode::Full) {
            let thinking = data
                .get("reasoning_content")
                .and_then(|c| c.as_str())
                .unwrap_or("");
            if !thinking.is_empty() {
                lines.push(format!("{prefix}**ASSISTANT** *(thinking)*\n{thinking}"));
            }
        }
        let content = data.get("content").and_then(|c| c.as_str()).unwrap_or("");
        if !content.is_empty() {
            lines.push(format!("{prefix}**ASSISTANT**\n{content}"));
        }
        if matches!(mode, ContentMode::WithTools | ContentMode::Full) {
            if let Some(tcs) = data.get("tool_calls").and_then(|t| t.as_array()) {
                for tc in tcs {
                    let f = tc.get("function");
                    let name = f
                        .and_then(|f| f.get("name"))
                        .and_then(|n| n.as_str())
                        .unwrap_or("unknown");
                    let args = f
                        .and_then(|f| f.get("arguments"))
                        .and_then(|a| a.as_str())
                        .unwrap_or("");
                    lines.push(format!("{prefix}**TOOL_CALL** `{name}({args})`"));
                }
            }
        }
        if lines.is_empty() {
            return None;
        }
        return Some(lines.join("\n\n"));
    }

    if role == "tool" {
        if matches!(mode, ContentMode::WithTools | ContentMode::Full) {
            let content = data.get("content").and_then(|c| c.as_str()).unwrap_or("");
            let (mut out, rest) = char_truncate(content, 500);
            if rest > 0 {
                out.push_str(&format!("\n... [{rest} chars truncated]"));
            }
            return Some(format!("{prefix}**TOOL_RESULT**\n{out}"));
        }
        return None;
    }

    Some(format!(
        "{prefix}**{}**\n{}",
        role.to_uppercase(),
        serde_json::to_string(data).unwrap_or_default()
    ))
}

/// Char-safe truncation (v1 sliced Python strs by code point).
/// Returns (truncated, remaining char count).
fn char_truncate(s: &str, max_chars: usize) -> (String, usize) {
    let total = s.chars().count();
    if total <= max_chars {
        return (s.to_string(), 0);
    }
    (s.chars().take(max_chars).collect(), total - max_chars)
}

/// Build a short excerpt highlighting the query term.
fn build_excerpt(data: &Value, query: &str, max_len: usize) -> String {
    let text = extract_searchable_text(data);
    let chars: Vec<char> = text.chars().collect();
    let lower: Vec<char> = text.to_lowercase().chars().collect();
    let q_lower: Vec<char> = query.to_lowercase().chars().collect();
    let idx = find_subseq(&lower, &q_lower);
    match idx {
        None => {
            if chars.len() > max_len {
                chars[..max_len].iter().collect::<String>() + "..."
            } else {
                text
            }
        }
        Some(idx) => {
            let start = idx.saturating_sub(40);
            let end = (idx + q_lower.len() + 40).min(chars.len());
            let mut excerpt: String = chars[start..end].iter().collect();
            if start > 0 {
                excerpt = format!("...{excerpt}");
            }
            if end < chars.len() {
                excerpt.push_str("...");
            }
            excerpt
        }
    }
}

fn find_subseq(haystack: &[char], needle: &[char]) -> Option<usize> {
    if needle.is_empty() {
        return Some(0);
    }
    if needle.len() > haystack.len() {
        return None;
    }
    haystack.windows(needle.len()).position(|w| w == needle)
}

/// Return messages within `context` messages of any match index.
fn apply_context_window<T: Clone>(
    messages: &[T],
    match_indices: &BTreeSet<usize>,
    context: usize,
) -> Vec<T> {
    if match_indices.is_empty() || context == 0 {
        return match_indices.iter().map(|&i| messages[i].clone()).collect();
    }
    let mut included = BTreeSet::new();
    for &idx in match_indices {
        for i in idx.saturating_sub(context)..(idx + context + 1).min(messages.len()) {
            included.insert(i);
        }
    }
    included.iter().map(|&i| messages[i].clone()).collect()
}

/// Trim an ISO timestamp to 'YYYY-MM-DD HH:MM' for compact tables.
fn fmt_when(iso: &str) -> String {
    if iso.is_empty() {
        return "—".to_string();
    }
    iso.chars().take(16).collect::<String>().replace('T', " ")
}

/// One-line, pipe-escaped snippet of a message for the sessions table.
fn snippet(data: Option<&Value>, role: Option<&str>, max_len: usize) -> String {
    let Some(data) = data else {
        return "—".to_string();
    };
    let mut text = extract_display_text(data);
    if text.is_empty() {
        if let Some(c) = data.get("content").and_then(|c| c.as_str()) {
            text = c.to_string();
        }
    }
    let text = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if text.is_empty() {
        return format!("({})", role.unwrap_or("?"));
    }
    let (mut out, _) = char_truncate(&text, max_len);
    if out.chars().count() < text.chars().count() {
        out.push('…');
    }
    out.replace('|', "\\|")
}

/// A message tagged with its agent_idx, ready for transcript rendering.
#[derive(Clone)]
struct TRec {
    id: i64,
    data: Value,
    created_at: String,
    agent_idx: i64,
}

/// Render message records as a markdown transcript, tagged by agent_idx.
fn render_transcript(
    session_id: &str,
    agent_idx: Option<i64>,
    recs: &[TRec],
    mode: ContentMode,
    note: &str,
) -> String {
    let mut header = format!("## Session: {session_id}");
    if let Some(a) = agent_idx {
        header.push_str(&format!(" | Agent: {a}"));
    }
    let mut lines = vec![header, String::new()];
    for rec in recs {
        // HH:MM:SS from the ISO timestamp (v1: created_at[:19].split("T")[-1])
        let ts = if rec.created_at.is_empty() {
            String::new()
        } else {
            let head: String = rec.created_at.chars().take(19).collect();
            head.rsplit('T').next().unwrap_or("").to_string()
        };
        if let Some(formatted) = format_message(&rec.data, mode, &ts, Some(rec.agent_idx)) {
            lines.push(formatted);
            lines.push(String::new());
        }
    }
    lines.push(note.to_string());
    lines.join("\n")
}

fn escape_pipe(s: &str) -> String {
    s.replace('|', "\\|")
}

// ---- Shared fetch helpers ----------------------------------------------------

impl CrowMcpServer {
    /// Agents of a session, optionally narrowed to one agent_idx.
    async fn session_agents(
        &self,
        session_id: &str,
        agent_idx: Option<i64>,
    ) -> Result<Vec<crow_memory_sdk::AgentRecord>, McpError> {
        let agents = self
            .memory
            .list_agents(Some(session_id))
            .await
            .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;
        Ok(match agent_idx {
            Some(idx) => agents.into_iter().filter(|a| a.agent_idx == idx).collect(),
            None => agents,
        })
    }

    /// Full chronological (id-asc) history for a set of agents, post-filtered
    /// by mode roles and after/before (inclusive, ISO string compare — same
    /// semantics as the v1 store's `created_at >= after AND created_at <= before`).
    async fn fetch_history(
        &self,
        agents: &[crow_memory_sdk::AgentRecord],
        roles: Option<&[&str]>,
        after: Option<&str>,
        before: Option<&str>,
    ) -> Result<Vec<TRec>, McpError> {
        let mut out: Vec<(i64, TRec)> = Vec::new();
        for agent in agents {
            let msgs = self
                .memory
                .query_messages_by_agent(&agent.agent_id, true, usize::MAX, None)
                .await
                .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;
            for m in msgs {
                if let Some(roles) = roles {
                    if !roles.contains(&m.role.as_str()) {
                        continue;
                    }
                }
                if let Some(after) = after {
                    if m.created_at.as_str() < after {
                        continue;
                    }
                }
                if let Some(before) = before {
                    if m.created_at.as_str() > before {
                        continue;
                    }
                }
                out.push((
                    m.id,
                    TRec {
                        id: m.id,
                        data: m.data,
                        created_at: m.created_at,
                        agent_idx: agent.agent_idx,
                    },
                ));
            }
        }
        out.sort_by_key(|(id, _)| *id);
        Ok(out.into_iter().map(|(_, r)| r).collect())
    }
}

#[tool_router(router = memory_router, vis = "pub")]
impl CrowMcpServer {
    /// List agent sessions, most-recently-active first.
    ///
    /// A session can contain multiple agents (delegation). Sessions are ordered by
    /// their most recent MESSAGE (last activity), not creation time — so this
    /// answers "who has been working, and when." Dig into one with
    /// query_session(session_id).
    #[tool]
    async fn list_sessions(
        &self,
        Parameters(params): Parameters<ListSessionsParams>,
    ) -> Result<CallToolResult, McpError> {
        let limit = params.limit.clamp(1, 200);
        let sessions = self
            .memory
            .list_sessions(limit, params.offset)
            .await
            .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;
        if sessions.is_empty() {
            return Ok(CallToolResult::success(vec![ContentBlock::text(
                "No sessions found.",
            )]));
        }

        let mut lines = vec![
            "| session_id | last active | agents | msgs | last message | model / cwd |"
                .to_string(),
            "|---|---|---|---|---|---|".to_string(),
        ];
        for s in &sessions {
            let agents = if s.agent_idxs.len() > 1 {
                format!(
                    "{} (a{}–a{})",
                    s.agent_count,
                    s.agent_idxs[0],
                    s.agent_idxs[s.agent_idxs.len() - 1]
                )
            } else {
                s.agent_count.to_string()
            };
            let (lm_data, lm_role): (Option<&Value>, Option<&str>) = match &s.last_message {
                Some(lm) => (
                    Some(&lm.data),
                    if lm.role.is_empty() {
                        nonempty(&s.last_role)
                    } else {
                        Some(lm.role.as_str())
                    },
                ),
                None => (None, nonempty(&s.last_role)),
            };
            let snip = snippet(lm_data, lm_role, 60);
            let model = nonempty(&s.model_identifier).unwrap_or("—");
            let cwd = nonempty(&s.cwd).unwrap_or("—");
            lines.push(format!(
                "| {} | {} | {} | {} | {} | {} / {} |",
                s.session_id,
                fmt_when(&s.last_activity),
                agents,
                s.message_count,
                snip,
                model,
                cwd
            ));
        }
        lines.push(format!("\n*Showing {} sessions*", sessions.len()));
        Ok(CallToolResult::success(vec![ContentBlock::text(
            lines.join("\n"),
        )]))
    }

    /// Search conversation history ACROSS all sessions (discovery).
    ///
    /// Semantic (ColBERT) search over every session. Use this to find WHICH session
    /// discussed something, then dig in with query_session(session_id). To browse a
    /// known session or search within one, use query_session.
    #[tool]
    async fn query_memory(
        &self,
        Parameters(params): Parameters<QueryMemoryParams>,
    ) -> Result<CallToolResult, McpError> {
        let limit = params.limit.clamp(1, 200);

        if params.search_type == SearchType::Keyword {
            return Ok(CallToolResult::success(vec![ContentBlock::text(
                "Keyword search across all sessions is not supported. Use semantic \
                 search here, or query_session(session_id, search_type='keyword') \
                 for keyword search within a session.",
            )]));
        }

        let roles = mode_roles(params.mode);
        let hits = self
            .memory
            .search_messages(&params.query, limit + params.offset, None)
            .await
            .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;
        let hits: Vec<_> = hits
            .into_iter()
            .filter(|h| match roles {
                Some(roles) => roles.contains(&h.role.as_str()),
                None => true,
            })
            .skip(params.offset)
            .take(limit)
            .collect();
        if hits.is_empty() {
            return Ok(CallToolResult::success(vec![ContentBlock::text(
                "No matches found.",
            )]));
        }

        // agent_id -> (session_id, agent_idx)
        let agents = self
            .memory
            .list_agents(None)
            .await
            .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;
        let meta: HashMap<&str, (&str, i64)> = agents
            .iter()
            .map(|a| (a.agent_id.as_str(), (a.session_id.as_str(), a.agent_idx)))
            .collect();

        let mut lines = vec![
            "| session_id | agent | time | role | score | excerpt |".to_string(),
            "|---|---|---|---|---|---|".to_string(),
        ];
        for h in &hits {
            let (sess, idx) = meta.get(h.agent_id.as_str()).copied().unwrap_or(("?", -1));
            let ts: String = h.created_at.chars().take(19).collect::<String>().replace('T', " ");
            let excerpt = escape_pipe(&build_excerpt(&h.data, &params.query, 120));
            lines.push(format!(
                "| {} | {} | {} | {} | {:.2} | {} |",
                sess,
                idx,
                ts,
                h.role,
                h.score.unwrap_or(0.0),
                excerpt
            ));
        }
        lines.push(format!("\n*Showing {} semantic matches*", hits.len()));
        Ok(CallToolResult::success(vec![ContentBlock::text(
            lines.join("\n"),
        )]))
    }

    /// Read or search a single session's conversation history.
    ///
    /// Spans ALL agents in the session by default (delegation means a session can
    /// have many agents) — so older agents' messages are never lost. agent_idx is
    /// shown on every message in the output; pass it as input only to narrow to one
    /// agent.
    ///
    /// Two ways to use it:
    /// - Browse (no query): returns recent messages. A bare call returns just the
    ///   tail (the latest message) so you aren't drowned — raise `limit` for more,
    ///   or set order="asc" to start from the first message of the session. Use
    ///   `offset` / `after` / `before` to dig backwards in time.
    /// - Search (query given): semantic / keyword search within the session across
    ///   all agents, with an optional context window.
    #[tool]
    async fn query_session(
        &self,
        Parameters(params): Parameters<QuerySessionParams>,
    ) -> Result<CallToolResult, McpError> {
        let order = if params.order == "asc" { "asc" } else { "desc" };
        let roles = mode_roles(params.mode);

        let agents = self
            .session_agents(&params.session_id, params.agent_idx)
            .await?;
        if agents.is_empty() {
            return Ok(CallToolResult::success(vec![ContentBlock::text(format!(
                "No agents found for session '{}'",
                params.session_id
            ))]));
        }

        if let Some(q) = params.query.as_deref().filter(|q| !q.is_empty()) {
            return self
                .search_session(&params, q, &agents, roles, order)
                .await;
        }
        self.browse_session(&params, &agents, roles, order).await
    }

    async fn browse_session(
        &self,
        params: &QuerySessionParams,
        agents: &[crow_memory_sdk::AgentRecord],
        roles: Option<&[&str]>,
        order: &str,
    ) -> Result<CallToolResult, McpError> {
        let limit = params.limit.unwrap_or(1).clamp(1, 200);
        let mut recs = self
            .fetch_history(agents, roles, params.after.as_deref(), params.before.as_deref())
            .await?;
        if order == "desc" {
            recs.reverse();
        }
        let recs: Vec<TRec> = recs.into_iter().skip(params.offset).take(limit).collect();
        if recs.is_empty() {
            return Ok(CallToolResult::success(vec![ContentBlock::text(
                "No messages found.",
            )]));
        }
        Ok(CallToolResult::success(vec![ContentBlock::text(
            render_transcript(
                &params.session_id,
                params.agent_idx,
                &recs,
                params.mode,
                &format!("*Showing {} messages*", recs.len()),
            ),
        )]))
    }

    async fn search_session(
        &self,
        params: &QuerySessionParams,
        query: &str,
        agents: &[crow_memory_sdk::AgentRecord],
        roles: Option<&[&str]>,
        order: &str,
    ) -> Result<CallToolResult, McpError> {
        let limit = params.limit.unwrap_or(20).clamp(1, 200);

        // Full ordered history for the context window + keyword matching.
        let all_recs = self
            .fetch_history(agents, roles, params.after.as_deref(), params.before.as_deref())
            .await?;

        let mut match_indices: BTreeSet<usize> = BTreeSet::new();

        if matches!(params.search_type, SearchType::Semantic | SearchType::Both) {
            // Global semantic search (no session pre-filter in the backend),
            // over-fetch then post-filter to this session's agents + roles.
            let sem_hits = self
                .memory
                .search_messages(query, limit * 4, None)
                .await
                .map_err(|e| McpError::internal_error(format!("memory error: {e}"), None))?;
            let agent_ids: std::collections::HashSet<&str> =
                agents.iter().map(|a| a.agent_id.as_str()).collect();
            let id_to_idx: HashMap<i64, usize> = all_recs
                .iter()
                .enumerate()
                .map(|(i, r)| (r.id, i))
                .collect();
            for h in sem_hits {
                if !agent_ids.contains(h.agent_id.as_str()) {
                    continue;
                }
                if let Some(roles) = roles {
                    if !roles.contains(&h.role.as_str()) {
                        continue;
                    }
                }
                if let Some(&i) = id_to_idx.get(&h.id) {
                    match_indices.insert(i);
                }
            }
        }

        if matches!(params.search_type, SearchType::Keyword | SearchType::Both) {
            let q_lower = query.to_lowercase();
            for (i, rec) in all_recs.iter().enumerate() {
                if extract_searchable_text(&rec.data)
                    .to_lowercase()
                    .contains(&q_lower)
                {
                    match_indices.insert(i);
                }
            }
        }

        if match_indices.is_empty() {
            return Ok(CallToolResult::success(vec![ContentBlock::text(
                "No matches found.",
            )]));
        }

        let mut messages = if params.context > 0 {
            apply_context_window(&all_recs, &match_indices, params.context)
        } else {
            match_indices.iter().map(|&i| all_recs[i].clone()).collect()
        };
        if order == "desc" {
            messages.reverse();
        }
        let total = messages.len();
        let messages: Vec<TRec> = messages.into_iter().skip(params.offset).take(limit).collect();
        if messages.is_empty() {
            return Ok(CallToolResult::success(vec![ContentBlock::text(
                "No messages found.",
            )]));
        }
        Ok(CallToolResult::success(vec![ContentBlock::text(
            render_transcript(
                &params.session_id,
                params.agent_idx,
                &messages,
                params.mode,
                &format!("*Showing {} of {total} matches*", messages.len()),
            ),
        )]))
    }
}

fn nonempty(s: &str) -> Option<&str> {
    if s.is_empty() {
        None
    } else {
        Some(s)
    }
}
