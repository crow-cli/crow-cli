import { useClientResource } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useState } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/store/clients/single-thread-list.ts
const RESOLVED_PROMISE = Promise.resolve();
const THREAD_ID = "default";
const useSingleThreadListItem = (t0) => {
	const $ = c(3);
	const { isRunning } = t0;
	const [custom, setCustom] = useState();
	let t1;
	if ($[0] !== custom || $[1] !== isRunning) {
		t1 = {
			getState: () => ({
				id: THREAD_ID,
				remoteId: void 0,
				externalId: void 0,
				title: void 0,
				status: "regular",
				custom,
				isRunning
			}),
			switchTo: _temp,
			rename: _temp2,
			updateCustom: setCustom,
			archive: _temp3,
			unarchive: _temp4,
			delete: _temp5,
			generateTitle: _temp6,
			initialize: _temp7,
			detach: _temp8
		};
		$[0] = custom;
		$[1] = isRunning;
		$[2] = t1;
	} else t1 = $[2];
	return t1;
};
const SingleThreadListItem = resource(useSingleThreadListItem);
/**
* A minimal threads scope that wraps a single thread.
* Automatically provided by ExternalThread when no threads scope exists.
* Mounts the provided thread resource element.
*/
const useSingleThreadList = (t0) => {
	const $ = c(22);
	const { thread } = t0;
	const threadClient = useClientResource(thread);
	let t1;
	if ($[0] !== threadClient.state.isRunning) {
		t1 = SingleThreadListItem({ isRunning: threadClient.state.isRunning });
		$[0] = threadClient.state.isRunning;
		$[1] = t1;
	} else t1 = $[1];
	const itemClient = useClientResource(t1);
	let t2;
	let t3;
	if ($[2] === Symbol.for("react.memo_cache_sentinel")) {
		t2 = [THREAD_ID];
		t3 = [];
		$[2] = t2;
		$[3] = t3;
	} else {
		t2 = $[2];
		t3 = $[3];
	}
	let t4;
	if ($[4] !== itemClient.state) {
		t4 = [itemClient.state];
		$[4] = itemClient.state;
		$[5] = t4;
	} else t4 = $[5];
	let t5;
	if ($[6] !== t4 || $[7] !== threadClient.state) {
		t5 = {
			mainThreadId: THREAD_ID,
			newThreadId: null,
			isLoading: false,
			loadError: void 0,
			isLoadingMore: false,
			hasMore: false,
			threadIds: t2,
			archivedThreadIds: t3,
			threadItems: t4,
			main: threadClient.state
		};
		$[6] = t4;
		$[7] = threadClient.state;
		$[8] = t5;
	} else t5 = $[8];
	const state = t5;
	let t6;
	if ($[9] !== state) {
		t6 = () => state;
		$[9] = state;
		$[10] = t6;
	} else t6 = $[10];
	let t7;
	if ($[11] !== threadClient.methods) {
		t7 = () => threadClient.methods.unstable_refetchThread?.() ?? RESOLVED_PROMISE;
		$[11] = threadClient.methods;
		$[12] = t7;
	} else t7 = $[12];
	let t8;
	if ($[13] !== itemClient.methods) {
		t8 = (selector) => {
			if (selector !== "main" && !(typeof selector === "object" && "id" in selector && selector.id === THREAD_ID) && !(typeof selector === "object" && "index" in selector && selector.index === 0 && !selector.archived)) throw new Error(`SingleThreadList: unknown item selector ${JSON.stringify(selector)}`);
			return itemClient.methods;
		};
		$[13] = itemClient.methods;
		$[14] = t8;
	} else t8 = $[14];
	let t9;
	if ($[15] !== threadClient.methods) {
		t9 = (selector_0) => {
			if (selector_0 !== "main" && selector_0 !== THREAD_ID) throw new Error(`SingleThreadList: unknown thread selector ${JSON.stringify(selector_0)}`);
			return threadClient.methods;
		};
		$[15] = threadClient.methods;
		$[16] = t9;
	} else t9 = $[16];
	let t10;
	if ($[17] !== t6 || $[18] !== t7 || $[19] !== t8 || $[20] !== t9) {
		t10 = {
			getState: t6,
			switchToThread: _temp9,
			switchToNewThread: _temp0,
			getLoadThreadsPromise: _temp1,
			reload: _temp10,
			reloadMainThread: t7,
			loadMore: _temp11,
			item: t8,
			thread: t9
		};
		$[17] = t6;
		$[18] = t7;
		$[19] = t8;
		$[20] = t9;
		$[21] = t10;
	} else t10 = $[21];
	return t10;
};
const SingleThreadList = resource(useSingleThreadList);
function _temp() {}
function _temp2() {}
function _temp3() {}
function _temp4() {}
function _temp5() {}
function _temp6() {}
async function _temp7() {
	return {
		remoteId: THREAD_ID,
		externalId: void 0
	};
}
function _temp8() {}
function _temp9() {
	throw new Error("SingleThreadList does not support switchToThread");
}
function _temp0() {
	throw new Error("SingleThreadList does not support switchToNewThread");
}
function _temp1() {
	return RESOLVED_PROMISE;
}
function _temp10() {
	return RESOLVED_PROMISE;
}
function _temp11() {
	return RESOLVED_PROMISE;
}
//#endregion
export { SingleThreadList };
