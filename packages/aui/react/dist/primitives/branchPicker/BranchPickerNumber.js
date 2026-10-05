"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useAuiState } from "@assistant-ui/store";
import { Fragment, jsx } from "react/jsx-runtime";
//#region src/primitives/branchPicker/BranchPickerNumber.tsx
const useBranchPickerNumber = () => {
	return useAuiState(_temp);
};
const BranchPickerPrimitiveNumber = () => {
	const $ = c(2);
	const branchNumber = useBranchPickerNumber();
	let t0;
	if ($[0] !== branchNumber) {
		t0 = /* @__PURE__ */ jsx(Fragment, { children: branchNumber });
		$[0] = branchNumber;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
};
BranchPickerPrimitiveNumber.displayName = "BranchPickerPrimitive.Number";
function _temp(s) {
	return s.message.branchNumber;
}
//#endregion
export { BranchPickerPrimitiveNumber };
