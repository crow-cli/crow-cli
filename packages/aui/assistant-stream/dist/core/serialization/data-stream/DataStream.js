import { PipeableTransformStream } from "../../utils/stream/PipeableTransformStream.js";
import { AssistantTransformStream } from "../../utils/stream/AssistantTransformStream.js";
import { DataStreamStreamChunkType } from "./chunk-types.js";
import { LineDecoderStream } from "../../utils/stream/LineDecoderStream.js";
import { DataStreamChunkDecoder, DataStreamChunkEncoder } from "./serialization.js";
import { AssistantMetaTransformStream } from "../../utils/stream/AssistantMetaTransformStream.js";
import { createToolCallPartRegistry } from "../tool-call-part-registry.js";
//#region src/core/serialization/data-stream/DataStream.ts
var DataStreamEncoder = class extends PipeableTransformStream {
	headers = new Headers({
		"Content-Type": "text/plain; charset=utf-8",
		"x-vercel-ai-data-stream": "v1"
	});
	constructor() {
		super((readable) => {
			const openToolCallArgs = /* @__PURE__ */ new Map();
			const finishToolCallArgs = (controller, toolCallId) => {
				const hasArgsText = openToolCallArgs.get(toolCallId);
				if (hasArgsText === void 0) return;
				openToolCallArgs.delete(toolCallId);
				controller.enqueue({
					type: DataStreamStreamChunkType.ToolCallArgsTextDelta,
					value: {
						toolCallId,
						argsTextDelta: hasArgsText ? "" : "{}",
						isFinal: true
					}
				});
			};
			const finishOpenToolCallArgs = (controller) => {
				for (const toolCallId of openToolCallArgs.keys()) finishToolCallArgs(controller, toolCallId);
			};
			const transform = new TransformStream({
				transform(chunk, controller) {
					const type = chunk.type;
					switch (type) {
						case "part-start": {
							const part = chunk.part;
							if (part.type === "tool-call") {
								const { type, ...value } = part;
								controller.enqueue({
									type: DataStreamStreamChunkType.StartToolCall,
									value
								});
								openToolCallArgs.set(part.toolCallId, false);
							}
							if (part.type === "source") {
								const { type, ...value } = part;
								controller.enqueue({
									type: DataStreamStreamChunkType.Source,
									value
								});
							}
							if (part.type === "file") {
								const { type, ...value } = part;
								controller.enqueue({
									type: DataStreamStreamChunkType.File,
									value
								});
							}
							if (part.type === "data") {
								const { type, ...value } = part;
								controller.enqueue({
									type: DataStreamStreamChunkType.AuiDataPart,
									value
								});
							}
							if (part.type === "reasoning" && part.unstable_summary !== void 0) controller.enqueue({
								type: DataStreamStreamChunkType.AuiReasoningPartStart,
								value: {
									unstable_summary: part.unstable_summary,
									...part.parentId !== void 0 ? { parentId: part.parentId } : {}
								}
							});
							break;
						}
						case "text-delta": {
							const part = chunk.meta;
							switch (part.type) {
								case "text":
									if (part.parentId) controller.enqueue({
										type: DataStreamStreamChunkType.AuiTextDelta,
										value: {
											textDelta: chunk.textDelta,
											parentId: part.parentId
										}
									});
									else controller.enqueue({
										type: DataStreamStreamChunkType.TextDelta,
										value: chunk.textDelta
									});
									break;
								case "reasoning":
									if (part.parentId) controller.enqueue({
										type: DataStreamStreamChunkType.AuiReasoningDelta,
										value: {
											reasoningDelta: chunk.textDelta,
											parentId: part.parentId
										}
									});
									else controller.enqueue({
										type: DataStreamStreamChunkType.ReasoningDelta,
										value: chunk.textDelta
									});
									break;
								case "tool-call":
									if (!openToolCallArgs.has(part.toolCallId)) break;
									openToolCallArgs.set(part.toolCallId, true);
									controller.enqueue({
										type: DataStreamStreamChunkType.ToolCallArgsTextDelta,
										value: {
											toolCallId: part.toolCallId,
											argsTextDelta: chunk.textDelta
										}
									});
									break;
								default: throw new Error(`Unsupported part type for text-delta: ${part.type}`);
							}
							break;
						}
						case "result": {
							const part = chunk.meta;
							if (part.type !== "tool-call") throw new Error(`Result chunk on non-tool-call part not supported: ${part.type}`);
							openToolCallArgs.delete(part.toolCallId);
							controller.enqueue({
								type: DataStreamStreamChunkType.ToolCallResult,
								value: {
									toolCallId: part.toolCallId,
									result: chunk.result,
									artifact: chunk.artifact,
									...chunk.isError ? { isError: chunk.isError } : {},
									...chunk.isPreliminary ? { isPreliminary: true } : {},
									...chunk.modelContent !== void 0 ? { modelContent: chunk.modelContent } : {}
								}
							});
							break;
						}
						case "step-start": {
							const { type, ...value } = chunk;
							controller.enqueue({
								type: DataStreamStreamChunkType.StartStep,
								value
							});
							break;
						}
						case "step-finish": {
							finishOpenToolCallArgs(controller);
							const { type, ...value } = chunk;
							controller.enqueue({
								type: DataStreamStreamChunkType.FinishStep,
								value
							});
							break;
						}
						case "message-finish": {
							finishOpenToolCallArgs(controller);
							const { type, ...value } = chunk;
							controller.enqueue({
								type: DataStreamStreamChunkType.FinishMessage,
								value
							});
							break;
						}
						case "error":
							if (chunk.severity !== "warning" && chunk.severity !== "info") finishOpenToolCallArgs(controller);
							controller.enqueue({
								type: DataStreamStreamChunkType.Error,
								value: chunk.error
							});
							break;
						case "annotations":
							controller.enqueue({
								type: DataStreamStreamChunkType.Annotation,
								value: chunk.annotations
							});
							break;
						case "data":
							controller.enqueue({
								type: DataStreamStreamChunkType.Data,
								value: chunk.data
							});
							break;
						case "update-state":
							controller.enqueue({
								type: DataStreamStreamChunkType.AuiUpdateStateOperations,
								value: chunk.operations
							});
							break;
						case "tool-call-args-text-finish":
							finishToolCallArgs(controller, chunk.meta.toolCallId);
							break;
						case "part-finish":
							if (chunk.meta.type === "tool-call") finishToolCallArgs(controller, chunk.meta.toolCallId);
							break;
						default: throw new Error(`Unsupported chunk type: ${type}`);
					}
				},
				flush(controller) {
					finishOpenToolCallArgs(controller);
				}
			});
			return readable.pipeThrough(new AssistantMetaTransformStream()).pipeThrough(transform).pipeThrough(new DataStreamChunkEncoder()).pipeThrough(new TextEncoderStream());
		});
	}
};
var DataStreamDecoder = class extends PipeableTransformStream {
	constructor(options = {}) {
		const strict = options.strict ?? true;
		super((readable) => {
			const toolCallPartRegistry = createToolCallPartRegistry();
			const warnedDroppedArgs = /* @__PURE__ */ new Set();
			const loggedDrops = /* @__PURE__ */ new Set();
			const logDropped = (key, message) => {
				if (loggedDrops.has(key) || loggedDrops.size >= 20) return;
				loggedDrops.add(key);
				console.error(message);
			};
			const closeOpenToolCallArgs = () => {
				toolCallPartRegistry.closeOpenArgsText();
			};
			const transform = new AssistantTransformStream({
				strict,
				transform(chunk, controller) {
					const { type, value } = chunk;
					switch (type) {
						case DataStreamStreamChunkType.ReasoningDelta:
							controller.appendReasoning(value);
							break;
						case DataStreamStreamChunkType.TextDelta:
							controller.appendText(value);
							break;
						case DataStreamStreamChunkType.AuiTextDelta:
							controller.withParentId(value.parentId).appendText(value.textDelta);
							break;
						case DataStreamStreamChunkType.AuiReasoningPartStart:
							(value.parentId ? controller.withParentId(value.parentId) : controller).appendReasoning("", { ...value.unstable_summary !== void 0 ? { unstable_summary: value.unstable_summary } : {} });
							break;
						case DataStreamStreamChunkType.AuiReasoningDelta:
							controller.withParentId(value.parentId).appendReasoning(value.reasoningDelta);
							break;
						case DataStreamStreamChunkType.StartToolCall: {
							const { toolCallId, toolName, parentId } = value;
							const ctrl = parentId ? controller.withParentId(parentId) : controller;
							if (toolCallPartRegistry.tryGet(toolCallId)) {
								if (strict) throw new Error(`Encountered duplicate tool call id: ${toolCallId}`);
								logDropped(`duplicate:${toolCallId}`, `Dropped duplicate tool call start: ${toolCallId}`);
								break;
							}
							toolCallPartRegistry.start(toolCallId, () => ctrl.addToolCallPart({
								toolCallId,
								toolName
							}));
							break;
						}
						case DataStreamStreamChunkType.ToolCallArgsTextDelta: {
							const { toolCallId, argsTextDelta, isFinal } = value;
							const toolCallController = toolCallPartRegistry.tryGet(toolCallId);
							if (!toolCallController) {
								if (strict) throw new Error(`Encountered tool call with unknown id: ${toolCallId}`);
								logDropped(`args:${toolCallId}`, `Dropped args delta for unknown tool call: ${toolCallId}`);
								break;
							}
							if (toolCallPartRegistry.isArgsTextClosed(toolCallController)) {
								if (!warnedDroppedArgs.has(toolCallId)) {
									warnedDroppedArgs.add(toolCallId);
									console.warn(`Dropped tool-call args delta for closed args stream: ${toolCallId}`);
								}
								break;
							}
							if (argsTextDelta.length > 0) toolCallPartRegistry.appendArgsText(toolCallController, argsTextDelta);
							if (isFinal === true) toolCallPartRegistry.closeArgsText(toolCallController);
							break;
						}
						case DataStreamStreamChunkType.ToolCallResult: {
							const { toolCallId, artifact, result, isError, isPreliminary, modelContent } = value;
							const toolCallController = toolCallPartRegistry.tryGet(toolCallId);
							if (!toolCallController) {
								if (strict) throw new Error(`Encountered tool call result with unknown id: ${toolCallId}`);
								logDropped(`result:${toolCallId}`, `Dropped result for unknown tool call: ${toolCallId}`);
								break;
							}
							toolCallPartRegistry.setResponse(toolCallController, {
								artifact,
								result,
								isError,
								...isPreliminary ? { isPreliminary: true } : {},
								...modelContent !== void 0 ? { modelContent } : {}
							});
							break;
						}
						case DataStreamStreamChunkType.ToolCall: {
							const { toolCallId, toolName, args } = value;
							const toolCallController = toolCallPartRegistry.tryGet(toolCallId);
							if (toolCallController) toolCallPartRegistry.closeArgsText(toolCallController);
							else {
								const toolCallController = toolCallPartRegistry.start(toolCallId, () => controller.addToolCallPart({
									toolCallId,
									toolName
								}));
								if (args !== void 0) toolCallPartRegistry.appendArgsText(toolCallController, JSON.stringify(args));
								toolCallPartRegistry.closeArgsText(toolCallController);
							}
							break;
						}
						case DataStreamStreamChunkType.FinishMessage:
							closeOpenToolCallArgs();
							controller.enqueue({
								type: "message-finish",
								path: [],
								...value
							});
							break;
						case DataStreamStreamChunkType.StartStep:
							controller.enqueue({
								type: "step-start",
								path: [],
								...value
							});
							break;
						case DataStreamStreamChunkType.FinishStep:
							closeOpenToolCallArgs();
							controller.enqueue({
								type: "step-finish",
								path: [],
								...value
							});
							break;
						case DataStreamStreamChunkType.Data:
							controller.enqueue({
								type: "data",
								path: [],
								data: value
							});
							break;
						case DataStreamStreamChunkType.Annotation:
							controller.enqueue({
								type: "annotations",
								path: [],
								annotations: value
							});
							break;
						case DataStreamStreamChunkType.Source: {
							const { parentId, ...sourceData } = value;
							(parentId ? controller.withParentId(parentId) : controller).appendSource({
								type: "source",
								...sourceData
							});
							break;
						}
						case DataStreamStreamChunkType.Error:
							controller.enqueue({
								type: "error",
								path: [],
								error: value
							});
							break;
						case DataStreamStreamChunkType.File: {
							const { parentId, ...fileData } = value;
							(parentId ? controller.withParentId(parentId) : controller).appendFile({
								type: "file",
								...fileData
							});
							break;
						}
						case DataStreamStreamChunkType.AuiDataPart:
							controller.appendData({
								type: "data",
								...value
							});
							break;
						case DataStreamStreamChunkType.AuiUpdateStateOperations:
							controller.enqueue({
								type: "update-state",
								path: [],
								operations: value
							});
							break;
						case DataStreamStreamChunkType.ReasoningSignature:
						case DataStreamStreamChunkType.RedactedReasoning: break;
						default: {
							const exhaustiveCheck = type;
							if (strict) throw new Error(`unsupported chunk type: ${exhaustiveCheck}`);
							logDropped(`type:${exhaustiveCheck}`, `Dropped unsupported chunk type: ${exhaustiveCheck}`);
						}
					}
				},
				flush() {
					closeOpenToolCallArgs();
					toolCallPartRegistry.closeAll();
				}
			});
			return readable.pipeThrough(new TextDecoderStream()).pipeThrough(new LineDecoderStream()).pipeThrough(new DataStreamChunkDecoder()).pipeThrough(transform);
		});
	}
};
//#endregion
export { DataStreamDecoder, DataStreamEncoder };
