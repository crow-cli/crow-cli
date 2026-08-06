//! Web tools: SearXNG search + URL fetch (ported from Python crow-mcp v1).

use crate::CrowMcpServer;
use rmcp::{
    ErrorData as McpError, handler::server::wrapper::Parameters, model::*, schemars, tool,
    tool_router,
};
use serde::Deserialize;

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct WebSearchParams {
    /// Your search queries for the search engine (searched in parallel, 4-5 max)
    pub queries: Vec<String>,
    /// Control the number of results per query (default 10)
    #[serde(default = "default_search_limit")]
    pub limit: usize,
}

fn default_search_limit() -> usize { 10 }

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct WebFetchParams {
    /// URL to fetch
    pub url: String,
    /// Max characters to return (default 5000)
    #[serde(default = "default_fetch_length")]
    pub max_length: usize,
    /// Start at this character (for pagination)
    #[serde(default)]
    pub start_index: usize,
    /// Get raw HTML instead of markdown
    #[serde(default)]
    pub raw: bool,
}

fn default_fetch_length() -> usize { 5000 }

#[tool_router(router = web_router, vis = "pub")]
impl CrowMcpServer {
    /// Search the web via the local SearXNG instance.
    #[tool(description = "Search the internet via the local SearXNG instance.\n\n## Search Tool Instructions\n**Search the internet. USE THIS LIBERALLY.**\nIf you are:\n- Uncertain about the user's query\n- About to make something up\n- Suspecting the USER is making something up\n- Working with a library/API you haven't seen recently\n- Debugging an error message you don't recognize\nThen SEARCH. Search in parallel (4-5 max). Search before you hallucinate.\nSEARCH INTERNET AS MUCH AS FILESYSTEM! I PITY THE FOOL WHO DON'T USE WEB SEARCH!\nThis is not a fallback tool. This is a primary tool. Good developers search the internet constantly. So should you.\n**Tips for better results:**\n- To search a specific website, add the site name to your query (e.g., \"python async stackoverflow\" or \"react hooks site:reactjs.org\")\n- To find recent results, add timeframes to your query (e.g., \"rust 2024\", \"next.js news this week\")\n- If a snippet looks promising but is cut off, use web_fetch to pull down the full page")]
    async fn web_search(
        &self,
        Parameters(params): Parameters<WebSearchParams>,
    ) -> Result<CallToolResult, McpError> {
        let queries = params.queries;
        let limit = params.limit;
        match web_search_inner(&queries, limit).await {
            Ok(text) => Ok(CallToolResult::success(vec![ContentBlock::text(text)])),
            Err(e) => Ok(CallToolResult::success(vec![ContentBlock::text(format!(
                "Error: web_search failed: {e}"
            ))])),
        }
    }

    /// Fetch a URL and extract content as markdown.
    #[tool(description = "Fetch a URL and extract content as markdown (readability + markdown conversion). Paginate with start_index when content is truncated. raw=true returns raw HTML.")]
    async fn web_fetch(
        &self,
        Parameters(params): Parameters<WebFetchParams>,
    ) -> Result<CallToolResult, McpError> {
        let text = web_fetch_inner(&params.url, params.max_length, params.start_index, params.raw)
            .await;
        Ok(CallToolResult::success(vec![ContentBlock::text(text)]))
    }
}

#[derive(Deserialize)]
struct SearchResult {
    url: String,
    title: String,
    #[serde(default)]
    content: String,
}

#[derive(Deserialize)]
struct Infobox {
    infobox: String,
    #[serde(default)]
    id: String,
    #[serde(default)]
    content: String,
}

#[derive(Deserialize)]
struct SearchResponse {
    #[serde(default)]
    results: Vec<SearchResult>,
    #[serde(default)]
    infoboxes: Vec<Infobox>,
}

fn searxng_base_url() -> String {
    if let Ok(url) = std::env::var("SEARXNG_URL") {
        return url;
    }
    let port = std::env::var("SEARXNG_PORT").unwrap_or_else(|_| "2946".into());
    format!("http://localhost:{port}")
}

/// Search via local SearXNG instance. One GET per query, formatted like v1.
async fn web_search_inner(queries: &[String], limit: usize) -> anyhow::Result<String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;
    let base = searxng_base_url();
    let mut out = Vec::new();

    for query in queries {
        let resp = client
            .get(format!("{base}/search"))
            .query(&[("q", query.as_str()), ("format", "json")])
            .send()
            .await?
            .error_for_status()?;
        let data: SearchResponse = resp.json().await?;

        let mut text = String::new();
        for infobox in &data.infoboxes {
            text.push_str(&format!("Infobox: {}\n", infobox.infobox));
            text.push_str(&format!("ID: {}\n", infobox.id));
            text.push_str(&format!("Content: {}\n\n", infobox.content));
        }
        if data.results.is_empty() {
            text.push_str("No results found\n");
        }
        for (i, result) in data.results.iter().enumerate() {
            if i >= limit {
                break;
            }
            text.push_str(&format!("Title: {}\n", result.title));
            text.push_str(&format!("URL: {}\n", result.url));
            text.push_str(&format!("Content: {}\n\n", result.content));
        }
        out.push(format!("Query:\n{query}\n\nResults:\n{text}"));
    }
    Ok(out.join("\n"))
}

/// Fetch a URL; HTML goes through readability + markdown conversion.
/// Errors are returned as text (v1 behavior), never as MCP errors.
async fn web_fetch_inner(url: &str, max_length: usize, start_index: usize, raw: bool) -> String {
    match fetch_inner(url, max_length, start_index, raw).await {
        Ok(s) => s,
        Err(e) => format!("Error fetching {url}: {e}"),
    }
}

async fn fetch_inner(
    url: &str,
    max_length: usize,
    start_index: usize,
    raw: bool,
) -> anyhow::Result<String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .redirect(reqwest::redirect::Policy::limited(10))
        .build()?;
    let response = client
        .get(url)
        .header("User-Agent", "CrowAgent/1.0")
        .send()
        .await?
        .error_for_status()?;
    let content_type = response
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();
    let page_raw = response.text().await?;

    let head = &page_raw[..page_raw.len().min(100)];
    let is_html = head.contains("<html") || content_type.contains("text/html") || content_type.is_empty();

    let (content, prefix) = if raw {
        (page_raw, String::new())
    } else if is_html {
        let parsed = url::Url::parse(url)?;
        let mut body = std::io::Cursor::new(page_raw);
        match readability::extractor::extract(&mut body, &parsed) {
            Ok(doc) if !doc.content.is_empty() => {
                let md = htmd::HtmlToMarkdown::new().convert(&doc.content)?;
                (md, String::new())
            }
            _ => ("<error>Failed to parse HTML</error>".to_string(), String::new()),
        }
    } else {
        (page_raw, format!("Content type: {content_type}\n"))
    };

    let total_len = content.len();
    if start_index >= total_len {
        return Ok("<error>No more content available.</error>".to_string());
    }
    let truncated = &content[start_index..(start_index + max_length).min(total_len)];
    let label = if raw { "Raw HTML from" } else { "Contents of" };
    let mut result = format!("{prefix}{label} {url}:\n{truncated}");
    if truncated.len() == max_length && start_index + max_length < total_len {
        result.push_str(&format!(
            "\n\n<error>Content truncated. Call fetch with start_index={}</error>",
            start_index + max_length
        ));
    }
    Ok(result)
}
