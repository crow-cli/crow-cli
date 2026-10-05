import { COMPLETE_STATUS, RUNNING_STATUS } from "./normalizePartStatus.js";
//#region src/utils/getGroupStatus.ts
const getGroupStatus = (parts) => {
	for (const part of parts) if (part?.status.type === "running") return RUNNING_STATUS;
	return parts.at(-1)?.status ?? COMPLETE_STATUS;
};
const getGroupSummary = (parts, indices) => {
	const counts = {
		running: 0,
		complete: 0,
		incomplete: 0,
		requiresAction: 0
	};
	let status = COMPLETE_STATUS;
	let isRunning = false;
	for (const index of indices) {
		status = parts[index]?.status ?? COMPLETE_STATUS;
		switch (status.type) {
			case "running":
				counts.running++;
				isRunning = true;
				break;
			case "complete":
				counts.complete++;
				break;
			case "incomplete":
				counts.incomplete++;
				break;
			case "requires-action": counts.requiresAction++;
		}
	}
	return {
		status: isRunning ? RUNNING_STATUS : status,
		counts
	};
};
//#endregion
export { getGroupStatus, getGroupSummary };
