import { CompositeContextProvider } from "../../utils/composite-context-provider.js";
//#region src/runtime/base/base-assistant-runtime-core.ts
var BaseAssistantRuntimeCore = class {
	_contextProvider = new CompositeContextProvider();
	registerModelContextProvider(provider) {
		return this._contextProvider.registerModelContextProvider(provider);
	}
	getModelContextProvider() {
		return this._contextProvider;
	}
};
//#endregion
export { BaseAssistantRuntimeCore };
