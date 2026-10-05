import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { AuiConfig, AuiProvider, Derived, useAui } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/react/providers/ThreadListItemByIndexProvider.tsx
const ThreadListItemByIndexProvider = (t0) => {
	const $ = c(7);
	const { index, archived, children } = t0;
	const aui = useAui();
	let t1;
	if ($[0] !== archived || $[1] !== index) {
		t1 = AuiConfig({ threadListItem: Derived({
			source: "threads",
			query: {
				type: "index",
				index,
				archived
			},
			get: (aui_0) => aui_0.threads.item({
				index,
				archived
			})
		}) });
		$[0] = archived;
		$[1] = index;
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
export { ThreadListItemByIndexProvider };
