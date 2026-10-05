"use client";
import { useThreadViewport, useThreadViewportStore } from "../../context/react/ThreadViewportContext.js";
import { createActionButton } from "../../utils/createActionButton.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
//#region src/primitives/thread/ThreadScrollToBottom.ts
const useThreadScrollToBottom = (t0) => {
	const $ = c(5);
	let t1;
	if ($[0] !== t0) {
		t1 = t0 === void 0 ? {} : t0;
		$[0] = t0;
		$[1] = t1;
	} else t1 = $[1];
	const { behavior } = t1;
	const isAtBottom = useThreadViewport(_temp);
	const threadViewportStore = useThreadViewportStore();
	let t2;
	if ($[2] !== behavior || $[3] !== threadViewportStore) {
		t2 = () => {
			threadViewportStore.getState().scrollToBottom({ behavior });
		};
		$[2] = behavior;
		$[3] = threadViewportStore;
		$[4] = t2;
	} else t2 = $[4];
	const handleScrollToBottom = t2;
	if (isAtBottom) return null;
	return handleScrollToBottom;
};
const ThreadPrimitiveScrollToBottom = createActionButton("ThreadPrimitive.ScrollToBottom", useThreadScrollToBottom, ["behavior"]);
function _temp(s) {
	return s.isAtBottom;
}
//#endregion
export { ThreadPrimitiveScrollToBottom };
