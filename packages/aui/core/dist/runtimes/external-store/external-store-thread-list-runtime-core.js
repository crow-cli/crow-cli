import { nullProtoRecord } from "../../utils/record.js";
import { BaseSubscribable } from "../../subscribable/subscribable.js";
import { disposeThreadRuntime } from "../../runtime/utils/thread-runtime-lifecycle.js";
//#region src/runtimes/external-store/external-store-thread-list-runtime-core.ts
const EMPTY_ARRAY = Object.freeze([]);
const DEFAULT_THREAD_ID = "DEFAULT_THREAD_ID";
const DEFAULT_THREADS = Object.freeze([DEFAULT_THREAD_ID]);
const DEFAULT_THREAD = Object.freeze({
	id: DEFAULT_THREAD_ID,
	remoteId: void 0,
	externalId: void 0,
	status: "regular"
});
const RESOLVED_PROMISE = Promise.resolve();
const DEFAULT_THREAD_DATA = Object.freeze(nullProtoRecord({ [DEFAULT_THREAD_ID]: DEFAULT_THREAD }));
var ExternalStoreThreadListRuntimeCore = class extends BaseSubscribable {
	_mainThreadId = DEFAULT_THREAD_ID;
	_threads = DEFAULT_THREADS;
	_archivedThreads = EMPTY_ARRAY;
	_threadData = DEFAULT_THREAD_DATA;
	adapter = {};
	get isLoading() {
		return this.adapter.isLoading ?? false;
	}
	get newThreadId() {}
	get threadIds() {
		return this._threads;
	}
	get archivedThreadIds() {
		return this._archivedThreads;
	}
	get threadItems() {
		return this._threadData;
	}
	getLoadThreadsPromise() {
		return RESOLVED_PROMISE;
	}
	_mainThread;
	get mainThreadId() {
		return this._mainThreadId;
	}
	threadFactory;
	constructor(adapter = {}, threadFactory) {
		super();
		this.threadFactory = threadFactory;
		this.__internal_setAdapter(adapter, true);
	}
	getMainThreadRuntimeCore() {
		return this._mainThread;
	}
	getThreadRuntimeCore() {
		throw new Error("Method not implemented.");
	}
	getItemById(threadId) {
		return Object.hasOwn(this._threadData, threadId) ? this._threadData[threadId] : void 0;
	}
	__internal_setAdapter(adapter, initialLoad = false) {
		const previousAdapter = this.adapter;
		this.adapter = adapter;
		const newThreadId = adapter.threadId ?? DEFAULT_THREAD_ID;
		const newThreads = adapter.threads ?? EMPTY_ARRAY;
		const newArchivedThreads = adapter.archivedThreads ?? EMPTY_ARRAY;
		const previousThreadId = previousAdapter.threadId ?? DEFAULT_THREAD_ID;
		const previousThreads = previousAdapter.threads ?? EMPTY_ARRAY;
		const previousArchivedThreads = previousAdapter.archivedThreads ?? EMPTY_ARRAY;
		if (!initialLoad && (previousAdapter.isLoading ?? false) === (adapter.isLoading ?? false) && previousThreadId === newThreadId && previousThreads === newThreads && previousArchivedThreads === newArchivedThreads) return;
		if (previousThreads !== newThreads || previousArchivedThreads !== newArchivedThreads || previousThreadId !== newThreadId) this._threadData = nullProtoRecord(DEFAULT_THREAD_DATA, Object.fromEntries(adapter.threads?.map((t) => [t.id, {
			...t,
			remoteId: t.remoteId,
			externalId: t.externalId,
			status: "regular"
		}]) ?? []), Object.fromEntries(adapter.archivedThreads?.map((t) => [t.id, {
			...t,
			remoteId: t.remoteId,
			externalId: t.externalId,
			status: "archived"
		}]) ?? []));
		if (previousThreads !== newThreads) this._threads = this.adapter.threads?.map((t) => t.id) ?? EMPTY_ARRAY;
		if (previousArchivedThreads !== newArchivedThreads) this._archivedThreads = this.adapter.archivedThreads?.map((t) => t.id) ?? EMPTY_ARRAY;
		if (initialLoad || previousThreadId !== newThreadId) {
			if (!initialLoad) disposeThreadRuntime(this._mainThread);
			this._mainThreadId = newThreadId;
			this._mainThread = this.threadFactory();
		}
		if (!Object.hasOwn(this._threadData, this._mainThreadId)) this._threadData = nullProtoRecord(this._threadData, { [this._mainThreadId]: {
			id: this._mainThreadId,
			remoteId: void 0,
			externalId: void 0,
			status: "regular"
		} });
		this._notifySubscribers();
	}
	async reloadMainThread() {
		if (!this._mainThread.unstable_refetchThread) return;
		await this._mainThread.unstable_refetchThread();
	}
	async switchToThread(threadId, _options) {
		if (this._mainThreadId === threadId) return;
		const onSwitchToThread = this.adapter.onSwitchToThread;
		if (!onSwitchToThread) throw new Error("External store adapter does not support switching to thread");
		await onSwitchToThread(threadId);
	}
	async switchToNewThread() {
		const onSwitchToNewThread = this.adapter.onSwitchToNewThread;
		if (!onSwitchToNewThread) throw new Error("External store adapter does not support switching to new thread");
		await onSwitchToNewThread();
	}
	async rename(threadId, newTitle) {
		const onRename = this.adapter.onRename;
		if (!onRename) throw new Error("External store adapter does not support renaming");
		await onRename(threadId, newTitle);
	}
	async updateCustom(threadId, custom) {
		const onUpdateCustom = this.adapter.onUpdateCustom;
		if (!onUpdateCustom) throw new Error("External store adapter does not support updating custom metadata");
		await onUpdateCustom(threadId, custom);
	}
	async detach() {}
	async archive(threadId) {
		const onArchive = this.adapter.onArchive;
		if (!onArchive) throw new Error("External store adapter does not support archiving");
		await onArchive(threadId);
	}
	async unarchive(threadId) {
		const onUnarchive = this.adapter.onUnarchive;
		if (!onUnarchive) throw new Error("External store adapter does not support unarchiving");
		await onUnarchive(threadId);
	}
	async delete(threadId) {
		const onDelete = this.adapter.onDelete;
		if (!onDelete) throw new Error("External store adapter does not support deleting");
		await onDelete(threadId);
	}
	initialize(threadId) {
		return Promise.resolve({
			remoteId: threadId,
			externalId: void 0
		});
	}
	generateTitle() {
		throw new Error("Method not implemented.");
	}
};
//#endregion
export { ExternalStoreThreadListRuntimeCore };
