import { notifyEventListeners } from "@assistant-ui/core/internal";
//#region src/devtools/DevToolsHooks.ts
let cachedHook;
const getHook = () => {
	if (cachedHook) return cachedHook;
	const createHook = () => ({
		apis: /* @__PURE__ */ new Map(),
		nextId: 0,
		listeners: /* @__PURE__ */ new Set()
	});
	if (typeof window === "undefined") {
		cachedHook = createHook();
		return cachedHook;
	}
	const existingHook = window.__ASSISTANT_UI_DEVTOOLS_HOOK__;
	if (existingHook) {
		cachedHook = existingHook;
		return existingHook;
	}
	const newHook = createHook();
	window.__ASSISTANT_UI_DEVTOOLS_HOOK__ = newHook;
	cachedHook = newHook;
	return newHook;
};
const notifyListeners = (apiId) => {
	notifyEventListeners(getHook().listeners, apiId, "DevTools");
};
var DevToolsHooks = class {
	static subscribe(listener) {
		const hook = getHook();
		hook.listeners.add(listener);
		return () => {
			hook.listeners.delete(listener);
		};
	}
	static clearEventLogs(apiId) {
		const entry = getHook().apis.get(apiId);
		if (!entry) return;
		entry.logs = [];
		notifyListeners(apiId);
	}
	static getApis() {
		return getHook().apis;
	}
};
var DevToolsProviderApi = class DevToolsProviderApi {
	static MAX_EVENT_LOGS_PER_API = 200;
	static register(aui) {
		const hook = getHook();
		for (const entry of hook.apis.values()) if (entry.api === aui) return () => {};
		const apiId = hook.nextId++;
		const entry = {
			api: aui,
			logs: []
		};
		const eventUnsubscribe = aui.on?.("*", (e) => {
			const entry = hook.apis.get(apiId);
			if (!entry) return;
			entry.logs.push({
				time: /* @__PURE__ */ new Date(),
				event: e.event,
				data: e.payload
			});
			if (entry.logs.length > DevToolsProviderApi.MAX_EVENT_LOGS_PER_API) entry.logs = entry.logs.slice(-DevToolsProviderApi.MAX_EVENT_LOGS_PER_API);
			notifyListeners(apiId);
		});
		const stateUnsubscribe = aui.subscribe?.(() => {
			notifyListeners(apiId);
		});
		hook.apis.set(apiId, entry);
		notifyListeners(apiId);
		return () => {
			const hook = getHook();
			if (!hook.apis.get(apiId)) return;
			eventUnsubscribe?.();
			stateUnsubscribe?.();
			hook.apis.delete(apiId);
			notifyListeners(apiId);
		};
	}
};
//#endregion
export { DevToolsHooks, DevToolsProviderApi };
