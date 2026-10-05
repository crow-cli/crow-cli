import type { SamplingCallData } from "./instrumentMcpSampling.js";
import type { AssistantCloudRunReport } from "./AssistantCloudRuns.js";
export type AssistantCloudRunReportToolCall = {
    tool_name: string;
    tool_call_id: string;
    tool_args?: string;
    tool_result?: string;
    tool_source?: "mcp" | "frontend" | "backend";
    start_ms?: number;
    end_ms?: number;
    sampling_calls?: SamplingCallData[];
};
export type RunReportOutcome = "aborted" | "disconnected" | "length" | "content_filter";
/**
 * Maps a finish event to the report status and outcome. `fallbackStatus`
 * applies when the event carries neither a finish reason nor a failure flag.
 */
export declare function deriveRunOutcome(input: {
    finishReason?: string | undefined;
    isAbort?: boolean | undefined;
    isDisconnect?: boolean | undefined;
    isError?: boolean | undefined;
}, fallbackStatus?: "completed" | "incomplete"): {
    status: "completed" | "incomplete" | "error";
    outcome?: RunReportOutcome;
};
/**
 * Reads the message and code the runs endpoint stores for a failed run. The
 * code is the error's `code` when it has one, else its class name.
 */
export declare function describeRunError(error: unknown): {
    error?: string;
    errorCode?: string;
};
/**
 * Clamps a string to the size the runs endpoint accepts for a single span
 * field.
 */
export declare function truncateRunTelemetryText(value: string): string;
export type RunTelemetryToolCallInit = {
    toolName: string;
    toolCallId: string;
    args?: unknown;
    /**
     * Pre-serialized arguments, used in place of serializing `args`. Values over
     * the span size are clamped before they are included in the report.
     */
    argsText?: string | undefined;
    result?: unknown;
    toolSource?: "mcp" | "frontend" | "backend" | undefined;
};
/**
 * Serializes one tool call into the shape the runs endpoint accepts. An `mcp`
 * source has its result summarized, because MCP content blocks carry inline
 * base64 image and audio payloads that would otherwise dominate the report.
 */
export declare function createRunTelemetryToolCall(init: RunTelemetryToolCallInit): AssistantCloudRunReportToolCall;
/**
 * Resolves the model ID a run reports, in the order an app can supply it: an
 * explicit `modelId`, the `custom` bag, then the per-step `response.modelId`
 * that a `messageMetadata` callback copies off the AI SDK's finish-step part.
 * The AI SDK puts no model ID on a UI message part, so message metadata is the
 * only channel one arrives on.
 */
export declare function extractRunTelemetryModelId(metadata: Record<string, unknown> | undefined): string | undefined;
export type RunTelemetryUsage = {
    inputTokens?: number | undefined;
    outputTokens?: number | undefined;
    reasoningTokens?: number | undefined;
    cachedInputTokens?: number | undefined;
};
export type RunTelemetryUsageInit = RunTelemetryUsage & {
    promptTokens?: number | undefined;
    completionTokens?: number | undefined;
    inputTokenDetails?: {
        cacheReadTokens?: number;
    };
    outputTokenDetails?: {
        reasoningTokens?: number;
    };
};
export type RunReportStepInit = {
    usage?: RunTelemetryUsageInit | undefined;
    toolCalls?: AssistantCloudRunReportToolCall[] | undefined;
    startMs?: number | undefined;
    endMs?: number | undefined;
    finishReason?: string | undefined;
    input?: string | undefined;
};
/**
 * The run report fields read from the messages of one run, in whichever
 * format they were stored: the status the messages imply, the tool calls, the
 * steps, the text, the usage and the model.
 */
export type RunMessageTelemetry = {
    assistantMessageId?: string;
    status: "completed" | "incomplete";
    toolCalls?: AssistantCloudRunReportToolCall[];
    steps?: RunReportStepInit[];
    totalSteps?: number;
    outputText?: string;
    usage?: RunTelemetryUsage;
    modelId?: string;
    metadata?: Record<string, unknown>;
};
export type RunReportInit = {
    threadId: string;
    status: AssistantCloudRunReport["status"];
    outcome?: AssistantCloudRunReport["outcome_type"] | undefined;
    errorCode?: string | undefined;
    error?: string | undefined;
    messageId?: string | undefined;
    traceId?: string | undefined;
    rootSpanId?: string | undefined;
    modelId?: string | undefined;
    provider?: string | undefined;
    usage?: RunTelemetryUsageInit | undefined;
    steps?: RunReportStepInit[] | undefined;
    totalSteps?: number | undefined;
    toolCalls?: AssistantCloudRunReportToolCall[] | undefined;
    durationMs?: number | undefined;
    firstTokenMs?: number | undefined;
    costUsd?: number | undefined;
    costDetails?: {
        input?: number | undefined;
        inputCachedTokens?: number | undefined;
        output?: number | undefined;
        total?: number | undefined;
    } | undefined;
    outputText?: string | undefined;
    attributes?: Record<string, unknown> | undefined;
    metadata?: Record<string, unknown> | undefined;
    telemetry?: {
        environment?: string | undefined;
        release?: string | undefined;
        tags?: readonly string[] | undefined;
    };
};
export declare function createRunReport(init: RunReportInit): AssistantCloudRunReport;
/**
 * Resolves the token counts a provider reports under any of the names the AI
 * SDK has used: the current top-level ones, the legacy prompt/completion pair,
 * and the v7 token detail objects. Returns undefined when no count is present,
 * so callers can tell an empty usage object from a zeroed one.
 */
export declare function normalizeRunTelemetryUsage(usage: RunTelemetryUsageInit): RunTelemetryUsage | undefined;