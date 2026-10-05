import { ToolResponse } from "./ToolResponse.js";
import { ToolExecutionStream } from "./ToolExecutionStream.js";
//#region src/core/tool/toolResultStream.ts
const TOOL_EXECUTION_ID = Symbol.for("assistant-stream.tool-execution-id");
const TOOL_ABORTED = Symbol("assistant-stream.tool-aborted");
const isStandardSchemaV1 = (schema) => {
	return typeof schema === "object" && schema !== null && "~standard" in schema && schema["~standard"].version === 1;
};
const isThenable = (value) => typeof value?.then === "function";
const raceWithAbort = async (value, abortSignal, delayAbort = false) => {
	let onAbort;
	const abortPromise = new Promise((resolve) => {
		onAbort = () => {
			if (delayAbort) queueMicrotask(() => queueMicrotask(() => resolve(TOOL_ABORTED)));
			else resolve(TOOL_ABORTED);
		};
		if (abortSignal.aborted) onAbort();
		else abortSignal.addEventListener("abort", onAbort, { once: true });
	});
	try {
		return await Promise.race([value, abortPromise]);
	} finally {
		abortSignal.removeEventListener("abort", onAbort);
	}
};
const cancelledToolResponse = () => new ToolResponse({
	result: "Tool execution was cancelled.",
	isError: true
});
function getToolResponse(tools, abortSignal, toolCall, human) {
	const tool = tools?.[toolCall.toolName];
	if (!tool?.execute) return void 0;
	const getResult = async (toolExecute) => {
		if (abortSignal.aborted) return cancelledToolResponse();
		let executeFn = toolExecute;
		let args = toolCall.args;
		if (isStandardSchemaV1(tool.parameters)) {
			const result = tool.parameters["~standard"].validate(toolCall.args);
			const validationResult = isThenable(result) ? await raceWithAbort(result, abortSignal) : result;
			if (validationResult === TOOL_ABORTED) return cancelledToolResponse();
			if (validationResult.issues) executeFn = tool.experimental_onSchemaValidationError ?? (() => {
				throw new Error(`Function parameter validation failed. ${JSON.stringify(validationResult.issues)}`);
			});
			else args = validationResult.value;
		}
		if (abortSignal.aborted) return cancelledToolResponse();
		const executePromise = (async () => {
			const executionContext = {
				toolCallId: toolCall.toolCallId,
				abortSignal,
				human: (payload) => human(toolCall.toolCallId, payload, toolCall.executionId),
				[TOOL_EXECUTION_ID]: toolCall.executionId
			};
			const result = await executeFn(args, executionContext);
			const response = ToolResponse.toResponse(result);
			if (tool.toModelOutput && !response.isError && response.modelContent === void 0) try {
				const modelContent = await tool.toModelOutput({
					toolCallId: toolCall.toolCallId,
					input: args,
					output: response.result
				});
				return new ToolResponse({
					result: response.result,
					artifact: response.artifact,
					isError: response.isError,
					messages: response.messages,
					modelContent
				});
			} catch (e) {
				console.warn(`[assistant-stream] tool "${toolCall.toolName}" toModelOutput threw; falling back to default projection.`, e);
			}
			return response;
		})();
		const executionResult = await raceWithAbort(executePromise, abortSignal, true);
		return executionResult === TOOL_ABORTED ? cancelledToolResponse() : executionResult;
	};
	return getResult(tool.execute);
}
function getToolStreamResponse(tools, abortSignal, reader, context, human) {
	const executionContext = {
		toolCallId: context.toolCallId,
		abortSignal,
		human: (payload) => human(context.toolCallId, payload, context.executionId),
		[TOOL_EXECUTION_ID]: context.executionId
	};
	tools?.[context.toolName]?.streamCall?.(reader, executionContext);
}
const isPendingToolCall = (part) => part.type === "tool-call" && part.state !== "result" && part.result === void 0;
async function unstable_runPendingTools(message, tools, abortSignal, human) {
	const toolCallPromises = message.parts.filter(isPendingToolCall).map(async (part) => {
		const promiseOrUndefined = getToolResponse(tools, abortSignal, {
			...part,
			executionId: Symbol()
		}, human ?? (async () => {
			throw new Error("Tool human input is not supported in this context");
		}));
		if (promiseOrUndefined) {
			const result = await promiseOrUndefined;
			return {
				toolCallId: part.toolCallId,
				result
			};
		}
		return null;
	});
	const toolCallResults = (await Promise.all(toolCallPromises)).filter((result) => result !== null);
	if (toolCallResults.length === 0) return message;
	const toolCallResultsById = new Map(toolCallResults.map(({ toolCallId, result }) => [toolCallId, result]));
	const updatedParts = message.parts.map((p) => {
		if (isPendingToolCall(p)) {
			const toolResponse = toolCallResultsById.get(p.toolCallId);
			if (toolResponse) return {
				...p,
				state: "result",
				...toolResponse.artifact !== void 0 ? { artifact: toolResponse.artifact } : {},
				...toolResponse.modelContent !== void 0 ? { modelContent: toolResponse.modelContent } : {},
				...toolResponse.messages !== void 0 ? { messages: toolResponse.messages } : {},
				result: toolResponse.result,
				isError: toolResponse.isError
			};
		}
		return p;
	});
	return {
		...message,
		parts: updatedParts,
		content: updatedParts
	};
}
/**
* Transform stream that executes frontend tools and appends tool results.
*
* The transform watches streamed tool-call arguments, runs the matching
* frontend tool once its arguments are complete, and emits a result chunk for
* the tool call. Backend and human tools pass through according to their tool
* definition.
*
* @param tools Tool registry or function returning the current registry.
* @param abortSignal Signal, or signal getter, used for the current run.
* @param human Callback used to resolve human-tool requests from UI input.
* @param options Optional execution lifecycle callbacks.
*/
function toolResultStream(tools, abortSignal, human, options) {
	const toolsFn = typeof tools === "function" ? tools : () => tools;
	const abortSignalFn = typeof abortSignal === "function" ? abortSignal : () => abortSignal;
	const internalOptions = options;
	const internalHuman = human;
	const executionOptions = {
		execute: (toolCall) => getToolResponse(toolsFn(), abortSignalFn(), toolCall, internalHuman),
		streamCall: ({ reader, ...context }) => getToolStreamResponse(toolsFn(), abortSignalFn(), reader, context, internalHuman),
		onExecutionStart: internalOptions?.onExecutionStart,
		onExecutionEnd: internalOptions?.onExecutionEnd
	};
	return new ToolExecutionStream(executionOptions);
}
//#endregion
export { toolResultStream, unstable_runPendingTools };
