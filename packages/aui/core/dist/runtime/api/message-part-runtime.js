import { createToolInteraction } from "../utils/tool-interactions.js";
import { resolveToolApprovalResponse } from "../utils/resolveToolApprovalResponse.js";
import { ToolResponse } from "assistant-stream";
//#region src/runtime/api/message-part-runtime.ts
var MessagePartRuntimeImpl = class {
	get path() {
		return this.contentBinding.path;
	}
	contentBinding;
	messageApi;
	threadApi;
	constructor(contentBinding, messageApi, threadApi) {
		this.contentBinding = contentBinding;
		this.messageApi = messageApi;
		this.threadApi = threadApi;
		this.__internal_bindMethods();
	}
	__internal_bindMethods() {
		this.addToolResult = this.addToolResult.bind(this);
		this.resumeToolCall = this.resumeToolCall.bind(this);
		this.respondToToolApproval = this.respondToToolApproval.bind(this);
		this.unstable_recordInteraction = this.unstable_recordInteraction.bind(this);
		this.getState = this.getState.bind(this);
		this.subscribe = this.subscribe.bind(this);
	}
	getState() {
		return this.contentBinding.getState();
	}
	addToolResult(result) {
		const state = this.contentBinding.getState();
		if (!state) throw new Error("Message part is not available");
		if (state.type !== "tool-call") throw new Error("Tried to add tool result to non-tool message part");
		if (!this.messageApi) throw new Error("Message API is not available. This is likely a bug in assistant-ui.");
		if (!this.threadApi) throw new Error("Thread API is not available");
		const message = this.messageApi.getState();
		if (!message) throw new Error("Message is not available");
		const toolName = state.toolName;
		const toolCallId = state.toolCallId;
		const response = ToolResponse.toResponse(result);
		this.threadApi.getState().addToolResult({
			messageId: message.id,
			toolName,
			toolCallId,
			result: response.result,
			isError: response.isError,
			...response.artifact !== void 0 && { artifact: response.artifact },
			...response.modelContent !== void 0 && { modelContent: response.modelContent }
		});
	}
	resumeToolCall(payload) {
		const state = this.contentBinding.getState();
		if (!state) throw new Error("Message part is not available");
		if (state.type !== "tool-call") throw new Error("Tried to resume tool call on non-tool message part");
		if (!this.threadApi) throw new Error("Thread API is not available");
		const toolCallId = state.toolCallId;
		this.threadApi.getState().resumeToolCall({
			toolCallId,
			payload
		});
		this.unstable_recordInteraction({
			type: "human-response",
			payload
		}).catch(() => {});
	}
	respondToToolApproval(response) {
		const state = this.contentBinding.getState();
		if (!state) throw new Error("Message part is not available");
		if (state.type !== "tool-call") throw new Error("Tried to respond to tool approval on non-tool message part");
		if (!state.approval || state.approval.approved !== void 0 || state.approval.resolution !== void 0) throw new Error("Tool call has no pending approval");
		if (!this.threadApi) throw new Error("Thread API is not available");
		return this.threadApi.getState().respondToToolApproval(resolveToolApprovalResponse(state.approval, response));
	}
	async unstable_recordInteraction(input) {
		const state = this.contentBinding.getState();
		if (!state) throw new Error("Message part is not available");
		if (state.type !== "tool-call") throw new Error("Tried to record interaction on non-tool message part");
		if (!this.messageApi) throw new Error("Message API is not available. This is likely a bug in assistant-ui.");
		if (!this.threadApi) throw new Error("Thread API is not available");
		const message = this.messageApi.getState();
		if (!message) throw new Error("Message is not available");
		const core = this.threadApi.getState();
		if (!core.unstable_recordToolInteraction) throw new Error("Runtime does not support recording tool interactions.");
		await core.unstable_recordToolInteraction({
			messageId: message.id,
			toolCallId: state.toolCallId,
			interaction: createToolInteraction(input)
		});
	}
	subscribe(callback) {
		return this.contentBinding.subscribe(callback);
	}
};
//#endregion
export { MessagePartRuntimeImpl };
