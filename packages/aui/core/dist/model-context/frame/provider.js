import { FRAME_MESSAGE_CHANNEL } from "./types.js";
import { isFrameMessage } from "./validate.js";
import { toJSONSchema } from "assistant-stream";
//#region src/model-context/frame/provider.ts
const serializeTool = (tool) => ({
	...tool.description && { description: tool.description },
	parameters: tool.parameters ? toJSONSchema(tool.parameters) : void 0,
	...tool.disabled !== void 0 && { disabled: tool.disabled },
	...tool.type && { type: tool.type }
});
const serializeModelContext = (context) => ({
	...context.system !== void 0 && { system: context.system },
	...context.tools && { tools: Object.fromEntries(Object.entries(context.tools).map(([name, tool]) => [name, serializeTool(tool)])) }
});
const getDefaultTargetOrigin = () => window.location.origin;
var AssistantFrameProvider = class AssistantFrameProvider {
	static _instance = null;
	_providers = /* @__PURE__ */ new Map();
	_providerUnsubscribes = /* @__PURE__ */ new Map();
	_activeToolCalls = /* @__PURE__ */ new Map();
	_targetOrigin;
	_strictRegistrations = 0;
	_wildcardRegistrations = 0;
	_startupTimer;
	_disposed = false;
	constructor(targetOrigin = getDefaultTargetOrigin()) {
		this._targetOrigin = targetOrigin;
		this.handleMessage = this.handleMessage.bind(this);
		window.addEventListener("message", this.handleMessage);
		this._startupTimer = setTimeout(() => {
			this._startupTimer = void 0;
			this.broadcastUpdate();
		}, 0);
	}
	static getInstance(targetOrigin) {
		if (!AssistantFrameProvider._instance) AssistantFrameProvider._instance = new AssistantFrameProvider(targetOrigin);
		else AssistantFrameProvider._instance.reconcileTargetOrigin(targetOrigin);
		return AssistantFrameProvider._instance;
	}
	reconcileTargetOrigin(targetOrigin = getDefaultTargetOrigin()) {
		if (targetOrigin === this._targetOrigin) return;
		if (this._providers.size === 0) {
			this._targetOrigin = targetOrigin;
			return;
		}
		if (targetOrigin === "*") return;
		if (this._targetOrigin === "*") {
			this._targetOrigin = targetOrigin;
			return;
		}
		throw new Error(`AssistantFrameProvider cannot register conflicting target origins: "${this._targetOrigin}" and "${targetOrigin}"`);
	}
	handleMessage(event) {
		if (this._targetOrigin !== "*" && event.origin !== this._targetOrigin) return;
		if (event.source !== window.parent) return;
		if (event.data?.channel !== "assistant-ui-frame") return;
		const message = event.data.message;
		if (!isFrameMessage(message)) return;
		switch (message.type) {
			case "model-context-request":
				this.sendMessage(event, {
					type: "model-context-update",
					context: serializeModelContext(this.getModelContext())
				});
				break;
			case "tool-call":
				this.handleToolCall(message, event).catch((error) => {
					console.error("[assistant-ui] AssistantFrame tool call failed.", error);
				});
				break;
			case "tool-cancel": this.cancelToolCall(message.id);
		}
	}
	async handleToolCall(message, event) {
		const resolvedTool = this.getTool(message.toolName);
		const tool = resolvedTool?.tool;
		const abortController = new AbortController();
		this._activeToolCalls.get(message.id)?.abortController.abort();
		const activeCall = {
			abortController,
			event,
			provider: resolvedTool?.provider
		};
		this._activeToolCalls.set(message.id, activeCall);
		let result;
		let error;
		if (!tool) error = `Tool "${message.toolName}" not found`;
		else try {
			result = tool.execute ? await tool.execute(message.args, {
				toolCallId: message.id,
				abortSignal: abortController.signal,
				human: async () => {
					throw new Error("Tool human input is not supported in frame context");
				}
			}) : void 0;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		if (this._activeToolCalls.get(message.id) !== activeCall) return;
		this._activeToolCalls.delete(message.id);
		try {
			this.sendMessage(event, {
				type: "tool-result",
				id: message.id,
				...error !== void 0 ? { error } : { result }
			});
		} catch (sendError) {
			if (error !== void 0) throw sendError;
			console.error("[assistant-ui] AssistantFrame tool result could not be sent.", sendError);
			this.sendMessage(event, {
				type: "tool-result",
				id: message.id,
				error: "Tool result could not be sent across the frame boundary"
			});
		}
	}
	cancelToolCall(id) {
		const activeCall = this._activeToolCalls.get(id);
		if (!activeCall) return;
		this._activeToolCalls.delete(id);
		activeCall.abortController.abort();
	}
	cancelToolCallsForProvider(provider) {
		const matchingCalls = Array.from(this._activeToolCalls).filter(([, activeCall]) => activeCall.provider === provider);
		for (const [id, activeCall] of matchingCalls) {
			this._activeToolCalls.delete(id);
			activeCall.abortController.abort();
		}
		let sendFailed = false;
		let sendError;
		for (const [id, activeCall] of matchingCalls) try {
			this.sendMessage(activeCall.event, {
				type: "tool-result",
				id,
				error: "AssistantFrame tool provider has been removed"
			});
		} catch (error) {
			if (sendFailed) console.error(error);
			else {
				sendFailed = true;
				sendError = error;
			}
		}
		if (sendFailed) throw sendError;
	}
	sendMessage(event, message) {
		event.source?.postMessage({
			channel: FRAME_MESSAGE_CHANNEL,
			message
		}, { targetOrigin: event.origin });
	}
	getProviders() {
		return Array.from(new Set(this._providers.values()));
	}
	getTool(toolName) {
		let resolved;
		for (const provider of this.getProviders()) {
			const tool = provider.getModelContext().tools?.[toolName];
			if (tool) resolved = {
				provider,
				tool
			};
		}
		return resolved;
	}
	getModelContext() {
		return this.getProviders().map((provider) => provider.getModelContext()).reduce((merged, context) => ({
			system: context.system ? merged.system ? `${merged.system}\n\n${context.system}` : context.system : merged.system,
			tools: {
				...merged.tools || {},
				...context.tools || {}
			}
		}), {});
	}
	broadcastUpdate() {
		if (this._disposed) return;
		this.postModelContext();
	}
	postModelContext() {
		if (window.parent && window.parent !== window) {
			const updateMessage = {
				type: "model-context-update",
				context: serializeModelContext(this.getModelContext())
			};
			window.parent.postMessage({
				channel: FRAME_MESSAGE_CHANNEL,
				message: updateMessage
			}, this._targetOrigin);
		}
	}
	removeProvider(id, origin) {
		const provider = this._providers.get(id);
		this._providers.delete(id);
		const unsubscribe = this._providerUnsubscribes.get(id);
		this._providerUnsubscribes.delete(id);
		if (origin === "*") {
			this._wildcardRegistrations -= 1;
			if (this._wildcardRegistrations === 0 && this._strictRegistrations === 0) this._targetOrigin = getDefaultTargetOrigin();
		} else {
			this._strictRegistrations -= 1;
			if (this._strictRegistrations === 0) this._targetOrigin = this._wildcardRegistrations > 0 ? "*" : getDefaultTargetOrigin();
		}
		return {
			unsubscribe,
			removedProvider: provider && !this.getProviders().includes(provider) ? provider : void 0
		};
	}
	static addModelContextProvider(provider, targetOrigin) {
		const origin = targetOrigin ?? getDefaultTargetOrigin();
		const instance = AssistantFrameProvider.getInstance(origin);
		const id = Symbol();
		instance._providers.set(id, provider);
		if (origin === "*") instance._wildcardRegistrations += 1;
		else instance._strictRegistrations += 1;
		try {
			const unsubscribe = provider.subscribe?.(() => instance.broadcastUpdate());
			if (unsubscribe) instance._providerUnsubscribes.set(id, unsubscribe);
			instance.broadcastUpdate();
		} catch (error) {
			const { unsubscribe, removedProvider } = instance.removeProvider(id, origin);
			try {
				if (removedProvider) instance.cancelToolCallsForProvider(removedProvider);
			} catch (cancelError) {
				console.error(cancelError);
			}
			try {
				unsubscribe?.();
			} catch (unsubscribeError) {
				console.error(unsubscribeError);
			}
			try {
				instance.broadcastUpdate();
			} catch (broadcastError) {
				console.error(broadcastError);
			}
			throw error;
		}
		let released = false;
		return () => {
			if (released) return;
			released = true;
			const { unsubscribe, removedProvider } = instance.removeProvider(id, origin);
			let cleanupFailed = false;
			let cleanupError;
			const runCleanup = (cleanup) => {
				try {
					cleanup();
				} catch (error) {
					if (cleanupFailed) console.error(error);
					else {
						cleanupFailed = true;
						cleanupError = error;
					}
				}
			};
			if (removedProvider) runCleanup(() => instance.cancelToolCallsForProvider(removedProvider));
			if (unsubscribe) runCleanup(unsubscribe);
			runCleanup(() => instance.broadcastUpdate());
			if (cleanupFailed) throw cleanupError;
		};
	}
	static dispose() {
		if (AssistantFrameProvider._instance) {
			const instance = AssistantFrameProvider._instance;
			instance._disposed = true;
			if (instance._startupTimer !== void 0) {
				clearTimeout(instance._startupTimer);
				instance._startupTimer = void 0;
			}
			window.removeEventListener("message", instance.handleMessage);
			let cleanupFailed = false;
			let cleanupError;
			const runCleanup = (cleanup) => {
				try {
					cleanup();
				} catch (error) {
					if (cleanupFailed) console.error(error);
					else {
						cleanupFailed = true;
						cleanupError = error;
					}
				}
			};
			instance._providerUnsubscribes.forEach((unsubscribe) => {
				if (unsubscribe) runCleanup(unsubscribe);
			});
			instance._providerUnsubscribes.clear();
			instance._providers.clear();
			runCleanup(() => instance.postModelContext());
			instance._activeToolCalls.forEach(({ abortController, event }, id) => {
				runCleanup(() => {
					abortController.abort();
					instance.sendMessage(event, {
						type: "tool-result",
						id,
						error: "AssistantFrameProvider has been disposed"
					});
				});
			});
			instance._activeToolCalls.clear();
			AssistantFrameProvider._instance = null;
			if (cleanupFailed) throw cleanupError;
		}
	}
};
//#endregion
export { AssistantFrameProvider };
