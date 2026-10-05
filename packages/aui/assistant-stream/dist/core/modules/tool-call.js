import { NO_RESULT } from "../tool/ToolResponse.js";
import { createControllerStream, createControllerStreamPair } from "../utils/stream/createControllerStream.js";
import { closeIfOpen, enqueueIfOpen } from "../utils/stream/controller-guards.js";
import { createTextStream } from "./text.js";
//#region src/core/modules/tool-call.ts
var ToolCallStreamControllerImpl = class {
	_isClosed = false;
	_mergeTask;
	_controller;
	constructor(_controller, options = {}) {
		this._controller = _controller;
		const stream = createTextStream({ start: (c) => {
			this._argsTextController = c;
		} }, options);
		let hasArgsText = false;
		this._mergeTask = stream.pipeTo(new WritableStream({ write: (chunk) => {
			switch (chunk.type) {
				case "text-delta":
					hasArgsText = true;
					enqueueIfOpen(this._controller, chunk);
					break;
				case "part-finish":
					if (!hasArgsText) enqueueIfOpen(this._controller, {
						type: "text-delta",
						textDelta: "{}",
						path: []
					});
					enqueueIfOpen(this._controller, {
						type: "tool-call-args-text-finish",
						path: []
					});
					break;
				default: throw new Error(`Unexpected chunk type: ${chunk.type}`);
			}
		} }));
	}
	get argsText() {
		return this._argsTextController;
	}
	_argsTextController;
	async setResponse(response) {
		if (this._isClosed) return;
		const result = response.result;
		enqueueIfOpen(this._controller, {
			type: "result",
			path: [],
			...response.artifact !== void 0 ? { artifact: response.artifact } : {},
			result: result === void 0 ? NO_RESULT : result,
			isError: response.isError ?? false,
			...response.isPreliminary ? { isPreliminary: true } : {},
			...response.modelContent !== void 0 ? { modelContent: response.modelContent } : {},
			...response.messages !== void 0 ? { messages: response.messages } : {}
		});
		if (response.isPreliminary) this._argsTextController.close();
		else await this.close();
	}
	async close() {
		if (this._isClosed) return;
		this._isClosed = true;
		this._argsTextController.close();
		await this._mergeTask;
		enqueueIfOpen(this._controller, {
			type: "part-finish",
			path: []
		});
		closeIfOpen(this._controller);
	}
};
const createToolCallStream = (readable, options = {}) => {
	return createControllerStream(readable, (controller) => new ToolCallStreamControllerImpl(controller, options));
};
const createToolCallStreamController = (options = {}) => {
	return createControllerStreamPair((controller) => new ToolCallStreamControllerImpl(controller, options));
};
//#endregion
export { createToolCallStream, createToolCallStreamController };
