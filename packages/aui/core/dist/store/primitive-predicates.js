//#region src/store/primitive-predicates.ts
/**
* Disabled predicates shared by every binding's primitive layer. Each binding
* consumes these as state selectors so the disabled semantics of a primitive
* cannot drift between frameworks.
*/
const composerSendDisabled = (s) => !s.composer.canSend || s.thread.isRunning && !s.thread.capabilities.queue && s.thread.voice === void 0;
const composerCancelDisabled = (s) => !s.composer.canCancel;
const composerInputDisabled = (s) => s.thread.isDisabled || s.composer.dictation?.inputDisabled === true;
const actionBarEditDisabled = (s) => s.composer.isEditing || s.optional.message?.submission !== void 0 || s.optional.thread?.voice !== void 0 || s.optional.thread?.capabilities.edit === false;
const actionBarReloadDisabled = (s) => s.thread.isRunning || s.thread.isDisabled || s.thread.voice !== void 0 || s.message.role !== "assistant" || !s.thread.capabilities.reload;
const actionBarCopyDisabled = (s) => !((s.message.role !== "assistant" || s.message.status?.type !== "running") && s.message.parts.some((part) => part.type === "text" && part.text.length > 0));
const branchPickerPreviousDisabled = (s) => s.message.branchNumber <= 1 || !s.thread.capabilities.switchToBranch || s.thread.isRunning && !s.thread.capabilities.switchBranchDuringRun;
const branchPickerNextDisabled = (s) => s.message.branchNumber >= s.message.branchCount || !s.thread.capabilities.switchToBranch || s.thread.isRunning && !s.thread.capabilities.switchBranchDuringRun;
const suggestionSendMode = (thread) => {
	if (thread.voice !== void 0) return thread.voice.canSendText ? "now" : "blocked";
	if (!thread.isRunning) return "now";
	return thread.capabilities.queue ? "queued" : "blocked";
};
const suggestionTriggerDisabled = (s, send) => s.thread.isDisabled || send && suggestionSendMode(s.thread) === "blocked";
const messageErrorText = (s) => {
	if (s.message.status?.type !== "incomplete" || s.message.status.reason !== "error") return;
	const error = s.message.status.error;
	if (typeof error === "string") return error;
	if (typeof error === "object" && error !== null && "message" in error && typeof error.message === "string") return error.message;
	return error ?? "An error occurred";
};
const threadListLoadMoreDisabled = (s) => !s.threads.hasMore || s.threads.isLoading || s.threads.isLoadingMore;
//#endregion
export { actionBarCopyDisabled, actionBarEditDisabled, actionBarReloadDisabled, branchPickerNextDisabled, branchPickerPreviousDisabled, composerCancelDisabled, composerInputDisabled, composerSendDisabled, messageErrorText, suggestionSendMode, suggestionTriggerDisabled, threadListLoadMoreDisabled };
