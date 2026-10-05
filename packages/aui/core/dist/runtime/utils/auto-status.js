import { hasPendingToolAction } from "../../utils/normalizePartStatus.js";
//#region src/runtime/utils/auto-status.ts
const isPendingToolCall = (c) => c.type === "tool-call" && c.result === void 0;
/** A pending tool call whose nested conversation is still streaming; the outer message stays running until the nested run settles. */
const isBackgroundToolCall = (c) => {
	if (c.type !== "tool-call" || c.result !== void 0) return false;
	const last = c.messages?.at(-1);
	return last?.role === "assistant" && last.status.type === "running";
};
const isInterruptedToolCall = (c) => c.type === "tool-call" && hasPendingToolAction(c);
const symbolAutoStatus = Symbol("autoStatus");
const AUTO_STATUS_RUNNING = Object.freeze(Object.assign({ type: "running" }, { [symbolAutoStatus]: true }));
const AUTO_STATUS_COMPLETE = Object.freeze(Object.assign({
	type: "complete",
	reason: "unknown"
}, { [symbolAutoStatus]: true }));
const AUTO_STATUS_CANCELLED = Object.freeze(Object.assign({
	type: "incomplete",
	reason: "cancelled"
}, { [symbolAutoStatus]: true }));
const AUTO_STATUS_PENDING = Object.freeze(Object.assign({
	type: "requires-action",
	reason: "tool-calls"
}, { [symbolAutoStatus]: true }));
const AUTO_STATUS_INTERRUPT = Object.freeze(Object.assign({
	type: "requires-action",
	reason: "interrupt"
}, { [symbolAutoStatus]: true }));
const isAutoStatus = (status) => status[symbolAutoStatus] === true;
const getAutoStatus = (isLast, isRunning, hasInterruptedToolCalls, hasPendingToolCalls, error, isCancelled, hasBackgroundToolCalls) => {
	if (isLast && error !== void 0 && error !== null) return Object.assign({
		type: "incomplete",
		reason: "error",
		error
	}, { [symbolAutoStatus]: true });
	return isLast && isRunning ? AUTO_STATUS_RUNNING : hasInterruptedToolCalls ? AUTO_STATUS_INTERRUPT : hasBackgroundToolCalls && !isCancelled ? AUTO_STATUS_RUNNING : hasPendingToolCalls ? AUTO_STATUS_PENDING : isCancelled ? AUTO_STATUS_CANCELLED : AUTO_STATUS_COMPLETE;
};
/** Status for a message entering the repository: the nested conversation is not being fed here, so it never keeps the message running. */
const getRepositoryContentAutoStatus = (content) => getAutoStatus(false, false, typeof content !== "string" && content.some(isInterruptedToolCall), typeof content !== "string" && content.some(isPendingToolCall));
const getContentAutoStatus = (content, isLast, isRunning) => getAutoStatus(isLast, isRunning, typeof content !== "string" && content.some(isInterruptedToolCall), typeof content !== "string" && content.some(isPendingToolCall), void 0, void 0, typeof content !== "string" && content.some(isBackgroundToolCall));
//#endregion
export { getAutoStatus, getContentAutoStatus, getRepositoryContentAutoStatus, isAutoStatus, isBackgroundToolCall, isInterruptedToolCall, isPendingToolCall };
