import { createControllerStream, createControllerStreamPair } from "../utils/stream/createControllerStream.js";
import { closeIfOpen, enqueueIfOpen } from "../utils/stream/controller-guards.js";
//#region src/core/modules/text.ts
var TextStreamControllerImpl = class {
	_controller;
	_strict;
	_isClosed = false;
	_warnedDropped = false;
	constructor(controller, options = {}) {
		this._controller = controller;
		this._strict = options.strict ?? true;
	}
	append(textDelta) {
		const chunk = {
			type: "text-delta",
			path: [],
			textDelta
		};
		if (this._isClosed) {
			if (this._strict) throw new TypeError("Cannot append to a closed TextStreamController");
			enqueueIfOpen(this._controller, chunk, this._warnDroppedAfterClose);
			return this;
		}
		enqueueIfOpen(this._controller, chunk);
		return this;
	}
	_warnDroppedAfterClose = (error) => {
		if (this._warnedDropped) return;
		this._warnedDropped = true;
		console.error(`Dropped text delta for closed stream: ${String(error)}`);
	};
	close() {
		if (this._isClosed) return;
		this._isClosed = true;
		enqueueIfOpen(this._controller, {
			type: "part-finish",
			path: []
		});
		closeIfOpen(this._controller);
	}
};
const createTextStream = (readable, options = {}) => {
	return createControllerStream(readable, (controller) => new TextStreamControllerImpl(controller, options));
};
const createTextStreamController = (options = {}) => {
	return createControllerStreamPair((controller) => new TextStreamControllerImpl(controller, options));
};
//#endregion
export { createTextStream, createTextStreamController };
