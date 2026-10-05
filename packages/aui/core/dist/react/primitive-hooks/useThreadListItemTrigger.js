import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useThreadListItemTrigger.ts
const useThreadListItemTrigger = () => {
	const $ = c(4);
	const aui = useAui();
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.threadListItem.switchTo();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const switchTo = t0;
	let t1;
	if ($[2] !== switchTo) {
		t1 = { switchTo };
		$[2] = switchTo;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
};
//#endregion
export { useThreadListItemTrigger };
