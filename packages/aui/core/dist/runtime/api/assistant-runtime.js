import { ThreadListRuntimeImpl } from "./thread-list-runtime.js";
//#region src/runtime/api/assistant-runtime.ts
var AssistantRuntimeImpl = class {
	threads;
	_thread;
	_core;
	constructor(_core) {
		this._core = _core;
		this.threads = new ThreadListRuntimeImpl(_core.threads);
		this._thread = this.threads.main;
		this.__internal_bindMethods();
	}
	__internal_bindMethods() {
		this.registerModelContextProvider = this.registerModelContextProvider.bind(this);
	}
	get thread() {
		return this._thread;
	}
	registerModelContextProvider(provider) {
		return this._core.registerModelContextProvider(provider);
	}
};
//#endregion
export { AssistantRuntimeImpl };
