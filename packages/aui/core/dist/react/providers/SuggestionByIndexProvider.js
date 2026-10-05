import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { AuiConfig, AuiProvider, Derived, useAui } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/react/providers/SuggestionByIndexProvider.tsx
const SuggestionByIndexProvider = (t0) => {
	const $ = c(6);
	const { index, children } = t0;
	const aui = useAui();
	let t1;
	if ($[0] !== index) {
		t1 = AuiConfig({ suggestion: Derived({
			source: "suggestions",
			query: { index },
			get: (aui_0) => aui_0.suggestions.suggestion({ index })
		}) });
		$[0] = index;
		$[1] = t1;
	} else t1 = $[1];
	const config = t1;
	let t2;
	if ($[2] !== aui || $[3] !== children || $[4] !== config) {
		t2 = /* @__PURE__ */ jsx(AuiProvider, {
			extends: aui,
			config,
			children
		});
		$[2] = aui;
		$[3] = children;
		$[4] = config;
		$[5] = t2;
	} else t2 = $[5];
	return t2;
};
//#endregion
export { SuggestionByIndexProvider };
