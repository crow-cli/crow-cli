"use client";
import { useRemoteThreadListRuntime } from "../useRemoteThreadListRuntime.js";
import { useCloudThreadListAdapter } from "./useCloudThreadListAdapter.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
//#region src/react/runtimes/cloud/useCloudThreadListRuntime.ts
function useCloudThreadListRuntime(t0) {
	const $ = c(6);
	let adapterOptions;
	let runtimeHook;
	if ($[0] !== t0) {
		({runtimeHook, ...adapterOptions} = t0);
		$[0] = t0;
		$[1] = adapterOptions;
		$[2] = runtimeHook;
	} else {
		adapterOptions = $[1];
		runtimeHook = $[2];
	}
	const adapter = useCloudThreadListAdapter(adapterOptions);
	let t1;
	if ($[3] !== adapter || $[4] !== runtimeHook) {
		t1 = {
			runtimeHook,
			adapter,
			allowNesting: true
		};
		$[3] = adapter;
		$[4] = runtimeHook;
		$[5] = t1;
	} else t1 = $[5];
	return useRemoteThreadListRuntime(t1);
}
//#endregion
export { useCloudThreadListRuntime };
