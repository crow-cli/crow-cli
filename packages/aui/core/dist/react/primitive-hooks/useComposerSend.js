import { composerSendDisabled } from "../../store/primitive-predicates.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useComposerSend.ts
const useComposerSend = () => {
	const $ = c(5);
	const aui = useAui();
	const disabled = useAuiState(composerSendDisabled);
	let t0;
	if ($[0] !== aui) {
		t0 = (opts) => {
			aui.composer.send(opts);
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const send = t0;
	let t1;
	if ($[2] !== disabled || $[3] !== send) {
		t1 = {
			send,
			disabled
		};
		$[2] = disabled;
		$[3] = send;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
//#endregion
export { useComposerSend };
