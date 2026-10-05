import { AssistantRuntimeImpl } from "../../runtime/api/assistant-runtime.js";
import { LocalRuntimeCore } from "../../runtimes/local/local-runtime-core.js";
import { useRuntimeAdapters } from "./useRuntimeAdapters.js";
import { useRemoteThreadListRuntime } from "./useRemoteThreadListRuntime.js";
import { useCloudThreadListAdapter } from "./cloud/useCloudThreadListAdapter.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { useReplaySafeEffect } from "@assistant-ui/store/internal";
//#region src/react/runtimes/useLocalRuntime.ts
const useLocalThreadRuntime = (chatModel, t0) => {
	const $ = c(39);
	let initialMessages;
	let options;
	if ($[0] !== t0) {
		({initialMessages, ...options} = t0);
		$[0] = t0;
		$[1] = initialMessages;
		$[2] = options;
	} else {
		initialMessages = $[1];
		options = $[2];
	}
	const t1 = useRuntimeAdapters() ?? {};
	let modelContext;
	let threadListAdapters;
	if ($[3] !== t1) {
		({modelContext, ...threadListAdapters} = t1);
		$[3] = t1;
		$[4] = modelContext;
		$[5] = threadListAdapters;
	} else {
		modelContext = $[4];
		threadListAdapters = $[5];
	}
	let t2;
	if ($[6] !== chatModel || $[7] !== options.adapters || $[8] !== threadListAdapters) {
		t2 = {
			...threadListAdapters,
			...options.adapters,
			chatModel
		};
		$[6] = chatModel;
		$[7] = options.adapters;
		$[8] = threadListAdapters;
		$[9] = t2;
	} else t2 = $[9];
	let t3;
	if ($[10] !== options || $[11] !== t2) {
		t3 = {
			...options,
			adapters: t2
		};
		$[10] = options;
		$[11] = t2;
		$[12] = t3;
	} else t3 = $[12];
	const opt = t3;
	let t4;
	if ($[13] !== initialMessages || $[14] !== opt) {
		t4 = () => new LocalRuntimeCore(opt, initialMessages);
		$[13] = initialMessages;
		$[14] = opt;
		$[15] = t4;
	} else t4 = $[15];
	const [runtime] = useState(t4);
	const aui = useAui();
	const historyLoadPromiseRef = useRef(void 0);
	let t5;
	if ($[16] !== aui || $[17] !== runtime.threads) {
		t5 = () => {
			runtime.threads.getMainThreadRuntimeCore().__internal_setGetThreadId(() => aui.threadListItem.__internal_getRuntime?.().getState().remoteId);
		};
		$[16] = aui;
		$[17] = runtime.threads;
		$[18] = t5;
	} else t5 = $[18];
	let t6;
	if ($[19] !== aui || $[20] !== runtime) {
		t6 = [aui, runtime];
		$[19] = aui;
		$[20] = runtime;
		$[21] = t6;
	} else t6 = $[21];
	useEffect(t5, t6);
	let t7;
	if ($[22] !== runtime.threads) {
		t7 = () => () => {
			runtime.threads.getMainThreadRuntimeCore().detach();
		};
		$[22] = runtime.threads;
		$[23] = t7;
	} else t7 = $[23];
	let t8;
	if ($[24] !== runtime) {
		t8 = [runtime];
		$[24] = runtime;
		$[25] = t8;
	} else t8 = $[25];
	useReplaySafeEffect(t7, t8);
	let t9;
	if ($[26] !== opt || $[27] !== runtime.threads) {
		t9 = () => {
			runtime.threads.getMainThreadRuntimeCore().__internal_setOptions(opt);
		};
		$[26] = opt;
		$[27] = runtime.threads;
		$[28] = t9;
	} else t9 = $[28];
	useEffect(t9);
	let t10;
	if ($[29] !== runtime.threads) {
		t10 = () => {
			const loadPromise = runtime.threads.getMainThreadRuntimeCore().__internal_load();
			if (historyLoadPromiseRef.current === loadPromise) return;
			historyLoadPromiseRef.current = loadPromise;
			loadPromise.catch(_temp);
		};
		$[29] = runtime.threads;
		$[30] = t10;
	} else t10 = $[30];
	let t11;
	if ($[31] !== runtime) {
		t11 = [runtime];
		$[31] = runtime;
		$[32] = t11;
	} else t11 = $[32];
	useEffect(t10, t11);
	let t12;
	let t13;
	if ($[33] !== modelContext || $[34] !== runtime) {
		t12 = () => {
			if (!modelContext) return;
			return runtime.registerModelContextProvider(modelContext);
		};
		t13 = [modelContext, runtime];
		$[33] = modelContext;
		$[34] = runtime;
		$[35] = t12;
		$[36] = t13;
	} else {
		t12 = $[35];
		t13 = $[36];
	}
	useEffect(t12, t13);
	let t14;
	if ($[37] !== runtime) {
		t14 = () => new AssistantRuntimeImpl(runtime);
		$[37] = runtime;
		$[38] = t14;
	} else t14 = $[38];
	const [assistantRuntime] = useState(t14);
	return assistantRuntime;
};
const splitLocalRuntimeOptions = (options) => {
	const { cloud, initialMessages, maxSteps, adapters, unstable_humanToolNames, unstable_enableMessageQueue, unstable_queueClearOnRewind, unstable_queueClearOnCancel, ...rest } = options;
	return {
		localRuntimeOptions: {
			cloud,
			initialMessages,
			maxSteps,
			adapters,
			unstable_humanToolNames,
			unstable_enableMessageQueue,
			unstable_queueClearOnRewind,
			unstable_queueClearOnCancel
		},
		otherOptions: rest
	};
};
const useLocalRuntime = (chatModel, { cloud, ...options } = {}) => {
	const cloudAdapter = useCloudThreadListAdapter({ cloud });
	return useRemoteThreadListRuntime({
		runtimeHook: function RuntimeHook() {
			return useLocalThreadRuntime(chatModel, options);
		},
		adapter: cloudAdapter,
		allowNesting: true
	});
};
function _temp(error) {
	console.error("[assistant-ui] local thread history load failed:", error);
}
//#endregion
export { splitLocalRuntimeOptions, useLocalRuntime };
