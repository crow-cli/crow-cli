import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useComposerAddAttachment.ts
const useComposerAddAttachment = () => {
	const $ = c(5);
	const aui = useAui();
	const disabled = useAuiState(_temp);
	let t0;
	if ($[0] !== aui) {
		t0 = (file) => aui.composer.addAttachment(file);
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const addAttachment = t0;
	let t1;
	if ($[2] !== addAttachment || $[3] !== disabled) {
		t1 = {
			addAttachment,
			disabled
		};
		$[2] = addAttachment;
		$[3] = disabled;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
function _temp(s) {
	return !s.composer.isEditing;
}
//#endregion
export { useComposerAddAttachment };
