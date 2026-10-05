import { BaseProxyHandler, handleIntrospectionProp } from "./utils/BaseProxyHandler.js";
import { CLIENT_ID_SYMBOL, INSTANCE_TAG_SYMBOL } from "./utils/client-accessor.js";
import { SYMBOL_CLIENT_INDEX, useClientStack, useClientStackProvider } from "./utils/tap-client-stack-context.js";
import { useEffect, useMemo, useRef } from "@assistant-ui/tap/react-shim";
import { resource, useResource } from "@assistant-ui/tap";
//#region src/useClientResource.ts
/**
* Symbol used internally to get state from ClientProxy.
* This allows getState() to be optional in the user-facing client.
*/
const SYMBOL_GET_OUTPUT = Symbol("assistant-ui.store.getValue");
const getClientState = (client) => {
	const output = client[SYMBOL_GET_OUTPUT];
	if (!output) throw new Error("Client scope contains a non-client resource. Ensure your Derived get() returns a client created with useClientResource(), not a plain resource.");
	return output.getState?.();
};
const fieldAccessFns = /* @__PURE__ */ new Map();
function getOrCreateProxyFn(prop) {
	let template = fieldAccessFns.get(prop);
	if (!template) {
		template = function(...args) {
			if (!this || typeof this !== "object") throw new Error(`Method "${String(prop)}" called without proper context. This may indicate the function was called incorrectly.`);
			const output = this[SYMBOL_GET_OUTPUT];
			if (!output) throw new Error(`Method "${String(prop)}" called on invalid client proxy. Ensure you are calling this method on a valid client instance.`);
			const method = output[prop];
			if (!method) throw new Error(`Method "${String(prop)}" is not implemented.`);
			if (typeof method !== "function") throw new Error(`"${String(prop)}" is not a function.`);
			return method(...args);
		};
		fieldAccessFns.set(prop, template);
	}
	return template;
}
var ClientProxyHandler = class extends BaseProxyHandler {
	boundFns;
	cachedReceiver;
	outputRef;
	tagRef;
	index;
	self;
	constructor(outputRef, tagRef, index) {
		super();
		this.outputRef = outputRef;
		this.tagRef = tagRef;
		this.index = index;
	}
	get(_, prop, receiver) {
		if (prop === SYMBOL_GET_OUTPUT) return this.outputRef.current;
		if (prop === SYMBOL_CLIENT_INDEX) return this.index;
		if (prop === CLIENT_ID_SYMBOL) return this.self;
		if (prop === INSTANCE_TAG_SYMBOL) return this.tagRef.current;
		const introspection = handleIntrospectionProp(prop, "ClientProxy");
		if (introspection !== false) return introspection;
		const value = this.outputRef.current[prop];
		if (typeof value === "function") {
			if (receiver === void 0) return value;
			if (!this.boundFns || this.cachedReceiver !== receiver) {
				this.boundFns = /* @__PURE__ */ new Map();
				this.cachedReceiver = receiver;
			}
			let bound = this.boundFns.get(prop);
			if (!bound) {
				bound = getOrCreateProxyFn(prop).bind(receiver);
				this.boundFns.set(prop, bound);
			}
			return bound;
		}
		return value;
	}
	ownKeys() {
		return Object.keys(this.outputRef.current);
	}
	has(_, prop) {
		if (prop === SYMBOL_GET_OUTPUT) return true;
		if (prop === SYMBOL_CLIENT_INDEX) return true;
		if (prop === CLIENT_ID_SYMBOL) return true;
		if (prop === INSTANCE_TAG_SYMBOL) return true;
		return prop in this.outputRef.current;
	}
};
const useClientResource = (element) => {
	const valueRef = useRef(null);
	const tagRef = useRef(null);
	const instanceTag = useMemo(() => ({}), [element.hook, element.key]);
	const index = useClientStack().length;
	const methods = useMemo(() => {
		const handler = new ClientProxyHandler(valueRef, tagRef, index);
		const proxy = new Proxy({}, handler);
		handler.self = proxy;
		return proxy;
	}, [index]);
	const value = useClientStackProvider(methods, function WithClientStack() {
		return useResource(element);
	});
	if (!valueRef.current) {
		valueRef.current = value;
		tagRef.current = instanceTag;
	}
	useEffect(() => {
		valueRef.current = value;
		tagRef.current = instanceTag;
	});
	return {
		methods,
		state: value.getState?.(),
		key: element.key
	};
};
const ClientResource = resource(useClientResource);
//#endregion
export { ClientResource, getClientState, useClientResource };
