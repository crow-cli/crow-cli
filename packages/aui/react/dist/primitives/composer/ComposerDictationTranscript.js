"use client";
import { Primitive } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/composer/ComposerDictationTranscript.tsx
/**
* Renders the current interim (partial) transcript while dictation is active.
*
* This component displays real-time feedback of what the user is saying before
* the transcription is finalized and committed to the composer input.
*
* @example
* ```tsx
* <AuiIf condition={(s) => s.composer.dictation != null}>
*   <div className="dictation-preview">
*     <ComposerPrimitive.DictationTranscript />
*   </div>
* </AuiIf>
* ```
*/
const ComposerPrimitiveDictationTranscript = forwardRef((t0, forwardRef) => {
	const $ = c(7);
	let children;
	let props;
	if ($[0] !== t0) {
		({children, ...props} = t0);
		$[0] = t0;
		$[1] = children;
		$[2] = props;
	} else {
		children = $[1];
		props = $[2];
	}
	const transcript = useAuiState(_temp);
	if (!transcript) return null;
	const t1 = children ?? transcript;
	let t2;
	if ($[3] !== forwardRef || $[4] !== props || $[5] !== t1) {
		t2 = /* @__PURE__ */ jsx(Primitive.span, {
			...props,
			ref: forwardRef,
			children: t1
		});
		$[3] = forwardRef;
		$[4] = props;
		$[5] = t1;
		$[6] = t2;
	} else t2 = $[6];
	return t2;
});
ComposerPrimitiveDictationTranscript.displayName = "ComposerPrimitive.DictationTranscript";
function _temp(s) {
	return s.composer.dictation?.transcript;
}
//#endregion
export { ComposerPrimitiveDictationTranscript };
