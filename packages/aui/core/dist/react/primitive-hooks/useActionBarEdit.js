import { actionBarEditDisabled } from "../../store/primitive-predicates.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useActionBarEdit.ts
const useActionBarEdit = () => {
	const $ = c(5);
	const aui = useAui();
	const disabled = useAuiState(actionBarEditDisabled);
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.composer.beginEdit();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const edit = t0;
	let t1;
	if ($[2] !== disabled || $[3] !== edit) {
		t1 = {
			edit,
			disabled
		};
		$[2] = disabled;
		$[3] = edit;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
//#endregion
export { useActionBarEdit };
