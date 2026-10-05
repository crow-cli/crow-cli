"use client";
import { useThreadViewportStore } from "../../../context/react/ThreadViewportContext.js";
import { mountTopAnchorReserve } from "./mountTopAnchorReserve.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useLayoutEffect } from "@assistant-ui/tap/react-shim";
//#region src/primitives/thread/topAnchor/useTopAnchorReserve.ts
/**
* Mounts the top-turn-anchor reserve element against the active
* `ThreadViewport` store. Call this from inside the scrollable viewport so
* the reserve `<div>` is appended next to the streaming assistant message.
*/
const useTopAnchorReserve = (enabled) => {
	const $ = c(4);
	const threadViewportStore = useThreadViewportStore();
	let t0;
	let t1;
	if ($[0] !== enabled || $[1] !== threadViewportStore) {
		t0 = () => {
			if (!enabled) return;
			return mountTopAnchorReserve(threadViewportStore);
		};
		t1 = [enabled, threadViewportStore];
		$[0] = enabled;
		$[1] = threadViewportStore;
		$[2] = t0;
		$[3] = t1;
	} else {
		t0 = $[2];
		t1 = $[3];
	}
	useLayoutEffect(t0, t1);
};
//#endregion
export { useTopAnchorReserve };
