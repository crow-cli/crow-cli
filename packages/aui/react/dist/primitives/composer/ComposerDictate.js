"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useComposerDictate } from "@assistant-ui/core/react";
//#region src/primitives/composer/ComposerDictate.ts
const useComposerDictate$1 = () => {
	const { disabled, startDictation } = useComposerDictate();
	if (disabled) return null;
	return startDictation;
};
/**
* A button that starts dictation to convert voice to text.
*
* Requires a DictationAdapter to be configured in the runtime.
*
* @example
* ```tsx
* <ComposerPrimitive.Dictate>
*   <MicIcon />
* </ComposerPrimitive.Dictate>
* ```
*/
const ComposerPrimitiveDictate = createActionButton("ComposerPrimitive.Dictate", useComposerDictate$1);
//#endregion
export { ComposerPrimitiveDictate };
