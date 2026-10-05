import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useAuiState } from "@assistant-ui/store";
import { Fragment, jsx } from "react/jsx-runtime";
//#region src/react/primitives/threadListItem/ThreadListItemTitle.tsx
const ThreadListItemPrimitiveTitle = (t0) => {
	const $ = c(2);
	const { fallback } = t0;
	const t1 = useAuiState(_temp) || fallback;
	let t2;
	if ($[0] !== t1) {
		t2 = /* @__PURE__ */ jsx(Fragment, { children: t1 });
		$[0] = t1;
		$[1] = t2;
	} else t2 = $[1];
	return t2;
};
ThreadListItemPrimitiveTitle.displayName = "ThreadListItemPrimitive.Title";
function _temp(s) {
	return s.threadListItem.title;
}
//#endregion
export { ThreadListItemPrimitiveTitle };
