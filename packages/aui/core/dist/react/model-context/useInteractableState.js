"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/model-context/useInteractableState.ts
const useInteractableState = (id) => {
	const $ = c(17);
	const aui = useAui();
	let t0;
	if ($[0] !== id) {
		t0 = (s) => s.unstable_interactables.definitions[id]?.state;
		$[0] = id;
		$[1] = t0;
	} else t0 = $[1];
	const state = useAuiState(t0);
	let t1;
	if ($[2] !== id) {
		t1 = (s_0) => s_0.unstable_interactables.persistence[id];
		$[2] = id;
		$[3] = t1;
	} else t1 = $[3];
	const persistenceStatus = useAuiState(t1);
	let t2;
	if ($[4] !== aui || $[5] !== id) {
		t2 = (updater) => {
			aui.unstable_interactables.setState(id, (prev) => {
				if (typeof updater === "function") return updater(prev);
				return updater;
			});
		};
		$[4] = aui;
		$[5] = id;
		$[6] = t2;
	} else t2 = $[6];
	const setState = t2;
	let t3;
	if ($[7] !== aui) {
		t3 = () => aui.unstable_interactables.flush();
		$[7] = aui;
		$[8] = t3;
	} else t3 = $[8];
	const flush = t3;
	const t4 = persistenceStatus?.isPending ?? false;
	const t5 = persistenceStatus?.error;
	let t6;
	if ($[9] !== flush || $[10] !== setState || $[11] !== t4 || $[12] !== t5) {
		t6 = {
			setState,
			isPending: t4,
			error: t5,
			flush
		};
		$[9] = flush;
		$[10] = setState;
		$[11] = t4;
		$[12] = t5;
		$[13] = t6;
	} else t6 = $[13];
	let t7;
	if ($[14] !== state || $[15] !== t6) {
		t7 = [state, t6];
		$[14] = state;
		$[15] = t6;
		$[16] = t7;
	} else t7 = $[16];
	return t7;
};
/**
* Reads and writes the state of an interactable registered elsewhere, by id.
*
* Use this from secondary readers (children, siblings); the owning component
* registers with `unstable_useInteractable`, which returns state directly. Returns
* `undefined` until the owning interactable is registered.
*
* @deprecated Unstable / Experimental (not actually removed).
*/
const unstable_useInteractableState = useInteractableState;
//#endregion
export { unstable_useInteractableState };
