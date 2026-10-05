"use client";
import { createContextStoreHook } from "../../context/react/utils/createContextStoreHook.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createContext, forwardRef, useContext, useState } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { create } from "zustand";
import { jsx } from "react/jsx-runtime";
//#region src/utils/smooth/SmoothContext.tsx
const SmoothContext = createContext(null);
const makeSmoothContext = (initialState) => {
	return { useSmoothStatus: create(() => initialState) };
};
const SmoothContextProvider = (t0) => {
	const $ = c(6);
	const { children } = t0;
	let t1;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = { optional: true };
		$[0] = t1;
	} else t1 = $[0];
	const outer = useSmoothContext(t1);
	const aui = useAui();
	let t2;
	if ($[1] !== aui.part) {
		t2 = () => makeSmoothContext(aui.part.getState().status);
		$[1] = aui.part;
		$[2] = t2;
	} else t2 = $[2];
	const [context] = useState(t2);
	if (outer) return children;
	let t3;
	if ($[3] !== children || $[4] !== context) {
		t3 = /* @__PURE__ */ jsx(SmoothContext.Provider, {
			value: context,
			children
		});
		$[3] = children;
		$[4] = context;
		$[5] = t3;
	} else t3 = $[5];
	return t3;
};
const withSmoothContextProvider = (Component) => {
	const Wrapped = forwardRef((props, ref) => {
		const $ = c(3);
		const t0 = props;
		let t1;
		if ($[0] !== ref || $[1] !== t0) {
			t1 = /* @__PURE__ */ jsx(SmoothContextProvider, { children: /* @__PURE__ */ jsx(Component, {
				...t0,
				ref
			}) });
			$[0] = ref;
			$[1] = t0;
			$[2] = t1;
		} else t1 = $[2];
		return t1;
	});
	Wrapped.displayName = Component.displayName;
	return Wrapped;
};
function useSmoothContext(options) {
	const context = useContext(SmoothContext);
	if (!options?.optional && !context) throw new Error("This component must be used within a SmoothContextProvider.");
	return context;
}
const { useSmoothStatus, useSmoothStatusStore } = createContextStoreHook(useSmoothContext, "useSmoothStatus");
//#endregion
export { SmoothContextProvider, useSmoothStatus, useSmoothStatusStore, withSmoothContextProvider };
