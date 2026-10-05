"use client";
import { disposeThreadRuntime, invalidateThreadRuntime } from "../../runtime/utils/thread-runtime-lifecycle.js";
import { AssistantRuntimeImpl } from "../../runtime/api/assistant-runtime.js";
import { ExternalStoreRuntimeCore } from "../../runtimes/external-store/external-store-runtime-core.js";
import { useRuntimeAdapters } from "./useRuntimeAdapters.js";
import { ExternalStoreHistoryCopy } from "./external-store-history-copy.js";
import { useIsRemoteThreadRuntimeHosted } from "./RemoteThreadRuntimeHostContext.js";
import { useEffect, useInsertionEffect, useMemo, useState } from "@assistant-ui/tap/react-shim";
import { useReplaySafeEffect } from "@assistant-ui/store/internal";
//#region src/react/runtimes/useExternalStoreRuntime.ts
const useExternalStoreRuntime = (store) => {
	const { modelContext, feedback, history } = useRuntimeAdapters() ?? {};
	const [historyCopy] = useState(() => new ExternalStoreHistoryCopy());
	const copiesHistory = !!history?.unstable_copy && !store.unstable_persistsHistory && !store.adapters?.threadList;
	const adaptedStore = useMemo(() => {
		const withFeedback = feedback && !store.adapters?.feedback ? {
			...store,
			adapters: {
				...store.adapters,
				feedback
			}
		} : store;
		if (!copiesHistory || store.unstable_onRecordToolInteraction) return withFeedback;
		return {
			...withFeedback,
			unstable_onRecordToolInteraction: historyCopy.recordInteraction
		};
	}, [
		copiesHistory,
		feedback,
		historyCopy,
		store
	]);
	const [runtime] = useState(() => new ExternalStoreRuntimeCore(adaptedStore));
	const isHosted = useIsRemoteThreadRuntimeHosted();
	const [lifetime] = useState(() => ({ generation: 0 }));
	useInsertionEffect(() => {
		if (isHosted) return;
		const generation = ++lifetime.generation;
		return () => queueMicrotask(() => {
			if (lifetime.generation === generation) disposeThreadRuntime(runtime.threads.getMainThreadRuntimeCore());
		});
	}, [
		isHosted,
		lifetime,
		runtime
	]);
	useReplaySafeEffect(() => {
		return () => {
			invalidateThreadRuntime(runtime.threads.getMainThreadRuntimeCore());
		};
	}, [runtime]);
	useEffect(() => {
		runtime.setAdapter(adaptedStore);
	});
	useReplaySafeEffect(() => {
		if (!copiesHistory || !history) return;
		return historyCopy.attach(runtime.threads.getMainThreadRuntimeCore(), history);
	}, [
		copiesHistory,
		history,
		historyCopy,
		runtime
	]);
	useEffect(() => {
		if (!modelContext) return void 0;
		return runtime.registerModelContextProvider(modelContext);
	}, [modelContext, runtime]);
	const [assistantRuntime] = useState(() => new AssistantRuntimeImpl(runtime));
	return assistantRuntime;
};
//#endregion
export { useExternalStoreRuntime };
