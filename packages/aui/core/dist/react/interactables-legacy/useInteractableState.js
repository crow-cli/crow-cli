import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/interactables-legacy/useInteractableState.ts
/**
* Reads and writes the state of a registered interactable.
*
* Pair with {@link useAssistantInteractable} which handles registration.
*
* @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API.
* Scheduled for removal on/after 2026-09-14. See
* {@link https://www.assistant-ui.com/docs/tools/interactables#migrating-from-the-previous-api | Interactables migration guide}.
*/
const useInteractableState = (id, fallback) => {
	const $ = c(19);
	const aui = useAui();
	const state = useAuiState((s) => s.interactables.definitions[id]?.state) ?? fallback;
	let t0;
	if ($[0] !== id) {
		t0 = (s_0) => s_0.interactables.persistence[id];
		$[0] = id;
		$[1] = t0;
	} else t0 = $[1];
	const persistenceStatus = useAuiState(t0);
	let t1;
	if ($[2] !== aui || $[3] !== id) {
		t1 = (updater) => {
			aui.interactables.setState(id, (prev) => {
				if (typeof updater === "function") return updater(prev);
				return updater;
			});
		};
		$[2] = aui;
		$[3] = id;
		$[4] = t1;
	} else t1 = $[4];
	const setState = t1;
	let t2;
	if ($[5] !== aui || $[6] !== id) {
		t2 = (selected) => {
			aui.interactables.setSelected(id, selected);
		};
		$[5] = aui;
		$[6] = id;
		$[7] = t2;
	} else t2 = $[7];
	const setSelected = t2;
	let t3;
	if ($[8] !== aui) {
		t3 = () => aui.interactables.flush();
		$[8] = aui;
		$[9] = t3;
	} else t3 = $[9];
	const flush = t3;
	const t4 = persistenceStatus?.isPending ?? false;
	const t5 = persistenceStatus?.error;
	let t6;
	if ($[10] !== flush || $[11] !== setSelected || $[12] !== setState || $[13] !== t4 || $[14] !== t5) {
		t6 = {
			setState,
			setSelected,
			isPending: t4,
			error: t5,
			flush
		};
		$[10] = flush;
		$[11] = setSelected;
		$[12] = setState;
		$[13] = t4;
		$[14] = t5;
		$[15] = t6;
	} else t6 = $[15];
	let t7;
	if ($[16] !== state || $[17] !== t6) {
		t7 = [state, t6];
		$[16] = state;
		$[17] = t6;
		$[18] = t7;
	} else t7 = $[18];
	return t7;
};
//#endregion
export { useInteractableState };
