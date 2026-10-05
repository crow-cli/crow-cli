import { useAssistantEmit } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef } from "@assistant-ui/tap/react-shim";
//#region src/store/clients/thread-selection-events.ts
/**
* Emits `threads.selectionChanged` whenever the main thread selection changes.
* Does not emit for the initially selected thread on mount. Every `threads`
* client whose selection can change calls this with its current main thread id.
*/
const useThreadSelectionEvents = (mainThreadId) => {
	const $ = c(4);
	const emit = useAssistantEmit();
	const previousMainThreadIdRef = useRef(mainThreadId);
	let t0;
	let t1;
	if ($[0] !== emit || $[1] !== mainThreadId) {
		t0 = () => {
			const previousThreadId = previousMainThreadIdRef.current;
			if (previousThreadId === mainThreadId) return;
			previousMainThreadIdRef.current = mainThreadId;
			emit("threads.selectionChanged", {
				threadId: mainThreadId,
				previousThreadId
			});
		};
		t1 = [mainThreadId, emit];
		$[0] = emit;
		$[1] = mainThreadId;
		$[2] = t0;
		$[3] = t1;
	} else {
		t0 = $[2];
		t1 = $[3];
	}
	useEffect(t0, t1);
};
/**
* Emits `threadListItem.switchedTo` or `threadListItem.switchedAway` from a
* thread list item's own scope when its thread gains or loses the main
* selection. Emitting after the commit delivers against the rebound derived
* scopes; a synchronous notification would reach the pre-switch binding.
* `wasMain` is whether the thread held the selection before this item
* mounted, so an item created and selected in one update reports the switch.
*/
const useThreadListItemSelectionEvents = (threadId, isMain, t0) => {
	const $ = c(8);
	const wasMain = t0 === void 0 ? isMain : t0;
	const emit = useAssistantEmit();
	const t1 = isMain && wasMain;
	let t2;
	if ($[0] !== t1 || $[1] !== threadId) {
		t2 = {
			isMain: t1,
			threadId
		};
		$[0] = t1;
		$[1] = threadId;
		$[2] = t2;
	} else t2 = $[2];
	const selectionRef = useRef(t2);
	let t3;
	let t4;
	if ($[3] !== emit || $[4] !== isMain || $[5] !== threadId) {
		t3 = () => {
			const previous = selectionRef.current;
			if (previous.isMain === isMain && previous.threadId === threadId) return;
			selectionRef.current = {
				isMain,
				threadId
			};
			emit(isMain ? "threadListItem.switchedTo" : "threadListItem.switchedAway", { threadId });
		};
		t4 = [
			isMain,
			threadId,
			emit
		];
		$[3] = emit;
		$[4] = isMain;
		$[5] = threadId;
		$[6] = t3;
		$[7] = t4;
	} else {
		t3 = $[6];
		t4 = $[7];
	}
	useEffect(t3, t4);
};
//#endregion
export { useThreadListItemSelectionEvents, useThreadSelectionEvents };
