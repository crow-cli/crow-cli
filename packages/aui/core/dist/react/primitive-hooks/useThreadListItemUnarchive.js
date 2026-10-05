import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useThreadListItemUnarchive.ts
const useThreadListItemUnarchive = () => {
	const $ = c(4);
	const aui = useAui();
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.threadListItem.unarchive();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const unarchive = t0;
	let t1;
	if ($[2] !== unarchive) {
		t1 = { unarchive };
		$[2] = unarchive;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
};
//#endregion
export { useThreadListItemUnarchive };
