import { trace } from "@opentelemetry/api";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";
//#region src/telemetry/index.ts
const DEFAULT_BACKEND_BASE_URL = "https://backend.assistant-api.com";
const AI_SPAN_PREFIXES = [
	"gen_ai.",
	"ai.",
	"llm."
];
function assistantCloudTraceExportOptions({ apiKey, baseUrl = DEFAULT_BACKEND_BASE_URL, headers }) {
	if (!apiKey) throw new Error("An Assistant Cloud API key is required");
	return {
		url: `${trimTrailingSlashes(baseUrl)}/v1/traces`,
		headers: {
			Authorization: `Bearer ${apiKey}`,
			...headers
		}
	};
}
function trimTrailingSlashes(url) {
	let end = url.length;
	while (end > 0 && url[end - 1] === "/") end--;
	return url.slice(0, end);
}
function createAssistantCloudTraceExporter(options) {
	return new OTLPTraceExporter(assistantCloudTraceExportOptions(options));
}
function isAssistantCloudSpan(span) {
	return typeof span.attributes["gen_ai.operation.name"] === "string" || AI_SPAN_PREFIXES.some((prefix) => span.name.startsWith(prefix));
}
function createAssistantCloudSpanProcessor(exporter, options = {}) {
	const processor = new BatchSpanProcessor(exporter);
	const filter = options.filter ?? isAssistantCloudSpan;
	return {
		onStart: (span, parentContext) => processor.onStart(span, parentContext),
		onEnd: (span) => {
			if (filter(span)) processor.onEnd(span);
		},
		forceFlush: () => processor.forceFlush(),
		shutdown: () => processor.shutdown()
	};
}
function assistantCloudTraceMetadata() {
	const spanContext = trace.getActiveSpan()?.spanContext();
	return spanContext && trace.isSpanContextValid(spanContext) ? { traceId: spanContext.traceId } : {};
}
function withAssistantCloudTraceMetadata(messageMetadata) {
	return (options) => {
		const metadata = messageMetadata?.(options);
		if (options.part.type !== "start") return metadata;
		const trace = assistantCloudTraceMetadata();
		return trace.traceId === void 0 ? metadata : {
			...metadata,
			...trace
		};
	};
}
//#endregion
export { assistantCloudTraceExportOptions, assistantCloudTraceMetadata, createAssistantCloudSpanProcessor, createAssistantCloudTraceExporter, isAssistantCloudSpan, withAssistantCloudTraceMetadata };
