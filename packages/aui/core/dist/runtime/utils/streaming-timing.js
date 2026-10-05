//#region src/runtime/utils/streaming-timing.ts
const defaultEstimateTokens = (textLength) => Math.ceil(textLength / 4);
/**
* Apply one content growth delta to `state`, recording the first-token time
* on the first growth and bumping the chunk count. Returns `state` unchanged
* when `len` has not grown.
*/
const applyGrowth = (state, len, now) => {
	if (len <= state.lastContentLength) return state;
	return {
		...state,
		firstTokenTime: state.firstTokenTime ?? now() - state.startTime,
		lastContentLength: len,
		totalChunks: state.totalChunks + 1
	};
};
/**
* Advance the client-side streaming timing tracker by one update.
*
* Pure: given the previous state and the current `(messages, isRunning)`
* snapshot, returns the next state plus any `MessageTiming` finalized this
* update (empty when streaming is still in flight). The caller owns the
* state (e.g. a ref) and merges finalized timings into its store.
*
* At finalize the text length is recomputed from the final messages, and any
* final growth delta that landed in the same update as the
* `isRunning -> false` transition is reconciled, so the token estimate and
* `totalChunks` count the same content (the per-adapter hooks this replaces
* reuse a stale growth delta and miss that last chunk).
*/
const stepStreamingTiming = (state, messages, isRunning, accessors, options, now = Date.now) => {
	const lastId = accessors.getAssistantMessageId(messages);
	const estimateTokens = options?.estimateTokens ?? defaultEstimateTokens;
	if (isRunning && lastId !== void 0) {
		let next;
		if (state === null || state.messageId !== lastId) next = {
			messageId: lastId,
			startTime: now(),
			lastContentLength: 0,
			totalChunks: 0
		};
		else next = state;
		return {
			state: applyGrowth(next, accessors.getTextLength(messages, next.messageId), now),
			timings: {}
		};
	}
	if (!isRunning && state !== null) {
		const nowMs = now();
		const reconciled = applyGrowth(state, accessors.getTextLength(messages, state.messageId), () => nowMs);
		const totalStreamTime = nowMs - reconciled.startTime;
		const tokenCount = estimateTokens(reconciled.lastContentLength);
		const toolCallCount = accessors.getToolCallCount(messages, reconciled.messageId);
		const timing = {
			streamStartTime: reconciled.startTime,
			totalStreamTime,
			totalChunks: reconciled.totalChunks,
			toolCallCount,
			...reconciled.firstTokenTime !== void 0 && { firstTokenTime: reconciled.firstTokenTime },
			...tokenCount > 0 && { tokenCount },
			...totalStreamTime > 0 && tokenCount > 0 && { tokensPerSecond: tokenCount / (totalStreamTime / 1e3) }
		};
		return {
			state: null,
			timings: { [reconciled.messageId]: timing }
		};
	}
	return {
		state,
		timings: {}
	};
};
//#endregion
export { stepStreamingTiming };
