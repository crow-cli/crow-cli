import { ThreadListClient } from "../store/runtime-clients/thread-list-runtime-client.js";
import { baseRuntimeAdapterTransformScopes } from "../store/clients/runtime-adapter.js";
import { DataRenderers } from "./client/DataRenderers.js";
import { Tools } from "./client/Tools.js";
import { attachTransformScopes, useAssistantClientRef, useAssistantScopeEffect } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { resource, useResource } from "@assistant-ui/tap";
//#region src/react/RuntimeAdapter.ts
const useRuntimeAdapter = (runtime) => {
	const $ = c(7);
	const clientRef = useAssistantClientRef();
	let t0;
	if ($[0] !== clientRef || $[1] !== runtime) {
		t0 = () => runtime.registerModelContextProvider(clientRef.current.modelContext());
		$[0] = clientRef;
		$[1] = runtime;
		$[2] = t0;
	} else t0 = $[2];
	let t1;
	if ($[3] !== runtime) {
		t1 = [runtime];
		$[3] = runtime;
		$[4] = t1;
	} else t1 = $[4];
	useAssistantScopeEffect("modelContext", t0, t1);
	let t2;
	if ($[5] !== runtime) {
		t2 = ThreadListClient({
			runtime: runtime.threads,
			__internal_assistantRuntime: runtime
		});
		$[5] = runtime;
		$[6] = t2;
	} else t2 = $[6];
	return useResource(t2);
};
const RuntimeAdapter = resource(useRuntimeAdapter);
/**
* The scope defaults `RuntimeAdapter` installs when it is used as the `threads`
* config entry. Adapter packages that wrap a runtime in their own config entry
* attach this to the wrapping resource for scope parity with `RuntimeAdapter`.
*/
const runtimeAdapterTransformScopes = (scopes, parent) => {
	baseRuntimeAdapterTransformScopes(scopes, parent);
	if (!scopes.tools && parent.tools.source === null) scopes.tools = Tools({});
	if (!scopes.dataRenderers && parent.dataRenderers.source === null) scopes.dataRenderers = DataRenderers();
};
attachTransformScopes(useRuntimeAdapter, runtimeAdapterTransformScopes);
//#endregion
export { RuntimeAdapter, runtimeAdapterTransformScopes };
