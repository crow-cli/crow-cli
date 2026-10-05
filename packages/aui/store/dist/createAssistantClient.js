"use client";
import { DefaultAssistantClient } from "./utils/react-assistant-context.js";
import { createNotificationManager } from "./utils/NotificationManager.js";
import { useDestroySignalProvider } from "./utils/destroy-signal-context.js";
import { applyTransformScopes, useAuiRoot } from "./useAui.js";
import { useSyncExternalStore } from "@assistant-ui/tap/react-shim";
import { createTapRoot, flushTapSync } from "@assistant-ui/tap";
//#region src/createAssistantClient.ts
const isConfigSource = (config) => typeof config.getConfig === "function";
const NO_OP_SUBSCRIBE = () => () => {};
const toConfigSource = (config) => {
	if (!isConfigSource(config)) return {
		getConfig: () => config,
		subscribe: NO_OP_SUBSCRIBE
	};
	let cache = null;
	return {
		getConfig: () => (cache ??= { value: config.getConfig() }).value,
		subscribe: (listener) => {
			cache = null;
			return config.subscribe(() => {
				cache = null;
				listener();
			});
		}
	};
};
const isClientSource = (parent) => typeof parent.getClient === "function" && !("on" in parent);
const toClientSource = (parent) => isClientSource(parent) ? parent : {
	getClient: () => parent,
	subscribe: parent.subscribe
};
/**
* Creates an `AssistantClient` outside any UI framework.
*
* The client's scopes run as tap resources inside a standalone tap root; no
* React renderer is involved. This is the construction seam for non-React
* bindings: a framework bridge creates the handle, reads the current client
* with `getClient`, re-reads it whenever `subscribe` fires (a structural
* change produces a new client object, a value-only update keeps its
* identity), and holds a subscription for as long as it needs the client
* alive.
*
* The handle's lifecycle rides its subscriber count. Scopes render lazily on the first read and mount when the first subscriber attaches; state updates before that throw, so an imperative consumer without a reactive framework holds a no-op subscription. When the last subscriber releases, the root soft-unmounts on the next task: effects other than insertion effects clean up, state is retained, and a later subscriber remounts the same scopes. `destroy` is the permanent teardown: it aborts the destroy signal and synchronously releases every scope, insertion effects included, whether or not subscribers are attached. A bridge that only releases its subscriptions keeps insertion effects mounted until `destroy`.
*
* The parent may be a plain client or another source/handle. Passing a source
* keeps the child bound to the parent's current client across the parent's
* structural changes without remounting the child's scopes.
*
* The config may be a plain value, captured at creation, or an
* {@link AssistantConfigSource} that is re-read in the root render whenever it
* notifies, so a binding can deliver config changes (updated element args,
* added or removed scopes) without remounting the surviving scopes.
*/
const createAssistantClient = (config, options) => {
	const parentSource = toClientSource(options?.parent ?? DefaultAssistantClient);
	const configSource = toConfigSource(config);
	const clientRef = {
		parent: parentSource.getClient(),
		current: null
	};
	const destroyController = new AbortController();
	const notifications = createNotificationManager();
	const root = createTapRoot(function AssistantClientRoot() {
		const parent = useSyncExternalStore(parentSource.subscribe, parentSource.getClient, parentSource.getClient);
		const currentConfig = useSyncExternalStore(configSource.subscribe, configSource.getConfig, configSource.getConfig);
		const entries = Object.entries(applyTransformScopes(currentConfig, parent));
		const result = useDestroySignalProvider(destroyController.signal, function useRootClient() {
			return useAuiRoot({
				parent,
				entries,
				clientRef,
				notifications
			});
		});
		if (clientRef.current === null) clientRef.current = result.client;
		return result;
	}, { mountOnSubscribe: true });
	const notify = () => {
		clientRef.parent = parentSource.getClient();
		clientRef.current = root.getValue().client;
		flushTapSync(notifications.notifySubscribers);
	};
	let subscriberCount = 0;
	let unwire = null;
	let destroyed = false;
	const wire = () => {
		const unsubscribeParent = parentSource.subscribe(notify);
		let unsubscribeRoot;
		try {
			unsubscribeRoot = root.subscribe(notify);
		} catch (error) {
			unsubscribeParent();
			throw error;
		}
		clientRef.parent = parentSource.getClient();
		clientRef.current = root.getValue().client;
		unwire = () => {
			unwire = null;
			unsubscribeRoot();
			unsubscribeParent();
		};
	};
	const release = () => {
		unwire?.();
		root.unmount();
	};
	return {
		getClient: () => root.getValue().client,
		subscribe: (listener) => {
			if (destroyed) return () => {};
			const unsubscribe = notifications.subscribe(listener);
			if (subscriberCount++ === 0) {
				try {
					wire();
				} catch (error) {
					subscriberCount--;
					unsubscribe();
					throw error;
				}
				if (destroyed) release();
			}
			let isSubscribed = true;
			return () => {
				if (!isSubscribed) return;
				isSubscribed = false;
				unsubscribe();
				if (--subscriberCount === 0) unwire?.();
			};
		},
		destroy: () => {
			if (destroyed) return;
			destroyed = true;
			destroyController.abort();
			if (subscriberCount > 0 && unwire === null) return;
			release();
		}
	};
};
//#endregion
export { createAssistantClient };
