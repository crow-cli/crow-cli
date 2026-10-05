import { getProxiedAssistantState } from "./utils/proxied-assistant-state.js";
import { useAui } from "./useAui.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useDebugValue, useSyncExternalStore } from "@assistant-ui/tap/react-shim";
//#region src/useAuiState.ts
/**
* Subscribes to a slice of {@link AssistantState} and re-renders the
* component whenever that slice changes.
*
* The `selector` is called on every store update; its return value is
* compared by `Object.is`, and the component re-renders only when the
* selected slice changes. Returning the entire state object is not
* supported and throws at runtime — select a specific field instead, or
* compose multiple `useAuiState` calls. Returning a new object or array
* literal, including spreading `s.thread` into a new object, causes a
* re-render on every store update; either select primitives or return a
* memoized reference.
*
* Scopes that may be unavailable can be read via `s.optional.<scope>`,
* which resolves to `undefined` instead of throwing.
*
* @param selector - Pure function that derives a value from the current
*   assistant state. Should be cheap and referentially stable for equal
*   inputs (plain field reads, primitives, or memoized values).
* @returns The currently selected slice.
*
* @example
* ```tsx
* // Disable a button while a run is in flight.
* const isRunning = useAuiState((s) => s.thread.isRunning);
* ```
*
* @example
* ```tsx
* // Prefer multiple selectors over an inline object literal, which would
* // create a new reference on every render.
* const text = useAuiState((s) => s.composer.text);
* const canSend = useAuiState((s) => s.composer.canSend);
* ```
*/
const useAuiState = (selector) => {
	const $ = c(6);
	const aui = useAui();
	let t0;
	if ($[0] !== aui) {
		t0 = getProxiedAssistantState(aui);
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const proxiedState = t0;
	let t1;
	let t2;
	if ($[2] !== proxiedState || $[3] !== selector) {
		t1 = () => selector(proxiedState);
		t2 = () => selector(proxiedState);
		$[2] = proxiedState;
		$[3] = selector;
		$[4] = t1;
		$[5] = t2;
	} else {
		t1 = $[4];
		t2 = $[5];
	}
	const slice = useSyncExternalStore(aui.subscribe, t1, t2);
	if (typeof slice === "object" && slice !== null && (slice === proxiedState || slice === proxiedState.optional)) throw new Error("You tried to return the entire AssistantState. This is not supported due to technical limitations.");
	useDebugValue(slice);
	return slice;
};
//#endregion
export { useAuiState };
