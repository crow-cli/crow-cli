//#region src/runTelemetry.ts
const MAX_TELEMETRY_TEXT_LENGTH = 5e4;
const BASE64_PATTERN = /^[A-Za-z0-9+/]+={0,2}$/;
/**
* Maps a finish event to the report status and outcome. `fallbackStatus`
* applies when the event carries neither a finish reason nor a failure flag.
*/
function deriveRunOutcome(input, fallbackStatus = "completed") {
	if (input.isError) return { status: "error" };
	if (input.isAbort) return {
		status: "incomplete",
		outcome: "aborted"
	};
	if (input.isDisconnect) return {
		status: "incomplete",
		outcome: "disconnected"
	};
	switch (input.finishReason) {
		case "length": return {
			status: "incomplete",
			outcome: "length"
		};
		case "content-filter":
		case "content_filter": return {
			status: "incomplete",
			outcome: "content_filter"
		};
		case "cancelled": return {
			status: "incomplete",
			outcome: "aborted"
		};
		case "error": return { status: "error" };
		default: return { status: input.finishReason === void 0 ? fallbackStatus : "completed" };
	}
}
const MAX_RUN_ERROR_CODE_LENGTH = 64;
const MAX_RUN_ERROR_LENGTH = 2048;
/**
* Reads the message and code the runs endpoint stores for a failed run. The
* code is the error's `code` when it has one, else its class name.
*/
function describeRunError(error) {
	if (error == null) return {};
	const record = typeof error === "object" ? error : void 0;
	const message = typeof error === "string" ? error : typeof record?.message === "string" ? record.message : void 0;
	const code = typeof record?.code === "string" ? record.code : typeof record?.name === "string" && record.name !== "Error" ? record.name : void 0;
	return {
		...message ? { error: message.slice(0, MAX_RUN_ERROR_LENGTH) } : void 0,
		...code ? { errorCode: code.slice(0, MAX_RUN_ERROR_CODE_LENGTH) } : void 0
	};
}
/**
* Clamps a string to the size the runs endpoint accepts for a single span
* field.
*/
function truncateRunTelemetryText(value) {
	if (value.length <= MAX_TELEMETRY_TEXT_LENGTH) return value;
	return value.slice(0, MAX_TELEMETRY_TEXT_LENGTH);
}
function safeStringify(value) {
	if (value == null) return void 0;
	try {
		return truncateRunTelemetryText(JSON.stringify(value));
	} catch {
		return;
	}
}
const base64SizeKB = (value) => (value.length * 3 / 4 / 1024).toFixed(1);
const isInlineBase64 = (value) => {
	if (typeof value !== "string") return false;
	const head = value.slice(0, 200);
	return head.length > 0 && head.length % 4 === 0 && BASE64_PATTERN.test(head);
};
function summarizeMcpContentBlock(item) {
	if (!item || typeof item !== "object") return item;
	const block = item;
	if ((block.type === "image" || block.type === "audio") && isInlineBase64(block.data)) return {
		...block,
		data: `[${String(block.type)}: ${base64SizeKB(block.data)}KB]`
	};
	if (block.type === "resource" && block.resource && typeof block.resource === "object") {
		const resource = block.resource;
		if (isInlineBase64(resource.blob)) return {
			...block,
			resource: {
				...resource,
				blob: `[resource: ${base64SizeKB(resource.blob)}KB]`
			}
		};
	}
	return item;
}
function summarizeMcpResult(value) {
	if (value == null) return void 0;
	try {
		const parsed = typeof value === "string" ? JSON.parse(value) : value;
		if (Array.isArray(parsed)) return truncateRunTelemetryText(JSON.stringify(parsed.map(summarizeMcpContentBlock)));
		if (typeof parsed === "object") {
			const content = parsed.content;
			if (Array.isArray(content)) return truncateRunTelemetryText(JSON.stringify({
				...parsed,
				content: content.map(summarizeMcpContentBlock)
			}));
		}
	} catch {}
	return safeStringify(value);
}
/**
* Serializes one tool call into the shape the runs endpoint accepts. An `mcp`
* source has its result summarized, because MCP content blocks carry inline
* base64 image and audio payloads that would otherwise dominate the report.
*/
function createRunTelemetryToolCall(init) {
	const { toolName, toolCallId, args, argsText, result, toolSource } = init;
	const call = {
		tool_name: toolName,
		tool_call_id: toolCallId
	};
	const toolArgs = argsText != null ? truncateRunTelemetryText(argsText) : safeStringify(args);
	if (toolArgs !== void 0) call.tool_args = toolArgs;
	const toolResult = toolSource === "mcp" ? summarizeMcpResult(result) : safeStringify(result);
	if (toolResult !== void 0) call.tool_result = toolResult;
	if (toolSource) call.tool_source = toolSource;
	return call;
}
/**
* Resolves the model ID a run reports, in the order an app can supply it: an
* explicit `modelId`, the `custom` bag, then the per-step `response.modelId`
* that a `messageMetadata` callback copies off the AI SDK's finish-step part.
* The AI SDK puts no model ID on a UI message part, so message metadata is the
* only channel one arrives on.
*/
function extractRunTelemetryModelId(metadata) {
	if (!metadata) return void 0;
	if (typeof metadata.modelId === "string") return metadata.modelId;
	const custom = metadata.custom;
	if (typeof custom?.modelId === "string") return custom.modelId;
	const steps = metadata.steps;
	if (!Array.isArray(steps)) return void 0;
	for (const step of steps) {
		if (!step || typeof step !== "object") continue;
		const response = step.response;
		if (!response || typeof response !== "object") continue;
		const modelId = response.modelId;
		if (typeof modelId === "string") return modelId;
	}
}
function assignUsage(report, usage) {
	if (!usage) return;
	const normalized = normalizeRunTelemetryUsage(usage);
	if (!normalized) return;
	if (normalized.inputTokens !== void 0) report.input_tokens = normalized.inputTokens;
	if (normalized.outputTokens !== void 0) report.output_tokens = normalized.outputTokens;
	if (normalized.reasoningTokens !== void 0) report.reasoning_tokens = normalized.reasoningTokens;
	if (normalized.cachedInputTokens !== void 0) report.cached_input_tokens = normalized.cachedInputTokens;
}
function createRunReportStep(init) {
	const step = {};
	const usage = init.usage ? normalizeRunTelemetryUsage(init.usage) : void 0;
	if (usage?.inputTokens !== void 0) step.input_tokens = usage.inputTokens;
	if (usage?.outputTokens !== void 0) step.output_tokens = usage.outputTokens;
	if (usage?.reasoningTokens !== void 0) step.reasoning_tokens = usage.reasoningTokens;
	if (usage?.cachedInputTokens !== void 0) step.cached_input_tokens = usage.cachedInputTokens;
	if (init.toolCalls !== void 0) step.tool_calls = init.toolCalls;
	if (init.startMs !== void 0) step.start_ms = init.startMs;
	if (init.endMs !== void 0) step.end_ms = init.endMs;
	if (init.finishReason !== void 0) step.finish_reason = init.finishReason.slice(0, 32);
	if (init.input !== void 0) step.input = truncateRunTelemetryText(init.input);
	return step;
}
function normalizeRunReportTags(tags) {
	if (!tags) return void 0;
	const result = [];
	const seen = /* @__PURE__ */ new Set();
	for (const tag of tags) {
		const normalized = tag.trim().slice(0, 64).trim();
		if (!normalized || seen.has(normalized)) continue;
		seen.add(normalized);
		result.push(normalized);
		if (result.length === 20) break;
	}
	return result.length > 0 ? result : void 0;
}
function normalizeRunReportMilliseconds(value) {
	if (value === void 0 || !Number.isFinite(value)) return void 0;
	return Math.max(0, Math.round(value));
}
function normalizeRunReportCost(value) {
	if (value === void 0 || !Number.isFinite(value) || value < 0) return;
	return value;
}
function assignCostDetails(report, costDetails) {
	if (!costDetails) return;
	const normalized = {};
	const input = normalizeRunReportCost(costDetails.input);
	if (input !== void 0) normalized.input = input;
	const inputCachedTokens = normalizeRunReportCost(costDetails.inputCachedTokens);
	if (inputCachedTokens !== void 0) normalized.input_cached_tokens = inputCachedTokens;
	const output = normalizeRunReportCost(costDetails.output);
	if (output !== void 0) normalized.output = output;
	const total = normalizeRunReportCost(costDetails.total);
	if (total !== void 0) normalized.total = total;
	if (Object.keys(normalized).length > 0) report.cost_details = normalized;
}
function createRunReport(init) {
	const report = {
		thread_id: init.threadId,
		status: init.status
	};
	const traceId = init.traceId?.toLowerCase();
	if (traceId && /^[0-9a-f]{32}$/.test(traceId)) report.trace_id = traceId;
	const rootSpanId = init.rootSpanId?.toLowerCase();
	if (rootSpanId && /^[0-9a-f]{16}$/.test(rootSpanId)) report.root_span_id = rootSpanId;
	if (init.outcome !== void 0) report.outcome_type = init.outcome;
	if (init.errorCode !== void 0) report.error_code = init.errorCode;
	if (init.error !== void 0) report.error = init.error;
	if (init.messageId !== void 0) report.message_id = init.messageId;
	if (init.modelId !== void 0) report.model_id = init.modelId;
	if (init.provider !== void 0) {
		report.provider = init.provider;
		report.provider_type = init.provider;
	}
	assignUsage(report, init.usage);
	if (init.steps !== void 0) {
		report.steps = init.steps.map(createRunReportStep);
		report.total_steps = init.steps.length;
	} else if (init.totalSteps !== void 0) report.total_steps = init.totalSteps;
	if (init.toolCalls !== void 0) report.tool_calls = init.toolCalls;
	const durationMs = normalizeRunReportMilliseconds(init.durationMs);
	if (durationMs !== void 0) report.duration_ms = durationMs;
	const firstTokenMs = normalizeRunReportMilliseconds(init.firstTokenMs);
	if (firstTokenMs !== void 0) report.first_token_ms = firstTokenMs;
	const costUsd = normalizeRunReportCost(init.costUsd);
	if (costUsd !== void 0) report.cost_usd = costUsd;
	assignCostDetails(report, init.costDetails);
	if (init.outputText !== void 0) report.output_text = truncateRunTelemetryText(init.outputText);
	if (init.attributes !== void 0) report.attributes = init.attributes;
	if (init.metadata !== void 0) report.metadata = init.metadata;
	if (init.telemetry?.environment !== void 0) report.environment = init.telemetry.environment;
	if (init.telemetry?.release !== void 0) report.release = init.telemetry.release;
	const tags = normalizeRunReportTags(init.telemetry?.tags);
	if (tags !== void 0) report.tags = tags;
	return report;
}
/**
* Resolves the token counts a provider reports under any of the names the AI
* SDK has used: the current top-level ones, the legacy prompt/completion pair,
* and the v7 token detail objects. Returns undefined when no count is present,
* so callers can tell an empty usage object from a zeroed one.
*/
function normalizeRunTelemetryUsage(usage) {
	const inputTokens = usage.inputTokens ?? usage.promptTokens;
	const outputTokens = usage.outputTokens ?? usage.completionTokens;
	const reasoningTokens = usage.reasoningTokens ?? usage.outputTokenDetails?.reasoningTokens;
	const cachedInputTokens = usage.cachedInputTokens ?? usage.inputTokenDetails?.cacheReadTokens;
	if (inputTokens == null && outputTokens == null && reasoningTokens == null && cachedInputTokens == null) return;
	return {
		...inputTokens != null ? { inputTokens } : void 0,
		...outputTokens != null ? { outputTokens } : void 0,
		...reasoningTokens != null ? { reasoningTokens } : void 0,
		...cachedInputTokens != null ? { cachedInputTokens } : void 0
	};
}
//#endregion
export { createRunReport, createRunTelemetryToolCall, deriveRunOutcome, describeRunError, extractRunTelemetryModelId, normalizeRunTelemetryUsage, truncateRunTelemetryText };
