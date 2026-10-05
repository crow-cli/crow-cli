import { type ReadableSpan, type SpanExporter, type SpanProcessor } from "@opentelemetry/sdk-trace-base";
export type AssistantCloudTraceExportOptions = {
    apiKey: string;
    baseUrl?: string;
    headers?: Record<string, string>;
};
export type AssistantCloudSpanProcessorOptions = {
    filter?: (span: ReadableSpan) => boolean;
};
export declare function assistantCloudTraceExportOptions({ apiKey, baseUrl, headers, }: AssistantCloudTraceExportOptions): {
    url: string;
    headers: Record<string, string>;
};
export declare function createAssistantCloudTraceExporter(options: AssistantCloudTraceExportOptions): SpanExporter;
export declare function isAssistantCloudSpan(span: ReadableSpan): boolean;
export declare function createAssistantCloudSpanProcessor(exporter: SpanExporter, options?: AssistantCloudSpanProcessorOptions): SpanProcessor;
export declare function assistantCloudTraceMetadata(): {
    traceId?: string;
};
export declare function withAssistantCloudTraceMetadata<Part extends {
    type: string;
} = {
    type: string;
}>(messageMetadata?: (options: {
    part: Part;
}) => Record<string, unknown> | undefined): (options: {
    part: Part;
}) => Record<string, unknown> | undefined;