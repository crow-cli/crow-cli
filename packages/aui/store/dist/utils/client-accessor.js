import { handleIntrospectionProp } from "./BaseProxyHandler.js";
//#region src/utils/client-accessor.ts
const CLIENT_ID_SYMBOL = Symbol("assistant-ui.store.clientId");
const INSTANCE_TAG_SYMBOL = Symbol("assistant-ui.store.instanceTag");
const createClientAccessor = (meta, read) => {
	const proxy = new Proxy((() => {}), {
		apply: () => {
			read();
			return proxy;
		},
		get: (_, prop) => {
			if (prop === "source") return meta.source;
			if (prop === "query") return meta.query;
			if (prop === "name") return meta.name;
			if (prop === CLIENT_ID_SYMBOL) return getClientId(read());
			return read()[prop];
		},
		has: (_, prop) => prop === "source" || prop === "query" || prop === "name" || prop === CLIENT_ID_SYMBOL || prop in read(),
		ownKeys: () => Reflect.ownKeys(read()),
		getOwnPropertyDescriptor: (_, prop) => {
			if (typeof prop === "symbol" || !(prop in read())) return void 0;
			return {
				value: read()[prop],
				writable: false,
				enumerable: true,
				configurable: true
			};
		}
	});
	return proxy;
};
const createErrorClientAccessor = (message, name) => {
	const fail = () => {
		throw new Error(message);
	};
	return new Proxy((() => {}), {
		apply: fail,
		get: (_, prop) => {
			if (prop === "source" || prop === "query") return null;
			if (prop === "name") return name;
			if (prop === CLIENT_ID_SYMBOL) return fail();
			const introspection = handleIntrospectionProp(prop, "AssistantClientAccessor");
			if (introspection !== false) return introspection;
			return fail();
		},
		has: (_, prop) => prop === "source" || prop === "query" || prop === "name",
		ownKeys: () => [],
		getOwnPropertyDescriptor: () => void 0
	});
};
/**
* Scope resolution is tri-state: available (a bound accessor), present but
* unavailable (an error accessor with `source: null`), or absent entirely (a
* hand-built parent chain without the scope). `isScopeAvailable` collapses
* the last two; event subscription keeps them apart because an absent scope
* still forwards to the parent.
*/
const isScopeAvailable = (accessor) => accessor?.source != null;
const isScopeUnavailable = (accessor) => accessor?.source === null;
/**
* Returns the opaque identity of a bound client instance.
*
* The identity resolves through any forwarding layer to the underlying
* `useClientResource` client. A scope that delegates to a replaceable client
* yields that client's identity, which can serve as a `WeakMap` key for
* per-client caches. Throws if the client is an accessor for an unavailable
* scope.
*/
const getClientId = (client) => client[CLIENT_ID_SYMBOL] ?? client;
/**
* Returns the identity of the underlying client instance.
*
* `getClientId` follows the stable client facade, which survives a remount
* of the resource behind it, so it cannot distinguish a structurally
* replaced instance whose state was reset. This identity changes exactly
* when that instance is remounted or replaced; clients without an instance
* tag (hand-built parent chains) fall back to the facade identity.
*/
const getClientInstanceId = (client) => client[INSTANCE_TAG_SYMBOL] ?? getClientId(client);
//#endregion
export { CLIENT_ID_SYMBOL, INSTANCE_TAG_SYMBOL, createClientAccessor, createErrorClientAccessor, getClientId, getClientInstanceId, isScopeAvailable, isScopeUnavailable };
