//! Verdict tool — structured pass/fail signal for the verifier proxy.

use crate::CrowMcpServer;
use rmcp::{
    ErrorData as McpError, handler::server::wrapper::Parameters, model::*, schemars, tool,
    tool_router,
};

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct VerdictParams {
    /// Whether the worker's output passes verification
    pub pass: bool,
    /// Feedback for the worker (what's missing or wrong). Empty if pass.
    #[serde(default)]
    pub feedback: String,
}

#[tool_router(router = verdict_router, vis = "pub")]
impl CrowMcpServer {
    /// Structured verdict signal for the verifier proxy.
    ///
    /// The verifier proxy watches for this tool call in the SSE stream
    /// and reads pass/feedback from the args. The tool itself is a no-op.
    #[tool(description = "Signal verification verdict. Call this to terminate the verification loop. pass=true means the worker's output is acceptable. pass=false means it needs revision — provide specific feedback.")]
    async fn verdict(
        &self,
        Parameters(params): Parameters<VerdictParams>,
    ) -> Result<CallToolResult, McpError> {
        tracing::info!(pass = params.pass, feedback = %params.feedback, "verdict");
        Ok(CallToolResult::success(vec![ContentBlock::text(
            "verdict recorded",
        )]))
    }
}
