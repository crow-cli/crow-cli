import { threadListLoadMoreDisabled } from "../../store/primitive-predicates.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useThreadListLoadMore.ts
const useThreadListLoadMore = () => {
	const $ = c(5);
	const aui = useAui();
	const disabled = useAuiState(threadListLoadMoreDisabled);
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.threads.loadMore();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const loadMore = t0;
	let t1;
	if ($[2] !== disabled || $[3] !== loadMore) {
		t1 = {
			loadMore,
			disabled
		};
		$[2] = disabled;
		$[3] = loadMore;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
//#endregion
export { useThreadListLoadMore };
