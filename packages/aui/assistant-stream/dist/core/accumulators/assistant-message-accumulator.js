import { generateId } from "../utils/generateId.js";
import { parsePartialJsonObject } from "../../utils/json/parse-partial-json-object.js";
import { GorpStreamAccumulator } from "../gorp/GorpStreamAccumulator.js";
import { TimingTracker } from "./TimingTracker.js";
//#region src/core/accumulators/assistant-message-accumulator.ts
/**
* Object spread materializes the deprecated `content` alias into a data
* property, so it is redefined after `parts` to keep tracking the replacement.
*/
const withParts = (message, parts) => ({
	...message,
	parts,
	get content() {
		return this.parts;
	}
});
const appendPart = (message, part) => withParts(message, [...message.parts, part]);
const createInitialMessage = ({ unstable_state = null } = {}) => ({
	role: "assistant",
	status: { type: "running" },
	parts: [],
	get content() {
		return this.parts;
	},
	metadata: {
		unstable_state,
		unstable_data: [],
		unstable_annotations: [],
		steps: [],
		custom: {}
	}
});
const MAX_WARNED_KEYS = 16;
const updatePartForPath = (message, chunk, warnOnce, updater) => {
	const part = chunk.path.length === 1 ? message.parts[chunk.path[0]] : void 0;
	if (part === void 0) {
		warnOnce(`no-part:${chunk.type}`, `Dropped ${chunk.type} chunk: no part at path [${chunk.path.join(", ")}]`);
		return message;
	}
	const partIndex = chunk.path[0];
	const updatedPart = updater(part);
	if (updatedPart === part) return message;
	return withParts(message, [
		...message.parts.slice(0, partIndex),
		updatedPart,
		...message.parts.slice(partIndex + 1)
	]);
};
const handlePartStart = (message, chunk, warnOnce) => {
	const partInit = chunk.part;
	if (partInit.type === "text" || partInit.type === "reasoning") {
		const newTextPart = {
			type: partInit.type,
			text: "",
			status: { type: "running" },
			...partInit.type === "reasoning" && partInit.unstable_summary !== void 0 ? { unstable_summary: partInit.unstable_summary } : void 0,
			...partInit.parentId && { parentId: partInit.parentId }
		};
		return appendPart(message, newTextPart);
	} else if (partInit.type === "tool-call") {
		const newToolCallPart = {
			type: "tool-call",
			state: "partial-call",
			status: {
				type: "running",
				isArgsComplete: false
			},
			toolCallId: partInit.toolCallId,
			toolName: partInit.toolName,
			argsText: "",
			args: {},
			timing: { startedAt: Date.now() },
			...partInit.parentId && { parentId: partInit.parentId }
		};
		return appendPart(message, newToolCallPart);
	} else if (partInit.type === "source") {
		const newSourcePart = {
			type: "source",
			sourceType: partInit.sourceType,
			id: partInit.id,
			url: partInit.url,
			...partInit.title ? { title: partInit.title } : void 0,
			...partInit.parentId && { parentId: partInit.parentId }
		};
		return appendPart(message, newSourcePart);
	} else if (partInit.type === "file") {
		const newFilePart = {
			type: "file",
			mimeType: partInit.mimeType,
			data: partInit.data,
			...partInit.parentId && { parentId: partInit.parentId }
		};
		return appendPart(message, newFilePart);
	} else if (partInit.type === "data") {
		const newDataPart = {
			type: "data",
			name: partInit.name,
			data: partInit.data,
			...partInit.parentId && { parentId: partInit.parentId }
		};
		return appendPart(message, newDataPart);
	} else {
		const unsupportedType = String(partInit.type);
		warnOnce(`unsupported-part-start:${unsupportedType}`, `Unsupported part-start type ${unsupportedType}: inserting an empty reasoning part to preserve part indices`);
		return appendPart(message, {
			type: "reasoning",
			text: "",
			status: { type: "running" }
		});
	}
};
const handleToolCallArgsTextFinish = (message, chunk, warnOnce) => {
	return updatePartForPath(message, chunk, warnOnce, (part) => {
		if (part.type !== "tool-call") {
			warnOnce("wrong-part:tool-call-args-text-finish", "Dropped tool-call-args-text-finish chunk: part is not a tool-call");
			return part;
		}
		if (part.state !== "partial-call") return part;
		return {
			...part,
			state: "call",
			status: part.status.type === "running" ? {
				type: "running",
				isArgsComplete: true
			} : part.status
		};
	});
};
const handlePartFinish = (message, chunk, warnOnce) => {
	return updatePartForPath(message, chunk, warnOnce, (part) => {
		if (part.type === "tool-call" && part.isPreliminary) return part;
		return {
			...part,
			status: {
				type: "complete",
				reason: "unknown"
			}
		};
	});
};
const handleTextDelta = (message, chunk, warnOnce) => {
	return updatePartForPath(message, chunk, warnOnce, (part) => {
		if (part.type === "text" || part.type === "reasoning") return {
			...part,
			text: part.text + chunk.textDelta
		};
		else if (part.type === "tool-call") {
			const newArgsText = part.argsText + chunk.textDelta;
			const newArgs = parsePartialJsonObject(newArgsText) ?? part.args;
			return {
				...part,
				argsText: newArgsText,
				args: newArgs
			};
		} else {
			warnOnce("wrong-part:text-delta", "Dropped text-delta chunk: part is neither text nor tool-call");
			return part;
		}
	});
};
const handleResult = (message, chunk, warnOnce) => {
	return updatePartForPath(message, chunk, warnOnce, (part) => {
		if (part.type === "tool-call") {
			const isPreliminary = chunk.isPreliminary === true;
			const runningStatus = part.status.type === "running" ? part.status : {
				type: "running",
				isArgsComplete: part.state !== "partial-call"
			};
			if (isPreliminary) {
				if (part.state === "result") return part;
				return {
					...part,
					state: part.state === "partial-call" ? "partial-call" : "call",
					...chunk.artifact !== void 0 ? { artifact: chunk.artifact } : {},
					result: chunk.result,
					isError: chunk.isError ?? false,
					isPreliminary: true,
					...chunk.modelContent !== void 0 ? { modelContent: chunk.modelContent } : {},
					...chunk.messages !== void 0 ? { messages: chunk.messages } : {},
					status: runningStatus
				};
			}
			const { isPreliminary: _isPreliminary, ...partWithoutPreliminary } = part;
			return {
				...partWithoutPreliminary,
				state: "result",
				...part.timing !== void 0 ? { timing: {
					...part.timing,
					completedAt: part.timing.completedAt ?? Date.now()
				} } : {},
				...chunk.artifact !== void 0 ? { artifact: chunk.artifact } : {},
				result: chunk.result,
				isError: chunk.isError ?? false,
				...chunk.modelContent !== void 0 ? { modelContent: chunk.modelContent } : {},
				...chunk.messages !== void 0 ? { messages: chunk.messages } : {},
				status: {
					type: "complete",
					reason: "stop"
				}
			};
		} else {
			warnOnce("wrong-part:result", "Dropped result chunk: part is not a tool-call");
			return part;
		}
	});
};
const handleMessageFinish = (message, chunk) => {
	if (message.status?.type === "incomplete" && message.status?.reason === "error") return message;
	const newStatus = getStatus(chunk);
	return {
		...message,
		status: newStatus
	};
};
const getStatus = (chunk) => {
	if (chunk.finishReason === "tool-calls") return {
		type: "requires-action",
		reason: "tool-calls"
	};
	else if (chunk.finishReason === "stop" || chunk.finishReason === "unknown") return {
		type: "complete",
		reason: chunk.finishReason
	};
	else return {
		type: "incomplete",
		reason: chunk.finishReason
	};
};
const handleAnnotations = (message, chunk) => {
	return {
		...message,
		metadata: {
			...message.metadata,
			unstable_annotations: [...message.metadata.unstable_annotations, ...chunk.annotations]
		}
	};
};
const handleData = (message, chunk) => {
	return {
		...message,
		metadata: {
			...message.metadata,
			unstable_data: [...message.metadata.unstable_data, ...chunk.data]
		}
	};
};
const handleStepStart = (message, chunk) => {
	return {
		...message,
		metadata: {
			...message.metadata,
			steps: [...message.metadata.steps, {
				state: "started",
				messageId: chunk.messageId
			}]
		}
	};
};
const handleStepFinish = (message, chunk) => {
	const steps = message.metadata.steps.slice();
	const lastIndex = steps.length - 1;
	if (steps.length > 0 && steps[lastIndex]?.state === "started") steps[lastIndex] = {
		...steps[lastIndex],
		state: "finished",
		finishReason: chunk.finishReason,
		usage: chunk.usage,
		isContinued: chunk.isContinued
	};
	else steps.push({
		state: "finished",
		messageId: generateId(),
		finishReason: chunk.finishReason,
		usage: chunk.usage,
		isContinued: chunk.isContinued
	});
	return {
		...message,
		metadata: {
			...message.metadata,
			steps
		}
	};
};
const handleErrorChunk = (message, chunk) => {
	const severity = chunk.severity === "critical" || chunk.severity === "warning" || chunk.severity === "info" ? chunk.severity : void 0;
	return {
		...message,
		status: {
			type: "incomplete",
			reason: "error",
			error: {
				code: chunk.code ?? "unknown",
				message: chunk.error ?? "unknown error",
				...severity !== void 0 && { severity }
			}
		}
	};
};
const handleUpdateState = (message, chunk, acc) => {
	acc.append(chunk.operations);
	return {
		...message,
		metadata: {
			...message.metadata,
			unstable_state: acc.state
		}
	};
};
const sumFinishedStepOutputTokens = (message) => {
	let outputTokens = 0;
	for (const step of message.metadata.steps) if (step.state === "finished" && step.usage) outputTokens += step.usage.outputTokens;
	return outputTokens;
};
const computeTiming = (tracker, message, finalOutputTokens = 0) => {
	const outputTokens = finalOutputTokens > 0 ? finalOutputTokens : sumFinishedStepOutputTokens(message);
	if (outputTokens > 0) return tracker.getTiming(outputTokens);
	let totalText = "";
	for (const part of message.parts) if (part.type === "text" || part.type === "reasoning") totalText += part.text;
	return tracker.getTiming(void 0, totalText || void 0);
};
const throttleCallback = (callback) => {
	let hasScheduled = false;
	return () => {
		if (hasScheduled) return;
		hasScheduled = true;
		queueMicrotask(() => {
			hasScheduled = false;
			callback();
		});
	};
};
var AssistantMessageAccumulator = class extends TransformStream {
	constructor({ initialMessage, throttle, onError, strict = true } = {}) {
		let message = initialMessage ?? createInitialMessage();
		let stateAccumulator;
		let finalOutputTokens;
		const tracker = new TimingTracker();
		const warnedKeys = /* @__PURE__ */ new Set();
		const warnOnce = (key, warning) => {
			if (warnedKeys.has(key) || warnedKeys.size >= MAX_WARNED_KEYS) return;
			warnedKeys.add(key);
			console.warn(warning);
		};
		let controller;
		const emitChunk = throttle ? throttleCallback(() => {
			controller?.enqueue(message);
		}) : () => {
			controller?.enqueue(message);
		};
		super({
			start(c) {
				controller = c;
			},
			transform(chunk) {
				tracker.recordChunk();
				const type = chunk.type;
				switch (type) {
					case "part-start":
						message = handlePartStart(message, chunk, warnOnce);
						if (chunk.part.type === "tool-call") tracker.recordToolCallStart(chunk.part.toolCallId);
						break;
					case "tool-call-args-text-finish":
						message = handleToolCallArgsTextFinish(message, chunk, warnOnce);
						break;
					case "part-finish":
						message = handlePartFinish(message, chunk, warnOnce);
						break;
					case "text-delta": {
						const next = handleTextDelta(message, chunk, warnOnce);
						if (next !== message) tracker.recordFirstToken();
						message = next;
						break;
					}
					case "result":
						message = handleResult(message, chunk, warnOnce);
						break;
					case "message-finish":
						finalOutputTokens = chunk.usage?.outputTokens;
						message = handleMessageFinish(message, chunk);
						break;
					case "annotations":
						message = handleAnnotations(message, chunk);
						break;
					case "data":
						message = handleData(message, chunk);
						break;
					case "step-start":
						message = handleStepStart(message, chunk);
						break;
					case "step-finish":
						message = handleStepFinish(message, chunk);
						break;
					case "error":
						message = handleErrorChunk(message, chunk);
						onError?.(chunk.error);
						break;
					case "update-state":
						stateAccumulator ??= new GorpStreamAccumulator(message.metadata.unstable_state, { strict });
						message = handleUpdateState(message, chunk, stateAccumulator);
						break;
					default: throw new Error(`Unsupported chunk type: ${type}`);
				}
				if (message.status.type !== "running") message = {
					...message,
					metadata: {
						...message.metadata,
						timing: computeTiming(tracker, message, finalOutputTokens)
					}
				};
				emitChunk();
			},
			flush(controller) {
				if (message.status?.type === "running") {
					const requiresAction = message.parts?.some((part) => part.type === "tool-call" && (part.state === "call" || part.state === "partial-call") && (part.result === void 0 || part.isPreliminary)) ?? false;
					message = handleMessageFinish(message, {
						type: "message-finish",
						path: [],
						finishReason: requiresAction ? "tool-calls" : "unknown",
						usage: {
							inputTokens: 0,
							outputTokens: 0
						}
					});
					message = {
						...message,
						metadata: {
							...message.metadata,
							timing: computeTiming(tracker, message, finalOutputTokens)
						}
					};
					controller.enqueue(message);
				}
			}
		});
	}
};
//#endregion
export { AssistantMessageAccumulator, createInitialMessage };
