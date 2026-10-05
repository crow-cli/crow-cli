"use client";
import { isDerivedHook } from "./utils/derived-hook.js";
import { createClientAccessor, getClientId, isScopeAvailable, isScopeUnavailable } from "./utils/client-accessor.js";
import { createOptionalClientView } from "./utils/optional-client-view.js";
import { DefaultAssistantClient, createRootAssistantClient, setTapEffects, useAssistantContextProvider, useAssistantContextValue } from "./utils/react-assistant-context.js";
import { getTransformScopes } from "./attachTransformScopes.js";
import { normalizeEventSelector } from "./types/events.js";
import { getClientIndex } from "./utils/tap-client-stack-context.js";
import { ClientResource } from "./useClientResource.js";
import { useNotificationManager } from "./utils/NotificationManager.js";
import { useAssistantTapContextProvider } from "./utils/tap-assistant-context.js";
import { useDestroySignalProvider } from "./utils/destroy-signal-context.js";
import { useHostDestroySignal } from "./utils/useHostDestroySignal.js";
import { useShallowStable } from "./utils/useShallowStable.js";
import { isDevelopment } from "./utils/env.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useInsertionEffect, useMemo, useRef, useState, useSyncExternalStore } from "@assistant-ui/tap/react-shim";
import { flushTapSync, resource, useResource, useResources, useTapHost, useTapRoot, withKey } from "@assistant-ui/tap";
//#region src/useAui.ts
const applyTransformScopes = (clients, parent) => {
	const scopes = { ...clients };
	const visited = /* @__PURE__ */ new Set();
	let changed = true;
	while (changed) {
		changed = false;
		for (const element of Object.values(scopes)) {
			if (visited.has(element.hook)) continue;
			visited.add(element.hook);
			const transform = getTransformScopes(element.hook);
			if (transform) {
				transform(scopes, parent);
				changed = true;
				break;
			}
		}
	}
	return scopes;
};
const isDerivedElement = (element) => isDerivedHook(element.hook);
const metaOf = (element) => {
	if (!isDerivedElement(element)) return {
		source: "root",
		query: {}
	};
	const props = element.args[0];
	return {
		source: props.source,
		query: props.query ?? {}
	};
};
const EVENT_RECEIVER_REF = Symbol.for("aui.event-receiver-ref");
const createClientObject = (parent, fields) => {
	const proto = parent === DefaultAssistantClient ? createRootAssistantClient() : parent;
	const client = Object.create(proto);
	Object.assign(client, fields);
	let optional;
	Object.defineProperty(client, "optional", {
		get: () => optional ??= createOptionalClientView(client),
		enumerable: false
	});
	return client;
};
const useClientFields = ({ notifications, clientRef }) => {
	return useMemo(() => ({
		subscribe: notifications.subscribe,
		on: function(selector, callback) {
			if (!this) throw new Error("const { on } = useAui() is not supported. Use aui.on() instead.");
			const { scope, event } = normalizeEventSelector(selector);
			const receiverRef = selector[EVENT_RECEIVER_REF];
			if (scope !== "*" && !receiverRef) {
				if (isScopeUnavailable(this[scope])) throw new Error(`Scope "${scope}" is not available. Use { scope: "*", event: "${event}" } to listen globally.`);
			}
			const localUnsub = notifications.on(event, (payload, clientStack) => {
				if (scope === "*") return callback(payload);
				const boundScope = ((receiverRef ?? clientRef).current ?? this)[scope];
				if (!isScopeAvailable(boundScope)) return;
				const scopeClient = getClientId(boundScope);
				if (scopeClient === clientStack[getClientIndex(scopeClient)]) return callback(payload);
			});
			if (scope !== "*") {
				if (receiverRef) {
					if (clientRef.parent === DefaultAssistantClient) return localUnsub;
				} else if (isScopeUnavailable(clientRef.parent[scope])) return localUnsub;
			}
			const parentUnsub = clientRef.parent.on(selector, callback);
			return () => {
				localUnsub();
				parentUnsub();
			};
		}
	}), [notifications, clientRef]);
};
const useScopeMeta = (element) => {
	const $ = c(5);
	let t0;
	if ($[0] !== element) {
		t0 = metaOf(element);
		$[0] = element;
		$[1] = t0;
	} else t0 = $[1];
	const { source, query } = t0;
	const t1 = useShallowStable(query);
	let t2;
	if ($[2] !== source || $[3] !== t1) {
		t2 = {
			source,
			query: t1
		};
		$[2] = source;
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	return useShallowStable(t2);
};
const useScopeValue = (element, derived) => {
	const $ = c(3);
	let t0;
	if ($[0] !== derived || $[1] !== element) {
		t0 = derived ? element : ClientResource(element);
		$[0] = derived;
		$[1] = element;
		$[2] = t0;
	} else t0 = $[2];
	return useResource(t0);
};
const useScopeMount = (name, element) => {
	const building = useAssistantContextValue();
	const derived = isDerivedElement(element);
	const value = useScopeValue(element, derived);
	const methods = derived ? value : value.methods;
	const meta = useScopeMeta(element);
	const accessor = useMemo(() => createClientAccessor({
		name,
		...meta
	}, () => methods), [
		name,
		meta,
		methods
	]);
	building[name] = accessor;
	return accessor;
};
const ScopeMount = resource(useScopeMount);
const useScopeMounts = (entries) => {
	const $ = c(2);
	let t0;
	if ($[0] !== entries) {
		t0 = entries.map(_temp);
		$[0] = entries;
		$[1] = t0;
	} else t0 = $[1];
	return useResources(t0);
};
const useCommittedClient = (building, deps) => {
	const stableDeps = useShallowStable(deps);
	const cell = useMemo(() => ({}), []);
	if (cell.deps !== stableDeps) {
		cell.deps = stableDeps;
		cell.client = building;
	}
	return cell.client;
};
const useAuiRoot = ({ parent, entries, clientRef, notifications }) => {
	const fields = useClientFields({
		notifications,
		clientRef
	});
	const building = createClientObject(parent, fields);
	const tapContextValue = useMemo(() => ({
		clientRef,
		emit: notifications.emit
	}), [clientRef, notifications.emit]);
	const accessors = useAssistantTapContextProvider(tapContextValue, function WithTapContext() {
		return useAssistantContextProvider(building, function WithBuildingClient() {
			return useScopeMounts(entries);
		});
	});
	return { client: useCommittedClient(building, [parent, ...accessors]) };
};
const useHostedAssistantClient = ({ parent, entries, destroySignal }) => {
	const clientRef = useRef({
		parent,
		current: null
	}).current;
	const { value: client_0, effects } = useTapHost(function AssistantClientHost() {
		const notifications = useNotificationManager();
		const { client } = useDestroySignalProvider(destroySignal, function useOwnedRoot() {
			return useAuiRoot({
				parent,
				entries,
				clientRef,
				notifications
			});
		});
		useEffect(() => parent.subscribe(notifications.notifySubscribers), [parent, notifications]);
		useEffect(() => notifications.notifySubscribers());
		return client;
	});
	useInsertionEffect(() => {
		clientRef.parent = parent;
		clientRef.current = client_0;
	}, [
		client_0,
		parent,
		clientRef
	]);
	return {
		client: client_0,
		effects
	};
};
const useTapRootAssistantClient = ({ parent, entries, destroySignal }) => {
	const clientRef = useRef({
		parent,
		current: null
	}).current;
	const { value: client_0, effects } = useTapHost(function LegacyAssistantClientHost() {
		const notifications = useNotificationManager();
		const store = useTapRoot(function AuiRoot() {
			return useDestroySignalProvider(destroySignal, function useOwnedRoot() {
				return useAuiRoot({
					parent,
					entries,
					clientRef,
					notifications
				});
			});
		});
		const client = useSyncExternalStore(store.subscribe, () => store.getValue().client, () => store.getValue().client);
		useEffect(() => {
			const notify = () => flushTapSync(() => {
				clientRef.current = store.getValue().client;
				notifications.notifySubscribers();
			});
			const unsubscribeStore = store.subscribe(notify);
			const unsubscribeParent = parent.subscribe(notify);
			return () => {
				unsubscribeStore();
				unsubscribeParent();
			};
		}, [
			store,
			parent,
			notifications
		]);
		return client;
	});
	useInsertionEffect(() => {
		clientRef.parent = parent;
		clientRef.current = client_0;
	}, [
		client_0,
		parent,
		clientRef
	]);
	return {
		client: client_0,
		effects
	};
};
const useDerivedScopeMount = (parent, building, name, element) => {
	const { get } = element.args[0];
	const value = useSyncExternalStore(parent.subscribe, () => get(parent), () => get(parent));
	const meta = useScopeMeta(element);
	const accessor = useMemo(() => createClientAccessor({
		name,
		...meta
	}, () => value), [
		name,
		meta,
		value
	]);
	building[name] = accessor;
	return accessor;
};
const useDerivedOnlyClient = (parent, entries) => {
	if (isDevelopment) {
		const [mountKeys] = useState(() => entries.map(([name]) => name).join(","));
		const root = entries.find(([, element]) => !isDerivedElement(element));
		if (root) throw new Error(`Scope "${root[0]}" is a root scope but this useAui mounted derived-only; remount with a new key to change scope kinds.`);
		const keys = entries.map(([name_0]) => name_0).join(",");
		if (keys !== mountKeys) throw new Error(`A derived-only config mounted scopes [${mountKeys}] but now has [${keys}]; remount with a new key to change the scope set.`);
	}
	const clientRef = useRef({
		parent,
		current: null
	}).current;
	const on = function(selector, callback) {
		if (!this) throw new Error("const { on } = useAui() is not supported. Use aui.on() instead.");
		const { scope, event } = normalizeEventSelector(selector);
		if (scope === "*") return parent.on(selector, callback);
		const ridden = selector[EVENT_RECEIVER_REF];
		if (!ridden) {
			if (isScopeUnavailable(this[scope])) throw new Error(`Scope "${scope}" is not available. Use { scope: "*", event: "${event}" } to listen globally.`);
		}
		return parent.on({
			scope,
			event,
			[EVENT_RECEIVER_REF]: ridden ?? clientRef
		}, callback);
	};
	const building = createClientObject(parent, {
		subscribe: parent.subscribe,
		on
	});
	const accessors = entries.map(([name, element]) => useDerivedScopeMount(parent, building, name, element));
	const client = useCommittedClient(building, [parent, ...accessors]);
	useInsertionEffect(() => {
		clientRef.parent = parent;
		clientRef.current = client;
	}, [
		client,
		parent,
		clientRef
	]);
	return client;
};
const useScopeEntries = (parent, clients) => {
	const $ = c(8);
	let t0;
	if ($[0] !== clients || $[1] !== parent) {
		t0 = Object.entries(applyTransformScopes(clients, parent));
		$[0] = clients;
		$[1] = parent;
		$[2] = t0;
	} else t0 = $[2];
	const entries = t0;
	let t1;
	if ($[3] !== entries) {
		t1 = () => entries.length === 0 || entries.some(_temp2);
		$[3] = entries;
		$[4] = t1;
	} else t1 = $[4];
	const [rooted] = useState(t1);
	let t2;
	if ($[5] !== entries || $[6] !== rooted) {
		t2 = {
			entries,
			rooted
		};
		$[5] = entries;
		$[6] = rooted;
		$[7] = t2;
	} else t2 = $[7];
	return t2;
};
const useConfiguredAuiImpl = (parent, clients, useHost, destroySignal) => {
	const { entries, rooted } = useScopeEntries(parent, clients);
	if (rooted) return useHost({
		parent,
		entries,
		destroySignal
	});
	return { client: useDerivedOnlyClient(parent, entries) };
};
const useConfiguredAui = (parent, clients, destroySignal) => useConfiguredAuiImpl(parent, clients, useHostedAssistantClient, destroySignal);
function useAui(clients) {
	const parent = useAssistantContextValue();
	if (clients) {
		const destroySignal = useHostDestroySignal();
		const { client, effects } = useConfiguredAuiImpl(parent, clients, useTapRootAssistantClient, destroySignal);
		if (effects) setTapEffects(client, effects);
		return client;
	}
	return parent;
}
function _temp(t0) {
	const [name, element] = t0;
	return withKey(name, ScopeMount(name, element));
}
function _temp2(t0) {
	const [, element] = t0;
	return !isDerivedElement(element);
}
//#endregion
export { applyTransformScopes, useAui, useAuiRoot, useConfiguredAui };
