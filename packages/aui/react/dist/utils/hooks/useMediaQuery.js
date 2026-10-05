"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useSyncExternalStore } from "@assistant-ui/tap/react-shim";
//#region src/utils/hooks/useMediaQuery.ts
const getServerSnapshot = () => false;
const noopUnsubscribe = () => {};
const useMediaQuery = (query) => {
	const $ = c(4);
	let t0;
	if ($[0] !== query) {
		t0 = (callback) => {
			if (typeof window === "undefined" || query === null || !window.matchMedia) return noopUnsubscribe;
			const mql = window.matchMedia(query);
			mql.addEventListener("change", callback);
			return () => mql.removeEventListener("change", callback);
		};
		$[0] = query;
		$[1] = t0;
	} else t0 = $[1];
	const subscribe = t0;
	let t1;
	if ($[2] !== query) {
		t1 = () => {
			if (typeof window === "undefined" || query === null || !window.matchMedia) return false;
			return window.matchMedia(query).matches;
		};
		$[2] = query;
		$[3] = t1;
	} else t1 = $[3];
	return useSyncExternalStore(subscribe, t1, getServerSnapshot);
};
//#endregion
export { useMediaQuery };
