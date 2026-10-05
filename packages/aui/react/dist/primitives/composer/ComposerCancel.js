"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useComposerCancel } from "@assistant-ui/core/react";
//#region src/primitives/composer/ComposerCancel.ts
const useComposerCancel$1 = () => {
	const { disabled, cancel } = useComposerCancel();
	if (disabled) return null;
	return cancel;
};
/**
* A button component that cancels the current message composition.
*
* This component automatically handles the cancel functionality and is disabled
* when canceling is not available.
*
* @example
* ```tsx
* <ComposerPrimitive.Cancel>
*   Cancel
* </ComposerPrimitive.Cancel>
* ```
*/
const ComposerPrimitiveCancel = createActionButton("ComposerPrimitive.Cancel", useComposerCancel$1);
//#endregion
export { ComposerPrimitiveCancel };
