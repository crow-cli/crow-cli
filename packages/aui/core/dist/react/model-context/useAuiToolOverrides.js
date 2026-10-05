import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useInsertionEffect, useRef } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/model-context/useAuiToolOverrides.ts
/**
* Overrides toolkit entries for the current assistant scope.
*
* This is intended for dynamic local-state tools whose model-facing contract is
* declared in a `"use generative"` toolkit file with `execute: stubTool()`, but
* whose actual executor must close over React state in the mounted component.
* Keep the override keys stable after mount; dynamic key addition/removal is not
* currently observed.
* Overrides are registered at priority 1000, above toolkit defaults. Only one
* mounted override provider may define a given tool name at a time.
*
* @deprecated Experimental, API may change.
*/
function useAuiToolOverrides(overrides) {
	const $ = c(7);
	const aui = useAui();
	const overridesRef = useRef(overrides);
	let t0;
	let t1;
	if ($[0] !== overrides) {
		t0 = () => {
			overridesRef.current = overrides;
		};
		t1 = [overrides];
		$[0] = overrides;
		$[1] = t0;
		$[2] = t1;
	} else {
		t0 = $[1];
		t1 = $[2];
	}
	useInsertionEffect(t0, t1);
	let t2;
	if ($[3] !== aui.modelContext) {
		t2 = () => aui.modelContext.register({ getModelContext: () => ({
			priority: 1e3,
			tools: overridesRef.current
		}) });
		$[3] = aui.modelContext;
		$[4] = t2;
	} else t2 = $[4];
	let t3;
	if ($[5] !== aui) {
		t3 = [aui];
		$[5] = aui;
		$[6] = t3;
	} else t3 = $[6];
	useEffect(t2, t3);
}
//#endregion
export { useAuiToolOverrides };
