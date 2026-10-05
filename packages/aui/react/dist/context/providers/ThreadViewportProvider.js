"use client";
import { makeThreadViewportStore } from "../stores/ThreadViewport.js";
import { ThreadViewportContext, useThreadViewportStore } from "../react/ThreadViewportContext.js";
import { writableStore } from "../ReadonlyStore.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useState } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/context/providers/ThreadViewportProvider.tsx
const useThreadViewportStoreValue = (options) => {
	const $ = c(11);
	let t0;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t0 = { optional: true };
		$[0] = t0;
	} else t0 = $[0];
	const outerViewport = useThreadViewportStore(t0);
	let t1;
	if ($[1] !== options) {
		t1 = () => makeThreadViewportStore(options);
		$[1] = options;
		$[2] = t1;
	} else t1 = $[2];
	const [store] = useState(t1);
	let t2;
	let t3;
	if ($[3] !== outerViewport || $[4] !== store) {
		t2 = () => outerViewport?.getState().onScrollToBottom((config) => {
			store.getState().scrollToBottom(config);
		});
		t3 = [outerViewport, store];
		$[3] = outerViewport;
		$[4] = store;
		$[5] = t2;
		$[6] = t3;
	} else {
		t2 = $[5];
		t3 = $[6];
	}
	useEffect(t2, t3);
	let t4;
	let t5;
	if ($[7] !== outerViewport || $[8] !== store) {
		t4 = () => {
			if (!outerViewport) return;
			return store.subscribe((state) => {
				if (outerViewport.getState().isAtBottom !== state.isAtBottom) writableStore(outerViewport).setState({ isAtBottom: state.isAtBottom });
			});
		};
		t5 = [store, outerViewport];
		$[7] = outerViewport;
		$[8] = store;
		$[9] = t4;
		$[10] = t5;
	} else {
		t4 = $[9];
		t5 = $[10];
	}
	useEffect(t4, t5);
	return store;
};
const ThreadPrimitiveViewportProvider = (t0) => {
	const $ = c(7);
	const { children, options: t1 } = t0;
	let t2;
	if ($[0] !== t1) {
		t2 = t1 === void 0 ? {} : t1;
		$[0] = t1;
		$[1] = t2;
	} else t2 = $[1];
	const useThreadViewport = useThreadViewportStoreValue(t2);
	let t3;
	if ($[2] !== useThreadViewport) {
		t3 = () => ({ useThreadViewport });
		$[2] = useThreadViewport;
		$[3] = t3;
	} else t3 = $[3];
	const [context] = useState(t3);
	let t4;
	if ($[4] !== children || $[5] !== context) {
		t4 = /* @__PURE__ */ jsx(ThreadViewportContext.Provider, {
			value: context,
			children
		});
		$[4] = children;
		$[5] = context;
		$[6] = t4;
	} else t4 = $[6];
	return t4;
};
//#endregion
export { ThreadPrimitiveViewportProvider };
