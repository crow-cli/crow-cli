import { nullProtoRecord } from "../../utils/record.js";
import { BaseSubscribable, WritableSubscribable } from "../../subscribable/subscribable.js";
import { invokeUserCallback } from "../../utils/invoke-user-callback.js";
import { OptimisticState } from "../../runtimes/remote-thread-list/optimistic-state.js";
import { EMPTY_THREAD_CORE } from "../../runtimes/remote-thread-list/empty-thread-core.js";
import { classifyThreads, createEmptyRemoteThreadState, createThreadMappingId, getThreadData, normalizeCursor, preserveMidLoadTransitions, promoteNewThreadReducer, reconcileInitializedThread, seedNewThread, statusSnapshot, updateStatusReducer } from "../../runtimes/remote-thread-list/remote-thread-state.js";
import { useSubscribable } from "../../store/runtime-clients/useSubscribable.js";
import { handleThreadListAction } from "../../store/runtime-clients/handle-thread-list-action.js";
import { useStableRuntimeAdapters } from "./useRuntimeAdapters.js";
import { RuntimeAdapterProvider } from "./RuntimeAdapterProvider.js";
import { ThreadListAdapterChangedError } from "../../runtimes/remote-thread-list/adapter-changed.js";
import { applyTitleStream, isTitleSourceMessage } from "../../runtimes/remote-thread-list/title.js";
import { clearThreadTitleState, finishThreadTitleRename, runThreadTitleGeneration, startThreadTitleRename } from "../../runtimes/remote-thread-list/title-generation.js";
import { RemoteThreadListHookInstanceManager } from "./RemoteThreadListHookInstanceManager.js";
import { Fragment, useEffect, useId } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { jsx, jsxs } from "react/jsx-runtime";
//#region src/react/runtimes/RemoteThreadListThreadListRuntimeCore.tsx
const threadNotFoundError = (threadIdOrRemoteId, action) => /* @__PURE__ */ new Error(`Thread "${threadIdOrRemoteId}" not found while ${action}.`);
const threadStatusError = (threadIdOrRemoteId, status, action) => /* @__PURE__ */ new Error(`Thread "${threadIdOrRemoteId}" has status "${status}", so it cannot ${action}.`);
const EMPTY_REMOTE_STATE = createEmptyRemoteThreadState();
var RemoteThreadListThreadListRuntimeCore = class extends BaseSubscribable {
	_options;
	_hookManager;
	_runtimeAdapters;
	_loadThreadsPromise;
	_loadMorePromise;
	_loadGeneration = 0;
	_adapterGeneration = 0;
	_replaceListOnNextLoad = false;
	_staleThreadIdsOnReplace;
	_switchGeneration = 0;
	_switchTask;
	_titleStates = /* @__PURE__ */ new Map();
	_mainThreadId;
	_state = new OptimisticState(EMPTY_REMOTE_STATE);
	_useAdaptersProvider = ({ children }) => {
		const useAdapters = this._options.adapter.unstable_useAdapters;
		if (useAdapters === void 0) return children;
		return /* @__PURE__ */ jsx(this._SynthesizedAdapters, {
			useAdapters,
			children
		});
	};
	_SynthesizedAdapters = ({ useAdapters, children }) => {
		const adapters = useStableRuntimeAdapters(useAdapters());
		if (adapters == null) return children;
		return /* @__PURE__ */ jsx(RuntimeAdapterProvider, {
			adapters,
			children
		});
	};
	resolveProvider(adapter) {
		if (adapter.unstable_Provider !== void 0) return adapter.unstable_Provider;
		if (adapter.unstable_useAdapters === void 0) return Fragment;
		return this._useAdaptersProvider;
	}
	get threadItems() {
		return this._state.value.threadData;
	}
	getLoadThreadsPromise() {
		if (!this._loadThreadsPromise) {
			const generation = this._loadGeneration;
			let replacedList = false;
			const statusAtRequest = statusSnapshot(this._state.baseValue);
			this._loadThreadsPromise = this._state.optimisticUpdate({
				execute: () => this._options.adapter.list(),
				loading: (state) => {
					if (generation !== this._loadGeneration) return state;
					return {
						...state,
						isLoading: true,
						loadError: void 0
					};
				},
				then: (state, l) => {
					if (generation !== this._loadGeneration) return state;
					if (this._replaceListOnNextLoad) {
						this._replaceListOnNextLoad = false;
						replacedList = true;
						return this._replaceWithThreads({
							...state,
							loadError: void 0
						}, l.threads, normalizeCursor(l.nextCursor));
					}
					const fresh = classifyThreads(l.threads, {
						threadIds: [],
						archivedThreadIds: [],
						threadIdMap: { ...state.threadIdMap },
						threadData: { ...state.threadData }
					});
					const merged = {
						...state,
						isLoading: false,
						loadError: void 0,
						cursor: normalizeCursor(l.nextCursor),
						threadIds: fresh.threadIds,
						archivedThreadIds: fresh.archivedThreadIds,
						threadIdMap: fresh.threadIdMap,
						threadData: fresh.threadData
					};
					return preserveMidLoadTransitions(merged, state, statusAtRequest);
				}
			}).catch((error) => {
				if (generation !== this._loadGeneration) return;
				console.error("[assistant-ui] thread list load failed:", error);
				this._loadThreadsPromise = void 0;
				if (!this._replaceListOnNextLoad) {
					this._state.update({
						...this._state.baseValue,
						isLoading: false,
						loadError: error
					});
					return;
				}
				this._replaceListOnNextLoad = false;
				replacedList = true;
				this._state.update(this._replaceWithThreads({
					...this._state.baseValue,
					loadError: error
				}, [], void 0));
			}).then(() => {
				if (!replacedList) return;
				const threadId = this._options.threadId;
				if (threadId === void 0) return;
				if (this.getItemById(threadId)?.id === this._mainThreadId) return;
				this._switchToThreadFromProp(threadId).catch(() => {});
			});
		}
		return this._loadThreadsPromise;
	}
	loadMore() {
		if (this._loadMorePromise) return this._loadMorePromise;
		const initialState = this._state.value;
		if (initialState.cursor === void 0 || initialState.isLoading) return Promise.resolve();
		const generation = this._loadGeneration;
		const adapter = this._options.adapter;
		const cursor = initialState.cursor;
		const dedup = this._state.optimisticUpdate({
			execute: () => adapter.list({ after: cursor }),
			loading: (state) => {
				if (generation !== this._loadGeneration) return state;
				return {
					...state,
					isLoadingMore: true
				};
			},
			then: (state, l) => {
				if (generation !== this._loadGeneration) return state;
				if (adapter !== this._options.adapter) return state;
				const appended = classifyThreads(l.threads, {
					threadIds: [...state.threadIds],
					archivedThreadIds: [...state.archivedThreadIds],
					threadIdMap: { ...state.threadIdMap },
					threadData: { ...state.threadData }
				});
				return {
					...state,
					isLoadingMore: false,
					cursor: normalizeCursor(l.nextCursor),
					threadIds: appended.threadIds,
					archivedThreadIds: appended.archivedThreadIds,
					threadIdMap: appended.threadIdMap,
					threadData: appended.threadData
				};
			}
		}).catch((error) => {
			if (generation !== this._loadGeneration) return;
			console.error("[assistant-ui] thread list loadMore failed:", error);
		}).then(() => {
			if (this._loadMorePromise === dedup) this._loadMorePromise = void 0;
		});
		this._loadMorePromise = dedup;
		return dedup;
	}
	constructor(options, contextProvider, initialThreadIdSeed) {
		super();
		this._state.subscribe(() => {
			this._notifySubscribers();
			this._notifyThreadIdChange();
		});
		this._runtimeAdapters = { modelContext: contextProvider };
		this._hookManager = new RemoteThreadListHookInstanceManager(options.runtimeHook, this);
		this._hookManager.__internal_setDefaultAdapters(this._runtimeAdapters);
		this._hookManager.__internal_subscribeRunningChanged(() => this._notifySubscribers());
		this._hookManager.__internal_subscribeRuntimeReplaced(() => {
			queueMicrotask(() => this._notifySubscribers());
		});
		this.providerStore = new WritableSubscribable(this.resolveProvider(options.adapter));
		this.__internal_setOptions(options);
		this._startSwitchToNewThread(true, initialThreadIdSeed);
	}
	_initialThreadLoaded = false;
	providerStore;
	__internal_setOptions(options) {
		if (this._options === options) return;
		const adapterChanged = this._options !== void 0 && this._options.adapter !== options.adapter;
		const controlledThreadIdChanged = this._initialThreadLoaded && this._options !== void 0 && this._options.threadId !== options.threadId;
		this._options = options;
		this.providerStore.setState(this.resolveProvider(options.adapter));
		this._hookManager.setRuntimeHook(options.runtimeHook);
		if (adapterChanged) {
			this._loadGeneration++;
			this._adapterGeneration++;
			this._switchGeneration++;
			this._switchTask = void 0;
			this._loadThreadsPromise = void 0;
			this._loadMorePromise = void 0;
			this._replaceListOnNextLoad = true;
			this._staleThreadIdsOnReplace = new Set(Object.values(this._state.baseValue.threadData).filter((item) => item.status !== "new").map((item) => item.id));
			this._state.update({
				...this._state.baseValue,
				cursor: void 0,
				loadError: void 0
			});
			this._titleStates.clear();
		}
		if (controlledThreadIdChanged) this._switchToThreadFromProp(options.threadId).catch(() => {});
	}
	_requireAdapterGeneration(generation) {
		if (generation !== this._adapterGeneration) throw new ThreadListAdapterChangedError();
	}
	_requireAdapterSettled() {
		if (this._replaceListOnNextLoad) throw new ThreadListAdapterChangedError();
	}
	_replaceWithThreads(state, threads, cursor) {
		const carried = [];
		if (state.newThreadId) {
			const mappingId = Object.hasOwn(state.threadIdMap, state.newThreadId) ? state.threadIdMap[state.newThreadId] : void 0;
			const draft = mappingId && Object.hasOwn(state.threadData, mappingId) ? state.threadData[mappingId] : void 0;
			if (draft?.status === "new") carried.push(draft);
		}
		const stale = this._staleThreadIdsOnReplace;
		if (stale) for (const item of Object.values(state.threadData)) {
			if (stale.has(item.id)) continue;
			if (item.status !== "new" && item.remoteId === void 0) continue;
			carried.push(item);
		}
		this._staleThreadIdsOnReplace = void 0;
		const seed = {
			threadIds: [],
			archivedThreadIds: [],
			threadIdMap: nullProtoRecord(),
			threadData: nullProtoRecord()
		};
		for (const item of carried) {
			const mappingId = createThreadMappingId(item.id);
			if (Object.hasOwn(seed.threadData, mappingId)) continue;
			seed.threadIdMap[item.id] = mappingId;
			if (item.remoteId !== void 0) seed.threadIdMap[item.remoteId] = mappingId;
			seed.threadData[mappingId] = item;
		}
		const { threadIds, archivedThreadIds, threadIdMap, threadData } = classifyThreads(threads, seed);
		for (const item of carried) {
			if (item.remoteId === void 0) continue;
			const currentMappingId = createThreadMappingId(item.id);
			const current = Object.hasOwn(threadData, currentMappingId) ? threadData[currentMappingId] : void 0;
			if (current === void 0) continue;
			if (current.status === "regular" && !threadIds.includes(current.id)) threadIds.push(current.id);
			else if (current.status === "archived" && !archivedThreadIds.includes(current.id)) archivedThreadIds.push(current.id);
		}
		let nextState = {
			...state,
			isLoading: false,
			cursor,
			threadIds,
			archivedThreadIds,
			threadIdMap,
			threadData,
			newThreadId: state.newThreadId !== void 0 && !Object.hasOwn(threadIdMap, state.newThreadId) ? void 0 : state.newThreadId
		};
		if (getThreadData(nextState, this._mainThreadId) === void 0) {
			const preservedDraft = nextState.newThreadId;
			if (preservedDraft !== void 0) this._mainThreadId = preservedDraft;
			else {
				const seeded = seedNewThread(nextState);
				this._mainThreadId = seeded.id;
				nextState = seeded.state;
			}
			if (this._options.threadId === void 0) this._notifyThreadIdChange();
			else this._lastNotifiedThreadId = void 0;
		}
		const nextIds = new Set(Object.values(nextState.threadData).map((item) => item.id));
		for (const item of Object.values(state.threadData)) {
			if (nextIds.has(item.id)) continue;
			try {
				this._hookManager.stopThreadRuntime(item.id);
			} catch (error) {
				console.error("[assistant-ui] Thread runtime cleanup threw while stopping a thread", error);
			}
		}
		this._hookManager.startThreadRuntime(this._mainThreadId).then(() => this._notifySubscribers(), () => void 0);
		return nextState;
	}
	__internal_load() {
		this.getLoadThreadsPromise();
		if (this._initialThreadLoaded) return;
		this._initialThreadLoaded = true;
		const startThreadId = this._options.threadId ?? this._options.initialThreadId;
		if (startThreadId !== void 0) (this._options.threadId !== void 0 ? this._switchToThreadFromProp(startThreadId) : this.switchToThread(startThreadId)).catch(() => {});
	}
	async reloadMainThread() {
		const threadId = this._mainThreadId;
		if (threadId === void 0) return;
		if (this.getItemById(threadId)?.status === "new") return;
		const runtimeCore = this._hookManager.getThreadRuntimeCore(threadId);
		try {
			if (runtimeCore?.unstable_refetchThread) await runtimeCore.unstable_refetchThread();
			else await this._hookManager.__internal_restartThreadRuntime(threadId);
		} catch (error) {
			if (threadId !== this._mainThreadId) return;
			throw error;
		}
		if (threadId !== this._mainThreadId) return;
		this._notifySubscribers();
	}
	reload() {
		this._loadGeneration++;
		this._loadThreadsPromise = void 0;
		this._loadMorePromise = void 0;
		this._state.update({
			...this._state.baseValue,
			cursor: void 0
		});
		return this.getLoadThreadsPromise();
	}
	get isLoading() {
		return this._state.value.isLoading;
	}
	get loadError() {
		return this._state.value.loadError;
	}
	get isLoadingMore() {
		return this._state.value.isLoadingMore;
	}
	get hasMore() {
		return this._state.value.cursor !== void 0;
	}
	get threadIds() {
		return this._state.value.threadIds;
	}
	get archivedThreadIds() {
		return this._state.value.archivedThreadIds;
	}
	get newThreadId() {
		return this._state.value.newThreadId;
	}
	get mainThreadId() {
		return this._mainThreadId;
	}
	get _mainThreadRemoteId() {
		if (this._mainThreadId === void 0) return void 0;
		return getThreadData(this._state.value, this._mainThreadId)?.remoteId;
	}
	_lastNotifiedThreadId = void 0;
	_notifyThreadIdChange(emit = true) {
		const threadId = this._mainThreadRemoteId;
		if (this._lastNotifiedThreadId === threadId) return;
		this._lastNotifiedThreadId = threadId;
		if (emit) invokeUserCallback("assistant-ui", "onThreadIdChange", this._options.onThreadIdChange, threadId);
	}
	getMainThreadRuntimeCore() {
		const result = this._hookManager.getThreadRuntimeCore(this._mainThreadId);
		if (!result) return EMPTY_THREAD_CORE;
		return result;
	}
	getThreadRuntimeCore(threadIdOrRemoteId) {
		const data = this.getItemById(threadIdOrRemoteId);
		if (!data) throw threadNotFoundError(threadIdOrRemoteId, "getting its runtime");
		const result = this._hookManager.getThreadRuntimeCore(data.id);
		if (!result) throw new Error(`Runtime for thread "${threadIdOrRemoteId}" not found while getting its runtime.`);
		return result;
	}
	unstable_isThreadRunning(threadIdOrRemoteId) {
		const data = this.getItemById(threadIdOrRemoteId);
		if (!data) return false;
		return this._hookManager.__internal_isThreadRunning(data.id);
	}
	unstable_subscribeThreadEvents(callback) {
		return this._hookManager.__internal_subscribeThreadEvents(callback);
	}
	getItemById(threadIdOrRemoteId) {
		return getThreadData(this._state.value, threadIdOrRemoteId);
	}
	switchToThread(threadIdOrRemoteId, options) {
		return this._startSwitchToThread(threadIdOrRemoteId, options, true);
	}
	_startSwitchToThread(threadIdOrRemoteId, options, emitThreadIdChange) {
		const generation = ++this._switchGeneration;
		const task = this._switchToThread(threadIdOrRemoteId, options, generation, emitThreadIdChange);
		this._switchTask = task;
		return task;
	}
	async _switchToThread(threadIdOrRemoteId, options, generation, emitThreadIdChange) {
		if (this._replaceListOnNextLoad && threadIdOrRemoteId !== this._state.value.newThreadId) throw new ThreadListAdapterChangedError();
		let data = this.getItemById(threadIdOrRemoteId);
		if (!data) {
			const remoteMetadata = await this._options.adapter.fetch(threadIdOrRemoteId);
			if (generation !== this._switchGeneration) return;
			const state = this._state.value;
			const mappingId = createThreadMappingId(remoteMetadata.remoteId);
			const newThreadData = {
				...state.threadData,
				[mappingId]: {
					id: mappingId,
					initializeTask: Promise.resolve({
						remoteId: remoteMetadata.remoteId,
						externalId: remoteMetadata.externalId
					}),
					remoteId: remoteMetadata.remoteId,
					externalId: remoteMetadata.externalId,
					status: remoteMetadata.status,
					title: remoteMetadata.title,
					lastMessageAt: remoteMetadata.lastMessageAt,
					custom: remoteMetadata.custom
				}
			};
			const newThreadIdMap = {
				...state.threadIdMap,
				[remoteMetadata.remoteId]: mappingId
			};
			const remoteId = remoteMetadata.remoteId;
			const wasInTarget = remoteMetadata.status === "regular" ? state.threadIds.includes(remoteId) : state.archivedThreadIds.includes(remoteId);
			const threadIdsWithoutRemote = state.threadIds.filter((id) => id !== remoteId);
			const archivedThreadIdsWithoutRemote = state.archivedThreadIds.filter((id) => id !== remoteId);
			const newThreadIds = remoteMetadata.status === "regular" ? wasInTarget ? state.threadIds : [...threadIdsWithoutRemote, remoteId] : threadIdsWithoutRemote;
			const newArchivedThreadIds = remoteMetadata.status === "archived" ? wasInTarget ? state.archivedThreadIds : [...archivedThreadIdsWithoutRemote, remoteId] : archivedThreadIdsWithoutRemote;
			this._state.update({
				...state,
				threadIds: newThreadIds,
				archivedThreadIds: newArchivedThreadIds,
				threadIdMap: newThreadIdMap,
				threadData: newThreadData
			});
			data = this.getItemById(threadIdOrRemoteId);
		}
		if (!data) throw threadNotFoundError(threadIdOrRemoteId, "switching to it");
		if (this._mainThreadId === data.id) return;
		const task = this._hookManager.startThreadRuntime(data.id);
		if (this.mainThreadId !== void 0) await task;
		else task.then(() => this._notifySubscribers(), () => void 0);
		if (generation !== this._switchGeneration) return;
		let current = this.getItemById(data.id);
		if (current?.id !== data.id) return;
		if (current.status === "archived" && options?.unarchive !== false) {
			await current.initializeTask;
			if (generation !== this._switchGeneration) return;
			current = this.getItemById(data.id);
			if (current?.id !== data.id) return;
			if (current.status === "archived") {
				await this.unarchive(current.id);
				if (generation !== this._switchGeneration) return;
				current = this.getItemById(data.id);
				if (current?.id !== data.id) return;
			}
		}
		this._mainThreadId = current.id;
		this._notifySubscribers();
		this._notifyThreadIdChange(emitThreadIdChange);
	}
	switchToNewThread() {
		return this._startSwitchToNewThread(true);
	}
	_switchToThreadFromProp(threadId) {
		return threadId !== void 0 ? handleThreadListAction("switch", () => this._startSwitchToThread(threadId, void 0, false)) : handleThreadListAction("create", () => this._startSwitchToNewThread(false));
	}
	_startSwitchToNewThread(emitThreadIdChange, initialThreadIdSeed) {
		const generation = ++this._switchGeneration;
		const task = this._switchToNewThread(generation, emitThreadIdChange, initialThreadIdSeed);
		this._switchTask = task;
		return task;
	}
	async _switchToNewThread(generation, emitThreadIdChange, initialThreadIdSeed) {
		while (this._state.baseValue.newThreadId !== void 0 && this._state.value.newThreadId === void 0) {
			await this._state.waitForUpdate();
			if (generation !== this._switchGeneration) return;
		}
		const state = this._state.baseValue;
		let id = this._state.value.newThreadId;
		if (id === void 0) {
			const next = seedNewThread(state, initialThreadIdSeed);
			id = next.id;
			this._state.update(next.state);
		}
		return this._switchToThread(id, void 0, generation, emitThreadIdChange);
	}
	initialize = async (threadId) => {
		const adapter = this._options.adapter;
		const adapterGeneration = this._adapterGeneration;
		if (this._state.value.newThreadId !== threadId) {
			this._requireAdapterSettled();
			const data = this.getItemById(threadId);
			if (!data) throw threadNotFoundError(threadId, "initializing it");
			if (data.status === "new") throw threadStatusError(threadId, data.status, "be initialized here");
			const { remoteId, externalId } = await data.initializeTask;
			this._requireAdapterGeneration(adapterGeneration);
			return {
				remoteId,
				externalId
			};
		}
		this._requireAdapterGeneration(adapterGeneration);
		const initializeTask = adapter.initialize(threadId);
		let removedMappingId;
		const { remoteId, externalId } = await this._state.optimisticUpdate({
			execute: () => initializeTask,
			optimistic: (state) => promoteNewThreadReducer(state, threadId, initializeTask),
			then: (state, { remoteId, externalId }) => {
				if (adapterGeneration !== this._adapterGeneration) return state;
				const reconciliation = reconcileInitializedThread(state, threadId, remoteId, externalId, threadId);
				removedMappingId = reconciliation.removedMappingId;
				if (removedMappingId === this._mainThreadId) this._mainThreadId = reconciliation.survivorMappingId;
				return reconciliation.state;
			}
		});
		this._requireAdapterGeneration(adapterGeneration);
		if (removedMappingId !== void 0) this._hookManager.stopThreadRuntime(removedMappingId);
		return {
			remoteId,
			externalId
		};
	};
	generateTitle = async (threadId, options) => {
		this._requireAdapterSettled();
		const adapter = this._options.adapter;
		const adapterGeneration = this._adapterGeneration;
		const data = this.getItemById(threadId);
		if (!data) throw threadNotFoundError(threadId, "generating its title");
		if (data.status === "new") throw threadStatusError(threadId, data.status, "generate a title");
		const { remoteId } = await data.initializeTask;
		this._requireAdapterGeneration(adapterGeneration);
		const runtimeCore = this._hookManager.getThreadRuntimeCore(data.id);
		if (!runtimeCore) return;
		const messages = runtimeCore.messages.filter(isTitleSourceMessage);
		await runThreadTitleGeneration({
			states: this._titleStates,
			threadId: data.id,
			automatic: options?.automatic === true,
			generate: async (onTitle) => {
				const stream = await adapter.generateTitle(remoteId, messages);
				this._requireAdapterGeneration(adapterGeneration);
				await applyTitleStream(stream, onTitle);
			},
			rename: async (title) => {
				this._requireAdapterGeneration(adapterGeneration);
				await adapter.rename(remoteId, title);
			},
			applyTitle: async (title) => {
				await this._state.optimisticUpdate({
					execute: async () => {},
					optimistic: (state) => {
						if (adapterGeneration !== this._adapterGeneration) return state;
						const currentData = getThreadData(state, data.id);
						if (!currentData) return state;
						return {
							...state,
							threadData: {
								...state.threadData,
								[currentData.id]: {
									...currentData,
									title
								}
							}
						};
					}
				});
			}
		});
	};
	async rename(threadIdOrRemoteId, newTitle) {
		this._requireAdapterSettled();
		const adapter = this._options.adapter;
		const adapterGeneration = this._adapterGeneration;
		const data = this.getItemById(threadIdOrRemoteId);
		if (!data) throw threadNotFoundError(threadIdOrRemoteId, "renaming it");
		if (data.status === "new") throw threadStatusError(threadIdOrRemoteId, data.status, "be renamed");
		const claim = startThreadTitleRename(this._titleStates, data.id, newTitle);
		try {
			const result = await this._state.optimisticUpdate({
				execute: async () => {
					const { remoteId } = await data.initializeTask;
					this._requireAdapterGeneration(adapterGeneration);
					return adapter.rename(remoteId, newTitle);
				},
				optimistic: (state) => {
					const currentData = getThreadData(state, threadIdOrRemoteId);
					if (!currentData) return state;
					return {
						...state,
						threadData: {
							...state.threadData,
							[currentData.id]: {
								...currentData,
								title: newTitle
							}
						}
					};
				}
			});
			finishThreadTitleRename(this._titleStates, data.id, claim, true);
			return result;
		} catch (error) {
			finishThreadTitleRename(this._titleStates, data.id, claim, false);
			throw error;
		}
	}
	async updateCustom(threadIdOrRemoteId, custom) {
		this._requireAdapterSettled();
		const adapter = this._options.adapter;
		const adapterGeneration = this._adapterGeneration;
		const data = this.getItemById(threadIdOrRemoteId);
		if (!data) throw threadNotFoundError(threadIdOrRemoteId, "updating its custom metadata");
		if (data.status === "new") throw threadStatusError(threadIdOrRemoteId, data.status, "update custom metadata");
		if (!adapter.updateCustom) throw new Error("Remote thread list adapter does not support updating custom metadata");
		return this._state.optimisticUpdate({
			execute: async () => {
				const { remoteId } = await data.initializeTask;
				this._requireAdapterGeneration(adapterGeneration);
				if (!adapter.updateCustom) throw new Error("Remote thread list adapter does not support updating custom metadata");
				return adapter.updateCustom(remoteId, custom);
			},
			optimistic: (state) => {
				const data = getThreadData(state, threadIdOrRemoteId);
				if (!data) return state;
				return {
					...state,
					threadData: {
						...state.threadData,
						[data.id]: {
							...data,
							custom
						}
					}
				};
			}
		});
	}
	async _ensureThreadIsNotMain(threadId) {
		if (threadId === this.newThreadId) throw new Error("Cannot ensure new thread is not main");
		let lastAwaitedTask;
		while (threadId === this._mainThreadId) {
			if (threadId === this.newThreadId) throw new Error("Cannot ensure new thread is not main");
			let switchTask = this._switchTask;
			const startedFallback = !switchTask || switchTask === lastAwaitedTask;
			if (startedFallback) switchTask = this.switchToNewThread();
			lastAwaitedTask = switchTask;
			try {
				await switchTask;
			} catch (error) {
				if (startedFallback && this._switchTask === switchTask) throw error;
			}
		}
	}
	async archive(threadIdOrRemoteId) {
		this._requireAdapterSettled();
		const adapter = this._options.adapter;
		const adapterGeneration = this._adapterGeneration;
		const data = this.getItemById(threadIdOrRemoteId);
		if (!data) throw threadNotFoundError(threadIdOrRemoteId, "archiving it");
		if (data.status !== "regular") throw threadStatusError(threadIdOrRemoteId, data.status, "be archived");
		await this._ensureThreadIsNotMain(data.id);
		this._requireAdapterGeneration(adapterGeneration);
		return this._state.optimisticUpdate({
			execute: async () => {
				const { remoteId } = await data.initializeTask;
				this._requireAdapterGeneration(adapterGeneration);
				return adapter.archive(remoteId);
			},
			optimistic: (state) => {
				return updateStatusReducer(state, data.id, "archived");
			}
		});
	}
	async unarchive(threadIdOrRemoteId) {
		this._requireAdapterSettled();
		const adapter = this._options.adapter;
		const adapterGeneration = this._adapterGeneration;
		const data = this.getItemById(threadIdOrRemoteId);
		if (!data) throw threadNotFoundError(threadIdOrRemoteId, "unarchiving it");
		if (data.status !== "archived") throw threadStatusError(threadIdOrRemoteId, data.status, "be unarchived");
		return this._state.optimisticUpdate({
			execute: async () => {
				try {
					const { remoteId } = await data.initializeTask;
					this._requireAdapterGeneration(adapterGeneration);
					return await adapter.unarchive(remoteId);
				} catch (error) {
					if (adapterGeneration === this._adapterGeneration) await this._ensureThreadIsNotMain(data.id);
					throw error;
				}
			},
			optimistic: (state) => {
				return updateStatusReducer(state, data.id, "regular");
			}
		});
	}
	async delete(threadIdOrRemoteId) {
		this._requireAdapterSettled();
		const adapter = this._options.adapter;
		const adapterGeneration = this._adapterGeneration;
		const data = this.getItemById(threadIdOrRemoteId);
		if (!data) throw threadNotFoundError(threadIdOrRemoteId, "deleting it");
		if (data.status !== "regular" && data.status !== "archived") throw threadStatusError(threadIdOrRemoteId, data.status, "be deleted");
		await this._ensureThreadIsNotMain(data.id);
		this._requireAdapterGeneration(adapterGeneration);
		const result = await this._state.optimisticUpdate({
			execute: async () => {
				const { remoteId } = await data.initializeTask;
				this._requireAdapterGeneration(adapterGeneration);
				return await adapter.delete(remoteId);
			},
			optimistic: (state) => {
				return updateStatusReducer(state, data.id, "deleted");
			}
		});
		this._hookManager.stopThreadRuntime(data.id);
		clearThreadTitleState(this._titleStates, data.id);
		return result;
	}
	__internal_dispose() {
		this._hookManager.__internal_dispose();
	}
	async detach(threadIdOrRemoteId) {
		const adapterGeneration = this._adapterGeneration;
		const data = this.getItemById(threadIdOrRemoteId);
		if (!data) throw threadNotFoundError(threadIdOrRemoteId, "detaching it");
		if (data.status !== "regular" && data.status !== "archived") throw threadStatusError(threadIdOrRemoteId, data.status, "be detached");
		await this._ensureThreadIsNotMain(data.id);
		this._requireAdapterGeneration(adapterGeneration);
		this._hookManager.stopThreadRuntime(data.id);
	}
	boundIdsStore = new WritableSubscribable([]);
	__internal_RenderComponent = () => {
		const id = useId();
		useEffect(() => {
			this.boundIdsStore.setState([...this.boundIdsStore.getState(), id]);
			return () => {
				this.boundIdsStore.setState(this.boundIdsStore.getState().filter((i) => i !== id));
			};
		}, [id]);
		const boundIds = useSubscribable(this.boundIdsStore);
		const Provider = useSubscribable(this.providerStore);
		const aui = useAui();
		return (boundIds.length === 0 || boundIds[0] === id) && /* @__PURE__ */ jsxs(RuntimeAdapterProvider, {
			adapters: this._runtimeAdapters,
			children: [/* @__PURE__ */ jsx(this._hookManager.__internal_RenderThreadRuntimes, { provider: Provider }), /* @__PURE__ */ jsx(this._hookManager.__internal_Host, { parentClient: aui })]
		});
	};
};
//#endregion
export { RemoteThreadListThreadListRuntimeCore };
