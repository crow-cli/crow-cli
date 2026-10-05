import { generateId } from "../../utils/id.js";
import { nullProtoRecord } from "../../utils/record.js";
//#region src/runtimes/remote-thread-list/remote-thread-state.ts
function createThreadMappingId(id) {
	return id;
}
const LOCAL_THREAD_ID_PREFIX = "__LOCALID_";
const normalizeCursor = (c) => c || void 0;
const classifyThreads = (threads, acc) => {
	let threadIds = [...acc.threadIds];
	let archivedThreadIds = [...acc.archivedThreadIds];
	const threadIdMap = nullProtoRecord(acc.threadIdMap);
	const threadData = nullProtoRecord(acc.threadData);
	const listed = /* @__PURE__ */ new Set([...threadIds, ...archivedThreadIds]);
	for (const thread of threads) {
		switch (thread.status) {
			case "regular":
			case "archived": break;
			default: {
				const _exhaustiveCheck = thread.status;
				throw new Error(`Unsupported state: ${_exhaustiveCheck}`);
			}
		}
		const existingMappingId = threadIdMap[thread.remoteId];
		const existing = existingMappingId !== void 0 ? threadData[existingMappingId] : void 0;
		const id = existing?.id ?? thread.remoteId;
		const mappingId = existingMappingId ?? createThreadMappingId(id);
		const existingTask = existing !== void 0 && existing.status !== "new" ? existing.initializeTask : void 0;
		if (!listed.has(id)) {
			listed.add(id);
			if (thread.status === "regular") threadIds.push(id);
			else archivedThreadIds.push(id);
		} else if (existing !== void 0 && existing.status !== thread.status) {
			if (thread.status === "regular") {
				archivedThreadIds = archivedThreadIds.filter((t) => t !== id);
				threadIds.push(id);
			} else {
				threadIds = threadIds.filter((t) => t !== id);
				archivedThreadIds.push(id);
			}
		}
		threadIdMap[id] = mappingId;
		threadIdMap[thread.remoteId] = mappingId;
		threadData[mappingId] = {
			...existing?.localOrigin === true ? { localOrigin: true } : {},
			id,
			remoteId: thread.remoteId,
			externalId: thread.externalId,
			status: thread.status,
			title: thread.title,
			lastMessageAt: thread.lastMessageAt,
			custom: thread.custom,
			initializeTask: existingTask ?? Promise.resolve({
				remoteId: thread.remoteId,
				externalId: thread.externalId
			})
		};
	}
	return {
		threadIds,
		archivedThreadIds,
		threadIdMap,
		threadData
	};
};
const createEmptyRemoteThreadState = () => ({
	isLoading: true,
	loadError: void 0,
	isLoadingMore: false,
	cursor: void 0,
	newThreadId: void 0,
	threadIds: [],
	archivedThreadIds: [],
	threadIdMap: nullProtoRecord(),
	threadData: nullProtoRecord()
});
const seedNewThread = (state, initialThreadIdSeed) => {
	let id = `${LOCAL_THREAD_ID_PREFIX}${initialThreadIdSeed ?? generateId()}`;
	while (state.threadIdMap[id]) id = `${LOCAL_THREAD_ID_PREFIX}${generateId()}`;
	const mappingId = createThreadMappingId(id);
	return {
		id,
		state: {
			...state,
			newThreadId: id,
			threadIdMap: nullProtoRecord(state.threadIdMap, { [id]: mappingId }),
			threadData: nullProtoRecord(state.threadData, { [mappingId]: {
				status: "new",
				id,
				remoteId: void 0,
				externalId: void 0,
				title: void 0,
				custom: void 0,
				localOrigin: true
			} })
		}
	};
};
const preserveMidLoadTransitions = (state, priorOrder, statusAtRequest) => {
	const regular = new Set(state.threadIds);
	const archived = new Set(state.archivedThreadIds);
	const rescuedRegular = [];
	const rescuedArchived = [];
	const contains = (ids, data) => ids.has(data.id) || data.remoteId !== void 0 && ids.has(data.remoteId);
	for (const data of Object.values(state.threadData)) {
		const before = statusAtRequest.get(data.id);
		if (before !== void 0 && before !== "new") continue;
		if (before === void 0 && data.localOrigin !== true) continue;
		if (data.status === "regular" && !contains(regular, data)) {
			rescuedRegular.push(data);
			regular.add(data.id);
		} else if (data.status === "archived" && !contains(archived, data)) {
			rescuedArchived.push(data);
			archived.add(data.id);
		}
	}
	if (rescuedRegular.length === 0 && rescuedArchived.length === 0) return state;
	const position = (ids, data) => {
		const byId = ids.indexOf(data.id);
		if (byId !== -1) return byId;
		const byRemoteId = data.remoteId !== void 0 ? ids.indexOf(data.remoteId) : -1;
		return byRemoteId !== -1 ? byRemoteId : Number.MAX_SAFE_INTEGER;
	};
	rescuedRegular.sort((a, b) => position(priorOrder.threadIds, a) - position(priorOrder.threadIds, b));
	rescuedArchived.sort((a, b) => position(priorOrder.archivedThreadIds, a) - position(priorOrder.archivedThreadIds, b));
	return {
		...state,
		threadIds: [...rescuedRegular.map((d) => d.id), ...state.threadIds],
		archivedThreadIds: [...rescuedArchived.map((d) => d.id), ...state.archivedThreadIds]
	};
};
const statusSnapshot = (state) => new Map(Object.values(state.threadData).map((d) => [d.id, d.status]));
const getThreadData = (state, threadIdOrRemoteId) => {
	const idx = Object.hasOwn(state.threadIdMap, threadIdOrRemoteId) ? state.threadIdMap[threadIdOrRemoteId] : void 0;
	if (idx === void 0) return void 0;
	return Object.hasOwn(state.threadData, idx) ? state.threadData[idx] : void 0;
};
const reconcileInitializedThread = (state, threadId, remoteId, externalId, retainedThreadId) => {
	const mappingId = createThreadMappingId(threadId);
	const data = Object.hasOwn(state.threadData, mappingId) ? state.threadData[mappingId] : void 0;
	if (!data) return {
		state,
		removedMappingId: void 0,
		survivorMappingId: mappingId
	};
	const listedMappingId = Object.hasOwn(state.threadIdMap, remoteId) ? state.threadIdMap[remoteId] : void 0;
	const listedData = listedMappingId !== void 0 && listedMappingId !== mappingId && Object.hasOwn(state.threadData, listedMappingId) ? state.threadData[listedMappingId] : void 0;
	const listedSlot = listedMappingId !== void 0 && listedData !== void 0 ? {
		mappingId: listedMappingId,
		data: listedData
	} : void 0;
	const retainedMappingId = retainedThreadId !== void 0 && Object.hasOwn(state.threadIdMap, retainedThreadId) ? state.threadIdMap[retainedThreadId] : void 0;
	const survivorMappingId = listedSlot !== void 0 && retainedMappingId === listedSlot.mappingId ? listedSlot.mappingId : mappingId;
	const removedMappingId = listedSlot === void 0 ? void 0 : survivorMappingId === mappingId ? listedSlot.mappingId : mappingId;
	const resolvedExternalId = externalId ?? listedSlot?.data.externalId;
	const threadData = nullProtoRecord(state.threadData);
	if (removedMappingId !== void 0) delete threadData[removedMappingId];
	const initializedData = {
		...data,
		id: survivorMappingId,
		initializeTask: Promise.resolve({
			remoteId,
			externalId: resolvedExternalId
		}),
		remoteId,
		externalId: resolvedExternalId
	};
	threadData[survivorMappingId] = {
		...listedSlot?.data,
		...initializedData,
		title: data.title ?? listedSlot?.data.title,
		lastMessageAt: ("lastMessageAt" in data ? data.lastMessageAt : void 0) ?? (listedSlot && "lastMessageAt" in listedSlot.data ? listedSlot.data.lastMessageAt : void 0),
		custom: data.custom ?? listedSlot?.data.custom
	};
	const threadIdMap = nullProtoRecord(state.threadIdMap);
	if (removedMappingId !== void 0) {
		for (const [id, target] of Object.entries(threadIdMap)) if (target === removedMappingId) threadIdMap[id] = survivorMappingId;
	}
	threadIdMap[threadId] = survivorMappingId;
	threadIdMap[remoteId] = survivorMappingId;
	const rewire = (ids) => listedSlot === void 0 ? ids : ids.filter((id) => id !== listedSlot.data.id).map((id) => id === data.id ? survivorMappingId : id);
	return {
		state: {
			...state,
			threadIds: rewire(state.threadIds),
			archivedThreadIds: rewire(state.archivedThreadIds),
			threadIdMap,
			threadData
		},
		removedMappingId,
		survivorMappingId
	};
};
const transitionReducer = (state, threadIdOrRemoteId, newStatus, initializeTask) => {
	const data = getThreadData(state, threadIdOrRemoteId);
	if (!data) return state;
	const { id, status: lastStatus } = data;
	if (lastStatus === newStatus) return state;
	let nextData;
	if (newStatus !== "deleted") {
		if (data.status === "new") {
			if (initializeTask === void 0) return state;
			nextData = {
				...data,
				initializeTask,
				status: newStatus
			};
		} else nextData = {
			...data,
			status: newStatus
		};
	}
	const newState = { ...state };
	switch (lastStatus) {
		case "new":
			newState.newThreadId = void 0;
			break;
		case "regular":
			newState.threadIds = newState.threadIds.filter((t) => t !== id);
			break;
		case "archived":
			newState.archivedThreadIds = newState.archivedThreadIds.filter((t) => t !== id);
			break;
		default: throw new Error(`Unsupported state: ${lastStatus}`);
	}
	switch (newStatus) {
		case "regular":
			newState.threadIds = [id, ...newState.threadIds];
			break;
		case "archived":
			newState.archivedThreadIds = [id, ...newState.archivedThreadIds];
			break;
		case "deleted": {
			const mappingId = state.threadIdMap[threadIdOrRemoteId];
			const threadData = nullProtoRecord(newState.threadData);
			delete threadData[mappingId];
			newState.threadData = threadData;
			const threadIdMap = nullProtoRecord(newState.threadIdMap);
			for (const [key, value] of Object.entries(threadIdMap)) if (value === mappingId) delete threadIdMap[key];
			newState.threadIdMap = threadIdMap;
			break;
		}
		default: throw new Error(`Unsupported state: ${newStatus}`);
	}
	if (nextData !== void 0) newState.threadData = {
		...newState.threadData,
		[id]: nextData
	};
	return newState;
};
/**
* Transitions a thread that already exists remotely. Promoting the local draft
* off `new` needs the initialization promise its destination variant requires,
* so that goes through `promoteNewThreadReducer`; asking for it here leaves the
* state unchanged.
*/
const updateStatusReducer = (state, threadIdOrRemoteId, newStatus) => transitionReducer(state, threadIdOrRemoteId, newStatus, void 0);
/**
* Promotes the local draft to `regular`, carrying the initialization promise
* onto the slot.
*/
const promoteNewThreadReducer = (state, threadIdOrRemoteId, initializeTask) => transitionReducer(state, threadIdOrRemoteId, "regular", initializeTask);
//#endregion
export { LOCAL_THREAD_ID_PREFIX, classifyThreads, createEmptyRemoteThreadState, createThreadMappingId, getThreadData, normalizeCursor, preserveMidLoadTransitions, promoteNewThreadReducer, reconcileInitializedThread, seedNewThread, statusSnapshot, updateStatusReducer };
