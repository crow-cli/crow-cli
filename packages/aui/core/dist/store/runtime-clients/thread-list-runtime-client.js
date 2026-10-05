import { useSubscribable } from "./useSubscribable.js";
import { ThreadClient } from "./thread-runtime-client.js";
import { useThreadSelectionEvents } from "../clients/thread-selection-events.js";
import { handleThreadListAction } from "./handle-thread-list-action.js";
import { ThreadListItemClient } from "./thread-list-item-runtime-client.js";
import { useAfterStateCommit } from "./useAfterStateCommit.js";
import { useAssistantEmit, useClientLookup, useClientResource } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect } from "@assistant-ui/tap/react-shim";
import { resource, useResource, withKey } from "@assistant-ui/tap";
//#region src/store/runtime-clients/thread-list-runtime-client.ts
const useThreadListItemClientById = (t0) => {
	const $ = c(6);
	const { runtime, id, mainThreadIsRunning } = t0;
	let t1;
	if ($[0] !== id || $[1] !== runtime) {
		t1 = runtime.getItemById(id);
		$[0] = id;
		$[1] = runtime;
		$[2] = t1;
	} else t1 = $[2];
	const threadListItemRuntime = t1;
	let t2;
	if ($[3] !== mainThreadIsRunning || $[4] !== threadListItemRuntime) {
		t2 = ThreadListItemClient({
			runtime: threadListItemRuntime,
			mainThreadIsRunning
		});
		$[3] = mainThreadIsRunning;
		$[4] = threadListItemRuntime;
		$[5] = t2;
	} else t2 = $[5];
	return useResource(t2);
};
const ThreadListItemClientById = resource(useThreadListItemClientById);
const useThreadListClient = (t0) => {
	const $ = c(53);
	const { runtime, __internal_assistantRuntime } = t0;
	const runtimeState = useSubscribable(runtime);
	const afterStateCommit = useAfterStateCommit(runtimeState, runtime.getState);
	useThreadSelectionEvents(runtimeState.mainThreadId);
	const emit = useAssistantEmit();
	let t1;
	let t2;
	if ($[0] !== emit || $[1] !== runtime) {
		t1 = () => runtime.unstable_subscribeThreadEvents((t3) => {
			const { threadId, type } = t3;
			if (threadId === runtime.getState().mainThreadId) return;
			emit(`thread.${type}`, { threadId });
		});
		t2 = [runtime, emit];
		$[0] = emit;
		$[1] = runtime;
		$[2] = t1;
		$[3] = t2;
	} else {
		t1 = $[2];
		t2 = $[3];
	}
	useEffect(t1, t2);
	let t3;
	if ($[4] !== runtime.main) {
		t3 = ThreadClient({ runtime: runtime.main });
		$[4] = runtime.main;
		$[5] = t3;
	} else t3 = $[5];
	const main = useClientResource(t3);
	let t4;
	if ($[6] !== main.state || $[7] !== runtime || $[8] !== runtimeState.threadItems) {
		t4 = Object.keys(runtimeState.threadItems).map((id) => withKey(id, ThreadListItemClientById({
			runtime,
			id,
			mainThreadIsRunning: main.state.isRunning
		}), [
			runtime,
			id,
			main.state.isRunning
		]));
		$[6] = main.state;
		$[7] = runtime;
		$[8] = runtimeState.threadItems;
		$[9] = t4;
	} else t4 = $[9];
	const threadItems = useClientLookup(t4);
	const t5 = runtimeState.newThreadId ?? null;
	let t6;
	if ($[10] !== main.state || $[11] !== runtimeState.archivedThreadIds || $[12] !== runtimeState.hasMore || $[13] !== runtimeState.isLoading || $[14] !== runtimeState.isLoadingMore || $[15] !== runtimeState.loadError || $[16] !== runtimeState.mainThreadId || $[17] !== runtimeState.threadIds || $[18] !== t5 || $[19] !== threadItems.state) {
		t6 = {
			mainThreadId: runtimeState.mainThreadId,
			newThreadId: t5,
			isLoading: runtimeState.isLoading,
			loadError: runtimeState.loadError,
			isLoadingMore: runtimeState.isLoadingMore,
			hasMore: runtimeState.hasMore,
			threadIds: runtimeState.threadIds,
			archivedThreadIds: runtimeState.archivedThreadIds,
			threadItems: threadItems.state,
			main: main.state
		};
		$[10] = main.state;
		$[11] = runtimeState.archivedThreadIds;
		$[12] = runtimeState.hasMore;
		$[13] = runtimeState.isLoading;
		$[14] = runtimeState.isLoadingMore;
		$[15] = runtimeState.loadError;
		$[16] = runtimeState.mainThreadId;
		$[17] = runtimeState.threadIds;
		$[18] = t5;
		$[19] = threadItems.state;
		$[20] = t6;
	} else t6 = $[20];
	const state = t6;
	let t7;
	if ($[21] !== state) {
		t7 = () => state;
		$[21] = state;
		$[22] = t7;
	} else t7 = $[22];
	let t8;
	if ($[23] !== main.methods) {
		t8 = () => main.methods;
		$[23] = main.methods;
		$[24] = t8;
	} else t8 = $[24];
	let t9;
	if ($[25] !== state || $[26] !== threadItems) {
		t9 = (threadIdOrOptions) => {
			if (threadIdOrOptions === "main") return threadItems.get({ key: state.mainThreadId });
			if ("id" in threadIdOrOptions) return threadItems.get({ key: threadIdOrOptions.id });
			const { index, archived: t10 } = threadIdOrOptions;
			const id_0 = (t10 === void 0 ? false : t10) ? state.archivedThreadIds[index] : state.threadIds[index];
			return threadItems.get({ key: id_0 });
		};
		$[25] = state;
		$[26] = threadItems;
		$[27] = t9;
	} else t9 = $[27];
	let t10;
	let t11;
	if ($[28] !== runtime) {
		t10 = (threadId_0, options) => handleThreadListAction("switch", () => runtime.switchToThread(threadId_0, options));
		t11 = () => handleThreadListAction("create", () => runtime.switchToNewThread());
		$[28] = runtime;
		$[29] = t10;
		$[30] = t11;
	} else {
		t10 = $[29];
		t11 = $[30];
	}
	let t12;
	let t13;
	if ($[31] !== afterStateCommit || $[32] !== runtime) {
		t12 = () => afterStateCommit(runtime.getLoadThreadsPromise());
		t13 = () => afterStateCommit(runtime.reload());
		$[31] = afterStateCommit;
		$[32] = runtime;
		$[33] = t12;
		$[34] = t13;
	} else {
		t12 = $[33];
		t13 = $[34];
	}
	let t14;
	if ($[35] !== runtime) {
		t14 = () => runtime.reloadMainThread();
		$[35] = runtime;
		$[36] = t14;
	} else t14 = $[36];
	let t15;
	if ($[37] !== afterStateCommit || $[38] !== runtime) {
		t15 = () => afterStateCommit(runtime.loadMore());
		$[37] = afterStateCommit;
		$[38] = runtime;
		$[39] = t15;
	} else t15 = $[39];
	let t16;
	if ($[40] !== __internal_assistantRuntime) {
		t16 = () => __internal_assistantRuntime;
		$[40] = __internal_assistantRuntime;
		$[41] = t16;
	} else t16 = $[41];
	let t17;
	if ($[42] !== t10 || $[43] !== t11 || $[44] !== t12 || $[45] !== t13 || $[46] !== t14 || $[47] !== t15 || $[48] !== t16 || $[49] !== t7 || $[50] !== t8 || $[51] !== t9) {
		t17 = {
			getState: t7,
			thread: t8,
			item: t9,
			switchToThread: t10,
			switchToNewThread: t11,
			getLoadThreadsPromise: t12,
			reload: t13,
			reloadMainThread: t14,
			loadMore: t15,
			__internal_getAssistantRuntime: t16
		};
		$[42] = t10;
		$[43] = t11;
		$[44] = t12;
		$[45] = t13;
		$[46] = t14;
		$[47] = t15;
		$[48] = t16;
		$[49] = t7;
		$[50] = t8;
		$[51] = t9;
		$[52] = t17;
	} else t17 = $[52];
	return t17;
};
const ThreadListClient = resource(useThreadListClient);
//#endregion
export { ThreadListClient };
