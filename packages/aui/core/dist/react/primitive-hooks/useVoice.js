import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useSyncExternalStore } from "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useVoice.ts
const useVoiceState = () => {
	return useAuiState(_temp);
};
const getServerVolume = () => 0;
const useVoiceVolume = () => {
	const thread = useAui().thread;
	return useSyncExternalStore(thread.subscribeVoiceVolume, thread.getVoiceVolume, getServerVolume);
};
const useVoiceControls = () => {
	const $ = c(13);
	const aui = useAui();
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.thread.connectVoice();
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const connect = t0;
	let t1;
	if ($[2] !== aui) {
		t1 = () => {
			aui.thread.disconnectVoice();
		};
		$[2] = aui;
		$[3] = t1;
	} else t1 = $[3];
	const disconnect = t1;
	let t2;
	if ($[4] !== aui) {
		t2 = () => {
			aui.thread.muteVoice();
		};
		$[4] = aui;
		$[5] = t2;
	} else t2 = $[5];
	const mute = t2;
	let t3;
	if ($[6] !== aui) {
		t3 = () => {
			aui.thread.unmuteVoice();
		};
		$[6] = aui;
		$[7] = t3;
	} else t3 = $[7];
	const unmute = t3;
	let t4;
	if ($[8] !== connect || $[9] !== disconnect || $[10] !== mute || $[11] !== unmute) {
		t4 = {
			connect,
			disconnect,
			mute,
			unmute
		};
		$[8] = connect;
		$[9] = disconnect;
		$[10] = mute;
		$[11] = unmute;
		$[12] = t4;
	} else t4 = $[12];
	return t4;
};
function _temp(s) {
	return s.thread.voice;
}
//#endregion
export { useVoiceControls, useVoiceState, useVoiceVolume };
