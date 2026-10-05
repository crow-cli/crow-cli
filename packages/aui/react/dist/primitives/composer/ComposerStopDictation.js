"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/primitives/composer/ComposerStopDictation.ts
const useComposerStopDictation = () => {
	const $ = c(2);
	const aui = useAui();
	const isDictating = useAuiState(_temp);
	let t0;
	if ($[0] !== aui.composer) {
		t0 = () => {
			aui.composer.stopDictation();
		};
		$[0] = aui.composer;
		$[1] = t0;
	} else t0 = $[1];
	const callback = t0;
	if (!isDictating) return null;
	return callback;
};
/**
* A button that stops the current dictation session.
*
* Only rendered when dictation is active.
*
* @example
* ```tsx
* <ComposerPrimitive.StopDictation>
*   <StopIcon />
* </ComposerPrimitive.StopDictation>
* ```
*/
const ComposerPrimitiveStopDictation = createActionButton("ComposerPrimitive.StopDictation", useComposerStopDictation);
function _temp(s) {
	return s.composer.dictation != null;
}
//#endregion
export { ComposerPrimitiveStopDictation };
