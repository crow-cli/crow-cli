import { withBatchedStateReads } from "./proxied-assistant-state.js";
import { useState } from "@assistant-ui/tap/react-shim";
//#region src/utils/NotificationManager.ts
const reportListenerError = (error) => {
	console.error("NotificationManager: event listener error", error);
};
const invokeListener = (cb, payload, clientStack) => {
	try {
		const result = cb(payload, clientStack);
		if (result !== null && (typeof result === "object" || typeof result === "function") && typeof result.then === "function") Promise.resolve(result).catch(reportListenerError);
	} catch (e) {
		reportListenerError(e);
	}
};
const createNotificationManager = () => {
	const listeners = /* @__PURE__ */ new Map();
	const wildcardListeners = /* @__PURE__ */ new Set();
	const subscribers = /* @__PURE__ */ new Set();
	return {
		on(event, callback) {
			const cb = callback;
			if (event === "*") {
				wildcardListeners.add(cb);
				return () => wildcardListeners.delete(cb);
			}
			let set = listeners.get(event);
			if (!set) {
				set = /* @__PURE__ */ new Set();
				listeners.set(event, set);
			}
			set.add(cb);
			return () => {
				set.delete(cb);
				if (set.size === 0 && listeners.get(event) === set) listeners.delete(event);
			};
		},
		emit(event, payload, clientStack) {
			if (!listeners.has(event) && wildcardListeners.size === 0) return;
			queueMicrotask(() => {
				const eventListeners = listeners.get(event);
				if (eventListeners) for (const cb of eventListeners) invokeListener(cb, payload, clientStack);
				if (wildcardListeners.size > 0) {
					const wrapped = {
						event,
						payload
					};
					for (const cb of wildcardListeners) invokeListener(cb, wrapped, clientStack);
				}
			});
		},
		subscribe(callback) {
			subscribers.add(callback);
			return () => subscribers.delete(callback);
		},
		notifySubscribers() {
			withBatchedStateReads(() => {
				for (const cb of subscribers) try {
					cb();
				} catch (e) {
					console.error("NotificationManager: subscriber callback error", e);
				}
			});
		}
	};
};
const useNotificationManager = () => {
	return useState(createNotificationManager)[0];
};
//#endregion
export { createNotificationManager, useNotificationManager };
