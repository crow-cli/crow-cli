import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useThreadListItemDelete.ts
const useThreadListItemDelete = () => {
	const $ = c(4);
	const aui = useAui();
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.threadListItem.delete();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const deleteThread = t0;
	let t1;
	if ($[2] !== deleteThread) {
		t1 = { delete: deleteThread };
		$[2] = deleteThread;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
};
//#endregion
export { useThreadListItemDelete };
