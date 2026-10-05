//#region src/core/serialization/tool-call-part-registry.ts
const createToolCallPartRegistry = () => {
	const toolCallControllers = /* @__PURE__ */ new Map();
	const closedToolCallArgs = /* @__PURE__ */ new Set();
	const tryGet = (toolCallId) => toolCallControllers.get(toolCallId);
	const get = (toolCallId) => {
		const toolCallController = tryGet(toolCallId);
		if (!toolCallController) throw new Error(`Encountered tool call with unknown id: ${toolCallId}`);
		return toolCallController;
	};
	const closeArgsText = (toolCallController) => {
		toolCallController.argsText.close();
		closedToolCallArgs.add(toolCallController);
	};
	return {
		start: (toolCallId, create) => {
			if (toolCallControllers.has(toolCallId)) throw new Error(`Encountered duplicate tool call id: ${toolCallId}`);
			const toolCallController = create();
			toolCallControllers.set(toolCallId, toolCallController);
			return toolCallController;
		},
		get,
		tryGet,
		appendArgsText: (toolCallController, argsTextDelta) => {
			toolCallController.argsText.append(argsTextDelta);
		},
		closeArgsText,
		isArgsTextClosed: (toolCallController) => {
			return closedToolCallArgs.has(toolCallController);
		},
		setResponse: (toolCallController, response) => {
			toolCallController.setResponse(response);
			closedToolCallArgs.add(toolCallController);
		},
		closeOpenArgsText: () => {
			for (const toolCallController of toolCallControllers.values()) {
				if (closedToolCallArgs.has(toolCallController)) continue;
				closeArgsText(toolCallController);
			}
		},
		closeAll: () => {
			toolCallControllers.forEach((toolCallController) => {
				closedToolCallArgs.add(toolCallController);
				toolCallController.close();
			});
			toolCallControllers.clear();
			closedToolCallArgs.clear();
		}
	};
};
//#endregion
export { createToolCallPartRegistry };
