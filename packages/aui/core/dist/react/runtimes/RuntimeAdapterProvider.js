import { RuntimeAdaptersContext, useRuntimeAdapters, useRuntimeAdaptersProvider } from "./useRuntimeAdapters.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useContext } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/react/runtimes/RuntimeAdapterProvider.tsx
const RuntimeAdapterProvider = (t0) => {
	const $ = c(6);
	const { adapters, children } = t0;
	const context = useContext(RuntimeAdaptersContext);
	let t1;
	if ($[0] !== adapters || $[1] !== context) {
		t1 = {
			...context,
			...adapters
		};
		$[0] = adapters;
		$[1] = context;
		$[2] = t1;
	} else t1 = $[2];
	const value = t1;
	let t2;
	if ($[3] !== children || $[4] !== value) {
		t2 = /* @__PURE__ */ jsx(RuntimeAdaptersContext.Provider, {
			value,
			children
		});
		$[3] = children;
		$[4] = value;
		$[5] = t2;
	} else t2 = $[5];
	return t2;
};
//#endregion
export { RuntimeAdapterProvider, useRuntimeAdapters, useRuntimeAdaptersProvider };
