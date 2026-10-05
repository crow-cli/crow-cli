//#region src/runtimes/local/should-continue.ts
const shouldContinue = (result, humanToolNames) => {
	if (result.status?.type !== "requires-action" || result.status.reason !== "tool-calls") return false;
	if (result.content.some((c) => c.type === "tool-call" && c.result === void 0 && c.approval !== void 0 && c.approval.approved === void 0 && c.approval.resolution === void 0)) return false;
	if (humanToolNames === void 0) return result.content.every((c) => c.type !== "tool-call" || c.result !== void 0 || c.approval !== void 0);
	return result.content.every((c) => c.type !== "tool-call" || c.result !== void 0 || c.approval !== void 0 || !humanToolNames.includes(c.toolName));
};
//#endregion
export { shouldContinue };
