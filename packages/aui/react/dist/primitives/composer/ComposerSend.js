"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useComposerSend as useComposerSend$1 } from "@assistant-ui/core/react";
import "@assistant-ui/tap/react-shim";
//#region src/primitives/composer/ComposerSend.ts
const useComposerSend = () => {
	const $ = c(2);
	const { disabled, send } = useComposerSend$1();
	let t0;
	if ($[0] !== send) {
		t0 = () => send();
		$[0] = send;
		$[1] = t0;
	} else t0 = $[1];
	const callback = t0;
	if (disabled) return null;
	return callback;
};
/**
* A button component that sends the current message in the composer.
*
* This component automatically handles the send functionality and is disabled
* when sending is not available (e.g., when the thread is running, the composer
* is empty, or not in editing mode).
*
* @example
* ```tsx
* <ComposerPrimitive.Send>
*   Send Message
* </ComposerPrimitive.Send>
* ```
*/
const ComposerPrimitiveSend = createActionButton("ComposerPrimitive.Send", useComposerSend);
//#endregion
export { ComposerPrimitiveSend, useComposerSend };
