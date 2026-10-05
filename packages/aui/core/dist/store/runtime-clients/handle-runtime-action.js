import { isSilentRuntimeAction } from "../../utils/silent-runtime-action.js";
//#region src/store/runtime-clients/handle-runtime-action.ts
const handleRuntimeAction = (label, execute) => {
	const task = execute();
	task.catch((error) => {
		if (isSilentRuntimeAction(error)) return;
		console.error(`[assistant-ui] ${label} failed:`, error);
	});
	return task;
};
//#endregion
export { handleRuntimeAction };
