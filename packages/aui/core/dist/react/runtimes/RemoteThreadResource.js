import { SKIP_UPDATE, ShallowMemoizeSubject } from "../../subscribable/subscribable.js";
import { ThreadListItemRuntimeImpl } from "../../runtime/api/thread-list-item-runtime.js";
import { isSilentRuntimeAction } from "../../utils/silent-runtime-action.js";
import { ThreadListItemClient } from "../../store/runtime-clients/thread-list-item-runtime-client.js";
import { useRuntimeAdaptersProvider } from "./useRuntimeAdapters.js";
import { isTitleSourceMessage } from "../../runtimes/remote-thread-list/title.js";
import { useRemoteThreadRuntimeHostProvider } from "./RemoteThreadRuntimeHostContext.js";
import { useAssistantContextProvider, useConfiguredAui, useDestroySignalProvider } from "@assistant-ui/store/client";
import { useCallback, useEffect, useEffectEvent, useMemo, useRef } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/react/runtimes/RemoteThreadResource.ts
const subscribeToTitleGeneration = (threadRuntime, itemRuntime) => {
	const generate = () => void itemRuntime.generateTitle({ automatic: true }).catch((error) => {
		if (isSilentRuntimeAction(error)) return;
		console.error("[assistant-ui] Thread title generation failed", error);
	});
	const hasTitleSource = () => threadRuntime.getState().messages.some(isTitleSourceMessage);
	if (hasTitleSource()) {
		generate();
		return () => {};
	}
	const unsubscribe = threadRuntime.subscribe(() => {
		if (!hasTitleSource()) return;
		unsubscribe();
		generate();
	});
	return unsubscribe;
};
const useRemoteThreadBinder = ({ threadId, generation, runtimeHook, publish, itemRuntime }) => {
	const runtime = useRemoteThreadRuntimeHostProvider(runtimeHook);
	const threadBinding = (runtime?.thread)?.__internal_threadBinding;
	const updateRuntime = useCallback(() => {
		if (!threadBinding) return;
		publish(threadId, threadBinding.getState(), generation);
	}, [
		threadId,
		generation,
		threadBinding,
		publish
	]);
	const isMounted = useRef(false);
	if (!isMounted.current) updateRuntime();
	useEffect(() => {
		if (!threadBinding) return void 0;
		isMounted.current = true;
		updateRuntime();
		return threadBinding.outerSubscribe(updateRuntime);
	}, [threadBinding, updateRuntime]);
	const initPromiseRef = useRef(void 0);
	const hasInitializedRef = useRef(false);
	const bornNewRef = useRef(itemRuntime.getState().status === "new");
	const titleDisposeRef = useRef(void 0);
	const titleAliveRef = useRef(false);
	const handleInitialize = useEffectEvent(() => {
		if (hasInitializedRef.current) return;
		if (itemRuntime.getState().status !== "new" && !bornNewRef.current) return;
		hasInitializedRef.current = true;
		bornNewRef.current = false;
		const initPromise = itemRuntime.initialize();
		initPromiseRef.current = initPromise;
		initPromise.then(() => {
			if (!titleAliveRef.current) return;
			titleDisposeRef.current?.();
			titleDisposeRef.current = subscribeToTitleGeneration(runtime.thread, itemRuntime);
		}, () => {
			if (initPromiseRef.current === initPromise) {
				initPromiseRef.current = void 0;
				hasInitializedRef.current = false;
			}
		});
	});
	const getInitializePromise = useEffectEvent(() => {
		handleInitialize();
		return initPromiseRef.current;
	});
	useEffect(() => {
		if (!threadBinding) return;
		const runtimeCore = threadBinding.getState();
		const setGetInitializePromise = runtimeCore.__internal_setGetInitializePromise;
		if (typeof setGetInitializePromise === "function") setGetInitializePromise.call(runtimeCore, getInitializePromise);
	}, [threadBinding]);
	useEffect(() => {
		if (!runtime?.threads?.main) return void 0;
		hasInitializedRef.current = false;
		titleAliveRef.current = true;
		const unsubscribe = runtime.threads.main.unstable_on("initialize", handleInitialize);
		return () => {
			titleAliveRef.current = false;
			unsubscribe();
			titleDisposeRef.current?.();
			titleDisposeRef.current = void 0;
		};
	}, [runtime]);
	return runtime;
};
const useRemoteThreadResource = ({ threadId, generation, parentList, runtimeHook, parentClient, adapters, publish, destroySignal }) => {
	const itemRuntime = useMemo(() => new ThreadListItemRuntimeImpl(new ShallowMemoizeSubject({
		path: {
			ref: `threadItems[threadId=${threadId}]`,
			threadSelector: {
				type: "threadId",
				threadId
			}
		},
		getState: () => {
			const data = parentList.getItemById(threadId);
			if (!data) return SKIP_UPDATE;
			return {
				id: data.id,
				remoteId: data.remoteId,
				externalId: data.externalId,
				title: data.title,
				lastMessageAt: data.lastMessageAt,
				custom: data.custom,
				status: data.status,
				isMain: data.id === parentList.mainThreadId,
				isRunning: parentList.unstable_isThreadRunning?.(data.id) ?? false
			};
		},
		subscribe: (callback) => parentList.subscribe(callback)
	}), parentList), [parentList, threadId]);
	const { client } = useConfiguredAui(parentClient, { threadListItem: ThreadListItemClient({ runtime: itemRuntime }) });
	return useDestroySignalProvider(destroySignal, function useOwnedThread() {
		return useAssistantContextProvider(client, function useThreadClient() {
			return useRuntimeAdaptersProvider(adapters, function useBoundRuntime() {
				return useRemoteThreadBinder({
					threadId,
					generation,
					runtimeHook,
					publish,
					itemRuntime
				});
			});
		});
	});
};
const RemoteThreadResource = resource(useRemoteThreadResource);
//#endregion
export { RemoteThreadResource, subscribeToTitleGeneration };
