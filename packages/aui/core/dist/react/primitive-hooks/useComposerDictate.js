import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useComposerDictate.ts
const useComposerDictate = () => {
	const $ = c(5);
	const aui = useAui();
	const disabled = useAuiState(_temp);
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.composer.startDictation();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const startDictation = t0;
	let t1;
	if ($[2] !== disabled || $[3] !== startDictation) {
		t1 = {
			startDictation,
			disabled
		};
		$[2] = disabled;
		$[3] = startDictation;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
function _temp(s) {
	return s.composer.dictation != null || !s.thread.capabilities.dictation || !s.composer.isEditing;
}
//#endregion
export { useComposerDictate };
