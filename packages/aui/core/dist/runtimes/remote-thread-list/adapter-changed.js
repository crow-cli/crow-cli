import { SILENT_RUNTIME_ACTION } from "../../utils/silent-runtime-action.js";
//#region src/runtimes/remote-thread-list/adapter-changed.ts
var ThreadListAdapterChangedError = class extends Error {
	[SILENT_RUNTIME_ACTION] = true;
	constructor() {
		super("Thread list adapter changed while an operation was pending.");
		this.name = "ThreadListAdapterChangedError";
	}
};
//#endregion
export { ThreadListAdapterChangedError };
