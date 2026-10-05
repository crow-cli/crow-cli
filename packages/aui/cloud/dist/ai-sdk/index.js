import { createRunTelemetryToolCall, extractRunTelemetryModelId, normalizeRunTelemetryUsage, truncateRunTelemetryText } from "../runTelemetry.js";
//#region src/ai-sdk/index.ts
/** The stored form of an AI SDK message: the message without its id. */
const aiSDKV6FormatAdapter = {
	format: "ai-sdk/v6",
	encode: ({ message: { id: _id, ...message } }) => message,
	decode: (stored) => ({
		parentId: stored.parent_id,
		message: {
			id: stored.id,
			...stored.content
		}
	}),
	getId: (message) => message.id
};
function isRecord(value) {
	return value !== null && typeof value === "object";
}
function isPart(value) {
	return isRecord(value) && typeof value.type === "string";
}
/**
* The AI SDK's own tool part rules, kept here so the entry loads without the
* `ai` runtime: a static tool part is `tool-<name>`, a dynamic one is
* `dynamic-tool` with its name in `toolName`.
*/
function toolCallOf(part) {
	if (typeof part.toolCallId !== "string") return void 0;
	const isStatic = part.type.startsWith("tool-");
	if (!isStatic && part.type !== "dynamic-tool") return void 0;
	const toolName = isStatic ? part.type.slice(5) : typeof part.toolName === "string" ? part.toolName : void 0;
	if (!toolName) return void 0;
	return createRunTelemetryToolCall({
		toolName,
		toolCallId: part.toolCallId,
		args: part.input ?? part.args,
		result: part.output ?? part.result,
		toolSource: isStatic ? "frontend" : "mcp"
	});
}
function attachSamplingCalls(toolCalls, metadata) {
	const samplingCalls = isRecord(metadata?.samplingCalls) ? metadata.samplingCalls : void 0;
	if (!samplingCalls) return;
	for (const toolCall of toolCalls) {
		const calls = samplingCalls[toolCall.tool_call_id];
		if (Array.isArray(calls) && calls.length > 0) toolCall.sampling_calls = calls;
	}
}
function stepUsages(metadata) {
	const steps = metadata?.steps;
	if (!Array.isArray(steps)) return [];
	return steps.map((step) => isRecord(step) && isRecord(step.usage) ? step.usage : void 0);
}
function sumUsage(usages) {
	const total = {};
	for (const usage of usages) {
		if (usage.inputTokens != null) total.inputTokens = (total.inputTokens ?? 0) + usage.inputTokens;
		if (usage.outputTokens != null) total.outputTokens = (total.outputTokens ?? 0) + usage.outputTokens;
		if (usage.reasoningTokens != null) total.reasoningTokens = (total.reasoningTokens ?? 0) + usage.reasoningTokens;
		if (usage.cachedInputTokens != null) total.cachedInputTokens = (total.cachedInputTokens ?? 0) + usage.cachedInputTokens;
	}
	return total;
}
/**
* The usage a message reports: `metadata.usage` when the integration copied
* the run total there, else the sum over `metadata.steps[].usage`.
*/
function messageUsage(metadata) {
	const total = isRecord(metadata?.usage) ? normalizeRunTelemetryUsage(metadata.usage) : void 0;
	if (total) return total;
	const perStep = stepUsages(metadata).flatMap((usage) => {
		const normalized = usage ? normalizeRunTelemetryUsage(usage) : void 0;
		return normalized ? [normalized] : [];
	});
	return perStep.length > 0 ? sumUsage(perStep) : void 0;
}
/**
* Reads the run report fields out of the assistant messages of one run. A run
* the AI SDK streamed as one message is one element; a run the cloud stored as
* several assistant rows is aggregated, step by step, in order. Returns null
* when no assistant message is present. Status reads completed when the run
* produced text or tool calls, as a live finish with reason `tool-calls` does;
* an integration that observed the finish event overrides it.
*/
function extractAISDKRunTelemetry(messages) {
	const textParts = [];
	const toolCalls = [];
	const steps = [];
	const usages = [];
	let assistant;
	for (const message of messages) {
		if (message.role !== "assistant") continue;
		assistant = message;
		const metadata = isRecord(message.metadata) ? message.metadata : void 0;
		const usagePerStep = stepUsages(metadata);
		const messageToolCalls = [];
		let step;
		let stepIndex = -1;
		for (const part of message.parts) {
			if (!isPart(part)) continue;
			if (part.type === "step-start") {
				stepIndex += 1;
				const usage = usagePerStep[stepIndex];
				step = usage ? { usage } : {};
				steps.push(step);
				continue;
			}
			if (part.type === "text" && typeof part.text === "string" && part.text) {
				textParts.push(part.text);
				continue;
			}
			const toolCall = toolCallOf(part);
			if (!toolCall) continue;
			toolCalls.push(toolCall);
			messageToolCalls.push(toolCall);
			if (step) {
				step.toolCalls = [...step.toolCalls ?? [], toolCall];
				step.finishReason = "tool-calls";
			}
		}
		attachSamplingCalls(messageToolCalls, metadata);
		const usage = messageUsage(metadata);
		if (usage) usages.push(usage);
	}
	if (!assistant) return null;
	const metadata = isRecord(assistant.metadata) ? assistant.metadata : void 0;
	const usage = usages.length > 0 ? sumUsage(usages) : void 0;
	const modelId = extractRunTelemetryModelId(metadata);
	const completed = textParts.length > 0 || toolCalls.length > 0;
	return {
		...assistant.id !== void 0 ? { assistantMessageId: assistant.id } : void 0,
		status: completed ? "completed" : "incomplete",
		...toolCalls.length > 0 ? { toolCalls } : void 0,
		...steps.length > 0 ? {
			steps,
			totalSteps: steps.length
		} : void 0,
		...textParts.length > 0 ? { outputText: truncateRunTelemetryText(textParts.join("")) } : void 0,
		...usage ? { usage } : void 0,
		...modelId ? { modelId } : void 0,
		...metadata ? { metadata } : void 0
	};
}
//#endregion
export { aiSDKV6FormatAdapter, extractAISDKRunTelemetry };
