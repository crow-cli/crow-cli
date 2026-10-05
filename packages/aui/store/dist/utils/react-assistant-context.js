import { BaseProxyHandler, handleIntrospectionProp } from "./BaseProxyHandler.js";
import { createErrorClientAccessor } from "./client-accessor.js";
import { createOptionalClientView } from "./optional-client-view.js";
import { createContext, useContext } from "@assistant-ui/tap/react-shim";
import { useContextProvider } from "@assistant-ui/tap";
//#region src/utils/react-assistant-context.tsx
const NO_OP_SUBSCRIBE = () => () => {};
const MISSING_PROVIDER_MESSAGE = "You are using a component or hook that requires an AuiProvider. Wrap your component in an <AuiProvider> component.";
var EmptyAssistantClientProxyHandler = class extends BaseProxyHandler {
	#displayName;
	#messageOf;
	#getClient;
	#optional;
	constructor(displayName, messageOf, getClient) {
		super();
		this.#displayName = displayName;
		this.#messageOf = messageOf;
		this.#getClient = getClient;
	}
	get(_, prop) {
		if (prop === "subscribe") return NO_OP_SUBSCRIBE;
		if (prop === "on") return NO_OP_SUBSCRIBE;
		if (prop === "optional") return this.#optional ??= createOptionalClientView(this.#getClient());
		const introspection = handleIntrospectionProp(prop, this.#displayName);
		if (introspection !== false) return introspection;
		return createErrorClientAccessor(this.#messageOf(String(prop)), String(prop));
	}
	ownKeys() {
		return [
			"subscribe",
			"on",
			"optional"
		];
	}
	getOwnPropertyDescriptor(_, prop) {
		if (prop !== "optional") return super.getOwnPropertyDescriptor(_, prop);
		const value = this.get(_, prop);
		if (value === void 0) return void 0;
		return {
			value,
			writable: false,
			enumerable: false,
			configurable: true
		};
	}
	has(_, prop) {
		return prop === "subscribe" || prop === "on" || prop === "optional";
	}
};
const createEmptyAssistantClient = (displayName, messageOf) => {
	const client = new Proxy({}, new EmptyAssistantClientProxyHandler(displayName, messageOf, () => client));
	return client;
};
/** Default context value - throws "wrap in AuiProvider" error */
const DefaultAssistantClient = createEmptyAssistantClient("DefaultAssistantClient", () => MISSING_PROVIDER_MESSAGE);
/** Root prototype for created clients - throws "scope not defined" error */
const createRootAssistantClient = () => new Proxy({}, { get(_, prop) {
	const introspection = handleIntrospectionProp(prop, "AssistantClient");
	if (introspection !== false) return introspection;
	return createErrorClientAccessor(`The current scope does not have a "${String(prop)}" property.`, String(prop));
} });
/**
* React Context for the AssistantClient
*/
const AssistantContext = createContext(DefaultAssistantClient);
const NOOP_EFFECT = () => {};
const tapEffects = /* @__PURE__ */ new WeakMap();
const getTapEffects = (client) => {
	return tapEffects.get(client) ?? NOOP_EFFECT;
};
/**
* Records the tap host's effects callback for clients created by the
* deprecated `useAui({...})` overload; the AuiProvider the client is passed
* to mounts the host's commit ahead of its children's effects.
*/
const setTapEffects = (client, effects) => {
	tapEffects.set(client, effects);
};
const useAssistantContextValue = () => {
	return useContext(AssistantContext);
};
const useAssistantContextProvider = (value, fn) => {
	return useContextProvider(AssistantContext, value, fn);
};
//#endregion
export { AssistantContext, DefaultAssistantClient, createRootAssistantClient, getTapEffects, setTapEffects, useAssistantContextProvider, useAssistantContextValue };
