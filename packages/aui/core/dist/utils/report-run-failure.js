import { isMessageNotSentError } from "../types/error.js";
//#region src/utils/report-run-failure.ts
const reportRunFailure = (label, task) => {
	Promise.resolve(task).catch((error) => {
		if (isMessageNotSentError(error)) return;
		console.error(`[assistant-ui] ${label} failed`, error);
	});
};
//#endregion
export { reportRunFailure };
