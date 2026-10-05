import { actionBarReloadDisabled } from "../../store/primitive-predicates.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useActionBarReload.ts
const useActionBarReload = () => {
	const $ = c(5);
	const aui = useAui();
	const disabled = useAuiState(actionBarReloadDisabled);
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
	if ($[2] !== disabled || $[3] !== reload) {
		t1 = {
			reload,
			disabled
		};
		$[2] = disabled;
		$[3] = reload;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
//#endregion
export { useActionBarReload };
