"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createContext, useContext, useRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/composer/ComposerInputPluginContext.tsx
const ComposerInputPluginRegistryContext = createContext(null);
const useComposerInputPluginRegistryOptional = () => {
	return useContext(ComposerInputPluginRegistryContext);
};
const ComposerInputPluginProvider = (t0) => {
	const $ = c(8);
	const { children } = t0;
	let t1;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = /* @__PURE__ */ new Map();
		$[0] = t1;
	} else t1 = $[0];
	const pluginsRef = useRef(t1);
	let t2;
	if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
		t2 = [];
		$[1] = t2;
	} else t2 = $[1];
	const snapshotRef = useRef(t2);
	let t3;
	if ($[2] === Symbol.for("react.memo_cache_sentinel")) {
		t3 = () => {
			const entries = Array.from(pluginsRef.current.entries());
			entries.sort(_temp);
			snapshotRef.current = entries.map(_temp2);
		};
		$[2] = t3;
	} else t3 = $[2];
	const refreshSnapshot = t3;
	let t4;
	if ($[3] === Symbol.for("react.memo_cache_sentinel")) {
		t4 = (plugin_0, opts) => {
			const priority = opts?.priority ?? 0;
			pluginsRef.current.set(plugin_0, priority);
			refreshSnapshot();
			return () => {
				pluginsRef.current.delete(plugin_0);
				refreshSnapshot();
			};
		};
		$[3] = t4;
	} else t4 = $[3];
	const register = t4;
	let t5;
	if ($[4] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = () => snapshotRef.current;
		$[4] = t5;
	} else t5 = $[4];
	const getPlugins = t5;
	let t6;
	if ($[5] === Symbol.for("react.memo_cache_sentinel")) {
		t6 = {
			register,
			getPlugins
		};
		$[5] = t6;
	} else t6 = $[5];
	const registry = t6;
	let t7;
	if ($[6] !== children) {
		t7 = /* @__PURE__ */ jsx(ComposerInputPluginRegistryContext.Provider, {
			value: registry,
			children
		});
		$[6] = children;
		$[7] = t7;
	} else t7 = $[7];
	return t7;
};
function _temp(a, b) {
	return b[1] - a[1];
}
function _temp2(t0) {
	const [plugin] = t0;
	return plugin;
}
//#endregion
export { ComposerInputPluginProvider, useComposerInputPluginRegistryOptional };
