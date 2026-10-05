import { generateId } from "../utils/generateId.js";
import { promiseWithResolvers } from "../../utils/promiseWithResolvers.js";
import { createMergeStream } from "../utils/stream/merge.js";
import { createTextStreamController } from "./text.js";
import { createToolCallStreamController } from "./tool-call.js";
import { Counter } from "../utils/Counter.js";
import { PathAppendEncoder, PathMergeEncoder } from "../utils/stream/path-utils.js";
//#region src/core/modules/assistant-stream.ts
var AssistantStreamControllerImpl = class AssistantStreamControllerImpl {
	_state;
	_parentId;
	constructor(state, options = {}) {
		this._state = state || {
			strict: options.strict ?? true,
			merger: createMergeStream(),
			contentCounter: new Counter()
		};
	}
	get __internal_isClosed() {
		return this._state.merger.isSealed() || this._state.merger.isCancelled() || this._state.merger.isErrored();
	}
	get __internal_isCancelled() {
		return this._state.merger.isCancelled();
	}
	__internal_getReadable() {
		return this._state.merger.readable;
	}
	__internal_subscribeToClose(callback) {
		this._state.closeSubscriber = callback;
	}
	_addTransformedStream(stream, transformer) {
		if (stream.locked) throw new TypeError("Cannot merge a stream that is already locked to a reader.");
		const pipeTask = stream.pipeTo(transformer.writable).catch(async (error) => {
			await transformer.writable.abort(error).catch(() => void 0);
			throw error;
		});
		this._state.merger.addStream(transformer.readable, pipeTask);
	}
	_addPart(part, stream) {
		if (this._state.append) {
			this._state.append.controller.close();
			this._state.append = void 0;
		}
		this.enqueue({
			type: "part-start",
			part,
			path: []
		});
		this._addTransformedStream(stream, new PathAppendEncoder(this._state.contentCounter.value));
	}
	merge(stream) {
		this._addTransformedStream(stream, new PathMergeEncoder(this._state.contentCounter));
	}
	appendText(textDelta) {
		if (this._state.append?.kind !== "text" || this._state.append.parentId !== this._parentId) this._state.append = {
			kind: "text",
			parentId: this._parentId,
			controller: this.addTextPart()
		};
		this._state.append.controller.append(textDelta);
	}
	appendReasoning(textDelta, options) {
		if (options !== void 0 || this._state.append?.kind !== "reasoning" || this._state.append.parentId !== this._parentId) this._state.append = {
			kind: "reasoning",
			parentId: this._parentId,
			controller: this.addReasoningPart(options)
		};
		if (options !== void 0 && textDelta.length === 0) return;
		this._state.append.controller.append(textDelta);
	}
	addTextPart() {
		const [stream, controller] = createTextStreamController({ strict: this._state.strict });
		this._addPart(this._withParentIdOption({ type: "text" }), stream);
		return controller;
	}
	addReasoningPart(options) {
		const [stream, controller] = createTextStreamController({ strict: this._state.strict });
		this._addPart(this._withParentIdOption({
			type: "reasoning",
			...options
		}), stream);
		return controller;
	}
	addToolCallPart(options) {
		const opt = typeof options === "string" ? { toolName: options } : options;
		const toolName = opt.toolName;
		const toolCallId = opt.toolCallId ?? generateId();
		const [stream, controller] = createToolCallStreamController({ strict: this._state.strict });
		this._addPart({
			type: "tool-call",
			toolName,
			toolCallId,
			...this._parentId && { parentId: this._parentId }
		}, stream);
		if (opt.argsText !== void 0) {
			controller.argsText.append(opt.argsText);
			controller.argsText.close();
		}
		if (opt.args !== void 0) {
			controller.argsText.append(JSON.stringify(opt.args));
			controller.argsText.close();
		}
		if (opt.response !== void 0) controller.setResponse(opt.response);
		return controller;
	}
	_finishedPartStream() {
		return new ReadableStream({ start(controller) {
			controller.enqueue({
				type: "part-finish",
				path: []
			});
			controller.close();
		} });
	}
	_withParentIdOption(options) {
		if (!this._parentId) return options;
		return {
			...options,
			parentId: this._parentId
		};
	}
	appendSource(options) {
		this._addPart(this._withParentIdOption(options), this._finishedPartStream());
	}
	appendFile(options) {
		this._addPart(this._withParentIdOption(options), this._finishedPartStream());
	}
	appendData(options) {
		this._addPart(this._withParentIdOption(options), this._finishedPartStream());
	}
	enqueue(chunk) {
		this._state.merger.enqueue(chunk);
		if (chunk.type === "part-start" && chunk.path.length === 0) this._state.contentCounter.up();
	}
	withParentId(parentId) {
		const controller = new AssistantStreamControllerImpl(this._state);
		controller._parentId = parentId;
		return controller;
	}
	close() {
		this._state.append?.controller?.close();
		this._state.merger.seal();
		this._state.closeSubscriber?.();
	}
};
/**
* Creates an {@link AssistantStream} and writes to it with an
* {@link AssistantStreamController}.
*
* The callback may write synchronously or asynchronously. If it throws while
* the stream is open, an `error` chunk is emitted. Failures after an explicit
* close are logged, while failures after consumer cancellation are discarded.
* When the callback settles, the stream is closed automatically unless the
* controller was already closed.
*/
function createAssistantStream(callback, options = {}) {
	const controller = new AssistantStreamControllerImpl(void 0, options);
	const runTask = async () => {
		try {
			await callback(controller);
		} catch (e) {
			if (!controller.__internal_isClosed) controller.enqueue({
				type: "error",
				path: [],
				error: String(e)
			});
			else if (!controller.__internal_isCancelled) console.error(e);
		} finally {
			if (!controller.__internal_isClosed) controller.close();
		}
	};
	runTask();
	return controller.__internal_getReadable();
}
/**
* Creates an {@link AssistantStream} together with the controller used to
* write into it.
*
* Use this when the stream needs to be returned before all writers are known.
* Closing the returned controller finishes the paired stream.
*/
function createAssistantStreamController(options = {}) {
	const { resolve, promise } = promiseWithResolvers();
	let controller;
	return [createAssistantStream((c) => {
		controller = c;
		controller.__internal_subscribeToClose(resolve);
		return promise;
	}, options), controller];
}
//#endregion
export { createAssistantStream, createAssistantStreamController };
