//#region src/utils/normalizePartStatus.ts
const COMPLETE_STATUS = Object.freeze({ type: "complete" });
const RUNNING_STATUS = Object.freeze({ type: "running" });
const INCOMPLETE_STATUSES = Object.freeze({
	cancelled: Object.freeze({
		type: "incomplete",
		reason: "cancelled"
	}),
	length: Object.freeze({
		type: "incomplete",
		reason: "length"
	}),
	"content-filter": Object.freeze({
		type: "incomplete",
		reason: "content-filter"
	}),
	other: Object.freeze({
		type: "incomplete",
		reason: "other"
	}),
	error: Object.freeze({
		type: "incomplete",
		reason: "error"
	})
});
const normalizePartStatus = (part) => {
	const status = part.status;
	if (!status || typeof status !== "object") return void 0;
	const { type } = status;
	if (type === "running") return RUNNING_STATUS;
	if (type === "complete") return COMPLETE_STATUS;
	if (type !== "incomplete") return void 0;
	const { reason } = status;
	return INCOMPLETE_STATUSES[reason === "cancelled" || reason === "length" || reason === "content-filter" || reason === "other" || reason === "error" ? reason : "other"];
};
const hasPendingToolAction = (part) => part.interrupt != null || part.approval != null && part.approval.approved === void 0 && part.approval.resolution === void 0;
const toMessagePartStatus = (message, partIndex, part) => {
	if (message.role !== "assistant") return COMPLETE_STATUS;
	if (part.type === "tool-call") {
		if (part.result === void 0 || part.isPreliminary || hasPendingToolAction(part)) return message.status;
		else return COMPLETE_STATUS;
	}
	if (message.status.type === "running") {
		const status = normalizePartStatus(part);
		if (status) return status;
	}
	const isLastPart = partIndex === Math.max(0, message.content.length - 1);
	if (message.status.type === "requires-action") return COMPLETE_STATUS;
	return isLastPart ? message.status : COMPLETE_STATUS;
};
//#endregion
export { COMPLETE_STATUS, RUNNING_STATUS, hasPendingToolAction, normalizePartStatus, toMessagePartStatus };
