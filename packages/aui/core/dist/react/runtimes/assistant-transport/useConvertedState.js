import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
//#region src/react/runtimes/assistant-transport/useConvertedState.ts
function useConvertedState(converter, agentState, pendingCommands, isSending, toolStatuses) {
	const $ = c(6);
	let t0;
	if ($[0] !== agentState || $[1] !== converter || $[2] !== isSending || $[3] !== pendingCommands || $[4] !== toolStatuses) {
		t0 = converter(agentState, {
			pendingCommands,
			isSending,
			toolStatuses
		});
		$[0] = agentState;
		$[1] = converter;
		$[2] = isSending;
		$[3] = pendingCommands;
		$[4] = toolStatuses;
		$[5] = t0;
	} else t0 = $[5];
	return t0;
}
//#endregion
export { useConvertedState };
