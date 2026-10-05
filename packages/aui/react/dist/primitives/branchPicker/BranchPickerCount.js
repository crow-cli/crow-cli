"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useAuiState } from "@assistant-ui/store";
import { Fragment, jsx } from "react/jsx-runtime";
//#region src/primitives/branchPicker/BranchPickerCount.tsx
const useBranchPickerCount = () => {
	return useAuiState(_temp);
};
/**
* A component that displays the total number of branches for the current message.
*
* This component renders the branch count as plain text, useful for showing
* users how many alternative responses are available.
*
* @example
* ```tsx
* <div>
*   Branch <BranchPickerPrimitive.Count /> of {totalBranches}
* </div>
* ```
*/
const BranchPickerPrimitiveCount = () => {
	const $ = c(2);
	const branchCount = useBranchPickerCount();
	let t0;
	if ($[0] !== branchCount) {
		t0 = /* @__PURE__ */ jsx(Fragment, { children: branchCount });
		$[0] = branchCount;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
};
BranchPickerPrimitiveCount.displayName = "BranchPickerPrimitive.Count";
function _temp(s) {
	return s.message.branchCount;
}
//#endregion
export { BranchPickerPrimitiveCount };
