import { ChainOfThoughtPartsContext } from "./ChainOfThoughtByIndicesProvider.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useContext } from "@assistant-ui/tap/react-shim";
import { AuiConfig, AuiProvider, Derived, useAui } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/react/providers/ChainOfThoughtPartByIndexProvider.tsx
const ChainOfThoughtPartByIndexProvider = (t0) => {
	const $ = c(7);
	const { index, children } = t0;
	const aui = useAui();
	const partsContext = useContext(ChainOfThoughtPartsContext);
	let t1;
	if ($[0] !== index || $[1] !== partsContext) {
		t1 = AuiConfig({ part: Derived({
			source: "chainOfThought",
			query: {
				type: "index",
				index
			},
			get: (aui_0) => partsContext ? aui_0.message.part({ index: partsContext.startIndex + index }) : aui_0.chainOfThought.part({ index })
		}) });
		$[0] = index;
		$[1] = partsContext;
		$[2] = t1;
	} else t1 = $[2];
	const config = t1;
	let t2;
	if ($[3] !== aui || $[4] !== children || $[5] !== config) {
		t2 = /* @__PURE__ */ jsx(AuiProvider, {
			extends: aui,
			config,
			children
		});
		$[3] = aui;
		$[4] = children;
		$[5] = config;
		$[6] = t2;
	} else t2 = $[6];
	return t2;
};
//#endregion
export { ChainOfThoughtPartByIndexProvider };
