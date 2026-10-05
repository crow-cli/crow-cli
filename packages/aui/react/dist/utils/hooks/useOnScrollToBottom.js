"use client";
import { useThreadViewport } from "../../context/react/ThreadViewportContext.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect } from "@assistant-ui/tap/react-shim";
import { useCallbackRef } from "radix-ui/internal";
//#region src/utils/hooks/useOnScrollToBottom.ts
const useOnScrollToBottom = (callback) => {
	const $ = c(4);
	const callbackRef = useCallbackRef(callback);
	const onScrollToBottom = useThreadViewport(_temp);
	let t0;
	let t1;
	if ($[0] !== callbackRef || $[1] !== onScrollToBottom) {
		t0 = () => onScrollToBottom(callbackRef);
		t1 = [onScrollToBottom, callbackRef];
		$[0] = callbackRef;
		$[1] = onScrollToBottom;
		$[2] = t0;
		$[3] = t1;
	} else {
		t0 = $[2];
		t1 = $[3];
	}
	useEffect(t0, t1);
};
function _temp(vp) {
	return vp.onScrollToBottom;
}
//#endregion
export { useOnScrollToBottom };
