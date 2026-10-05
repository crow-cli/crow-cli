//#region src/runtime/utils/pending-tool-calls.ts
const scanPendingToolCalls = (messages, getMessage, getToolCallId) => {
	const pending = /* @__PURE__ */ new Map();
	for (const message of messages) {
		const value = getMessage(message);
		if (!value) continue;
		if ("toolCalls" in value) for (const toolCall of value.toolCalls) pending.set(getToolCallId(toolCall), toolCall);
		else pending.delete(value.toolCallId);
	}
	return [...pending.values()];
};
const createToolCallCancellationStub = (toolCall) => ({
	type: "tool",
	name: toolCall.name,
	tool_call_id: toolCall.id,
	content: JSON.stringify({ cancelled: true }),
	status: "error"
});
//#endregion
export { createToolCallCancellationStub, scanPendingToolCalls };
