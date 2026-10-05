"use client";
import { BaseProxyHandler, handleIntrospectionProp } from "./BaseProxyHandler.js";
import { isScopeAvailable } from "./client-accessor.js";
import { clientScopeKeys, isIgnoredClientKey } from "./client-keys.js";
import { getClientState } from "../useClientResource.js";
//#region src/utils/proxied-assistant-state.ts
let readWindow = 0;
let readWindowDepth = 0;
/**
* Opens a window in which a scope's state is resolved at most once per client.
*
* Resolving one scope walks the client accessor, the client proxy and the
* resource output, and a notification flush re-runs every mounted selector, so
* the same pair is resolved many times over. The window only spans a
* synchronous flush, during which the store publishes nothing new. The
* counters are shared by every notification manager on purpose: a flush that
* nests inside another, from any host, advances them and so invalidates every
* client's cache, which costs the outer flush its remaining batching and never
* serves it a stale read.
*/
const withBatchedStateReads = (fn) => {
	readWindow++;
	readWindowDepth++;
	try {
		return fn();
	} finally {
		readWindowDepth--;
		readWindow++;
	}
};
/**
* Proxied state that lazily accesses scope states
*/
const createProxiedAssistantState = (client) => {
	let optionalState;
	const scopeCache = /* @__PURE__ */ new Map();
	let scopeCacheWindow = -1;
	const readScopeState = (scope) => {
		if (readWindowDepth === 0) return getClientState(client[scope]());
		if (scopeCacheWindow !== readWindow) {
			scopeCache.clear();
			scopeCacheWindow = readWindow;
		} else if (scopeCache.has(scope)) return scopeCache.get(scope);
		const state = getClientState(client[scope]());
		scopeCache.set(scope, state);
		return state;
	};
	class OptionalAssistantStateProxyHandler extends BaseProxyHandler {
		get(_, prop) {
			const introspection = handleIntrospectionProp(prop, "OptionalAssistantState");
			if (introspection !== false) return introspection;
			const scope = prop;
			if (isIgnoredClientKey(scope)) return void 0;
			if (!isScopeAvailable(client[scope])) return void 0;
			return readScopeState(scope);
		}
		ownKeys() {
			return clientScopeKeys(client);
		}
		has(_, prop) {
			return !isIgnoredClientKey(prop) && prop in client;
		}
	}
	class ProxiedAssistantStateProxyHandler extends BaseProxyHandler {
		get(_, prop) {
			const introspection = handleIntrospectionProp(prop, "AssistantState");
			if (introspection !== false) return introspection;
			if (prop === "optional") return optionalState ??= new Proxy({}, new OptionalAssistantStateProxyHandler());
			const scope = prop;
			if (isIgnoredClientKey(scope)) return void 0;
			return readScopeState(scope);
		}
		ownKeys() {
			return [...clientScopeKeys(client), "optional"];
		}
		has(_, prop) {
			return prop === "optional" || !isIgnoredClientKey(prop) && prop in client;
		}
	}
	return new Proxy({}, new ProxiedAssistantStateProxyHandler());
};
const stateProxies = /* @__PURE__ */ new WeakMap();
const getProxiedAssistantState = (client) => {
	let proxy = stateProxies.get(client);
	if (!proxy) {
		proxy = createProxiedAssistantState(client);
		stateProxies.set(client, proxy);
	}
	return proxy;
};
//#endregion
export { getProxiedAssistantState, withBatchedStateReads };
