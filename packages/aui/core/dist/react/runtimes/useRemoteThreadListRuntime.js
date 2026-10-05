import { WritableSubscribable } from "../../subscribable/subscribable.js";
import { BaseAssistantRuntimeCore } from "../../runtime/base/base-assistant-runtime-core.js";
import { AssistantRuntimeImpl } from "../../runtime/api/assistant-runtime.js";
import { useSubscribable } from "../../store/runtime-clients/useSubscribable.js";
import { RemoteThreadListThreadListRuntimeCore } from "./RemoteThreadListThreadListRuntimeCore.js";
import { useEffect, useEffectEvent, useId, useInsertionEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/runtimes/useRemoteThreadListRuntime.ts
var RemoteThreadListRuntimeCore = class extends BaseAssistantRuntimeCore {
	threads;
	constructor(options, initialThreadIdSeed) {
		super();
		this.threads = new RemoteThreadListThreadListRuntimeCore(options, this._contextProvider, initialThreadIdSeed);
	}
	get RenderComponent() {
		return this.threads.__internal_RenderComponent;
	}
};
const subscribeNever = () => () => {};
const useRemoteThreadListRuntimeImpl = (options) => {
	const serverThreadIdSeed = useId();
	const isServerRender = useSyncExternalStore(subscribeNever, () => false, () => typeof document === "undefined");
	const [runtime] = useState(() => new RemoteThreadListRuntimeCore(options, isServerRender ? serverThreadIdSeed : void 0));
	const [lifetime] = useState(() => ({ generation: 0 }));
	useInsertionEffect(() => {
		const generation = ++lifetime.generation;
		return () => queueMicrotask(() => {
			if (lifetime.generation === generation) runtime.threads.__internal_dispose();
		});
	}, [runtime, lifetime]);
	useEffect(() => {
		runtime.threads.__internal_setOptions(options);
		runtime.threads.__internal_load();
	}, [runtime, options]);
	useEffect(() => {
		if (typeof window === "undefined" || typeof document === "undefined") return;
		const reloadAfterError = () => {
			if (runtime.threads.loadError !== void 0) runtime.threads.reload();
		};
		const reloadAfterVisible = () => {
			if (document.visibilityState === "visible") reloadAfterError();
		};
		window.addEventListener("online", reloadAfterError);
		document.addEventListener("visibilitychange", reloadAfterVisible);
		return () => {
			window.removeEventListener("online", reloadAfterError);
			document.removeEventListener("visibilitychange", reloadAfterVisible);
		};
	}, [runtime]);
	const [assistantRuntime] = useState(() => new AssistantRuntimeImpl(runtime));
	return assistantRuntime;
};
const useRemoteThreadListRuntime = (options) => {
	const [runtimeHookStore] = useState(() => new WritableSubscribable(options.runtimeHook));
	useLayoutEffect(() => {
		runtimeHookStore.setState(options.runtimeHook);
	}, [runtimeHookStore, options.runtimeHook]);
	const initialThreadIdRef = useRef(options.initialThreadId);
	const [stableRuntimeHook] = useState(() => function useCommittedRuntimeHook() {
		return useSubscribable({
			subscribe: runtimeHookStore.subscribe,
			getState: runtimeHookStore.getState,
			getServerSnapshot: runtimeHookStore.getState
		})();
	});
	const onThreadIdChange = useEffectEvent((threadId) => {
		return options.onThreadIdChange?.(threadId);
	});
	const stableOptions = useMemo(() => ({
		adapter: options.adapter,
		allowNesting: options.allowNesting,
		threadId: options.threadId,
		initialThreadId: initialThreadIdRef.current,
		runtimeHook: stableRuntimeHook,
		onThreadIdChange
	}), [
		options.adapter,
		options.allowNesting,
		options.threadId,
		stableRuntimeHook
	]);
	if (useAui().threadListItem.source !== null) {
		if (!stableOptions.allowNesting) throw new Error("useRemoteThreadListRuntime cannot be nested inside another RemoteThreadListRuntime. Set allowNesting: true to allow nesting (the inner runtime will become a no-op).");
		return options.runtimeHook();
	}
	return useRemoteThreadListRuntimeImpl(stableOptions);
};
//#endregion
export { useRemoteThreadListRuntime };
