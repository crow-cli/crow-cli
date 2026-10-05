import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useActionBarSpeak.ts
const useActionBarSpeak = () => {
	const $ = c(5);
	const aui = useAui();
	const disabled = useAuiState(_temp2);
	let t0;
	if ($[0] !== aui) {
		t0 = async () => {
			aui.message.speak();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const speak = t0;
	let t1;
	if ($[2] !== disabled || $[3] !== speak) {
		t1 = {
			speak,
			disabled
		};
		$[2] = disabled;
		$[3] = speak;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
function _temp(c) {
	return c.type === "text" && c.text.length > 0;
}
function _temp2(s) {
	return !((s.message.role !== "assistant" || s.message.status?.type !== "running") && s.message.parts.some(_temp));
}
//#endregion
export { useActionBarSpeak };
