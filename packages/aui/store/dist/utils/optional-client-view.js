import { BaseProxyHandler, handleIntrospectionProp } from "./BaseProxyHandler.js";
import { isScopeAvailable } from "./client-accessor.js";
import { clientScopeKeys, isIgnoredClientKey } from "./client-keys.js";
//#region src/utils/optional-client-view.ts
var OptionalClientViewProxyHandler = class extends BaseProxyHandler {
	#client;
	constructor(client) {
		super();
		this.#client = client;
	}
	get(_, prop) {
		const introspection = handleIntrospectionProp(prop, "OptionalAssistantClient");
		if (introspection !== false) return introspection;
		if (isIgnoredClientKey(prop)) return void 0;
		const accessor = this.#client[prop];
		return isScopeAvailable(accessor) ? accessor : void 0;
	}
	ownKeys() {
		return clientScopeKeys(this.#client);
	}
	has(_, prop) {
		return !isIgnoredClientKey(prop) && prop in this.#client;
	}
};
const createOptionalClientView = (client) => new Proxy({}, new OptionalClientViewProxyHandler(client));
//#endregion
export { createOptionalClientView };
