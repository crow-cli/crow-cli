//#region src/instrumentMcpSampling.ts
const reportSamplingError = (error) => {
	try {
		console.error("[assistant-cloud] onSamplingCall callback threw an error", error);
	} catch {}
};
/**
* Wraps an MCP sampling handler to intercept and measure sampling calls.
*
* @param handler - The original sampling handler from the MCP client
* @param onSamplingCall - Callback invoked with metrics for each sampling call
* @returns A wrapped handler that transparently captures sampling metrics
*
* @example
* ```ts
* const samplingCalls: SamplingCallData[] = [];
* const wrapped = wrapSamplingHandler(
*   originalHandler,
*   (data) => samplingCalls.push(data),
* );
* // Use `wrapped` as the MCP client's sampling handler
* // After tool execution, `samplingCalls` contains metrics for all nested LLM calls
* ```
*/
function wrapSamplingHandler(handler, onSamplingCall) {
	return async (request) => {
		const startTime = Date.now();
		const response = await handler(request);
		const durationMs = Date.now() - startTime;
		const modelId = response.model ?? request.params.modelPreferences?.hints?.[0]?.name;
		const inputTokens = response.usage?.inputTokens ?? response.usage?.promptTokens;
		const outputTokens = response.usage?.outputTokens ?? response.usage?.completionTokens;
		const reasoningTokens = response.usage?.reasoningTokens;
		const cachedInputTokens = response.usage?.cachedInputTokens;
		const data = {
			...modelId ? { model_id: modelId } : void 0,
			...inputTokens != null ? { input_tokens: inputTokens } : void 0,
			...outputTokens != null ? { output_tokens: outputTokens } : void 0,
			...reasoningTokens != null ? { reasoning_tokens: reasoningTokens } : void 0,
			...cachedInputTokens != null ? { cached_input_tokens: cachedInputTokens } : void 0,
			duration_ms: durationMs
		};
		try {
			Promise.resolve(onSamplingCall(data)).catch(reportSamplingError);
		} catch (error) {
			reportSamplingError(error);
		}
		return response;
	};
}
/**
* Creates a collector that accumulates sampling call data during tool execution.
* Use with `wrapSamplingHandler` to capture all sampling calls for a tool invocation.
*
* @example
* ```ts
* const collector = createSamplingCollector();
* const wrappedHandler = wrapSamplingHandler(handler, collector.collect);
* // ... execute MCP tool ...
* const calls = collector.getCalls(); // SamplingCallData[]
* ```
*/
function createSamplingCollector() {
	const calls = [];
	return {
		collect: (data) => calls.push(data),
		getCalls: () => [...calls],
		reset: () => {
			calls.length = 0;
		}
	};
}
//#endregion
export { createSamplingCollector, wrapSamplingHandler };
