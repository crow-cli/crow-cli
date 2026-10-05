"use client";
import { Primitive } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/chainOfThought/ChainOfThoughtRoot.tsx
/**
* The root container for chain of thought components.
*
* This component provides a wrapper for chain of thought content,
* including reasoning and tool-call parts that can be collapsed in an accordion.
*
* @example
* ```tsx
* <ChainOfThoughtPrimitive.Root>
*   <ChainOfThoughtPrimitive.AccordionTrigger>
*     Toggle reasoning
*   </ChainOfThoughtPrimitive.AccordionTrigger>
*   <ChainOfThoughtPrimitive.Parts />
* </ChainOfThoughtPrimitive.Root>
* ```
*/
const ChainOfThoughtPrimitiveRoot = forwardRef((props, ref) => {
	const $ = c(3);
	let t0;
	if ($[0] !== props || $[1] !== ref) {
		t0 = /* @__PURE__ */ jsx(Primitive.div, {
			...props,
			ref
		});
		$[0] = props;
		$[1] = ref;
		$[2] = t0;
	} else t0 = $[2];
	return t0;
});
ChainOfThoughtPrimitiveRoot.displayName = "ChainOfThoughtPrimitive.Root";
//#endregion
export { ChainOfThoughtPrimitiveRoot };
