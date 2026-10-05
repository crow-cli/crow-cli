import { LazyMemoizeSubject, NestedSubscriptionSubject, SKIP_UPDATE, ShallowMemoizeSubject } from "../../subscribable/subscribable.js";
import { ThreadRuntimeImpl } from "./thread-runtime.js";
import { ThreadListItemRuntimeImpl } from "./thread-list-item-runtime.js";
//#region src/runtime/api/thread-list-runtime.ts
const RESOLVED_PROMISE = Promise.resolve();
const NOOP_UNSUBSCRIBE = () => {};
const getThreadListState = (threadList) => {
	return {
		mainThreadId: threadList.mainThreadId,
		newThreadId: threadList.newThreadId,
		threadIds: threadList.threadIds,
		archivedThreadIds: threadList.archivedThreadIds,
		isLoading: threadList.isLoading,
		loadError: threadList.loadError,
		isLoadingMore: threadList.isLoadingMore ?? false,
		hasMore: threadList.hasMore ?? false,
		threadItems: threadList.threadItems
	};
};
const getThreadListItemState = (threadList, threadId) => {
	if (threadId === void 0) return SKIP_UPDATE;
	const threadData = threadList.getItemById(threadId);
	if (!threadData) return SKIP_UPDATE;
	return {
		id: threadData.id,
		remoteId: threadData.remoteId,
		externalId: threadData.externalId,
		title: threadData.title,
		status: threadData.status,
		lastMessageAt: threadData.lastMessageAt,
		custom: threadData.custom,
		isMain: threadData.id === threadList.mainThreadId,
		isRunning: threadList.unstable_isThreadRunning?.(threadData.id) ?? false
	};
};
var ThreadListRuntimeImpl = class {
	_getState;
	_stateBinding;
	_core;
	_runtimeFactory;
	constructor(_core, _runtimeFactory = ThreadRuntimeImpl) {
		this._core = _core;
		this._runtimeFactory = _runtimeFactory;
		const stateBinding = new LazyMemoizeSubject({
			path: {},
			getState: () => getThreadListState(_core),
			subscribe: (callback) => _core.subscribe(callback)
		});
		this._getState = stateBinding.getState.bind(stateBinding);
		this._stateBinding = stateBinding;
		this._mainThreadListItemRuntime = new ThreadListItemRuntimeImpl(new ShallowMemoizeSubject({
			path: {
				ref: `threadItems[main]`,
				threadSelector: { type: "main" }
			},
			getState: () => {
				return getThreadListItemState(this._core, this._core.mainThreadId);
			},
			subscribe: (callback) => this._core.subscribe(callback)
		}), this._core);
		this.main = new _runtimeFactory(new NestedSubscriptionSubject({
			path: {
				ref: "threads.main",
				threadSelector: { type: "main" }
			},
			getState: () => _core.getMainThreadRuntimeCore(),
			subscribe: (callback) => _core.subscribe(callback)
		}), this._mainThreadListItemRuntime);
		this.__internal_bindMethods();
	}
	__internal_bindMethods() {
		this.switchToThread = this.switchToThread.bind(this);
		this.switchToNewThread = this.switchToNewThread.bind(this);
		this.unstable_subscribeThreadEvents = this.unstable_subscribeThreadEvents.bind(this);
		this.getLoadThreadsPromise = this.getLoadThreadsPromise.bind(this);
		this.reload = this.reload.bind(this);
		this.reloadMainThread = this.reloadMainThread.bind(this);
		this.loadMore = this.loadMore.bind(this);
		this.getState = this.getState.bind(this);
		this.subscribe = this.subscribe.bind(this);
		this.getById = this.getById.bind(this);
		this.getItemById = this.getItemById.bind(this);
		this.getItemByIndex = this.getItemByIndex.bind(this);
		this.getArchivedItemByIndex = this.getArchivedItemByIndex.bind(this);
	}
	switchToThread(threadId, options) {
		return this._core.switchToThread(threadId, options);
	}
	switchToNewThread() {
		return this._core.switchToNewThread();
	}
	unstable_subscribeThreadEvents(callback) {
		return this._core.unstable_subscribeThreadEvents?.(callback) ?? NOOP_UNSUBSCRIBE;
	}
	getLoadThreadsPromise() {
		return this._core.getLoadThreadsPromise();
	}
	reload() {
		return this._core.reload?.() ?? RESOLVED_PROMISE;
	}
	reloadMainThread() {
		return this._core.reloadMainThread?.() ?? RESOLVED_PROMISE;
	}
	loadMore() {
		return this._core.loadMore?.() ?? RESOLVED_PROMISE;
	}
	getState() {
		return this._getState();
	}
	subscribe(callback) {
		return this._stateBinding.subscribe(callback);
	}
	_mainThreadListItemRuntime;
	main;
	get mainItem() {
		return this._mainThreadListItemRuntime;
	}
	_createItemStateBinding(threadId) {
		return new ShallowMemoizeSubject({
			path: {
				ref: `threadItems[threadId=${threadId}]`,
				threadSelector: {
					type: "threadId",
					threadId
				}
			},
			getState: () => {
				return getThreadListItemState(this._core, threadId);
			},
			subscribe: (callback) => this._core.subscribe(callback)
		});
	}
	getById(threadId) {
		return new this._runtimeFactory(new NestedSubscriptionSubject({
			path: {
				ref: `threads[threadId=${JSON.stringify(threadId)}]`,
				threadSelector: {
					type: "threadId",
					threadId
				}
			},
			getState: () => this._core.getThreadRuntimeCore(threadId),
			subscribe: (callback) => this._core.subscribe(callback)
		}), this._createItemStateBinding(threadId));
	}
	getItemByIndex(idx) {
		return new ThreadListItemRuntimeImpl(new ShallowMemoizeSubject({
			path: {
				ref: `threadItems[${idx}]`,
				threadSelector: {
					type: "index",
					index: idx
				}
			},
			getState: () => {
				return getThreadListItemState(this._core, this._core.threadIds[idx]);
			},
			subscribe: (callback) => this._core.subscribe(callback)
		}), this._core);
	}
	getArchivedItemByIndex(idx) {
		return new ThreadListItemRuntimeImpl(new ShallowMemoizeSubject({
			path: {
				ref: `archivedThreadItems[${idx}]`,
				threadSelector: {
					type: "archiveIndex",
					index: idx
				}
			},
			getState: () => {
				return getThreadListItemState(this._core, this._core.archivedThreadIds[idx]);
			},
			subscribe: (callback) => this._core.subscribe(callback)
		}), this._core);
	}
	getItemById(threadId) {
		return new ThreadListItemRuntimeImpl(this._createItemStateBinding(threadId), this._core);
	}
};
//#endregion
export { ThreadListRuntimeImpl };
