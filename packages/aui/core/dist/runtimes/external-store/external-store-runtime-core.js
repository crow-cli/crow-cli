import { BaseAssistantRuntimeCore } from "../../runtime/base/base-assistant-runtime-core.js";
import { ExternalStoreThreadListRuntimeCore } from "./external-store-thread-list-runtime-core.js";
import { ExternalStoreThreadRuntimeCore } from "./external-store-thread-runtime-core.js";
//#region src/runtimes/external-store/external-store-runtime-core.ts
const getThreadListAdapter = (store) => {
	return store.adapters?.threadList ?? {};
};
var ExternalStoreRuntimeCore = class extends BaseAssistantRuntimeCore {
	threads;
	_adapter;
	constructor(adapter) {
		super();
		this._adapter = adapter;
		this.threads = new ExternalStoreThreadListRuntimeCore(getThreadListAdapter(adapter), () => new ExternalStoreThreadRuntimeCore(this._contextProvider, this._adapter));
	}
	setAdapter(adapter) {
		this._adapter = adapter;
		this.threads.__internal_setAdapter(getThreadListAdapter(adapter));
		this.threads.getMainThreadRuntimeCore().__internal_setAdapter(adapter);
	}
};
//#endregion
export { ExternalStoreRuntimeCore };
