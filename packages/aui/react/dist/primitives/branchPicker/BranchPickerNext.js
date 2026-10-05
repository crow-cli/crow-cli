"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useBranchPickerNext } from "@assistant-ui/core/react";
//#region src/primitives/branchPicker/BranchPickerNext.ts
const useBranchPickerNext$1 = () => {
	const { disabled, next } = useBranchPickerNext();
	if (disabled) return null;
	return next;
};
/**
* A button component that navigates to the next branch in the message tree.
*
* This component automatically handles switching to the next available branch
* and is disabled when there are no more branches to navigate to.
*
* @example
* ```tsx
* <BranchPickerPrimitive.Next>
*   Next →
* </BranchPickerPrimitive.Next>
* ```
*/
const BranchPickerPrimitiveNext = createActionButton("BranchPickerPrimitive.Next", useBranchPickerNext$1);
//#endregion
export { BranchPickerPrimitiveNext };
