"use client";
import { Primitive } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/suggestion/SuggestionDescription.tsx
/**
* Renders the description/label of the suggestion.
*
* @example
* ```tsx
* <SuggestionPrimitive.Description />
* ```
*/
const SuggestionPrimitiveDescription = forwardRef((props, ref) => {
	const $ = c(4);
	const label = useAuiState(_temp);
	const t0 = props.children ?? label;
	let t1;
	if ($[0] !== props || $[1] !== ref || $[2] !== t0) {
		t1 = /* @__PURE__ */ jsx(Primitive.span, {
			...props,
			ref,
			children: t0
		});
		$[0] = props;
		$[1] = ref;
		$[2] = t0;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
});
SuggestionPrimitiveDescription.displayName = "SuggestionPrimitive.Description";
function _temp(s) {
	return s.suggestion.label;
}
//#endregion
export { SuggestionPrimitiveDescription };
