"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useSuggestionTrigger } from "@assistant-ui/core/react";
import { useAuiState } from "@assistant-ui/store";
//#region src/primitives/suggestion/SuggestionTrigger.ts
const useSuggestionTrigger$1 = (t0) => {
	const $ = c(4);
	const { send, clearComposer } = t0;
	const prompt = useAuiState(_temp);
	let t1;
	if ($[0] !== clearComposer || $[1] !== prompt || $[2] !== send) {
		t1 = {
			prompt,
			send,
			clearComposer
		};
		$[0] = clearComposer;
		$[1] = prompt;
		$[2] = send;
		$[3] = t1;
	} else t1 = $[3];
	const { trigger, disabled } = useSuggestionTrigger(t1);
	if (disabled) return null;
	return trigger;
};
/**
* A button that triggers the suggestion action (send or insert into composer).
*
* @example
* ```tsx
* <SuggestionPrimitive.Trigger send>
*   Click me
* </SuggestionPrimitive.Trigger>
* ```
*/
const SuggestionPrimitiveTrigger = createActionButton("SuggestionPrimitive.Trigger", useSuggestionTrigger$1, ["send", "clearComposer"]);
function _temp(s) {
	return s.suggestion.prompt;
}
//#endregion
export { SuggestionPrimitiveTrigger };
