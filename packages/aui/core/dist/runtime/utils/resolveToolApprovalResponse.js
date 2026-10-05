import { toolApprovalAcceptsText } from "../../types/message.js";
//#region src/runtime/utils/resolveToolApprovalResponse.ts
const APPROVED_BY_KIND = {
	"allow-once": true,
	"allow-always": true,
	"reject-once": false,
	"reject-always": false
};
/**
* Resolves a renderer-facing approval response (boolean, optionId, or
* free-form answer) against the approval's request shape into the
* runtime-facing decision shape.
*/
const resolveToolApprovalResponse = (approval, response) => {
	const text = response.text;
	if (text !== void 0 && !toolApprovalAcceptsText(approval)) throw new Error(`Tool approval "${approval.id}" does not accept a free-form answer; the request must declare display "text" or allowFreeform`);
	let approved;
	let optionId;
	if ("optionId" in response) {
		const option = approval.options?.find((o) => o.id === response.optionId);
		if (!option) throw new Error(`Tool approval has no option with id "${response.optionId}"`);
		if ("approved" in response) approved = response.approved;
		else {
			if (!Object.hasOwn(APPROVED_BY_KIND, option.kind)) throw new Error(`Tool approval option "${option.id}" has a custom kind "${option.kind}"; respond with an explicit approved value instead`);
			approved = APPROVED_BY_KIND[option.kind];
		}
		optionId = option.id;
	} else if ("approved" in response) approved = response.approved;
	else {
		if (approval.display !== "text" && approval.display !== "select") throw new Error(`Tool approval "${approval.id}" is a decision, not a question; respond with an explicit approved value, optionally alongside the answer`);
		approved = true;
	}
	return {
		approvalId: approval.id,
		approved,
		...optionId !== void 0 && { optionId },
		...text !== void 0 && { text },
		...response.reason != null && { reason: response.reason }
	};
};
//#endregion
export { resolveToolApprovalResponse };
