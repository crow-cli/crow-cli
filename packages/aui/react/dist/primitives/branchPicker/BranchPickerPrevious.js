"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useBranchPickerPrevious } from "@assistant-ui/core/react";
//#region src/primitives/branchPicker/BranchPickerPrevious.ts
const useBranchPickerPrevious$1 = () => {
	const { disabled, previous } = useBranchPickerPrevious();
	if (disabled) return null;
	return previous;
};
/**
* A button component that navigates to the previous branch in the message tree.
*
* This component automatically handles switching to the previous available branch
* and is disabled when there are no previous branches to navigate to.
*
* @example
* ```tsx
* <BranchPickerPrimitive.Previous>
*   ← Previous
* </BranchPickerPrimitive.Previous>
* ```
*/
const BranchPickerPrimitivePrevious = createActionButton("BranchPickerPrimitive.Previous", useBranchPickerPrevious$1);
//#endregion
export { BranchPickerPrimitivePrevious };
