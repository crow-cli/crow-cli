import { generateId } from "../../utils/id.js";
import { useThreadListItemSelectionEvents, useThreadSelectionEvents } from "../../store/clients/thread-selection-events.js";
import { ModelContext } from "../../store/clients/model-context-client.js";
import { DataRenderers } from "./DataRenderers.js";
import { Tools } from "./Tools.js";
import { Derived, attachTransformScopes, useClientLookup, useClientResource, useDestroySignalProvider } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useState } from "@assistant-ui/tap/react-shim";
import { resource, withKey } from "@assistant-ui/tap";
import { useAssistantClientDestroySignal } from "@assistant-ui/store/internal";
//#region src/react/client/InMemoryThreadList.ts
const RESOLVED_PROMISE = Promise.resolve();
const useThreadListItemClient = (props) => {
	const $ = c(19);
	const { data, isMain, isInitialMain, isRunning, onSwitchTo, onRename, onUpdateCustom, onArchive, onUnarchive, onDelete } = props;
	let t0;
	if ($[0] !== data.custom || $[1] !== data.id || $[2] !== data.status || $[3] !== data.title || $[4] !== isRunning) {
		t0 = {
			id: data.id,
			remoteId: void 0,
			externalId: void 0,
			title: data.title,
			status: data.status,
			custom: data.custom,
			isRunning
		};
		$[0] = data.custom;
		$[1] = data.id;
		$[2] = data.status;
		$[3] = data.title;
		$[4] = isRunning;
		$[5] = t0;
	} else t0 = $[5];
	const state = t0;
	useThreadListItemSelectionEvents(data.id, isMain, isInitialMain);
	let t1;
	if ($[6] !== state) {
		t1 = () => state;
		$[6] = state;
		$[7] = t1;
	} else t1 = $[7];
	let t2;
	if ($[8] !== data.id) {
		t2 = async () => ({
			remoteId: data.id,
			externalId: void 0
		});
		$[8] = data.id;
		$[9] = t2;
	} else t2 = $[9];
	let t3;
	if ($[10] !== onArchive || $[11] !== onDelete || $[12] !== onRename || $[13] !== onSwitchTo || $[14] !== onUnarchive || $[15] !== onUpdateCustom || $[16] !== t1 || $[17] !== t2) {
		t3 = {
			getState: t1,
			switchTo: onSwitchTo,
			rename: onRename,
			updateCustom: onUpdateCustom,
			archive: onArchive,
			unarchive: onUnarchive,
			delete: onDelete,
			generateTitle: _temp,
			initialize: t2,
			detach: _temp2
		};
		$[10] = onArchive;
		$[11] = onDelete;
		$[12] = onRename;
		$[13] = onSwitchTo;
		$[14] = onUnarchive;
		$[15] = onUpdateCustom;
		$[16] = t1;
		$[17] = t2;
		$[18] = t3;
	} else t3 = $[18];
	return t3;
};
const ThreadListItemClient = resource(useThreadListItemClient);
const createThreadLifetimes = () => {
	const controllers = /* @__PURE__ */ new Map();
	let owner;
	let unlinkOwner;
	const abortAll = () => {
		unlinkOwner?.();
		unlinkOwner = void 0;
		for (const controller of controllers.values()) controller.abort(owner?.reason);
	};
	return {
		signalFor(threadId, ownerSignal) {
			let controller = controllers.get(threadId);
			if (!controller) {
				controller = new AbortController();
				if (ownerSignal?.aborted) controller.abort(ownerSignal.reason);
				controllers.set(threadId, controller);
			}
			return controller.signal;
		},
		release(threadId) {
			controllers.get(threadId)?.abort();
			controllers.delete(threadId);
		},
		bindOwner(signal) {
			if (owner === signal) return;
			unlinkOwner?.();
			unlinkOwner = void 0;
			owner = signal;
			if (!signal) return;
			if (signal.aborted) {
				abortAll();
				return;
			}
			signal.addEventListener("abort", abortAll);
			unlinkOwner = () => signal.removeEventListener("abort", abortAll);
		}
	};
};
const useOwnedThread = ({ destroySignal, thread }) => useDestroySignalProvider(destroySignal, function useSelectedThread() {
	return useClientResource(thread).methods;
});
const OwnedThread = resource(useOwnedThread);
const INITIAL_THREAD_ID = "main";
const useInMemoryThreadList = (props) => {
	const $ = c(71);
	const { thread: threadFactory, onSwitchToThread, onSwitchToNewThread, onDelete } = props;
	const ownerDestroySignal = useAssistantClientDestroySignal();
	const [lifetimes] = useState(createThreadLifetimes);
	let t0;
	let t1;
	if ($[0] !== lifetimes || $[1] !== ownerDestroySignal) {
		t0 = () => {
			lifetimes.bindOwner(ownerDestroySignal);
		};
		t1 = [lifetimes, ownerDestroySignal];
		$[0] = lifetimes;
		$[1] = ownerDestroySignal;
		$[2] = t0;
		$[3] = t1;
	} else {
		t0 = $[2];
		t1 = $[3];
	}
	useEffect(t0, t1);
	const [t2, setListState] = useState(_temp3);
	const { threads, mainThreadId } = t2;
	let t3;
	if ($[4] === Symbol.for("react.memo_cache_sentinel")) {
		t3 = (update) => setListState((prev) => ({
			...prev,
			threads: update(prev.threads)
		}));
		$[4] = t3;
	} else t3 = $[4];
	const setThreads = t3;
	useThreadSelectionEvents(mainThreadId);
	let t4;
	if ($[5] !== onSwitchToThread) {
		t4 = (threadId) => {
			setListState((prev_0) => ({
				...prev_0,
				mainThreadId: threadId
			}));
			onSwitchToThread?.(threadId);
		};
		$[5] = onSwitchToThread;
		$[6] = t4;
	} else t4 = $[6];
	const handleSwitchToThread = t4;
	let t5;
	if ($[7] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = (threadId_0, title) => {
			setThreads((prev_1) => prev_1.map((t) => t.id === threadId_0 ? {
				...t,
				title
			} : t));
		};
		$[7] = t5;
	} else t5 = $[7];
	const handleRename = t5;
	let t6;
	if ($[8] === Symbol.for("react.memo_cache_sentinel")) {
		t6 = (threadId_1) => {
			setThreads((prev_2) => prev_2.map((t_0) => t_0.id === threadId_1 ? {
				...t_0,
				status: "archived"
			} : t_0));
		};
		$[8] = t6;
	} else t6 = $[8];
	const handleArchive = t6;
	let t7;
	if ($[9] === Symbol.for("react.memo_cache_sentinel")) {
		t7 = (threadId_2) => {
			setThreads((prev_3) => prev_3.map((t_1) => t_1.id === threadId_2 ? {
				...t_1,
				status: "regular"
			} : t_1));
		};
		$[9] = t7;
	} else t7 = $[9];
	const handleUnarchive = t7;
	let t8;
	if ($[10] === Symbol.for("react.memo_cache_sentinel")) {
		t8 = (threadId_3, custom) => {
			setThreads((prev_4) => prev_4.map((t_2) => t_2.id === threadId_3 ? {
				...t_2,
				custom
			} : t_2));
		};
		$[10] = t8;
	} else t8 = $[10];
	const handleUpdateCustom = t8;
	let t9;
	if ($[11] !== lifetimes || $[12] !== onDelete) {
		t9 = (threadId_4) => {
			lifetimes.release(threadId_4);
			const fallbackId = `thread-${generateId()}`;
			setListState((prev_5) => {
				const remaining = prev_5.threads.filter((t_3) => t_3.id !== threadId_4);
				if (remaining.length === 0) return {
					threads: [{
						id: fallbackId,
						title: "New Thread",
						status: "regular"
					}],
					mainThreadId: fallbackId
				};
				return {
					threads: remaining,
					mainThreadId: prev_5.mainThreadId === threadId_4 ? (remaining.find(_temp4) ?? remaining[0]).id : prev_5.mainThreadId
				};
			});
			onDelete?.(threadId_4);
		};
		$[11] = lifetimes;
		$[12] = onDelete;
		$[13] = t9;
	} else t9 = $[13];
	const handleDelete = t9;
	let t10;
	if ($[14] !== onSwitchToNewThread) {
		t10 = () => {
			const newId = `thread-${generateId()}`;
			setListState((prev_6) => ({
				threads: [...prev_6.threads, {
					id: newId,
					title: "New Thread",
					status: "regular"
				}],
				mainThreadId: newId
			}));
			onSwitchToNewThread?.();
		};
		$[14] = onSwitchToNewThread;
		$[15] = t10;
	} else t10 = $[15];
	const handleSwitchToNewThread = t10;
	let t11;
	if ($[16] !== lifetimes || $[17] !== mainThreadId || $[18] !== ownerDestroySignal || $[19] !== threadFactory) {
		t11 = withKey(mainThreadId, OwnedThread({
			destroySignal: lifetimes.signalFor(mainThreadId, ownerDestroySignal),
			thread: threadFactory(mainThreadId)
		}));
		$[16] = lifetimes;
		$[17] = mainThreadId;
		$[18] = ownerDestroySignal;
		$[19] = threadFactory;
		$[20] = t11;
	} else t11 = $[20];
	const mainThreadClient = useClientResource(t11);
	let t12;
	if ($[21] !== handleDelete || $[22] !== handleSwitchToThread || $[23] !== mainThreadClient.state || $[24] !== mainThreadId || $[25] !== threads) {
		let t13;
		if ($[27] !== handleDelete || $[28] !== handleSwitchToThread || $[29] !== mainThreadClient.state || $[30] !== mainThreadId) {
			t13 = (t_5) => withKey(t_5.id, ThreadListItemClient({
				data: t_5,
				isMain: t_5.id === mainThreadId,
				isInitialMain: t_5.id === INITIAL_THREAD_ID,
				isRunning: t_5.id === mainThreadId && mainThreadClient.state.isRunning,
				onSwitchTo: () => handleSwitchToThread(t_5.id),
				onRename: (title_0) => handleRename(t_5.id, title_0),
				onUpdateCustom: (custom_0) => handleUpdateCustom(t_5.id, custom_0),
				onArchive: () => handleArchive(t_5.id),
				onUnarchive: () => handleUnarchive(t_5.id),
				onDelete: () => handleDelete(t_5.id)
			}));
			$[27] = handleDelete;
			$[28] = handleSwitchToThread;
			$[29] = mainThreadClient.state;
			$[30] = mainThreadId;
			$[31] = t13;
		} else t13 = $[31];
		t12 = threads.map(t13);
		$[21] = handleDelete;
		$[22] = handleSwitchToThread;
		$[23] = mainThreadClient.state;
		$[24] = mainThreadId;
		$[25] = threads;
		$[26] = t12;
	} else t12 = $[26];
	const threadListItems = useClientLookup(t12);
	let t13;
	let t14;
	let t15;
	let t16;
	let t17;
	let t18;
	let t19;
	let t20;
	if ($[32] !== mainThreadId || $[33] !== threads) {
		const regularThreads = threads.filter(_temp5);
		const archivedThreads = threads.filter(_temp6);
		t13 = mainThreadId;
		t14 = null;
		t15 = false;
		t16 = void 0;
		t17 = false;
		t18 = false;
		t19 = regularThreads.map(_temp7);
		t20 = archivedThreads.map(_temp8);
		$[32] = mainThreadId;
		$[33] = threads;
		$[34] = t13;
		$[35] = t14;
		$[36] = t15;
		$[37] = t16;
		$[38] = t17;
		$[39] = t18;
		$[40] = t19;
		$[41] = t20;
	} else {
		t13 = $[34];
		t14 = $[35];
		t15 = $[36];
		t16 = $[37];
		t17 = $[38];
		t18 = $[39];
		t19 = $[40];
		t20 = $[41];
	}
	let t21;
	if ($[42] !== mainThreadClient.state || $[43] !== t13 || $[44] !== t14 || $[45] !== t15 || $[46] !== t16 || $[47] !== t17 || $[48] !== t18 || $[49] !== t19 || $[50] !== t20 || $[51] !== threadListItems.state) {
		t21 = {
			mainThreadId: t13,
			newThreadId: t14,
			isLoading: t15,
			loadError: t16,
			isLoadingMore: t17,
			hasMore: t18,
			threadIds: t19,
			archivedThreadIds: t20,
			threadItems: threadListItems.state,
			main: mainThreadClient.state
		};
		$[42] = mainThreadClient.state;
		$[43] = t13;
		$[44] = t14;
		$[45] = t15;
		$[46] = t16;
		$[47] = t17;
		$[48] = t18;
		$[49] = t19;
		$[50] = t20;
		$[51] = threadListItems.state;
		$[52] = t21;
	} else t21 = $[52];
	const state = t21;
	let t22;
	if ($[53] !== state) {
		t22 = () => state;
		$[53] = state;
		$[54] = t22;
	} else t22 = $[54];
	let t23;
	if ($[55] !== mainThreadClient.methods) {
		t23 = () => mainThreadClient.methods.unstable_refetchThread?.() ?? RESOLVED_PROMISE;
		$[55] = mainThreadClient.methods;
		$[56] = t23;
	} else t23 = $[56];
	let t24;
	if ($[57] !== mainThreadId || $[58] !== state || $[59] !== threadListItems || $[60] !== threads) {
		t24 = (selector) => {
			if (selector === "main") {
				const index = threads.findIndex((t_10) => t_10.id === mainThreadId);
				return threadListItems.get({ index: index === -1 ? 0 : index });
			}
			if ("id" in selector) {
				const index_0 = threads.findIndex((t_11) => t_11.id === selector.id);
				return threadListItems.get({ index: index_0 });
			}
			const id = (selector.archived ? state.archivedThreadIds : state.threadIds)[selector.index];
			if (id === void 0) return threadListItems.get({ index: -1 });
			const index_1 = threads.findIndex((t_12) => t_12.id === id);
			return threadListItems.get({ index: index_1 });
		};
		$[57] = mainThreadId;
		$[58] = state;
		$[59] = threadListItems;
		$[60] = threads;
		$[61] = t24;
	} else t24 = $[61];
	let t25;
	if ($[62] !== mainThreadClient.methods) {
		t25 = () => mainThreadClient.methods;
		$[62] = mainThreadClient.methods;
		$[63] = t25;
	} else t25 = $[63];
	let t26;
	if ($[64] !== handleSwitchToNewThread || $[65] !== handleSwitchToThread || $[66] !== t22 || $[67] !== t23 || $[68] !== t24 || $[69] !== t25) {
		t26 = {
			getState: t22,
			switchToThread: handleSwitchToThread,
			switchToNewThread: handleSwitchToNewThread,
			getLoadThreadsPromise: _temp9,
			reload: _temp0,
			reloadMainThread: t23,
			loadMore: _temp1,
			item: t24,
			thread: t25
		};
		$[64] = handleSwitchToNewThread;
		$[65] = handleSwitchToThread;
		$[66] = t22;
		$[67] = t23;
		$[68] = t24;
		$[69] = t25;
		$[70] = t26;
	} else t26 = $[70];
	return t26;
};
const InMemoryThreadList = resource(useInMemoryThreadList);
/**
* The scope defaults `InMemoryThreadList` installs when it is used as the
* `threads` config entry. Adapter packages that wrap it in their own config
* entry attach this to the wrapping resource for scope parity.
*/
const inMemoryThreadListTransformScopes = (scopes, parent) => {
	scopes.thread ??= Derived({
		source: "threads",
		query: { type: "main" },
		get: (aui) => aui.threads.thread("main")
	});
	scopes.threadListItem ??= Derived({
		source: "threads",
		query: { type: "main" },
		get: (aui) => aui.threads.item("main")
	});
	scopes.composer ??= Derived({
		source: "thread",
		query: {},
		get: (aui) => aui.threads.thread("main").composer()
	});
	if (!scopes.modelContext && parent.modelContext.source === null) scopes.modelContext = ModelContext();
	if (!scopes.tools && parent.tools.source === null) scopes.tools = Tools({});
	if (!scopes.dataRenderers && parent.dataRenderers.source === null) scopes.dataRenderers = DataRenderers();
	if (!scopes.suggestions && parent.suggestions.source === null) scopes.suggestions = Derived({
		source: "thread",
		query: {},
		get: (aui) => aui.thread.suggestions()
	});
};
attachTransformScopes(useInMemoryThreadList, inMemoryThreadListTransformScopes);
function _temp() {}
function _temp2() {}
function _temp3() {
	return {
		threads: [{
			id: INITIAL_THREAD_ID,
			title: "Main Thread",
			status: "regular"
		}],
		mainThreadId: INITIAL_THREAD_ID
	};
}
function _temp4(t_4) {
	return t_4.status === "regular";
}
function _temp5(t_6) {
	return t_6.status === "regular";
}
function _temp6(t_7) {
	return t_7.status === "archived";
}
function _temp7(t_8) {
	return t_8.id;
}
function _temp8(t_9) {
	return t_9.id;
}
function _temp9() {
	return RESOLVED_PROMISE;
}
function _temp0() {
	return RESOLVED_PROMISE;
}
function _temp1() {
	return RESOLVED_PROMISE;
}
//#endregion
export { InMemoryThreadList, inMemoryThreadListTransformScopes };
