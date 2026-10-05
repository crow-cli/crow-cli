//#region src/core/accumulators/TimingTracker.ts
var TimingTracker = class {
	_streamStartTime;
	_firstTokenTime;
	_totalChunks = 0;
	_toolCallIds = /* @__PURE__ */ new Set();
	constructor() {
		this._streamStartTime = Date.now();
	}
	recordChunk() {
		this._totalChunks++;
	}
	recordFirstToken() {
		if (this._firstTokenTime === void 0) this._firstTokenTime = Date.now();
	}
	recordToolCallStart(toolCallId) {
		this._toolCallIds.add(toolCallId);
	}
	getTiming(outputTokens, totalText) {
		const totalStreamTime = Date.now() - this._streamStartTime;
		const tokenCount = outputTokens && outputTokens > 0 ? outputTokens : totalText ? Math.ceil(totalText.length / 4) : void 0;
		const tokensPerSecond = tokenCount && totalStreamTime > 0 ? tokenCount / totalStreamTime * 1e3 : void 0;
		return {
			streamStartTime: this._streamStartTime,
			...this._firstTokenTime !== void 0 ? { firstTokenTime: this._firstTokenTime - this._streamStartTime } : void 0,
			totalStreamTime,
			...tokenCount !== void 0 ? { tokenCount } : void 0,
			...tokensPerSecond !== void 0 ? { tokensPerSecond } : void 0,
			totalChunks: this._totalChunks,
			toolCallCount: this._toolCallIds.size
		};
	}
};
//#endregion
export { TimingTracker };
