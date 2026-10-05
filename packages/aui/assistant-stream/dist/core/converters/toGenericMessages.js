import { NO_RESULT } from "../tool/ToolResponse.js";
//#region src/core/converters/toGenericMessages.ts
/**
* Generic message types for framework-agnostic LLM message interchange.
* These types represent a common format that can be converted to/from
* various LLM provider formats (AI SDK, LangChain, etc.).
*/
const IMAGE_MEDIA_TYPES = {
	jpg: "image/jpeg",
	jpeg: "image/jpeg",
	png: "image/png",
	gif: "image/gif",
	webp: "image/webp",
	svg: "image/svg+xml",
	avif: "image/avif",
	bmp: "image/bmp",
	ico: "image/x-icon",
	tiff: "image/tiff",
	tif: "image/tiff",
	heic: "image/heic",
	heif: "image/heif"
};
function getDataUrlMediaType(value) {
	return value.match(/^data:([^;,]+)(?:[;,])/i)?.[1]?.toLowerCase();
}
function inferImageMediaType(url) {
	if (/^data:/i.test(url)) {
		const match = url.match(/^data:([^;,]+)/i);
		if (match?.[1]) return match[1].toLowerCase();
	}
	const [pathWithoutParams = ""] = url.split(/[?#]/);
	const ext = pathWithoutParams.split(".").pop()?.toLowerCase() ?? "";
	return IMAGE_MEDIA_TYPES[ext] ?? "image/png";
}
function toUrlOrString(value) {
	try {
		return new URL(value);
	} catch {
		return value;
	}
}
function isAwaitingHost(part) {
	if (part.interrupt != null) return true;
	if (part.approval == null) return false;
	return part.approval.approved !== false && part.approval.resolution === void 0;
}
function processToolCall(part, accumulator, inFlight) {
	if (!part.toolCallId || !part.toolName) return false;
	accumulator.textParts.push({
		type: "tool-call",
		toolCallId: part.toolCallId,
		toolName: part.toolName,
		args: part.args ?? {}
	});
	const settled = !part.isPreliminary && (part.state === "result" || part.result !== void 0);
	if (!settled && inFlight && isAwaitingHost(part)) return false;
	const toolResult = {
		type: "tool-result",
		toolCallId: part.toolCallId,
		toolName: part.toolName,
		result: !settled ? { error: "Tool call was not completed" } : part.result === void 0 ? NO_RESULT : part.result
	};
	if (!settled || part.isError) toolResult.isError = true;
	accumulator.toolResults.push(toolResult);
	return true;
}
function flushAccumulator(accumulator, result) {
	if (accumulator.textParts.length > 0) {
		result.push({
			role: "assistant",
			content: accumulator.textParts
		});
		accumulator.textParts = [];
	}
	if (accumulator.toolResults.length > 0) {
		result.push({
			role: "tool",
			content: accumulator.toolResults
		});
		accumulator.toolResults = [];
	}
}
function convertSystemMessage(message, result) {
	const textPart = message.content?.find((p) => p?.type === "text");
	if (textPart?.text) result.push({
		role: "system",
		content: textPart.text
	});
}
function convertUserMessage(message, result) {
	const attachments = message.attachments ?? [];
	const allContent = [...message.content ?? [], ...attachments.flatMap((a) => a?.content ?? [])];
	const content = [];
	for (const part of allContent) {
		if (!part) continue;
		if (part.type === "text" && part.text) content.push({
			type: "text",
			text: part.text
		});
		else if (part.type === "image" && part.image) content.push({
			type: "file",
			data: toUrlOrString(part.image),
			mediaType: inferImageMediaType(part.image),
			...part.filename && { filename: part.filename }
		});
		else if (part.type === "file" && typeof part.data === "string") content.push({
			type: "file",
			data: toUrlOrString(part.data),
			mediaType: typeof part.mimeType === "string" && part.mimeType || getDataUrlMediaType(part.data) || "application/octet-stream",
			...part.filename && { filename: part.filename }
		});
	}
	if (content.length > 0) result.push({
		role: "user",
		content
	});
}
function convertAssistantMessage(message, result, isLast) {
	const accumulator = {
		textParts: [],
		toolResults: []
	};
	let hasPendingToolResults = false;
	const inFlight = isLast && message.status?.type !== "complete" && message.status?.type !== "incomplete";
	for (const part of message.content ?? []) {
		if (!part) continue;
		if (part.type === "text" && part.text) {
			if (hasPendingToolResults) {
				flushAccumulator(accumulator, result);
				hasPendingToolResults = false;
			}
			accumulator.textParts.push({
				type: "text",
				text: part.text
			});
		} else if (part.type === "tool-call") {
			if (processToolCall(part, accumulator, inFlight)) hasPendingToolResults = true;
		}
	}
	flushAccumulator(accumulator, result);
}
/**
* Converts thread messages to generic LLM messages.
* This format can then be easily converted to provider-specific formats.
*/
function toGenericMessages(messages) {
	const result = [];
	const present = messages.filter(Boolean);
	for (const [index, message] of present.entries()) switch (message.role) {
		case "system":
			convertSystemMessage(message, result);
			break;
		case "user":
			convertUserMessage(message, result);
			break;
		case "assistant": convertAssistantMessage(message, result, index === present.length - 1);
	}
	return result;
}
//#endregion
export { toGenericMessages };
