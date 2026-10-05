import { composerCancelDisabled } from "../../store/primitive-predicates.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useComposerCancel.ts
const useComposerCancel = () => {
	const $ = c(5);
	const aui = useAui();
	const disabled = useAuiState(composerCancelDisabled);
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.composer.cancel();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const cancel = t0;
	let t1;
	if ($[2] !== cancel || $[3] !== disabled) {
		t1 = {
			cancel,
			disabled
		};
		$[2] = cancel;
		$[3] = disabled;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
//#endregion
export { useComposerCancel };
