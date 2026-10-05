import { unstable_getInteractableVersions } from "../../model-context/interactable-composer-metadata.js";
import { useJSONEqual } from "../utils/useJSONEqual.js";
import { unstable_useInteractableState } from "./useInteractableState.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
//#region src/react/model-context/useInteractableVersions.ts
const useInteractableVersions = (id, name) => {
	const $ = c(8);
	let t0;
	if ($[0] !== id || $[1] !== name) {
		t0 = (s) => unstable_getInteractableVersions(s.thread.messages, id, name);
		$[0] = id;
		$[1] = name;
		$[2] = t0;
	} else t0 = $[2];
	const versions = useAuiState(useJSONEqual(t0));
	const [, t1] = unstable_useInteractableState(id);
	const { setState } = t1;
	let t2;
	if ($[3] !== setState || $[4] !== versions) {
		let t3;
		if ($[6] !== setState) {
			t3 = (v) => ({
				...v,
				state: v.state,
				restore: () => setState(v.state)
			});
			$[6] = setState;
			$[7] = t3;
		} else t3 = $[7];
		t2 = versions.map(t3);
		$[3] = setState;
		$[4] = versions;
		$[5] = t2;
	} else t2 = $[5];
	return t2;
};
/**
* Every version of a tool-created interactable recorded in the current
* thread, oldest first: the creating tool call, each user edit, and each
* `update_*` call. Each entry carries the full state as of that version and a
* `restore()` that sets the live instance back to it — enough for a version
* picker like an artifact's history dropdown.
*
* @deprecated Unstable / Experimental (not actually removed).
*/
const unstable_useInteractableVersions = useInteractableVersions;
//#endregion
export { unstable_useInteractableVersions };
