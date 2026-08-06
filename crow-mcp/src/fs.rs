//! Filesystem tools: read (with line numbers) and write.

use crate::CrowMcpServer;
use rmcp::{
    ErrorData as McpError, handler::server::wrapper::Parameters, model::*, schemars, tool,
    tool_router,
};

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct ReadParams {
    /// Absolute path of the file to read
    file_path: String,
    /// Line number to start from (1-indexed, default 1)
    #[serde(default = "default_offset")]
    offset: usize,
    /// Maximum number of lines to read (default 2000)
    #[serde(default = "default_limit")]
    limit: usize,
}

fn default_offset() -> usize { 1 }
fn default_limit() -> usize { 2000 }

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct WriteParams {
    /// The absolute path to the file to write
    file_path: String,
    /// The content to write to the file
    content: String,
}

#[tool_router(router = fs_router, vis = "pub")]
impl CrowMcpServer {
    /// Reads files from the filesystem with line numbers.
    #[tool(description = "Reads files from the local filesystem with line numbers. Cannot read directories.")]
    fn read(
        &self,
        Parameters(params): Parameters<ReadParams>,
    ) -> Result<CallToolResult, McpError> {
        let path = std::path::Path::new(&params.file_path);
        if path.is_dir() {
            return Ok(CallToolResult::success(vec![ContentBlock::text(format!(
                "Error: {} is a directory, not a file",
                params.file_path
            ))]));
        }
        let content = match std::fs::read_to_string(path) {
            Ok(c) => c,
            Err(e) => {
                return Ok(CallToolResult::success(vec![ContentBlock::text(format!(
                    "Error: Failed to read {}: {e}",
                    params.file_path
                ))]));
            }
        };

        let lines: Vec<&str> = content.lines().collect();
        let start = params.offset.saturating_sub(1).min(lines.len());
        let end = (start + params.limit).min(lines.len());

        let mut numbered = String::new();
        for (i, line) in lines[start..end].iter().enumerate() {
            numbered.push_str(&format!("{:>6}\t{}\n", start + i + 1, line));
        }

        if numbered.is_empty() {
            numbered = format!(
                "(file is empty or offset {} is past end of file, {} lines total)",
                params.offset,
                lines.len()
            );
        }

        Ok(CallToolResult::success(vec![ContentBlock::text(numbered)]))
    }

    /// Writes content to a file, creating it if needed or overwriting.
    #[tool(description = "Writes content to a file, creating it if it doesn't exist or overwriting if it does.")]
    fn write(
        &self,
        Parameters(params): Parameters<WriteParams>,
    ) -> Result<CallToolResult, McpError> {
        let path = std::path::Path::new(&params.file_path);
        if let Some(parent) = path.parent() {
            if !parent.exists() {
                if let Err(e) = std::fs::create_dir_all(parent) {
                    return Ok(CallToolResult::success(vec![ContentBlock::text(format!(
                        "Error: Failed to create parent directories: {e}"
                    ))]));
                }
            }
        }
        match std::fs::write(path, &params.content) {
            Ok(()) => Ok(CallToolResult::success(vec![ContentBlock::text(format!(
                "Successfully wrote to {}",
                params.file_path
            ))])),
            Err(e) => Ok(CallToolResult::success(vec![ContentBlock::text(format!(
                "Error: Failed to write {}: {e}",
                params.file_path
            ))])),
        }
    }
}
