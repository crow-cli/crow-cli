import { branchPickerPreviousDisabled } from "../../store/primitive-predicates.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useBranchPickerPrevious.ts
const useBranchPickerPrevious = () => {
	const $ = c(5);
	const aui = useAui();
	const disabled = useAuiState(branchPickerPreviousDisabled);
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.message.switchToBranch({ position: "previous" });
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const previous = t0;
	let t1;
	if ($[2] !== disabled || $[3] !== previous) {
		t1 = {
			previous,
			disabled
		};
		$[2] = disabled;
		$[3] = previous;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
//#endregion
export { useBranchPickerPrevious };
