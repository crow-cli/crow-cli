import { generateId } from "../../utils/id.js";
import { notifySubscribers } from "../../subscribable/subscribable.js";
import { FRAME_MESSAGE_CHANNEL } from "./types.js";
import { isFrameMessage } from "./validate.js";
//#region src/model-context/frame/host.ts
const getDefaultTargetOrigin = () => window.location.origin;
const logCancellationFailure = (error) => {
	console.error("[assistant-ui] AssistantFrameHost tool cancellation could not be sent.", error);
};
/**
* Deserializes tools from JSON Schema format back to Tool objects
*/
const deserializeTool = (serializedTool) => ({
	parameters: serializedTool.parameters,
	...serializedTool.description && { description: serializedTool.description },
	...serializedTool.disabled !== void 0 && { disabled: serializedTool.disabled },
	...serializedTool.type && { type: serializedTool.type }
});
/**
* Deserializes a ModelContext from transmission format
*/
const deserializeModelContext = (serialized) => ({
	...serialized.system !== void 0 && { system: serialized.system },
	...serialized.tools && { tools: Object.fromEntries(Object.entries(serialized.tools).map(([name, tool]) => [name, deserializeTool(tool)])) }
});
const getAbortReason = (signal) => {
	if (signal.reason !== void 0) return signal.reason;
	const error = /* @__PURE__ */ new Error("Tool call was aborted");
	error.name = "AbortError";
	return error;
};
var AssistantFrameHost = class {
	_context = {};
	_subscribers = /* @__PURE__ */ new Set();
	_pendingRequests = /* @__PURE__ */ new Map();
	_iframeWindow;
	_targetOrigin;
	_disposed = false;
	constructor(iframeWindow, targetOrigin = getDefaultTargetOrigin()) {
		this._iframeWindow = iframeWindow;
		this._targetOrigin = targetOrigin;
		this.handleMessage = this.handleMessage.bind(this);
		this.requestContext();
		window.addEventListener("message", this.handleMessage);
	}
	handleMessage(event) {
		if (this._targetOrigin !== "*" && event.origin !== this._targetOrigin) return;
		if (event.source !== this._iframeWindow) return;
		if (event.data?.channel !== "assistant-ui-frame") return;
		const message = event.data.message;
		if (!isFrameMessage(message)) return;
		switch (message.type) {
			case "model-context-update":
				this.updateContext(message.context);
				break;
			case "tool-result": {
				const pending = this._pendingRequests.get(message.id);
				if (pending) {
					if (typeof message.error === "string") pending.reject(new Error(message.error));
					else pending.resolve(message.result);
					this._pendingRequests.delete(message.id);
				}
				break;
			}
		}
	}
	updateContext(serializedContext) {
		const context = deserializeModelContext(serializedContext);
		this._context = {
			...context,
			tools: context.tools && Object.fromEntries(Object.entries(context.tools).map(([name, tool]) => [name, {
				...tool,
				execute: (args, context) => this.callTool(name, args, context.abortSignal)
			}]))
		};
		this.notifySubscribers();
	}
	callTool(toolName, args, abortSignal) {
		return this.sendRequest({
			type: "tool-call",
			id: `tool-${generateId()}`,
			toolName,
			args
		}, 3e4, `Tool call "${toolName}" timed out`, abortSignal);
	}
	sendRequest(message, timeout = 3e4, timeoutMessage = "Request timed out", abortSignal) {
		if (this._disposed) return Promise.reject(/* @__PURE__ */ new Error("AssistantFrameHost has been disposed"));
		if (abortSignal?.aborted) return Promise.reject(getAbortReason(abortSignal));
		return new Promise((resolve, reject) => {
			let timeoutId;
			const onAbort = () => {
				if (!abortSignal) return;
				const pending = this._pendingRequests.get(message.id);
				if (pending) {
					this.cancelToolCall(message.id);
					pending.reject(getAbortReason(abortSignal));
					this._pendingRequests.delete(message.id);
				}
			};
			const cleanup = () => {
				if (timeoutId !== void 0) clearTimeout(timeoutId);
				abortSignal?.removeEventListener("abort", onAbort);
			};
			this._pendingRequests.set(message.id, {
				resolve: (value) => {
					cleanup();
					resolve(value);
				},
				reject: (error) => {
					cleanup();
					reject(error);
				}
			});
			timeoutId = setTimeout(() => {
				const pending = this._pendingRequests.get(message.id);
				if (pending) {
					this.cancelToolCall(message.id);
					pending.reject(new Error(timeoutMessage));
					this._pendingRequests.delete(message.id);
				}
			}, timeout);
			abortSignal?.addEventListener("abort", onAbort, { once: true });
			try {
				this._iframeWindow.postMessage({
					channel: FRAME_MESSAGE_CHANNEL,
					message
				}, this._targetOrigin);
			} catch (error) {
				const pending = this._pendingRequests.get(message.id);
				this._pendingRequests.delete(message.id);
				pending?.reject(error);
			}
		});
	}
	cancelToolCall(id, onError = logCancellationFailure) {
		try {
			this._iframeWindow.postMessage({
				channel: FRAME_MESSAGE_CHANNEL,
				message: {
					type: "tool-cancel",
					id
				}
			}, this._targetOrigin);
		} catch (error) {
			onError(error);
		}
	}
	requestContext() {
		this._iframeWindow.postMessage({
			channel: FRAME_MESSAGE_CHANNEL,
			message: { type: "model-context-request" }
		}, this._targetOrigin);
	}
	notifySubscribers() {
		notifySubscribers(this._subscribers);
	}
	getModelContext() {
		return this._context;
	}
	subscribe(callback) {
		this._subscribers.add(callback);
		return () => this._subscribers.delete(callback);
	}
	dispose() {
		this._disposed = true;
		window.removeEventListener("message", this.handleMessage);
		this._subscribers.clear();
		const error = /* @__PURE__ */ new Error("AssistantFrameHost has been disposed");
		let cancellationFailed = false;
		let cancellationError;
		for (const [id, pending] of this._pendingRequests) {
			this._pendingRequests.delete(id);
			this.cancelToolCall(id, (error) => {
				if (!cancellationFailed) {
					cancellationFailed = true;
					cancellationError = error;
				} else logCancellationFailure(error);
			});
			pending.reject(error);
		}
		if (cancellationFailed) throw cancellationError;
	}
};
//#endregion
export { AssistantFrameHost };
