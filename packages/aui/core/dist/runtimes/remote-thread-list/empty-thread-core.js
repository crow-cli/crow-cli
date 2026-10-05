import { InertThreadRuntimeCore, createInertComposer } from "../inert/InertThreadRuntimeCore.js";
//#region src/runtimes/remote-thread-list/empty-thread-core.ts
const EMPTY_THREAD_ERROR = /* @__PURE__ */ new Error("This is the empty thread, a placeholder for the main thread. You cannot perform any actions on this thread instance. This error is probably because you tried to call a thread method in your render function. Call the method inside a `useEffect` hook instead.");
var EmptyThreadRuntimeCore = class extends InertThreadRuntimeCore {
	get error() {
		return EMPTY_THREAD_ERROR;
	}
	messages = [];
	composer = createInertComposer(EMPTY_THREAD_ERROR, true);
	isLoading = true;
	getMessageById() {}
	getBranches() {
		return [];
	}
	export() {
		return { messages: [] };
	}
	subscribe() {
		return () => {};
	}
	waitForUpdate() {
		return Promise.reject(EMPTY_THREAD_ERROR);
	}
};
const EMPTY_THREAD_CORE = new EmptyThreadRuntimeCore();
//#endregion
export { EMPTY_THREAD_CORE };
