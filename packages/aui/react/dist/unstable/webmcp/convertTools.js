import { generateId } from "@assistant-ui/core/internal";
import { ToolResponse, toJSONSchema } from "assistant-stream";
//#region src/unstable/webmcp/convertTools.ts
/**
* The predicate the WebMCP provider uses when no `filter` is passed: an enabled
* frontend tool with a client-side `execute`. A tool authored without a `type`
* is included, because `execute` is what distinguishes the deprecated
* type-less form from a backend or human tool. A `filter` replaces this, so
* pass it through to narrow the default set rather than widen it.
*/
const defaultWebMcpFilter = (_name, tool) => (tool.type === "frontend" || tool.type === void 0) && !!tool.execute && !tool.disabled;
const toWebMcpInputSchema = (tool) => tool.parameters ? toJSONSchema(tool.parameters) : {
	type: "object",
	properties: {}
};
const textContent = (text) => ({
	type: "text",
	text
});
const errorResult = (message) => ({
	isError: true,
	content: [textContent(message)]
});
const toText = (value) => {
	if (typeof value === "string") return value;
	if (typeof value === "bigint" || typeof value === "symbol") return value.toString();
	return JSON.stringify(value) ?? String(value);
};
const primitiveContent = (value) => [textContent(toText(value))];
const mapModelContentPart = (part) => {
	if (part.type === "text") return textContent(part.text ?? "");
	if (part.type === "file") {
		if (typeof part.mediaType === "string" && part.mediaType.startsWith("image/")) return {
			type: "image",
			data: part.data ?? "",
			mimeType: part.mediaType
		};
		return textContent(part.data ?? "");
	}
	return textContent(toText(part));
};
const toMcpContent = async (result, options) => {
	const response = ToolResponse.toResponse(result);
	if (response.modelContent) {
		const content = response.modelContent.map(mapModelContentPart);
		return response.isError ? {
			isError: true,
			content
		} : { content };
	}
	if (!response.isError && options.tool.toModelOutput) try {
		return { content: (await options.tool.toModelOutput({
			toolCallId: options.toolCallId,
			input: options.args,
			output: response.result
		})).map(mapModelContentPart) };
	} catch (e) {
		console.warn("[assistant-ui] toModelOutput threw; falling back to default projection.", e);
	}
	const content = primitiveContent(response.result);
	return response.isError ? {
		isError: true,
		content
	} : { content };
};
const isStandardSchema = (schema) => typeof schema === "object" && schema !== null && "~standard" in schema && schema["~standard"].version === 1;
const TOOL_ABORTED = Symbol("assistant-ui.webmcp-tool-aborted");
const isThenable = (value) => typeof value?.then === "function";
const raceWithAbort = async (value, abortSignal) => {
	let onAbort;
	const abortPromise = new Promise((resolve) => {
		onAbort = () => resolve(TOOL_ABORTED);
		if (abortSignal.aborted) onAbort();
		else abortSignal.addEventListener("abort", onAbort, { once: true });
	});
	try {
		return await Promise.race([abortPromise, value]);
	} finally {
		abortSignal.removeEventListener("abort", onAbort);
	}
};
const combineAbortSignals = (callerSignal, lifecycleSignal) => {
	const controller = new AbortController();
	const teardown = [];
	const cleanup = () => {
		while (teardown.length) teardown.pop()();
	};
	const abort = (reason) => {
		cleanup();
		controller.abort(reason);
	};
	const listen = (signal) => {
		const onAbort = () => abort(signal.reason);
		signal.addEventListener("abort", onAbort, { once: true });
		teardown.push(() => signal.removeEventListener("abort", onAbort));
	};
	if (callerSignal.aborted) abort(callerSignal.reason);
	else if (lifecycleSignal.aborted) abort(lifecycleSignal.reason);
	else {
		listen(callerSignal);
		listen(lifecycleSignal);
	}
	return {
		signal: controller.signal,
		cleanup
	};
};
const toWebMcpTool = (name, getTool, lifecycleSignal) => ({
	name,
	description: getTool().description ?? "",
	inputSchema: toWebMcpInputSchema(getTool()),
	execute: async (rawArgs, context) => {
		if (lifecycleSignal?.aborted) return errorResult(`Tool "${name}" is no longer registered`);
		const tool = getTool();
		let args = rawArgs ?? {};
		const toolCallId = generateId();
		let cleanup;
		try {
			const callerSignal = context?.signal;
			let abortSignal;
			if (callerSignal && lifecycleSignal) {
				const combined = combineAbortSignals(callerSignal, lifecycleSignal);
				abortSignal = combined.signal;
				cleanup = combined.cleanup;
			} else abortSignal = callerSignal ?? lifecycleSignal;
			if (abortSignal?.aborted) return errorResult("Tool execution was cancelled.");
			let executeFn = tool.execute;
			if (isStandardSchema(tool.parameters)) {
				const result = tool.parameters["~standard"].validate(args);
				const validation = isThenable(result) ? abortSignal ? await raceWithAbort(result, abortSignal) : await result : result;
				if (validation === TOOL_ABORTED) return errorResult("Tool execution was cancelled.");
				if (validation.issues) {
					const issues = validation.issues;
					executeFn = tool.experimental_onSchemaValidationError ?? (() => {
						throw new Error(`Function parameter validation failed. ${JSON.stringify(issues)}`);
					});
				} else args = validation.value;
			}
			if (abortSignal?.aborted) return errorResult("Tool execution was cancelled.");
			if (!executeFn) return errorResult(`Tool "${name}" has no client-side implementation.`);
			const result = await executeFn(args, {
				toolCallId,
				abortSignal: abortSignal ?? new AbortController().signal,
				human: () => Promise.reject(/* @__PURE__ */ new Error("human input not supported in WebMCP context"))
			});
			return await toMcpContent(result, {
				tool,
				toolCallId,
				args
			});
		} catch (e) {
			return errorResult(e instanceof Error ? e.message : String(e));
		} finally {
			cleanup?.();
		}
	}
});
//#endregion
export { defaultWebMcpFilter, toMcpContent, toWebMcpInputSchema, toWebMcpTool };
