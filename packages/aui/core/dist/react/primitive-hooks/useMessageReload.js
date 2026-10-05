import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useMessageReload.ts
const useMessageReload = () => {
	const $ = c(5);
	const aui = useAui();
	const canReload = useAuiState(_temp);
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.message.reload();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const reload = t0;
	let t1;
	if ($[2] !== canReload || $[3] !== reload) {
		t1 = {
			reload,
			canReload
		};
		$[2] = canReload;
		$[3] = reload;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
function _temp(s) {
	return s.message.role === "assistant";
}
//#endregion
export { useMessageReload };
