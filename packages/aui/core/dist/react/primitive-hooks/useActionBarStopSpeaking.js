import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useActionBarStopSpeaking.ts
const useActionBarStopSpeaking = () => {
	const $ = c(5);
	const aui = useAui();
	const disabled = useAuiState(_temp);
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.message.stopSpeaking();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const stopSpeaking = t0;
	let t1;
	if ($[2] !== disabled || $[3] !== stopSpeaking) {
		t1 = {
			stopSpeaking,
			disabled
		};
		$[2] = disabled;
		$[3] = stopSpeaking;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
function _temp(s) {
	return s.message.speech == null;
}
//#endregion
export { useActionBarStopSpeaking };
