import type { AssistantCloudAPI } from "./AssistantCloudAPI.js";
import type { AssistantCloudRunReportToolCall } from "./runTelemetry.js";
import { AssistantStream } from "assistant-stream";
type AssistantCloudRunsStreamBody = {
    thread_id: string;
    assistant_id: "system/thread_title";
    messages: readonly unknown[];
};
export type AssistantCloudRunReport = {
    thread_id: string;
    status: "completed" | "incomplete" | "error";
    outcome_type?: "rate_limited" | "validation_failed" | "provider_error" | "server_error" | "budget_denied" | "persistence_error" | "aborted" | "timeout" | "disconnected" | "length" | "content_filter";
    message_id?: string;
    first_token_ms?: number;
    release?: string;
    environment?: string;
    tags?: string[];
    provider?: string;
    trace_id?: string;
    root_span_id?: string;
    error_code?: string;
    error?: string;
    total_steps?: number;
    tool_calls?: AssistantCloudRunReportToolCall[];
    steps?: {
        input_tokens?: number;
        output_tokens?: number;
        reasoning_tokens?: number;
        cached_input_tokens?: number;
        tool_calls?: AssistantCloudRunReportToolCall[];
        start_ms?: number;
        end_ms?: number;
        finish_reason?: string;
        input?: string;
    }[];
    input_tokens?: number;
    output_tokens?: number;
    reasoning_tokens?: number;
    cached_input_tokens?: number;
    cost_usd?: number;
    cost_details?: {
        input?: number;
        input_cached_tokens?: number;
        output?: number;
        total?: number;
    };
    model_id?: string;
    provider_type?: string;
    duration_ms?: number;
    output_text?: string;
    attributes?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
};
export declare class AssistantCloudRuns {
    private cloud;
    constructor(cloud: AssistantCloudAPI);
    __internal_getAssistantOptions(assistantId: string): {
        api: string;
        protocol: "ui-message-stream";
        headers: () => Promise<{
            Accept: string;
            "Aui-Sdk": string;
        }>;
        body: (options?: {
            threadId?: string;
        }) => Promise<{
            assistant_id: string;
            response_format: string;
            thread_id: string;
        }>;
    };
    stream(body: AssistantCloudRunsStreamBody): Promise<AssistantStream>;
    report(body: AssistantCloudRunReport): Promise<{
        run_id: string;
    }>;
}
export {};