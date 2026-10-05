import { markDerivedHook } from "./utils/derived-hook.js";
import { useAui } from "./useAui.js";
import { useAuiState } from "./useAuiState.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { resource } from "@assistant-ui/tap";
//#region src/Derived.ts
const useDerived = (t0) => {
	const $ = c(3);
	const { get } = t0;
	const aui = useAui();
	let t1;
	if ($[0] !== aui || $[1] !== get) {
		t1 = () => get(aui);
		$[0] = aui;
		$[1] = get;
		$[2] = t1;
	} else t1 = $[2];
	return useAuiState(t1);
};
markDerivedHook(useDerived);
/**
* Creates a derived client field whose resolved instance is bound into the
* client returned by `useAui`; a structural swap produces a new client through
* a React re-render. `get` must return a client created via
* `useClientResource` (or `useClientLookup`/`useClientList`).
*
* @example
* ```tsx
* const aui = useAui();
* const config = AuiConfig({
*   message: Derived({
*     source: "thread",
*     query: { index: 0 },
*     get: (aui) => aui.thread.message({ index: 0 }),
*   }),
* });
*
* <AuiProvider extends={aui} config={config}>{children}</AuiProvider>;
* ```
*/
const Derived = resource(useDerived);
//#endregion
export { Derived, useDerived };
