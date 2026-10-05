import { GorpStreamAccumulator } from "./GorpStreamAccumulator.js";
import { createControllerStreamPair } from "../utils/stream/createControllerStream.js";
import { withPromiseOrValue } from "../utils/withPromiseOrValue.js";
//#region src/core/gorp/createGorpStream.ts
var GorpStreamControllerImpl = class {
	_controller;
	_abortController = new AbortController();
	_accumulator;
	_cancelled = false;
	get abortSignal() {
		return this._abortController.signal;
	}
	constructor(controller, defaultValue) {
		this._controller = controller;
		this._accumulator = new GorpStreamAccumulator(defaultValue);
	}
	enqueue(operations) {
		if (this._cancelled) return;
		this._accumulator.append(operations);
		this._controller.enqueue({
			snapshot: this._accumulator.state,
			operations
		});
	}
	__internalError(error) {
		if (this._cancelled) return;
		this._controller.error(error);
	}
	__internalClose() {
		if (this._cancelled) return;
		this._controller.close();
	}
	__internalCancel(reason) {
		this._cancelled = true;
		this._abortController.abort(reason);
	}
};
const createGorpStream = ({ execute, defaultValue = {} }) => {
	const [stream, controller] = createControllerStreamPair((streamController) => new GorpStreamControllerImpl(streamController, defaultValue), (streamController, reason) => streamController.__internalCancel(reason));
	withPromiseOrValue(() => execute(controller), () => {
		controller.__internalClose();
	}, (e) => {
		controller.__internalError(e);
	});
	return stream;
};
//#endregion
export { createGorpStream };
