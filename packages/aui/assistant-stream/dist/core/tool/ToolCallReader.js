import { asAsyncIterableStream } from "../../utils/AsyncIterableStream.js";
import { getPartialJsonObjectFieldState, parsePartialJsonObject } from "../../utils/json/parse-partial-json-object.js";
import { promiseWithResolvers } from "../../utils/promiseWithResolvers.js";
//#region src/core/tool/ToolCallReader.ts
function getField(obj, fieldPath) {
	let current = obj;
	for (const key of fieldPath) {
		if (current === void 0 || current === null || !Object.hasOwn(current, key)) return;
		current = current[key];
	}
	return current;
}
var GetHandle = class {
	resolve;
	reject;
	disposed = false;
	fieldPath;
	get isDisposed() {
		return this.disposed;
	}
	constructor(resolve, reject, fieldPath) {
		this.resolve = resolve;
		this.reject = reject;
		this.fieldPath = fieldPath;
	}
	update(args) {
		if (this.disposed) return;
		try {
			if (getPartialJsonObjectFieldState(args, this.fieldPath) === "complete") {
				const value = getField(args, this.fieldPath);
				if (value !== void 0) {
					this.resolve(value);
					this.dispose();
				}
			}
		} catch (e) {
			this.reject(e);
			this.dispose();
		}
	}
	end(args) {
		if (this.disposed) return;
		try {
			const value = getField(args, this.fieldPath);
			this.resolve(value);
		} catch (e) {
			this.reject(e);
		} finally {
			this.dispose();
		}
	}
	error(reason) {
		if (this.disposed) return;
		this.reject(reason);
		this.dispose();
	}
	dispose() {
		this.disposed = true;
	}
};
var StreamValuesHandle = class {
	controller;
	disposed = false;
	fieldPath;
	get isDisposed() {
		return this.disposed;
	}
	constructor(controller, fieldPath) {
		this.controller = controller;
		this.fieldPath = fieldPath;
	}
	update(args) {
		if (this.disposed) return;
		try {
			const value = getField(args, this.fieldPath);
			if (value !== void 0) this.controller.enqueue(value);
			if (getPartialJsonObjectFieldState(args, this.fieldPath) === "complete") {
				this.controller.close();
				this.dispose();
			}
		} catch (e) {
			this.controller.error(e);
			this.dispose();
		}
	}
	end() {
		if (this.disposed) return;
		this.controller.close();
		this.dispose();
	}
	error(reason) {
		if (this.disposed) return;
		this.controller.error(reason);
		this.dispose();
	}
	dispose() {
		this.disposed = true;
	}
};
var StreamTextHandle = class {
	controller;
	disposed = false;
	fieldPath;
	lastValue = void 0;
	get isDisposed() {
		return this.disposed;
	}
	constructor(controller, fieldPath) {
		this.controller = controller;
		this.fieldPath = fieldPath;
	}
	update(args) {
		if (this.disposed) return;
		try {
			const value = getField(args, this.fieldPath);
			if (value !== void 0 && typeof value === "string") {
				const delta = value.substring(this.lastValue?.length || 0);
				this.lastValue = value;
				this.controller.enqueue(delta);
			}
			if (getPartialJsonObjectFieldState(args, this.fieldPath) === "complete") {
				this.controller.close();
				this.dispose();
			}
		} catch (e) {
			this.controller.error(e);
			this.dispose();
		}
	}
	end() {
		if (this.disposed) return;
		this.controller.close();
		this.dispose();
	}
	error(reason) {
		if (this.disposed) return;
		this.controller.error(reason);
		this.dispose();
	}
	dispose() {
		this.disposed = true;
	}
};
var ForEachHandle = class {
	controller;
	disposed = false;
	fieldPath;
	nextIndex = 0;
	get isDisposed() {
		return this.disposed;
	}
	constructor(controller, fieldPath) {
		this.controller = controller;
		this.fieldPath = fieldPath;
	}
	update(args) {
		if (this.disposed) return;
		try {
			const array = getField(args, this.fieldPath);
			if (!Array.isArray(array)) return;
			for (; this.nextIndex < array.length; this.nextIndex++) {
				const elementPath = [...this.fieldPath, this.nextIndex];
				if (getPartialJsonObjectFieldState(args, elementPath) !== "complete") break;
				this.controller.enqueue(array[this.nextIndex]);
			}
			if (getPartialJsonObjectFieldState(args, this.fieldPath) === "complete") {
				this.controller.close();
				this.dispose();
			}
		} catch (e) {
			this.controller.error(e);
			this.dispose();
		}
	}
	end() {
		if (this.disposed) return;
		this.controller.close();
		this.dispose();
	}
	error(reason) {
		if (this.disposed) return;
		this.controller.error(reason);
		this.dispose();
	}
	dispose() {
		this.disposed = true;
	}
};
var ToolCallArgsReaderImpl = class {
	argTextDeltas;
	handles = /* @__PURE__ */ new Set();
	accumulatedText = "";
	parsedTextLength = -1;
	args = void 0;
	finished = false;
	failure = void 0;
	constructor(argTextDeltas) {
		this.argTextDeltas = argTextDeltas;
		this.processStream();
	}
	async processStream() {
		try {
			const reader = this.argTextDeltas.getReader();
			while (true) {
				const { value, done } = await reader.read();
				if (done) break;
				this.accumulatedText += value;
				if (this.handles.size === 0) continue;
				if (this.parseCurrentArgs()) this.updateHandles();
			}
		} catch (error) {
			this.failure = { reason: error };
		} finally {
			this.finished = true;
			for (const handle of this.handles) this.settleHandle(handle);
			this.handles.clear();
		}
	}
	settleHandle(handle) {
		if (this.failure) handle.error(this.failure.reason);
		else handle.end(this.args);
	}
	parseCurrentArgs() {
		if (this.parsedTextLength === this.accumulatedText.length) return false;
		const parsedArgs = parsePartialJsonObject(this.accumulatedText);
		this.parsedTextLength = this.accumulatedText.length;
		if (parsedArgs === void 0) {
			this.args ??= parsePartialJsonObject("");
			return false;
		}
		this.args = parsedArgs;
		return true;
	}
	updateHandles() {
		for (const handle of this.handles) {
			handle.update(this.args);
			if (handle.isDisposed) this.handles.delete(handle);
		}
	}
	activateHandle(handle) {
		this.parseCurrentArgs();
		handle.update(this.args);
		if (handle.isDisposed) return;
		if (this.finished) {
			this.settleHandle(handle);
			return;
		}
		this.handles.add(handle);
	}
	get(...fieldPath) {
		return new Promise((resolve, reject) => {
			const handle = new GetHandle(resolve, reject, fieldPath);
			this.activateHandle(handle);
		});
	}
	streamValues(...fieldPath) {
		const simplePath = fieldPath;
		let handle;
		const stream = new ReadableStream({
			start: (controller) => {
				handle = new StreamValuesHandle(controller, simplePath);
				this.activateHandle(handle);
			},
			cancel: () => {
				if (handle) {
					handle.dispose();
					this.handles.delete(handle);
				}
			}
		});
		return asAsyncIterableStream(stream);
	}
	streamText(...fieldPath) {
		const simplePath = fieldPath;
		let handle;
		const stream = new ReadableStream({
			start: (controller) => {
				handle = new StreamTextHandle(controller, simplePath);
				this.activateHandle(handle);
			},
			cancel: () => {
				if (handle) {
					handle.dispose();
					this.handles.delete(handle);
				}
			}
		});
		return asAsyncIterableStream(stream);
	}
	forEach(...fieldPath) {
		const simplePath = fieldPath;
		let handle;
		const stream = new ReadableStream({
			start: (controller) => {
				handle = new ForEachHandle(controller, simplePath);
				this.activateHandle(handle);
			},
			cancel: () => {
				if (handle) {
					handle.dispose();
					this.handles.delete(handle);
				}
			}
		});
		return asAsyncIterableStream(stream);
	}
};
var ToolCallResponseReaderImpl = class {
	promise;
	constructor(promise) {
		this.promise = promise;
	}
	get() {
		return this.promise;
	}
};
var ToolCallReaderImpl = class {
	args;
	response;
	writable;
	resolve;
	argsText = "";
	constructor() {
		const stream = new TransformStream();
		this.writable = stream.writable;
		this.args = new ToolCallArgsReaderImpl(stream.readable);
		const { promise, resolve } = promiseWithResolvers();
		this.resolve = resolve;
		this.response = new ToolCallResponseReaderImpl(promise);
	}
	async appendArgsTextDelta(text) {
		const writer = this.writable.getWriter();
		try {
			await writer.write(text);
		} catch (err) {
			console.warn(err);
		} finally {
			writer.releaseLock();
		}
		this.argsText += text;
	}
	async finishArgsText() {
		const writer = this.writable.getWriter();
		try {
			await writer.close();
		} catch (err) {
			console.warn(err);
		} finally {
			writer.releaseLock();
		}
	}
	setResponse(value) {
		this.resolve(value);
	}
	result = { get: async () => {
		return (await this.response.get()).result;
	} };
};
//#endregion
export { ToolCallArgsReaderImpl, ToolCallReaderImpl, ToolCallResponseReaderImpl };
