import { invokeUserCallback } from "../../utils/invoke-user-callback.js";
import { OptimisticState } from "../../runtimes/remote-thread-list/optimistic-state.js";
import { classifyThreads, createEmptyRemoteThreadState, createThreadMappingId, getThreadData, normalizeCursor, preserveMidLoadTransitions, promoteNewThreadReducer, reconcileInitializedThread, seedNewThread, statusSnapshot, updateStatusReducer } from "../../runtimes/remote-thread-list/remote-thread-state.js";
import { useThreadListItemSelectionEvents, useThreadSelectionEvents } from "../../store/clients/thread-selection-events.js";
import { handleThreadListAction } from "../../store/runtime-clients/handle-thread-list-action.js";
import { useAfterStateCommit } from "../../store/runtime-clients/useAfterStateCommit.js";
import { isDevelopment } from "../../store/env.js";
import { AdaptedRemoteThread } from "./AdaptedRemoteThread.js";
import { inMemoryThreadListTransformScopes } from "./InMemoryThreadList.js";
import { ThreadListAdapterChangedError } from "../../runtimes/remote-thread-list/adapter-changed.js";
import { applyTitleStream, isTitleSourceMessage } from "../../runtimes/remote-thread-list/title.js";
import { clearThreadTitleState, finishThreadTitleRename, runThreadTitleGeneration, startThreadTitleRename } from "../../runtimes/remote-thread-list/title-generation.js";
import { Derived, attachTransformScopes, useAssistantContextProvider, useAssistantContextValue, useClientLookup, useClientResource, useConfiguredAui } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "@assistant-ui/tap/react-shim";
import { resource, withKey } from "@assistant-ui/tap";
//#region src/react/client/RemoteThreadList.ts
const RESOLVED_PROMISE = Promise.resolve();
const EMPTY_LIST = createEmptyRemoteThreadState();
const threadNotFoundError = (threadIdOrRemoteId, action) => /* @__PURE__ */ new Error(`Thread "${threadIdOrRemoteId}" was not found while ${action}.`);
const threadStatusError = (threadIdOrRemoteId, status, action) => /* @__PURE__ */ new Error(`Thread "${threadIdOrRemoteId}" has status "${status}", so it cannot ${action}.`);
const toInitializeResult = (result) => ({
	remoteId: result.remoteId,
	externalId: result.externalId
});
const useThreadListItemClient = (props) => {
	const $ = c(22);
	const { data, isMain, isInitialMain, isRunning, onSwitchTo, onRename, onUpdateCustom, onArchive, onUnarchive, onDelete, onGenerateTitle, onInitialize, onDetach } = props;
	const t0 = "lastMessageAt" in data ? data.lastMessageAt : void 0;
	let t1;
	if ($[0] !== data.custom || $[1] !== data.externalId || $[2] !== data.id || $[3] !== data.remoteId || $[4] !== data.status || $[5] !== data.title || $[6] !== isRunning || $[7] !== t0) {
		t1 = {
			id: data.id,
			remoteId: data.remoteId,
			externalId: data.externalId,
			title: data.title,
			lastMessageAt: t0,
			status: data.status,
			custom: data.custom,
			isRunning
		};
		$[0] = data.custom;
		$[1] = data.externalId;
		$[2] = data.id;
		$[3] = data.remoteId;
		$[4] = data.status;
		$[5] = data.title;
		$[6] = isRunning;
		$[7] = t0;
		$[8] = t1;
	} else t1 = $[8];
	const state = t1;
	useThreadListItemSelectionEvents(data.id, isMain, isInitialMain);
	let t2;
	if ($[9] !== state) {
		t2 = () => state;
		$[9] = state;
		$[10] = t2;
	} else t2 = $[10];
	let t3;
	if ($[11] !== onArchive || $[12] !== onDelete || $[13] !== onDetach || $[14] !== onGenerateTitle || $[15] !== onInitialize || $[16] !== onRename || $[17] !== onSwitchTo || $[18] !== onUnarchive || $[19] !== onUpdateCustom || $[20] !== t2) {
		t3 = {
			getState: t2,
			switchTo: onSwitchTo,
			rename: onRename,
			updateCustom: onUpdateCustom,
			archive: onArchive,
			unarchive: onUnarchive,
			delete: onDelete,
			generateTitle: onGenerateTitle,
			initialize: onInitialize,
			detach: onDetach
		};
		$[11] = onArchive;
		$[12] = onDelete;
		$[13] = onDetach;
		$[14] = onGenerateTitle;
		$[15] = onInitialize;
		$[16] = onRename;
		$[17] = onSwitchTo;
		$[18] = onUnarchive;
		$[19] = onUpdateCustom;
		$[20] = t2;
		$[21] = t3;
	} else t3 = $[21];
	return t3;
};
const ThreadListItemClient = resource(useThreadListItemClient);
const collectItemOrder = (listState, mainThreadId) => {
	const ids = [
		listState.newThreadId,
		...listState.threadIds,
		...listState.archivedThreadIds,
		mainThreadId
	].filter((id) => id !== void 0);
	const seenIds = /* @__PURE__ */ new Set();
	const seenRemoteIds = /* @__PURE__ */ new Set();
	const items = [];
	for (const id of ids) {
		const data = getThreadData(listState, id);
		if (!data || seenIds.has(data.id)) continue;
		if (data.remoteId !== void 0 && seenRemoteIds.has(data.remoteId)) continue;
		seenIds.add(data.id);
		if (data.remoteId !== void 0) seenRemoteIds.add(data.remoteId);
		items.push(data);
	}
	return items;
};
const itemMatchesId = (item, listState, id) => {
	const data = getThreadData(listState, id);
	return item.id === id || item.id === data?.id || data?.remoteId !== void 0 && (item.id === data.remoteId || item.remoteId === data.remoteId);
};
const isSameThread = (listState, left, right) => {
	if (left === right) return true;
	const data = getThreadData(listState, left);
	return data !== void 0 && itemMatchesId(data, listState, right);
};
const useRemoteThreadBody = ({ id, status, remoteId, item, thread }) => {
	const parent = useAssistantContextValue();
	const [isRunning, setIsRunning] = useState(false);
	const itemHandle = useClientResource(item(isRunning));
	const { client } = useConfiguredAui(parent, { threadListItem: Derived({
		source: "threads",
		query: {
			type: "id",
			id
		},
		get: () => itemHandle.methods
	}) });
	const bornNewRef = useRef(status === "new");
	const titleFiredRef = useRef(false);
	return useAssistantContextProvider(client, function useBoundRemoteBody() {
		const body = useClientResource(thread);
		const bodyRunning = body.state.isRunning === true;
		useEffect(() => {
			setIsRunning(bodyRunning);
		}, [bodyRunning]);
		const hasTitleSource = bornNewRef.current && !titleFiredRef.current && remoteId !== void 0 && body.state.messages.some(isTitleSourceMessage);
		useEffect(() => {
			if (!hasTitleSource || titleFiredRef.current) return;
			titleFiredRef.current = true;
			client.threadListItem.generateTitle({ automatic: true });
		}, [hasTitleSource]);
		return body.methods;
	});
};
const RemoteThreadBody = resource(useRemoteThreadBody);
const useMainThreadFacade = (current) => {
	const currentRef = useRef(current);
	useEffect(() => {
		currentRef.current = current;
	}, [current]);
	const [facade] = useState(() => new Proxy({}, {
		get: (_, prop) => currentRef.current[prop],
		has: (__0, prop_0) => prop_0 in currentRef.current,
		ownKeys: () => Reflect.ownKeys(currentRef.current),
		getOwnPropertyDescriptor: (__1, prop_1) => Reflect.getOwnPropertyDescriptor(currentRef.current, prop_1)
	}));
	return facade;
};
const useRemoteThreadListView = (t0) => {
	const $ = c(21);
	const { listState, mainThreadId, initialMainId, startedIds, backgroundThreads, threadFactory, useAdapters, onSwitchTo, onRename, onUpdateCustom, onArchive, onUnarchive, onDelete, onGenerateTitle, onInitialize, onDetach } = t0;
	let t1;
	bb0: {
		if (!backgroundThreads) {
			let t2;
			if ($[0] !== mainThreadId) {
				t2 = [mainThreadId];
				$[0] = mainThreadId;
				$[1] = t2;
			} else t2 = $[1];
			t1 = t2;
			break bb0;
		}
		let ids;
		if ($[2] !== listState || $[3] !== startedIds) {
			const seen = /* @__PURE__ */ new Set();
			const seenRemoteIds = /* @__PURE__ */ new Set();
			ids = [];
			for (const id of startedIds) {
				const data = getThreadData(listState, id);
				if (!data || seen.has(data.id)) continue;
				if (data.remoteId !== void 0 && seenRemoteIds.has(data.remoteId)) continue;
				seen.add(data.id);
				if (data.remoteId !== void 0) seenRemoteIds.add(data.remoteId);
				ids.push(data.id);
			}
			$[2] = listState;
			$[3] = startedIds;
			$[4] = ids;
		} else ids = $[4];
		t1 = ids;
	}
	const bodyIds = t1;
	const itemElementFor = (data_0, isRunning, reportsSelection) => ThreadListItemClient({
		data: data_0,
		isMain: reportsSelection && itemMatchesId(data_0, listState, mainThreadId),
		isInitialMain: data_0.id === initialMainId,
		isRunning,
		onSwitchTo: (options) => handleThreadListAction("switch", () => onSwitchTo(data_0.id, options)),
		onRename: (title) => handleThreadListAction("rename", () => onRename(data_0.id, title)),
		onUpdateCustom: (custom) => handleThreadListAction("update custom metadata", () => onUpdateCustom(data_0.id, custom)),
		onArchive: () => handleThreadListAction("archive", () => onArchive(data_0.id)),
		onUnarchive: () => handleThreadListAction("unarchive", () => onUnarchive(data_0.id)),
		onDelete: () => handleThreadListAction("delete", () => onDelete(data_0.id)),
		onGenerateTitle: (options_0) => handleThreadListAction("generate title", () => onGenerateTitle(data_0.id, backgroundThreads ? bodyStateOf(data_0.id)?.messages : mainThreadClient.state.messages, options_0)),
		onInitialize: () => onInitialize(data_0.id),
		onDetach: () => handleThreadListAction("detach", () => onDetach(data_0.id))
	});
	const bodies = useClientLookup(bodyIds.map((id_0) => {
		const made = threadFactory(id_0);
		const thread = backgroundThreads && made.key === void 0 ? withKey(id_0, made) : made;
		const wrapped = useAdapters === void 0 ? thread : AdaptedRemoteThread({
			useAdapters,
			thread
		});
		const data_1 = getThreadData(listState, id_0);
		const element = backgroundThreads && data_1 !== void 0 ? RemoteThreadBody({
			id: id_0,
			status: data_1.status,
			remoteId: data_1.remoteId,
			item: (isRunning_0) => itemElementFor(data_1, isRunning_0, false),
			thread: wrapped
		}) : wrapped;
		return withKey(backgroundThreads ? id_0 : made.key ?? "main", element);
	}));
	let t2;
	if ($[5] !== bodyIds || $[6] !== listState) {
		t2 = (id_1) => {
			const direct = bodyIds.indexOf(id_1);
			if (direct !== -1) return direct;
			return bodyIds.findIndex((bodyId) => isSameThread(listState, bodyId, id_1));
		};
		$[5] = bodyIds;
		$[6] = listState;
		$[7] = t2;
	} else t2 = $[7];
	const bodyIndexOf = t2;
	const bodyStateOf = (id_2) => {
		const index = bodyIndexOf(id_2);
		return index === -1 ? void 0 : bodies.state[index];
	};
	let t3;
	let t4;
	let t5;
	if ($[8] !== bodies || $[9] !== bodyIndexOf || $[10] !== mainThreadId) {
		const mainIndex = bodyIndexOf(mainThreadId);
		t5 = bodies.state[mainIndex];
		t3 = useMainThreadFacade;
		t4 = bodies.get({ index: mainIndex });
		$[8] = bodies;
		$[9] = bodyIndexOf;
		$[10] = mainThreadId;
		$[11] = t3;
		$[12] = t4;
		$[13] = t5;
	} else {
		t3 = $[11];
		t4 = $[12];
		t5 = $[13];
	}
	const mainThreadClient = {
		state: t5,
		methods: t3(t4)
	};
	let t6;
	if ($[14] !== listState || $[15] !== mainThreadId) {
		t6 = collectItemOrder(listState, mainThreadId);
		$[14] = listState;
		$[15] = mainThreadId;
		$[16] = t6;
	} else t6 = $[16];
	const itemOrder = t6;
	const threadListItems = useClientLookup(itemOrder.map((data_2) => withKey(data_2.id, itemElementFor(data_2, backgroundThreads ? bodyStateOf(data_2.id)?.isRunning ?? false : itemMatchesId(data_2, listState, mainThreadId) && mainThreadClient.state.isRunning, true))));
	let t7;
	if ($[17] !== itemOrder || $[18] !== mainThreadClient || $[19] !== threadListItems) {
		t7 = {
			mainThreadClient,
			itemOrder,
			threadListItems
		};
		$[17] = itemOrder;
		$[18] = mainThreadClient;
		$[19] = threadListItems;
		$[20] = t7;
	} else t7 = $[20];
	return t7;
};
const useRemoteThreadList = (props) => {
	const { adapter, thread: threadFactory, threadId, onThreadIdChange, onSwitchToThread, onSwitchToNewThread, onDelete } = props;
	const [{ store, initialMainId, session }] = useState(() => {
		const seeded = seedNewThread(EMPTY_LIST);
		return {
			store: new OptimisticState(seeded.state),
			initialMainId: seeded.id,
			session: {
				adapter,
				adapterAtLoad: adapter,
				adapterGeneration: 0,
				titleStates: /* @__PURE__ */ new Map(),
				loadGeneration: 0,
				switchGeneration: 0,
				loadPromise: void 0,
				loadMorePromise: void 0,
				lastNotifiedRemoteId: void 0,
				lastControlledThreadId: void 0,
				switchTask: void 0,
				mainThreadId: seeded.id,
				isFirstThreadIdEffect: true,
				onThreadIdChange,
				onSwitchToThread,
				onSwitchToNewThread
			}
		};
	});
	const listState = useSyncExternalStore((onStoreChange) => store.subscribe(onStoreChange), () => store.value, () => store.value);
	const getListState = useCallback(() => store.value, [store]);
	const afterStateCommit = useAfterStateCommit(listState, getListState);
	const [mainThreadId, setMainThreadId] = useState(initialMainId);
	const [startedIds, setStartedIds] = useState([initialMainId]);
	const [backgroundThreads] = useState(props.backgroundThreads === true);
	const assignMainThreadId = useCallback((id) => {
		session.mainThreadId = id;
		setMainThreadId(id);
		setStartedIds((prev) => prev.includes(id) ? prev : [...prev, id]);
	}, [session]);
	useThreadSelectionEvents(mainThreadId);
	useEffect(() => {
		session.adapter = adapter;
		session.mainThreadId = mainThreadId;
		session.onThreadIdChange = onThreadIdChange;
		session.onSwitchToThread = onSwitchToThread;
		session.onSwitchToNewThread = onSwitchToNewThread;
	}, [
		adapter,
		mainThreadId,
		onSwitchToNewThread,
		onSwitchToThread,
		onThreadIdChange,
		session
	]);
	const notifyRemoteId = useCallback((remoteId, emit) => {
		if (session.lastNotifiedRemoteId === remoteId) return;
		session.lastNotifiedRemoteId = remoteId;
		if (emit) invokeUserCallback("assistant-ui", "onThreadIdChange", session.onThreadIdChange, remoteId);
	}, [session]);
	const getLoadThreadsPromise = useCallback(() => {
		if (session.loadPromise) return session.loadPromise;
		const generation = session.loadGeneration;
		const adapter_0 = session.adapter;
		const statusAtRequest = statusSnapshot(store.baseValue);
		session.loadPromise = store.optimisticUpdate({
			execute: () => adapter_0.list(),
			loading: (state) => {
				if (generation !== session.loadGeneration) return state;
				return {
					...state,
					isLoading: true,
					loadError: void 0
				};
			},
			then: (state_0, page) => {
				if (generation !== session.loadGeneration) return state_0;
				session.adapterAtLoad = adapter_0;
				const fresh = classifyThreads(page.threads, {
					threadIds: [],
					archivedThreadIds: [],
					threadIdMap: { ...state_0.threadIdMap },
					threadData: { ...state_0.threadData }
				});
				const merged = {
					...state_0,
					isLoading: false,
					loadError: void 0,
					cursor: normalizeCursor(page.nextCursor),
					threadIds: fresh.threadIds,
					archivedThreadIds: fresh.archivedThreadIds,
					threadIdMap: fresh.threadIdMap,
					threadData: fresh.threadData
				};
				return preserveMidLoadTransitions(merged, state_0, statusAtRequest);
			}
		}).catch((error) => {
			if (generation !== session.loadGeneration) return;
			console.error("[assistant-ui] thread list load failed:", error);
			session.loadPromise = void 0;
			store.update({
				...store.baseValue,
				isLoading: false,
				loadError: error
			});
		}).then(() => {});
		return session.loadPromise;
	}, [session, store]);
	const reload = useCallback(() => {
		const adapterChanged = adapter !== session.adapterAtLoad;
		session.loadGeneration++;
		session.loadPromise = void 0;
		session.loadMorePromise = void 0;
		if (adapterChanged) {
			session.adapterGeneration++;
			session.titleStates.clear();
			session.switchGeneration++;
			session.switchTask = void 0;
			session.adapterAtLoad = adapter;
			const seeded_0 = seedNewThread(EMPTY_LIST);
			store.reset({
				...seeded_0.state,
				isLoading: true
			});
			assignMainThreadId(seeded_0.id);
			setStartedIds([seeded_0.id]);
			notifyRemoteId(void 0, true);
		} else store.update({
			...store.baseValue,
			cursor: void 0
		});
		return getLoadThreadsPromise();
	}, [
		adapter,
		assignMainThreadId,
		getLoadThreadsPromise,
		notifyRemoteId,
		session,
		store
	]);
	useEffect(() => {
		if (typeof window === "undefined" || typeof document === "undefined") return;
		const retryAfterError = () => {
			if (store.value.loadError !== void 0) getLoadThreadsPromise();
		};
		const retryAfterVisible = () => {
			if (document.visibilityState === "visible") retryAfterError();
		};
		window.addEventListener("online", retryAfterError);
		document.addEventListener("visibilitychange", retryAfterVisible);
		return () => {
			window.removeEventListener("online", retryAfterError);
			document.removeEventListener("visibilitychange", retryAfterVisible);
		};
	}, [getLoadThreadsPromise, store]);
	useEffect(() => {
		getLoadThreadsPromise();
	}, [getLoadThreadsPromise]);
	useEffect(() => {
		if (!isDevelopment) return;
		if (adapter.unstable_useAdapters !== void 0) return;
		if (adapter.unstable_Provider === void 0) return;
		console.warn("[assistant-ui] RemoteThreadList ignores RemoteThreadListAdapter.unstable_Provider. Expose unstable_useAdapters so per-thread history loads on this entry. useRemoteThreadListRuntime still honors unstable_Provider.");
	}, [adapter]);
	const loadMore = useCallback(() => {
		if (session.loadMorePromise) return session.loadMorePromise;
		const snapshot = store.value;
		if (snapshot.cursor === void 0 || snapshot.isLoading) return RESOLVED_PROMISE;
		const generation_0 = session.loadGeneration;
		const cursor = snapshot.cursor;
		const currentAdapter = session.adapter;
		const task = store.optimisticUpdate({
			execute: () => currentAdapter.list({ after: cursor }),
			loading: (state_1) => {
				if (generation_0 !== session.loadGeneration) return state_1;
				return {
					...state_1,
					isLoadingMore: true
				};
			},
			then: (state_2, page_0) => {
				if (generation_0 !== session.loadGeneration) return state_2;
				const appended = classifyThreads(page_0.threads, {
					threadIds: [...state_2.threadIds],
					archivedThreadIds: [...state_2.archivedThreadIds],
					threadIdMap: { ...state_2.threadIdMap },
					threadData: { ...state_2.threadData }
				});
				return {
					...state_2,
					isLoadingMore: false,
					cursor: normalizeCursor(page_0.nextCursor),
					threadIds: appended.threadIds,
					archivedThreadIds: appended.archivedThreadIds,
					threadIdMap: appended.threadIdMap,
					threadData: appended.threadData
				};
			}
		}).catch((error_0) => {
			if (generation_0 !== session.loadGeneration) return;
			console.error("[assistant-ui] thread list loadMore failed:", error_0);
		}).then(() => {
			if (session.loadMorePromise === task) session.loadMorePromise = void 0;
		});
		session.loadMorePromise = task;
		return task;
	}, [session, store]);
	const startSwitch = useCallback((run) => {
		const generation_1 = ++session.switchGeneration;
		let settle;
		const task_0 = new Promise((resolve, reject) => {
			settle = (error_1) => {
				if (error_1 === void 0) resolve();
				else reject(error_1);
			};
		});
		session.switchTask = task_0;
		run(generation_1).then(() => settle(), (error_2) => settle(error_2));
		return task_0;
	}, [session]);
	const switchToThread = useCallback((threadIdOrRemoteId, options, emitThreadIdChange = true) => startSwitch(async (generation_2) => {
		let data = getThreadData(store.value, threadIdOrRemoteId);
		if (!data) {
			const remoteMetadata = await session.adapter.fetch(threadIdOrRemoteId);
			if (generation_2 !== session.switchGeneration) return;
			const state_3 = store.value;
			const mappingId = createThreadMappingId(remoteMetadata.remoteId);
			const wasInTarget = remoteMetadata.status === "regular" ? state_3.threadIds.includes(remoteMetadata.remoteId) : state_3.archivedThreadIds.includes(remoteMetadata.remoteId);
			const threadIdsWithoutRemote = state_3.threadIds.filter((id_0) => id_0 !== remoteMetadata.remoteId);
			const archivedThreadIdsWithoutRemote = state_3.archivedThreadIds.filter((id_1) => id_1 !== remoteMetadata.remoteId);
			store.update({
				...state_3,
				threadIds: remoteMetadata.status === "regular" ? wasInTarget ? state_3.threadIds : [...threadIdsWithoutRemote, remoteMetadata.remoteId] : threadIdsWithoutRemote,
				archivedThreadIds: remoteMetadata.status === "archived" ? wasInTarget ? state_3.archivedThreadIds : [...archivedThreadIdsWithoutRemote, remoteMetadata.remoteId] : archivedThreadIdsWithoutRemote,
				threadIdMap: {
					...state_3.threadIdMap,
					[remoteMetadata.remoteId]: mappingId
				},
				threadData: {
					...state_3.threadData,
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
				}
			});
			data = getThreadData(store.value, threadIdOrRemoteId);
		}
		if (!data) throw threadNotFoundError(threadIdOrRemoteId, "switching to it");
		if (isSameThread(store.value, data.id, session.mainThreadId)) return;
		const targetId = data.id;
		let current = data;
		if (current.status === "archived" && options?.unarchive !== false) {
			const { remoteId: remoteId_0 } = await current.initializeTask;
			if (generation_2 !== session.switchGeneration) return;
			current = getThreadData(store.value, targetId);
			if (current?.id !== targetId) return;
			if (current.status === "archived") {
				await store.optimisticUpdate({
					execute: () => session.adapter.unarchive(remoteId_0),
					optimistic: (state_4) => updateStatusReducer(state_4, targetId, "regular")
				});
				if (generation_2 !== session.switchGeneration) return;
				current = getThreadData(store.value, targetId);
				if (current?.id !== targetId) return;
			}
		}
		if (generation_2 !== session.switchGeneration) return;
		assignMainThreadId(current.id);
		notifyRemoteId(current.remoteId, emitThreadIdChange);
		session.onSwitchToThread?.(current.id);
	}), [
		assignMainThreadId,
		notifyRemoteId,
		session,
		startSwitch,
		store
	]);
	const switchToNewThread = useCallback((emitThreadIdChange_0 = true) => startSwitch(async (generation_3) => {
		while (store.baseValue.newThreadId !== void 0 && store.value.newThreadId === void 0) {
			await store.waitForUpdate();
			if (generation_3 !== session.switchGeneration) return;
		}
		const existing = store.value.newThreadId;
		if (existing !== void 0) {
			const existingId = getThreadData(store.value, existing)?.id ?? existing;
			if (isSameThread(store.value, existingId, session.mainThreadId)) return;
			assignMainThreadId(existingId);
			notifyRemoteId(void 0, emitThreadIdChange_0);
			session.onSwitchToNewThread?.();
			return;
		}
		const seeded_1 = seedNewThread(store.baseValue);
		store.update(seeded_1.state);
		if (generation_3 !== session.switchGeneration) return;
		assignMainThreadId(seeded_1.id);
		notifyRemoteId(void 0, emitThreadIdChange_0);
		session.onSwitchToNewThread?.();
	}), [
		assignMainThreadId,
		notifyRemoteId,
		session,
		startSwitch,
		store
	]);
	const ensureNotMain = useCallback(async (threadId_0) => {
		if (threadId_0 === store.value.newThreadId) throw new Error("Cannot ensure new thread is not main");
		let lastAwaitedTask;
		while (isSameThread(store.value, threadId_0, session.mainThreadId)) {
			if (threadId_0 === store.value.newThreadId) throw new Error("Cannot ensure new thread is not main");
			let switchTask = session.switchTask;
			const startedFallback = !switchTask || switchTask === lastAwaitedTask;
			if (startedFallback) switchTask = switchToNewThread();
			lastAwaitedTask = switchTask;
			try {
				await switchTask;
			} catch (error_3) {
				if (startedFallback && session.switchTask === switchTask) throw error_3;
			}
		}
	}, [
		session,
		store,
		switchToNewThread
	]);
	const requireAdapterGeneration = useCallback((generation_4) => {
		if (generation_4 !== session.adapterGeneration) throw new ThreadListAdapterChangedError();
	}, [session]);
	const initialize = useCallback(async (threadId_1) => {
		const currentAdapter_0 = session.adapter;
		const adapterGeneration = session.adapterGeneration;
		if (store.value.newThreadId !== threadId_1) {
			const data_0 = getThreadData(store.value, threadId_1);
			if (!data_0) throw threadNotFoundError(threadId_1, "initializing it");
			if (data_0.status === "new") throw threadStatusError(threadId_1, data_0.status, "be initialized here");
			const result = toInitializeResult(await data_0.initializeTask);
			requireAdapterGeneration(adapterGeneration);
			return result;
		}
		requireAdapterGeneration(adapterGeneration);
		const initializeTask = currentAdapter_0.initialize(threadId_1);
		let removedMappingId;
		let replacementMainThreadId;
		const result_0 = await store.optimisticUpdate({
			execute: () => initializeTask,
			optimistic: (state_5) => promoteNewThreadReducer(state_5, threadId_1, initializeTask),
			then: (state_6, { remoteId: remoteId_1, externalId }) => {
				if (adapterGeneration !== session.adapterGeneration) return state_6;
				const retainedThreadId = backgroundThreads ? threadId_1 : session.mainThreadId;
				const reconciliation = reconcileInitializedThread(state_6, threadId_1, remoteId_1, externalId, retainedThreadId);
				removedMappingId = reconciliation.removedMappingId;
				if (removedMappingId === session.mainThreadId) replacementMainThreadId = reconciliation.survivorMappingId;
				return reconciliation.state;
			}
		});
		requireAdapterGeneration(adapterGeneration);
		if (removedMappingId !== void 0) setStartedIds((prev_0) => prev_0.filter((startedId) => startedId !== removedMappingId));
		if (replacementMainThreadId !== void 0 && session.mainThreadId === removedMappingId) assignMainThreadId(replacementMainThreadId);
		if (threadId_1 === session.mainThreadId) notifyRemoteId(result_0.remoteId, true);
		return toInitializeResult(result_0);
	}, [
		assignMainThreadId,
		backgroundThreads,
		notifyRemoteId,
		requireAdapterGeneration,
		session,
		store
	]);
	const rename = useCallback((threadIdOrRemoteId_0, newTitle) => {
		const currentAdapter_1 = session.adapter;
		const adapterGeneration_0 = session.adapterGeneration;
		const data_1 = getThreadData(store.value, threadIdOrRemoteId_0);
		if (!data_1) throw threadNotFoundError(threadIdOrRemoteId_0, "renaming it");
		if (data_1.status === "new") throw threadStatusError(threadIdOrRemoteId_0, data_1.status, "be renamed");
		const claim = startThreadTitleRename(session.titleStates, data_1.id, newTitle);
		return store.optimisticUpdate({
			execute: async () => {
				const { remoteId: remoteId_2 } = await data_1.initializeTask;
				requireAdapterGeneration(adapterGeneration_0);
				return currentAdapter_1.rename(remoteId_2, newTitle);
			},
			optimistic: (state_7) => {
				const current_0 = getThreadData(state_7, threadIdOrRemoteId_0);
				if (!current_0) return state_7;
				return {
					...state_7,
					threadData: {
						...state_7.threadData,
						[current_0.id]: {
							...current_0,
							title: newTitle
						}
					}
				};
			}
		}).then((result_1) => {
			finishThreadTitleRename(session.titleStates, data_1.id, claim, true);
			return result_1;
		}, (error_4) => {
			finishThreadTitleRename(session.titleStates, data_1.id, claim, false);
			throw error_4;
		});
	}, [
		requireAdapterGeneration,
		session,
		store
	]);
	const updateCustom = useCallback((threadIdOrRemoteId_1, custom) => {
		const currentAdapter_2 = session.adapter;
		const adapterGeneration_1 = session.adapterGeneration;
		const data_2 = getThreadData(store.value, threadIdOrRemoteId_1);
		if (!data_2) throw threadNotFoundError(threadIdOrRemoteId_1, "updating its custom metadata");
		if (data_2.status === "new") throw threadStatusError(threadIdOrRemoteId_1, data_2.status, "update custom metadata");
		if (!currentAdapter_2.updateCustom) throw new Error("Remote thread list adapter does not support updating custom metadata");
		return store.optimisticUpdate({
			execute: async () => {
				const { remoteId: remoteId_3 } = await data_2.initializeTask;
				requireAdapterGeneration(adapterGeneration_1);
				if (!currentAdapter_2.updateCustom) throw new Error("Remote thread list adapter does not support updating custom metadata");
				return currentAdapter_2.updateCustom(remoteId_3, custom);
			},
			optimistic: (state_8) => {
				const current_1 = getThreadData(state_8, threadIdOrRemoteId_1);
				if (!current_1) return state_8;
				return {
					...state_8,
					threadData: {
						...state_8.threadData,
						[current_1.id]: {
							...current_1,
							custom
						}
					}
				};
			}
		});
	}, [
		requireAdapterGeneration,
		session,
		store
	]);
	const archive = useCallback(async (threadIdOrRemoteId_2) => {
		const currentAdapter_3 = session.adapter;
		const adapterGeneration_2 = session.adapterGeneration;
		const data_3 = getThreadData(store.value, threadIdOrRemoteId_2);
		if (!data_3) throw threadNotFoundError(threadIdOrRemoteId_2, "archiving it");
		if (data_3.status !== "regular") throw threadStatusError(threadIdOrRemoteId_2, data_3.status, "be archived");
		await ensureNotMain(data_3.id);
		requireAdapterGeneration(adapterGeneration_2);
		return store.optimisticUpdate({
			execute: async () => {
				const { remoteId: remoteId_4 } = await data_3.initializeTask;
				requireAdapterGeneration(adapterGeneration_2);
				return currentAdapter_3.archive(remoteId_4);
			},
			optimistic: (state_9) => updateStatusReducer(state_9, data_3.id, "archived")
		});
	}, [
		ensureNotMain,
		requireAdapterGeneration,
		session,
		store
	]);
	const unarchive = useCallback((threadIdOrRemoteId_3) => {
		const currentAdapter_4 = session.adapter;
		const adapterGeneration_3 = session.adapterGeneration;
		const data_4 = getThreadData(store.value, threadIdOrRemoteId_3);
		if (!data_4) throw threadNotFoundError(threadIdOrRemoteId_3, "unarchiving it");
		if (data_4.status !== "archived") throw threadStatusError(threadIdOrRemoteId_3, data_4.status, "be unarchived");
		return store.optimisticUpdate({
			execute: async () => {
				try {
					const { remoteId: remoteId_5 } = await data_4.initializeTask;
					requireAdapterGeneration(adapterGeneration_3);
					return await currentAdapter_4.unarchive(remoteId_5);
				} catch (error_5) {
					if (adapterGeneration_3 === session.adapterGeneration) await ensureNotMain(data_4.id);
					throw error_5;
				}
			},
			optimistic: (state_10) => updateStatusReducer(state_10, data_4.id, "regular")
		});
	}, [
		ensureNotMain,
		requireAdapterGeneration,
		session,
		store
	]);
	const deleteThread = useCallback(async (threadIdOrRemoteId_4) => {
		const currentAdapter_5 = session.adapter;
		const adapterGeneration_4 = session.adapterGeneration;
		const data_5 = getThreadData(store.value, threadIdOrRemoteId_4);
		if (!data_5) throw threadNotFoundError(threadIdOrRemoteId_4, "deleting it");
		if (data_5.status !== "regular" && data_5.status !== "archived") throw threadStatusError(threadIdOrRemoteId_4, data_5.status, "be deleted");
		await ensureNotMain(data_5.id);
		requireAdapterGeneration(adapterGeneration_4);
		const result_2 = await store.optimisticUpdate({
			execute: async () => {
				const { remoteId: remoteId_6 } = await data_5.initializeTask;
				requireAdapterGeneration(adapterGeneration_4);
				return currentAdapter_5.delete(remoteId_6);
			},
			optimistic: (state_11) => updateStatusReducer(state_11, data_5.id, "deleted")
		});
		if (getThreadData(store.value, data_5.id) !== void 0) return result_2;
		clearThreadTitleState(session.titleStates, data_5.id);
		onDelete?.(data_5.id);
		return result_2;
	}, [
		ensureNotMain,
		onDelete,
		requireAdapterGeneration,
		session,
		store
	]);
	const generateTitle = useCallback(async (threadIdOrRemoteId_5, messages, options_0) => {
		const currentAdapter_6 = session.adapter;
		const adapterGeneration_5 = session.adapterGeneration;
		const data_6 = getThreadData(store.value, threadIdOrRemoteId_5);
		if (!data_6) throw threadNotFoundError(threadIdOrRemoteId_5, "generating its title");
		if (data_6.status === "new") throw threadStatusError(threadIdOrRemoteId_5, data_6.status, "generate a title");
		const { remoteId: remoteId_7 } = await data_6.initializeTask;
		requireAdapterGeneration(adapterGeneration_5);
		if (!backgroundThreads && !isSameThread(store.value, data_6.id, session.mainThreadId)) return;
		if (!messages) return;
		await runThreadTitleGeneration({
			states: session.titleStates,
			threadId: data_6.id,
			automatic: options_0?.automatic === true,
			generate: async (onTitle) => {
				const stream = await currentAdapter_6.generateTitle(remoteId_7, messages);
				requireAdapterGeneration(adapterGeneration_5);
				await applyTitleStream(stream, onTitle);
			},
			rename: async (title) => {
				requireAdapterGeneration(adapterGeneration_5);
				await currentAdapter_6.rename(remoteId_7, title);
			},
			applyTitle: async (title_0) => {
				await store.optimisticUpdate({
					execute: async () => {},
					optimistic: (state_12) => {
						if (adapterGeneration_5 !== session.adapterGeneration) return state_12;
						const current_2 = getThreadData(state_12, data_6.id);
						if (!current_2) return state_12;
						return {
							...state_12,
							threadData: {
								...state_12.threadData,
								[current_2.id]: {
									...current_2,
									title: title_0
								}
							}
						};
					}
				});
			}
		});
	}, [
		backgroundThreads,
		requireAdapterGeneration,
		session,
		store
	]);
	const detach = useCallback(async (threadId_2) => {
		await ensureNotMain(threadId_2);
		setStartedIds((prev_1) => prev_1.filter((id_2) => id_2 !== threadId_2));
	}, [ensureNotMain]);
	const { mainThreadClient, itemOrder, threadListItems } = useRemoteThreadListView({
		listState,
		mainThreadId,
		initialMainId,
		startedIds,
		backgroundThreads,
		threadFactory,
		useAdapters: adapter.unstable_useAdapters,
		onSwitchTo: (id_3, options_1) => switchToThread(id_3, options_1),
		onRename: (id_4, title_1) => rename(id_4, title_1),
		onUpdateCustom: (id_5, custom_0) => updateCustom(id_5, custom_0),
		onArchive: (id_6) => archive(id_6),
		onUnarchive: (id_7) => unarchive(id_7),
		onDelete: (id_8) => deleteThread(id_8),
		onGenerateTitle: (id_9, messages_0, options_2) => generateTitle(id_9, messages_0, options_2),
		onInitialize: async (id_10) => toInitializeResult(await initialize(id_10)),
		onDetach: (id_11) => detach(id_11)
	});
	const mainRemoteId = getThreadData(listState, mainThreadId)?.remoteId;
	useEffect(() => {
		if (session.lastNotifiedRemoteId === mainRemoteId) return;
		session.lastNotifiedRemoteId = mainRemoteId;
		invokeUserCallback("assistant-ui", "onThreadIdChange", onThreadIdChange, mainRemoteId);
	}, [
		mainRemoteId,
		onThreadIdChange,
		session
	]);
	useEffect(() => {
		if (session.isFirstThreadIdEffect) {
			session.isFirstThreadIdEffect = false;
			session.lastControlledThreadId = threadId;
			if (threadId === void 0) return;
			handleThreadListAction("switch", () => switchToThread(threadId, void 0, false));
			return;
		}
		if (Object.is(session.lastControlledThreadId, threadId)) return;
		session.lastControlledThreadId = threadId;
		if (threadId === void 0) {
			handleThreadListAction("create", () => switchToNewThread(false));
			return;
		}
		handleThreadListAction("switch", () => switchToThread(threadId, void 0, false));
	}, [
		session,
		switchToNewThread,
		switchToThread,
		threadId
	]);
	const state_13 = useMemo(() => ({
		mainThreadId,
		newThreadId: listState.newThreadId ?? null,
		isLoading: listState.isLoading,
		loadError: listState.loadError,
		isLoadingMore: listState.isLoadingMore,
		hasMore: listState.cursor !== void 0,
		threadIds: listState.threadIds,
		archivedThreadIds: listState.archivedThreadIds,
		threadItems: threadListItems.state,
		main: mainThreadClient.state
	}), [
		listState.archivedThreadIds,
		listState.cursor,
		listState.isLoading,
		listState.loadError,
		listState.isLoadingMore,
		listState.newThreadId,
		listState.threadIds,
		mainThreadClient.state,
		mainThreadId,
		threadListItems.state
	]);
	return {
		getState: () => state_13,
		switchToThread: (id_12, options_3) => {
			handleThreadListAction("switch", () => switchToThread(id_12, options_3));
		},
		switchToNewThread: () => {
			handleThreadListAction("create", () => switchToNewThread());
		},
		getLoadThreadsPromise: () => afterStateCommit(getLoadThreadsPromise()),
		reload: () => afterStateCommit(reload()),
		reloadMainThread: () => {
			if (getThreadData(store.value, mainThreadId)?.status === "new") return RESOLVED_PROMISE;
			return mainThreadClient.methods.unstable_refetchThread?.() ?? RESOLVED_PROMISE;
		},
		loadMore: () => afterStateCommit(loadMore()),
		item: (selector) => {
			if (selector === "main") {
				const index = itemOrder.findIndex((item) => itemMatchesId(item, listState, mainThreadId));
				return threadListItems.get({ index });
			}
			if ("id" in selector) {
				const index_0 = itemOrder.findIndex((item_0) => itemMatchesId(item_0, listState, selector.id));
				return threadListItems.get({ index: index_0 });
			}
			const id_13 = (selector.archived ? listState.archivedThreadIds : listState.threadIds)[selector.index];
			if (id_13 === void 0) return threadListItems.get({ index: -1 });
			const index_1 = itemOrder.findIndex((item_1) => itemMatchesId(item_1, listState, id_13));
			return threadListItems.get({ index: index_1 });
		},
		thread: () => mainThreadClient.methods
	};
};
/**
* `AuiConfig` `threads` entry backed by a `RemoteThreadListAdapter`. Thread
* bodies are born from the `thread` factory inside the client tree, so any
* `AssistantClient` host can run a remote or cloud list. Per-thread history
* and attachments come from `unstable_useAdapters`. `useRemoteThreadListRuntime`
* uses the same hook when `unstable_Provider` is omitted. Key the factory
* with `withKey` so history reloads when the visible thread changes.
* With `backgroundThreads`, every visited thread stays mounted: runs continue
* across switches, per-item `isRunning` is live, and freshly initialized
* threads title themselves.
*/
const RemoteThreadList = resource(useRemoteThreadList);
attachTransformScopes(useRemoteThreadList, inMemoryThreadListTransformScopes);
//#endregion
export { RemoteThreadList };
