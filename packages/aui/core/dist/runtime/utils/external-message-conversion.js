import { generateErrorMessageId } from "../../utils/id.js";
import { isJSONValueEqual } from "../../utils/json/is-json-equal.js";
import { fromThreadMessageLike } from "./thread-message-like.js";
import { FALLBACK_ID_PREFIX, bindExternalStoreMessage, getExternalStoreMessages, symbolInnerMessage } from "./external-store-message.js";
import { getAutoStatus, isAutoStatus, isBackgroundToolCall, isInterruptedToolCall, isPendingToolCall } from "./auto-status.js";
import { ThreadMessageConverter } from "../../runtimes/external-store/thread-message-converter.js";
//#region src/runtime/utils/external-message-conversion.ts
const stringifyForError = (value) => {
	let text;
	try {
		text = value instanceof Error ? String(value) : JSON.stringify(value);
	} catch {}
	text ??= String(value);
	return text.length > 200 ? `${text.slice(0, 200)}…` : text;
};
const toCallbackOutputs = (output, input) => {
	const outputs = Array.isArray(output) ? output : [output];
	for (const o of outputs) if (!(typeof o === "object" && o !== null && (o.role === "tool" || (o.role === "assistant" || o.role === "user" || o.role === "system") && (typeof o.content === "string" || Array.isArray(o.content))))) throw new Error(`External message converter: the converter callback returned an invalid message (${stringifyForError(o)}) for input ${stringifyForError(input)}. Return an empty array to skip a message.`);
	return outputs.filter((o) => {
		if (o.role !== "tool") return true;
		if (typeof o.toolCallId === "string" && o.toolCallId.length > 0) return true;
		if (!warnedDroppedToolResults.has(o)) {
			warnedDroppedToolResults.add(o);
			console.warn(`External message converter: dropping a tool result without a toolCallId (${stringifyForError(o)}) for input ${stringifyForError(input)}.`);
		}
		return false;
	});
};
const warnedDroppedToolResults = /* @__PURE__ */ new WeakSet();
const convertExternalMessageCallback = (input, callback, metadata) => ({
	input,
	outputs: toCallbackOutputs(callback(input, metadata), input)
});
const mergeInnerMessages = (existing, incoming) => ({ [symbolInnerMessage]: [...existing[symbolInnerMessage] ?? [], ...incoming[symbolInnerMessage] ?? []] });
const isNaNToolCallId = (toolCallId) => typeof toolCallId === "number" && Number.isNaN(toolCallId);
const joinExternalMessages = (messages) => {
	const assistantMessage = {
		role: "assistant",
		content: []
	};
	const toolCallIndices = /* @__PURE__ */ new Map();
	const reasoningIndices = /* @__PURE__ */ new Map();
	for (const output of messages) if (output.role === "tool") {
		const toolCallIdx = !isNaNToolCallId(output.toolCallId) ? toolCallIndices.get(output.toolCallId) ?? -1 : -1;
		if (toolCallIdx !== -1) {
			const { isPreliminary: _isPreliminary, ...toolCall } = assistantMessage.content[toolCallIdx];
			if (output.toolName != null) {
				if (toolCall.toolName !== output.toolName) throw new Error(`Tool call name ${output.toolCallId} ${output.toolName} does not match existing tool call ${toolCall.toolName}`);
			}
			assistantMessage.content[toolCallIdx] = {
				...toolCall,
				[symbolInnerMessage]: [...toolCall[symbolInnerMessage] ?? [], output],
				result: output.result,
				artifact: output.artifact,
				isError: output.isError,
				messages: output.messages ?? toolCall.messages
			};
		}
	} else {
		const role = output.role;
		const content = (typeof output.content === "string" ? [{
			type: "text",
			text: output.content
		}] : output.content).map((c) => ({
			...c,
			[symbolInnerMessage]: [output]
		}));
		switch (role) {
			case "system":
			case "user": return {
				...output,
				content
			};
			case "assistant":
				assistantMessage.status = output.status;
				if (assistantMessage.content.length === 0) {
					assistantMessage.id = output.id;
					assistantMessage.createdAt ??= output.createdAt;
					if (output.attachments) assistantMessage.attachments = [...assistantMessage.attachments ?? [], ...output.attachments];
				}
				if (output.metadata) {
					assistantMessage.metadata ??= {};
					if (output.metadata.unstable_state !== void 0) assistantMessage.metadata.unstable_state = output.metadata.unstable_state;
					if (output.metadata.unstable_annotations) assistantMessage.metadata.unstable_annotations = [...assistantMessage.metadata.unstable_annotations ?? [], ...output.metadata.unstable_annotations];
					if (output.metadata.unstable_data) assistantMessage.metadata.unstable_data = [...assistantMessage.metadata.unstable_data ?? [], ...output.metadata.unstable_data];
					if (output.metadata.steps) assistantMessage.metadata.steps = [...assistantMessage.metadata.steps ?? [], ...output.metadata.steps];
					if (output.metadata.custom) assistantMessage.metadata.custom = {
						...assistantMessage.metadata.custom ?? {},
						...output.metadata.custom
					};
					if (output.metadata.timing) assistantMessage.metadata.timing = output.metadata.timing;
					if (output.metadata.modality) assistantMessage.metadata.modality = output.metadata.modality;
					if (output.metadata.submittedFeedback) assistantMessage.metadata.submittedFeedback = output.metadata.submittedFeedback;
					if (output.metadata.isOptimistic) assistantMessage.metadata.isOptimistic = true;
				}
				for (const part of content) {
					if (part.type === "tool-call" && part.toolCallId) {
						const existingIdx = toolCallIndices.get(part.toolCallId);
						if (existingIdx !== void 0) {
							const existing = assistantMessage.content[existingIdx];
							assistantMessage.content[existingIdx] = {
								...existing,
								...part,
								...mergeInnerMessages(existing, part)
							};
							continue;
						}
					}
					if (part.type === "reasoning" && "parentId" in part && part.parentId) {
						const existingIdx = reasoningIndices.get(part.parentId);
						if (existingIdx !== void 0) {
							const existing = assistantMessage.content[existingIdx];
							assistantMessage.content[existingIdx] = {
								...existing,
								text: `${existing.text}\n\n${part.text}`,
								...mergeInnerMessages(existing, part)
							};
							continue;
						}
					}
					const partIdx = assistantMessage.content.length;
					assistantMessage.content.push(part);
					if (part.type === "tool-call" && !isNaNToolCallId(part.toolCallId) && !toolCallIndices.has(part.toolCallId)) toolCallIndices.set(part.toolCallId, partIdx);
					else if (part.type === "reasoning" && "parentId" in part && part.parentId) reasoningIndices.set(part.parentId, partIdx);
				}
				break;
			default: throw new Error(`Unknown message role: ${role}`);
		}
	}
	return assistantMessage;
};
const chunkExternalMessages = (callbackResults, joinStrategy) => {
	const results = [];
	let isAssistant = false;
	let pendingNone = false;
	let inputs = [];
	let outputs = [];
	const flush = () => {
		if (outputs.length) results.push({
			inputs,
			outputs
		});
		inputs = [];
		outputs = [];
		isAssistant = false;
		pendingNone = false;
	};
	for (const callbackResult of callbackResults) for (const output of callbackResult.outputs) {
		const isVoice = output.role === "assistant" && output.metadata?.modality === "voice";
		if (pendingNone && output.role !== "tool" || !isAssistant || output.role === "user" || output.role === "system" || isVoice) flush();
		isAssistant = output.role === "assistant" || output.role === "tool";
		if (inputs.at(-1) !== callbackResult.input) inputs.push(callbackResult.input);
		outputs.push(output);
		if (output.role === "assistant" && (isVoice || output.convertConfig?.joinStrategy === "none" || joinStrategy === "none")) pendingNone = true;
	}
	flush();
	return results;
};
const shallowArrayEqual = (a, b) => {
	if (a.length !== b.length) return false;
	for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
	return true;
};
const createExternalMessageConversionCache = () => ({
	callbackCache: /* @__PURE__ */ new WeakMap(),
	chunkCache: /* @__PURE__ */ new WeakMap(),
	converterCache: new ThreadMessageConverter(),
	generatedFallbackMessages: /* @__PURE__ */ new WeakSet()
});
const convertExternalMessageChunk = (message, idx, chunkCount, isRunning, error, cache, cancelledMessageIds) => {
	const isLast = idx === chunkCount - 1;
	const joined = joinExternalMessages(message.outputs);
	const isCancelled = cancelledMessageIds !== void 0 && message.outputs.some((output) => output.role !== "tool" && output.id != null && cancelledMessageIds.has(output.id));
	const hasInterruptedToolCalls = typeof joined.content === "object" && joined.content.some(isInterruptedToolCall);
	const hasPendingToolCalls = typeof joined.content === "object" && joined.content.some(isPendingToolCall);
	const hasBackgroundToolCalls = typeof joined.content === "object" && joined.content.some(isBackgroundToolCall);
	const autoStatus = getAutoStatus(isLast, isRunning, hasInterruptedToolCalls, hasPendingToolCalls, isLast ? error : void 0, isCancelled, hasBackgroundToolCalls);
	const fallbackId = `${FALLBACK_ID_PREFIX}${idx}`;
	const cachedMessage = cache?.message;
	if (cachedMessage && (cachedMessage.role !== "assistant" || !isAutoStatus(cachedMessage.status) || cachedMessage.status === autoStatus || cachedMessage.status.type === "incomplete" && cachedMessage.status.reason === "error" && cachedMessage.status.error !== void 0 && autoStatus.type === "incomplete" && autoStatus.reason === "error" && autoStatus.error !== void 0 && (cachedMessage.status.error === autoStatus.error || isJSONValueEqual(cachedMessage.status.error, autoStatus.error)))) {
		const inputs = getExternalStoreMessages(cachedMessage);
		if (shallowArrayEqual(inputs, message.inputs)) {
			if (cache.generatedFallbackMessages.has(cachedMessage) && cachedMessage.id !== fallbackId) {
				const updated = {
					...cachedMessage,
					id: fallbackId
				};
				cache.generatedFallbackMessages.add(updated);
				bindExternalStoreMessage(updated, message.inputs);
				return updated;
			}
			return cachedMessage;
		}
	}
	const newMessage = fromThreadMessageLike(joined, fallbackId, autoStatus);
	if (cache && joined.id == null) cache.generatedFallbackMessages.add(newMessage);
	bindExternalStoreMessage(newMessage, message.inputs);
	return newMessage;
};
function createErrorAssistantMessage(error) {
	const msg = {
		id: generateErrorMessageId(),
		role: "assistant",
		content: [],
		status: {
			type: "incomplete",
			reason: "error",
			error
		},
		createdAt: /* @__PURE__ */ new Date(),
		metadata: {
			unstable_state: null,
			unstable_annotations: [],
			unstable_data: [],
			custom: {},
			steps: []
		}
	};
	bindExternalStoreMessage(msg, []);
	return msg;
}
const completeExternalMessageConversion = (messages, error) => {
	if (error !== void 0 && error !== null) {
		const lastMessage = messages.at(-1);
		if (!lastMessage || lastMessage.role !== "assistant") messages.push(createErrorAssistantMessage(error));
	}
	return messages;
};
const convertExternalMessages = (messages, callback, isRunning, metadata, joinStrategy, cache) => {
	const callbackResults = messages.map((message) => {
		let result = cache?.callbackCache.get(message);
		if (!result || result.metadata !== metadata || result.callback !== callback) {
			result = {
				...convertExternalMessageCallback(message, callback, metadata),
				metadata,
				callback
			};
			cache?.callbackCache.set(message, result);
		}
		return result;
	});
	const chunks = chunkExternalMessages(callbackResults, joinStrategy).map((message) => {
		const key = message.outputs[0];
		if (!key || !cache) return message;
		const cached = cache.chunkCache.get(key);
		if (cached && shallowArrayEqual(cached.outputs, message.outputs) && shallowArrayEqual(cached.inputs, message.inputs)) return cached;
		cache.chunkCache.set(key, message);
		return message;
	});
	const result = cache ? cache.converterCache.convertMessages(chunks, (cached, message, idx) => convertExternalMessageChunk(message, idx, chunks.length, isRunning, metadata.error, {
		message: cached,
		generatedFallbackMessages: cache.generatedFallbackMessages
	}, metadata.cancelledMessageIds)) : chunks.map((message, idx) => convertExternalMessageChunk(message, idx, chunks.length, isRunning, metadata.error, void 0, metadata.cancelledMessageIds));
	return completeExternalMessageConversion(result, metadata.error);
};
//#endregion
export { chunkExternalMessages, completeExternalMessageConversion, convertExternalMessageCallback, convertExternalMessageChunk, convertExternalMessages, createExternalMessageConversionCache, joinExternalMessages, shallowArrayEqual };
