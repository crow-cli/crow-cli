"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useSuggestionTrigger } from "@assistant-ui/core/react";
//#region src/primitives/thread/ThreadSuggestion.ts
const useThreadSuggestion = (t0) => {
	const $ = c(4);
	const { prompt, send, clearComposer, autoSend } = t0;
	const resolvedSend = send ?? autoSend ?? false;
	let t1;
	if ($[0] !== clearComposer || $[1] !== prompt || $[2] !== resolvedSend) {
		t1 = {
			prompt,
			send: resolvedSend,
			clearComposer
		};
		$[0] = clearComposer;
		$[1] = prompt;
		$[2] = resolvedSend;
		$[3] = t1;
	} else t1 = $[3];
	const { disabled, trigger } = useSuggestionTrigger(t1);
	if (disabled) return null;
	return trigger;
};
const ThreadPrimitiveSuggestion = createActionButton("ThreadPrimitive.Suggestion", useThreadSuggestion, [
	"prompt",
	"send",
	"clearComposer",
	"autoSend",
	"method"
]);
//#endregion
export { ThreadPrimitiveSuggestion };
