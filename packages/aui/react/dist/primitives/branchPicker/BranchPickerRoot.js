"use client";
import { Primitive } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { AuiIf } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/branchPicker/BranchPickerRoot.tsx
/**
* The root container for branch picker components.
*
* This component provides a container for branch navigation controls,
* with optional conditional rendering based on the number of available branches.
* It integrates with the message branching system to allow users to navigate
* between different response variations.
*
* @example
* ```tsx
* <BranchPickerPrimitive.Root hideWhenSingleBranch={true}>
*   <BranchPickerPrimitive.Previous />
*   <BranchPickerPrimitive.Count />
*   <BranchPickerPrimitive.Next />
* </BranchPickerPrimitive.Root>
* ```
*/
const BranchPickerPrimitiveRoot = forwardRef((t0, ref) => {
	const $ = c(11);
	let hideWhenSingleBranch;
	let rest;
	if ($[0] !== t0) {
		({hideWhenSingleBranch, ...rest} = t0);
		$[0] = t0;
		$[1] = hideWhenSingleBranch;
		$[2] = rest;
	} else {
		hideWhenSingleBranch = $[1];
		rest = $[2];
	}
	let t1;
	if ($[3] !== hideWhenSingleBranch) {
		t1 = (s) => !hideWhenSingleBranch || s.message.branchCount >= 2;
		$[3] = hideWhenSingleBranch;
		$[4] = t1;
	} else t1 = $[4];
	let t2;
	if ($[5] !== ref || $[6] !== rest) {
		t2 = /* @__PURE__ */ jsx(Primitive.div, {
			...rest,
			ref
		});
		$[5] = ref;
		$[6] = rest;
		$[7] = t2;
	} else t2 = $[7];
	let t3;
	if ($[8] !== t1 || $[9] !== t2) {
		t3 = /* @__PURE__ */ jsx(AuiIf, {
			condition: t1,
			children: t2
		});
		$[8] = t1;
		$[9] = t2;
		$[10] = t3;
	} else t3 = $[10];
	return t3;
});
BranchPickerPrimitiveRoot.displayName = "BranchPickerPrimitive.Root";
//#endregion
export { BranchPickerPrimitiveRoot };
