import { ToolResponse } from "./ToolResponse.js";
import { PipeableTransformStream } from "../utils/stream/PipeableTransformStream.js";
import { withPromiseOrValue } from "../utils/withPromiseOrValue.js";
import { enqueueIfOpen } from "../utils/stream/controller-guards.js";
import { AssistantMetaTransformStream } from "../utils/stream/AssistantMetaTransformStream.js";
import { ToolCallReaderImpl } from "./ToolCallReader.js";
import sjson from "secure-json-parse";
//#region src/core/tool/ToolExecutionStream.ts
const TOOL_EXECUTION_ID = Symbol.for("assistant-stream.tool-execution-id");
const invokeExecutionCallback = (name, callback, toolCallId, toolName, executionId) => {
	try {
		const result = callback?.(toolCallId, toolName, executionId);
		Promise.resolve(result).catch((error) => {
			console.error(`[assistant-stream] ${name} callback threw an error`, error);
		});
	} catch (error) {
		console.error(`[assistant-stream] ${name} callback threw an error`, error);
	}
};
const pathKey = (path) => path.join(",");
const withExecutionId = (chunk, executionId) => {
	const result = { ...chunk };
	Object.defineProperty(result, TOOL_EXECUTION_ID, {
		value: executionId,
		enumerable: true
	});
	return result;
};
var ToolExecutionStream = class extends PipeableTransformStream {
	constructor(options) {
		const internalOptions = options;
		const toolCallPromises = /* @__PURE__ */ new Map();
		const toolCallControllers = /* @__PURE__ */ new Map();
		const toolCallIdsWithBackendResult = /* @__PURE__ */ new Set();
		const executionIdsByPath = /* @__PURE__ */ new Map();
		let nextPartIndex = 0;
		super((readable) => {
			const transform = new TransformStream({
				async transform(chunk, controller) {
					const executionId = executionIdsByPath.get(pathKey(chunk.path));
					if (chunk.type !== "part-finish" || chunk.meta.type !== "tool-call") controller.enqueue(executionId ? withExecutionId(chunk, executionId) : chunk);
					switch (chunk.type) {
						case "part-start": {
							const partIndex = nextPartIndex;
							nextPartIndex += 1;
							if (chunk.part.type === "tool-call") {
								const reader = new ToolCallReaderImpl();
								const executionId = Symbol();
								executionIdsByPath.set(String(partIndex), executionId);
								toolCallControllers.set(executionId, reader);
								internalOptions.streamCall({
									reader,
									toolCallId: chunk.part.toolCallId,
									toolName: chunk.part.toolName,
									executionId
								});
							}
							break;
						}
						case "text-delta":
							if (chunk.meta.type === "tool-call") {
								const executionId = executionIdsByPath.get(pathKey(chunk.path));
								const controller = executionId ? toolCallControllers.get(executionId) : void 0;
								if (!controller) throw new Error("No controller found for tool call");
								await controller.appendArgsTextDelta(chunk.textDelta);
							}
							break;
						case "result": {
							if (chunk.meta.type !== "tool-call") break;
							const executionId = executionIdsByPath.get(pathKey(chunk.path));
							const controller = executionId ? toolCallControllers.get(executionId) : void 0;
							if (!controller) throw new Error("No controller found for tool call");
							toolCallIdsWithBackendResult.add(executionId);
							if (chunk.isPreliminary) break;
							controller.setResponse(new ToolResponse({
								result: chunk.result,
								artifact: chunk.artifact,
								isError: chunk.isError,
								modelContent: chunk.modelContent,
								messages: chunk.messages
							}));
							break;
						}
						case "tool-call-args-text-finish": {
							if (chunk.meta.type !== "tool-call") break;
							const { toolCallId, toolName } = chunk.meta;
							const executionId = executionIdsByPath.get(pathKey(chunk.path));
							const streamController = executionId ? toolCallControllers.get(executionId) : void 0;
							if (!streamController) throw new Error("No controller found for tool call");
							await streamController.finishArgsText();
							if (toolCallIdsWithBackendResult.has(executionId)) break;
							let isExecuting = false;
							const promise = withPromiseOrValue(() => {
								let args;
								try {
									args = sjson.parse(streamController.argsText);
								} catch (e) {
									throw new Error(`Function parameter parsing failed. ${JSON.stringify(e.message)}`);
								}
								const executeResult = internalOptions.execute({
									toolCallId,
									toolName,
									args,
									executionId
								});
								if (executeResult !== void 0) {
									isExecuting = true;
									invokeExecutionCallback("onExecutionStart", internalOptions.onExecutionStart, toolCallId, toolName, executionId);
								}
								return executeResult;
							}, (c) => {
								if (isExecuting) invokeExecutionCallback("onExecutionEnd", internalOptions.onExecutionEnd, toolCallId, toolName, executionId);
								if (c === void 0) return;
								const result = new ToolResponse({
									artifact: c.artifact,
									result: c.result,
									isError: c.isError,
									messages: c.messages,
									modelContent: c.modelContent
								});
								streamController.setResponse(result);
								enqueueIfOpen(controller, withExecutionId({
									type: "result",
									path: chunk.path,
									...result
								}, executionId));
							}, (e) => {
								if (isExecuting) invokeExecutionCallback("onExecutionEnd", internalOptions.onExecutionEnd, toolCallId, toolName, executionId);
								const result = new ToolResponse({
									result: String(e),
									isError: true
								});
								streamController.setResponse(result);
								enqueueIfOpen(controller, withExecutionId({
									type: "result",
									path: chunk.path,
									...result
								}, executionId));
							});
							if (promise) toolCallPromises.set(executionId, promise);
							break;
						}
						case "part-finish": {
							if (chunk.meta.type !== "tool-call") break;
							const executionId = executionIdsByPath.get(pathKey(chunk.path));
							const toolCallPromise = executionId ? toolCallPromises.get(executionId) : void 0;
							const cleanup = () => {
								if (!executionId) return;
								toolCallPromises.delete(executionId);
								toolCallControllers.delete(executionId);
								toolCallIdsWithBackendResult.delete(executionId);
								executionIdsByPath.delete(pathKey(chunk.path));
							};
							if (toolCallPromise) toolCallPromise.then(() => {
								cleanup();
								enqueueIfOpen(controller, chunk);
							});
							else {
								cleanup();
								controller.enqueue(chunk);
							}
						}
					}
				},
				async flush() {
					await Promise.all(toolCallPromises.values());
				}
			});
			return readable.pipeThrough(new AssistantMetaTransformStream()).pipeThrough(transform);
		});
	}
};
//#endregion
export { ToolExecutionStream };
