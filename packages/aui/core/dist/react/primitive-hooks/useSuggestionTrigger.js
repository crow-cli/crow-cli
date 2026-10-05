import { suggestionSendMode, suggestionTriggerDisabled } from "../../store/primitive-predicates.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useSuggestionTrigger.ts
const useSuggestionTrigger = (t0) => {
	const $ = c(10);
	const { prompt, send, clearComposer: t1 } = t0;
	const clearComposer = t1 === void 0 ? true : t1;
	const aui = useAui();
	const resolvedSend = send ?? false;
	let t2;
	if ($[0] !== resolvedSend) {
		t2 = (s) => suggestionTriggerDisabled(s, resolvedSend);
		$[0] = resolvedSend;
		$[1] = t2;
	} else t2 = $[1];
	const disabled = useAuiState(t2);
	let t3;
	if ($[2] !== aui || $[3] !== clearComposer || $[4] !== prompt || $[5] !== resolvedSend) {
		t3 = () => {
			if (resolvedSend) {
				const mode = suggestionSendMode(aui.thread.getState());
				if (mode === "blocked") return;
				aui.thread.append({
					content: [{
						type: "text",
						text: prompt
					}],
					runConfig: aui.composer.getState().runConfig
				});
				if (clearComposer && mode === "now") aui.composer.setText("");
			} else if (clearComposer) aui.composer.setText(prompt);
			else {
				const currentText = aui.composer.getState().text;
				aui.composer.setText([currentText, prompt].filter(_temp).join(" "));
			}
		};
		$[2] = aui;
		$[3] = clearComposer;
		$[4] = prompt;
		$[5] = resolvedSend;
		$[6] = t3;
	} else t3 = $[6];
	const trigger = t3;
	let t4;
	if ($[7] !== disabled || $[8] !== trigger) {
		t4 = {
			trigger,
			disabled
		};
		$[7] = disabled;
		$[8] = trigger;
		$[9] = t4;
	} else t4 = $[9];
	return t4;
};
function _temp(part) {
	return part.trim();
}
//#endregion
export { useSuggestionTrigger };
