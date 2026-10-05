import { useSubscribable } from "./useSubscribable.js";
import { useThreadListItemSelectionEvents } from "../clients/thread-selection-events.js";
import { handleThreadListAction } from "./handle-thread-list-action.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/store/runtime-clients/thread-list-item-runtime-client.ts
const useThreadListItemClient = (t0) => {
	const $ = c(27);
	const { runtime, mainThreadIsRunning: t1 } = t0;
	const mainThreadIsRunning = t1 === void 0 ? false : t1;
	const runtimeState = useSubscribable(runtime);
	let t2;
	bb0: {
		const isRunning = runtimeState.isRunning || runtimeState.isMain && mainThreadIsRunning;
		if (isRunning === runtimeState.isRunning) {
			t2 = runtimeState;
			break bb0;
		}
		let t3;
		if ($[0] !== isRunning || $[1] !== runtimeState) {
			t3 = {
				...runtimeState,
				isRunning
			};
			$[0] = isRunning;
			$[1] = runtimeState;
			$[2] = t3;
		} else t3 = $[2];
		t2 = t3;
	}
	const state = t2;
	useThreadListItemSelectionEvents(runtimeState.id, runtimeState.isMain);
	let t3;
	if ($[3] !== state) {
		t3 = () => state;
		$[3] = state;
		$[4] = t3;
	} else t3 = $[4];
	let t10;
	let t4;
	let t5;
	let t6;
	let t7;
	let t8;
	let t9;
	if ($[5] !== runtime) {
		t4 = (options) => handleThreadListAction("switch", () => runtime.switchTo(options));
		t5 = (newTitle) => handleThreadListAction("rename", () => runtime.rename(newTitle));
		t6 = (custom) => handleThreadListAction("update custom metadata", () => runtime.updateCustom(custom));
		t7 = () => handleThreadListAction("archive", () => runtime.archive());
		t8 = () => handleThreadListAction("unarchive", () => runtime.unarchive());
		t9 = () => handleThreadListAction("delete", () => runtime.delete());
		t10 = (options_0) => handleThreadListAction("generate title", () => runtime.generateTitle(options_0));
		$[5] = runtime;
		$[6] = t10;
		$[7] = t4;
		$[8] = t5;
		$[9] = t6;
		$[10] = t7;
		$[11] = t8;
		$[12] = t9;
	} else {
		t10 = $[6];
		t4 = $[7];
		t5 = $[8];
		t6 = $[9];
		t7 = $[10];
		t8 = $[11];
		t9 = $[12];
	}
	let t11;
	if ($[13] !== runtime) {
		t11 = () => runtime;
		$[13] = runtime;
		$[14] = t11;
	} else t11 = $[14];
	let t12;
	if ($[15] !== runtime.detach || $[16] !== runtime.initialize || $[17] !== t10 || $[18] !== t11 || $[19] !== t3 || $[20] !== t4 || $[21] !== t5 || $[22] !== t6 || $[23] !== t7 || $[24] !== t8 || $[25] !== t9) {
		t12 = {
			getState: t3,
			switchTo: t4,
			rename: t5,
			updateCustom: t6,
			archive: t7,
			unarchive: t8,
			delete: t9,
			generateTitle: t10,
			initialize: runtime.initialize,
			detach: runtime.detach,
			__internal_getRuntime: t11
		};
		$[15] = runtime.detach;
		$[16] = runtime.initialize;
		$[17] = t10;
		$[18] = t11;
		$[19] = t3;
		$[20] = t4;
		$[21] = t5;
		$[22] = t6;
		$[23] = t7;
		$[24] = t8;
		$[25] = t9;
		$[26] = t12;
	} else t12 = $[26];
	return t12;
};
const ThreadListItemClient = resource(useThreadListItemClient);
//#endregion
export { ThreadListItemClient };
