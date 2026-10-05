import { notifyEventListeners } from "../../utils/notify-event-listeners.js";
import { BaseSubscribable, WritableSubscribable, notifySubscribers, runCleanups } from "../../subscribable/subscribable.js";
import { disposeThreadRuntime, supersedeThreadRuntime } from "../../runtime/utils/thread-runtime-lifecycle.js";
import { getThreadRuntimeCoreIsRunning } from "../../runtime/api/thread-runtime.js";
import { ThreadListRuntimeImpl } from "../../runtime/api/thread-list-runtime.js";
import { useSubscribable } from "../../store/runtime-clients/useSubscribable.js";
import { useRuntimeAdapters } from "./useRuntimeAdapters.js";
import { ThreadListItemRuntimeProvider } from "../providers/ThreadListItemRuntimeProvider.js";
import { RemoteThreadResource } from "./RemoteThreadResource.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { Fragment, memo, useEffect, useLayoutEffect, useMemo, useRef } from "@assistant-ui/tap/react-shim";
import { useResources, useTapHost, withKey } from "@assistant-ui/tap";
import { jsx } from "react/jsx-runtime";
//#region src/react/runtimes/RemoteThreadListHookInstanceManager.tsx
const THREAD_EVENTS = [
	"runStart",
	"runEnd",
	"initialize",
	"modelContextUpdate"
];
const ProviderRenderDetector = (t0) => {
	const $ = c(3);
	const { detectorRef } = t0;
	let t1;
	let t2;
	if ($[0] !== detectorRef) {
		t1 = () => {
			detectorRef.current = true;
		};
		t2 = [detectorRef];
		$[0] = detectorRef;
		$[1] = t1;
		$[2] = t2;
	} else {
		t1 = $[1];
		t2 = $[2];
	}
	useLayoutEffect(t1, t2);
	return null;
};
var RemoteThreadListHookInstanceManager = class extends BaseSubscribable {
	runtimeHook;
	adapterStore = new WritableSubscribable({
		defaultAdapters: null,
		threadAdapters: /* @__PURE__ */ new Map()
	});
	hostStore = new WritableSubscribable({
		threads: [],
		hookEpoch: 0
	});
	pendingThreadAdapters = /* @__PURE__ */ new Map();
	instances = /* @__PURE__ */ new Map();
	nextGeneration = 0;
	parent;
	constructor(runtimeHook, parent) {
		super();
		this.parent = parent;
		this.runtimeHook = runtimeHook;
	}
	_whenRuntimeAttached(threadId) {
		return new Promise((resolve, reject) => {
			const callback = () => {
				const instance = this.instances.get(threadId);
				if (!instance) {
					dispose();
					reject(/* @__PURE__ */ new Error("Thread was deleted before runtime was started"));
				} else if (!instance.runtime || instance.publishedGeneration !== instance.generation) return;
				else {
					dispose();
					resolve(instance.runtime);
				}
			};
			const dispose = this.subscribe(callback);
			callback();
		});
	}
	startThreadRuntime(threadId) {
		if (!this.instances.has(threadId)) {
			const generation = this.nextGeneration++;
			this.instances.set(threadId, {
				generation,
				isRunning: false,
				destroy: new AbortController()
			});
			this._syncHostThreads();
		}
		return this._whenRuntimeAttached(threadId);
	}
	__internal_restartThreadRuntime(threadId) {
		const instance = this.instances.get(threadId);
		if (!instance) return this.startThreadRuntime(threadId);
		try {
			instance.unsubscribeRunning?.();
		} finally {
			instance.unsubscribeRunning = void 0;
			if (instance.runtime) supersedeThreadRuntime(instance.runtime);
			instance.destroy.abort();
			instance.destroy = new AbortController();
			instance.generation = this.nextGeneration++;
			this._syncHostThreads();
			this._notifySubscribers();
		}
		return this._whenRuntimeAttached(threadId);
	}
	getThreadRuntimeCore(threadId) {
		const instance = this.instances.get(threadId);
		if (!instance) return void 0;
		return instance.runtime;
	}
	__internal_isThreadRunning(threadId) {
		return this.instances.get(threadId)?.isRunning ?? false;
	}
	runningSubscribers = /* @__PURE__ */ new Set();
	__internal_subscribeRunningChanged(callback) {
		this.runningSubscribers.add(callback);
		return () => this.runningSubscribers.delete(callback);
	}
	threadEventSubscribers = /* @__PURE__ */ new Set();
	__internal_subscribeThreadEvents(callback) {
		this.threadEventSubscribers.add(callback);
		return () => this.threadEventSubscribers.delete(callback);
	}
	_publish = (threadId, runtime, generation) => {
		this._publishThreadRuntime(threadId, runtime, generation);
	};
	_publishThreadRuntime(threadId, runtime, generation) {
		const instance = this.instances.get(threadId);
		if (!instance) return;
		if (instance.generation !== generation) return;
		const previousRuntime = instance.runtime;
		const previousPublishedGeneration = instance.publishedGeneration;
		instance.runtime = runtime;
		instance.publishedGeneration = generation;
		try {
			if (previousRuntime !== runtime) this._trackRunning(threadId, instance);
		} finally {
			try {
				this._notifySubscribers();
				if (previousRuntime !== void 0 && previousRuntime !== runtime) notifySubscribers(this.replacedSubscribers);
			} finally {
				if (previousPublishedGeneration === generation && previousRuntime !== void 0 && previousRuntime !== runtime) disposeThreadRuntime(previousRuntime);
			}
		}
	}
	replacedSubscribers = /* @__PURE__ */ new Set();
	__internal_subscribeRuntimeReplaced(callback) {
		this.replacedSubscribers.add(callback);
		return () => this.replacedSubscribers.delete(callback);
	}
	_trackRunning(threadId, instance) {
		const previousCleanup = instance.unsubscribeRunning;
		instance.unsubscribeRunning = void 0;
		try {
			previousCleanup?.();
		} finally {
			const runtime = instance.runtime;
			if (!runtime) this._setRunning(instance, false);
			else {
				const isRunning = getThreadRuntimeCoreIsRunning(runtime);
				if (instance.isRunning !== isRunning) {
					instance.isRunning = isRunning;
					queueMicrotask(() => notifySubscribers(this.runningSubscribers));
				}
				const unsubscribers = [runtime.subscribe(() => {
					this._setRunning(instance, getThreadRuntimeCoreIsRunning(runtime));
				}), ...THREAD_EVENTS.map((type) => runtime.unstable_on(type, () => {
					notifyEventListeners(this.threadEventSubscribers, {
						threadId,
						type
					}, `Thread event "${type}"`);
				}))];
				instance.unsubscribeRunning = () => runCleanups(unsubscribers);
			}
		}
	}
	_setRunning(instance, isRunning) {
		if (instance.isRunning === isRunning) return;
		instance.isRunning = isRunning;
		notifySubscribers(this.runningSubscribers);
	}
	stopThreadRuntime(threadId) {
		const instance = this.instances.get(threadId);
		try {
			instance?.unsubscribeRunning?.();
		} finally {
			if (instance?.runtime) disposeThreadRuntime(instance.runtime);
			instance?.destroy.abort();
			this.instances.delete(threadId);
			this.pendingThreadAdapters.delete(threadId);
			this._syncHostThreads();
			this._notifySubscribers();
		}
	}
	setRuntimeHook(newRuntimeHook) {
		if (this.runtimeHook === newRuntimeHook) return;
		this.runtimeHook = newRuntimeHook;
		const host = this.hostStore.getState();
		this.hostStore.setState({
			...host,
			hookEpoch: host.hookEpoch + 1
		});
	}
	__internal_setDefaultAdapters(adapters) {
		const current = this.adapterStore.getState();
		if (current.defaultAdapters === adapters) return;
		this.adapterStore.setState({
			...current,
			defaultAdapters: adapters
		});
	}
	__internal_setThreadAdapters(threadId, adapters) {
		const current = this.adapterStore.getState();
		const next = new Map(current.threadAdapters);
		if (adapters === null) next.delete(threadId);
		else next.set(threadId, adapters);
		this.adapterStore.setState({
			...current,
			threadAdapters: next
		});
	}
	__internal_dispose() {
		for (const threadId of [...this.instances.keys()]) try {
			this.stopThreadRuntime(threadId);
		} catch (error) {
			console.error("[assistant-ui] Thread runtime cleanup threw while stopping a thread", error);
		}
	}
	_syncHostThreads() {
		const host = this.hostStore.getState();
		this.hostStore.setState({
			...host,
			threads: Array.from(this.instances.entries()).map(([id, { generation, destroy }]) => ({
				id,
				generation,
				destroySignal: destroy.signal
			}))
		});
	}
	_threadElements(parentClient, { threads, hookEpoch }, adapters) {
		const runtimeHook = this.runtimeHook;
		return threads.map(({ id, generation, destroySignal }) => {
			const threadAdapters = this.pendingThreadAdapters.has(id) ? this.pendingThreadAdapters.get(id) : adapters.threadAdapters.get(id) ?? adapters.defaultAdapters;
			return withKey(`${id}:${generation}:${hookEpoch}`, RemoteThreadResource({
				threadId: id,
				generation,
				parentList: this.parent,
				runtimeHook,
				parentClient,
				adapters: threadAdapters,
				publish: this._publish,
				destroySignal
			}));
		});
	}
	/** @deprecated Commits the hosted threads after descendant layout effects; render `__internal_Host` instead. */
	__internal_useHost(parentClient) {
		const host = useSubscribable(this.hostStore);
		const adapters = useSubscribable(this.adapterStore);
		return useResources(this._threadElements(parentClient, host, adapters));
	}
	__internal_RenderThreadRuntimes = ({ provider }) => {
		useSubscribable(this.hostStore);
		return Array.from(this.instances.entries()).map(([threadId, { generation }]) => /* @__PURE__ */ jsx(this._OuterActiveThreadProvider, {
			threadId,
			provider
		}, `${threadId}:${generation}`));
	};
	__internal_Host = ({ parentClient }) => {
		const host = useSubscribable(this.hostStore);
		const adapters = useSubscribable(this.adapterStore);
		const elements = this._threadElements(parentClient, host, adapters);
		const { effects } = useTapHost(function RemoteThreadResources() {
			return useResources(elements);
		});
		useLayoutEffect(effects);
		return null;
	};
	_OuterActiveThreadProvider = memo(({ threadId, provider: Provider }) => {
		const runtime = useMemo(() => new ThreadListRuntimeImpl(this.parent).getItemById(threadId), [threadId]);
		const detectorRef = useRef(false);
		useEffect(() => {
			if (process.env.NODE_ENV !== "production" && Provider !== Fragment) {
				const id = setTimeout(() => {
					if (!detectorRef.current) console.warn("RemoteThreadListAdapter.unstable_Provider did not render its `children` synchronously. Render `children` on first commit; deferring them behind a loading state, Suspense boundary, or `useEffect` gate strands the runtime host and leaves the thread without context.");
				}, 100);
				return () => clearTimeout(id);
			}
		}, [Provider]);
		return /* @__PURE__ */ jsx(ThreadListItemRuntimeProvider, {
			runtime,
			children: /* @__PURE__ */ jsx(Provider, { children: /* @__PURE__ */ jsx(this._AdapterSink, {
				threadId,
				detectorRef
			}) })
		});
	});
	_AdapterSink = ({ threadId, detectorRef }) => {
		const adapters = useRuntimeAdapters();
		this.pendingThreadAdapters.set(threadId, adapters);
		useLayoutEffect(() => {
			this.__internal_setThreadAdapters(threadId, adapters);
			return () => {
				if (this.pendingThreadAdapters.get(threadId) === adapters) this.pendingThreadAdapters.delete(threadId);
				this.__internal_setThreadAdapters(threadId, null);
			};
		}, [threadId, adapters]);
		return /* @__PURE__ */ jsx(ProviderRenderDetector, { detectorRef });
	};
};
//#endregion
export { RemoteThreadListHookInstanceManager };
