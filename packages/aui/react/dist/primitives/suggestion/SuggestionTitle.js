"use client";
import { Primitive } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/suggestion/SuggestionTitle.tsx
/**
* Renders the title of the suggestion.
*
* @example
* ```tsx
* <SuggestionPrimitive.Title />
* ```
*/
const SuggestionPrimitiveTitle = forwardRef((props, ref) => {
	const $ = c(4);
	const title = useAuiState(_temp);
	const t0 = props.children ?? title;
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
SuggestionPrimitiveTitle.displayName = "SuggestionPrimitive.Title";
function _temp(s) {
	return s.suggestion.title;
}
//#endregion
export { SuggestionPrimitiveTitle };
