import { generateId } from "../../utils/generateId.js";
import { PipeableTransformStream } from "../../utils/stream/PipeableTransformStream.js";
import { createSSEJsonDecoder } from "../../utils/stream/SSEJson.js";
import { AssistantTransformStream } from "../../utils/stream/AssistantTransformStream.js";
import { createToolCallPartRegistry } from "../tool-call-part-registry.js";
import { createChunkNormalizer } from "./chunk-normalizer.js";
import sjson from "secure-json-parse";
//#region src/core/serialization/ui-message-stream/UIMessageStream.ts
const isDataChunk = (chunk) => chunk.type.startsWith("data-");
/**
* Decodes AI SDK v6 UI Message Stream format into AssistantStreamChunks.
*/
var UIMessageStreamDecoder = class extends PipeableTransformStream {
	constructor(options = {}) {
		super((readable) => {
			const toolCallPartRegistry = createToolCallPartRegistry();
			const normalizer = createChunkNormalizer();
			let activeToolCallId;
			let currentMessageId;
			const transform = new AssistantTransformStream({
				transform(chunk, controller) {
					const type = chunk.type;
					if (isDataChunk(chunk)) {
						const name = chunk.type.slice(5);
						if (options.onData) options.onData({
							type: chunk.type,
							name,
							data: chunk.data,
							...chunk.transient !== void 0 && { transient: chunk.transient }
						});
						if (!chunk.transient) controller.enqueue({
							type: "data",
							path: [],
							data: [{
								name,
								data: chunk.data
							}]
						});
						return;
					}
					switch (type) {
						case "start":
							currentMessageId = chunk.messageId;
							controller.enqueue({
								type: "step-start",
								path: [],
								messageId: chunk.messageId
							});
							break;
						case "text-start":
						case "text-end":
						case "reasoning-start":
						case "reasoning-end": break;
						case "text-delta":
							controller.appendText(chunk.textDelta);
							break;
						case "reasoning-delta":
							controller.appendReasoning(chunk.delta);
							break;
						case "source":
							controller.appendSource({
								type: "source",
								sourceType: chunk.source.sourceType,
								id: chunk.source.id,
								url: chunk.source.url,
								...chunk.source.title && { title: chunk.source.title }
							});
							break;
						case "file":
							controller.appendFile({
								type: "file",
								mimeType: chunk.file.mimeType,
								data: chunk.file.data
							});
							break;
						case "tool-call-start":
							if (activeToolCallId !== void 0) {
								toolCallPartRegistry.closeArgsText(toolCallPartRegistry.get(activeToolCallId));
								activeToolCallId = void 0;
							}
							toolCallPartRegistry.start(chunk.toolCallId, () => controller.addToolCallPart({
								toolCallId: chunk.toolCallId,
								toolName: chunk.toolName
							}));
							activeToolCallId = chunk.toolCallId;
							break;
						case "tool-call-delta":
							if (activeToolCallId !== void 0) toolCallPartRegistry.appendArgsText(toolCallPartRegistry.get(activeToolCallId), chunk.argsText);
							break;
						case "tool-call-end":
							if (activeToolCallId !== void 0) {
								toolCallPartRegistry.closeArgsText(toolCallPartRegistry.get(activeToolCallId));
								activeToolCallId = void 0;
							}
							break;
						case "tool-result": {
							if (chunk.toolCallId === activeToolCallId) activeToolCallId = void 0;
							const toolCallController = toolCallPartRegistry.tryGet(chunk.toolCallId);
							if (!toolCallController) throw new Error(`Encountered tool result with unknown id: ${chunk.toolCallId}`);
							toolCallPartRegistry.setResponse(toolCallController, {
								result: chunk.result,
								isError: chunk.isError ?? false,
								...chunk.isPreliminary ? { isPreliminary: true } : {},
								...chunk.messages !== void 0 ? { messages: chunk.messages } : {}
							});
							break;
						}
						case "start-step":
							controller.enqueue({
								type: "step-start",
								path: [],
								messageId: chunk.messageId ?? currentMessageId ?? generateId()
							});
							break;
						case "finish-step":
							controller.enqueue({
								type: "step-finish",
								path: [],
								finishReason: chunk.finishReason,
								usage: chunk.usage,
								isContinued: chunk.isContinued
							});
							break;
						case "finish":
							controller.enqueue({
								type: "message-finish",
								path: [],
								finishReason: chunk.finishReason,
								usage: chunk.usage
							});
							break;
						case "error": controller.enqueue({
							type: "error",
							path: [],
							error: chunk.errorText
						});
					}
				},
				flush() {
					if (activeToolCallId !== void 0) toolCallPartRegistry.closeArgsText(toolCallPartRegistry.get(activeToolCallId));
					toolCallPartRegistry.closeAll();
				}
			});
			return createSSEJsonDecoder({
				strict: true,
				parse(data, controller) {
					let chunk;
					try {
						chunk = sjson.parse(data);
					} catch {
						chunk = void 0;
					}
					if (typeof chunk !== "object" || chunk === null || Array.isArray(chunk) || typeof chunk.type !== "string") {
						console.warn(`Dropped invalid UIMessageStream chunk: ${data.slice(0, 200)}`);
						return;
					}
					normalizer.normalize(chunk, controller);
				},
				done: {
					marker: "[DONE]",
					onDone(controller) {
						normalizer.flush(controller);
					},
					onMissing() {
						throw new Error("Stream ended abruptly without receiving [DONE] marker");
					}
				}
			})(readable).pipeThrough(transform);
		});
	}
};
//#endregion
export { UIMessageStreamDecoder };
