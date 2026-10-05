import { normalizeEventSelector } from "./types/events.js";
import { useAui } from "./useAui.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useEffectEvent } from "@assistant-ui/tap/react-shim";
//#region src/useAuiEvent.ts
/**
* Subscribes to an assistant event for the lifetime of the component.
*
* The subscription is established on mount and re-established whenever the
* scope or event name changes. The `callback` is wrapped in an effect-event
* shim, so the latest closure is invoked on each emission — you do not
* need to memoize it.
*
* @param selector - Either a dotted event name like
*   `"thread.modelContextUpdate"` or an object `{ scope, event }`. Use
*   `scope: "*"` to subscribe at the root client and receive emissions
*   from any descendant scope, regardless of which one is in React
*   context.
* @param callback - Invoked with the event payload. The most recent
*   reference is always called. Return values are ignored, async callbacks
*   are not awaited, and the callback cannot be called during render.
*
* @example
* ```tsx
* // React to transient model-context changes.
* useAuiEvent("thread.modelContextUpdate", ({ threadId }) => {
*   analytics.track("model_context_update", { threadId });
* });
* ```
*
* @example
* ```tsx
* // React to thread switches.
* useAuiEvent("threads.selectionChanged", () => {
*   resetLocalState();
* });
* ```
*
* @example
* ```tsx
* // Listen from the root client rather than the current React context.
* useAuiEvent({ scope: "*", event: "thread.modelContextUpdate" }, (payload) => {
*   analytics.track("model_context_update", payload);
* });
* ```
*/
const useAuiEvent = (selector, callback) => {
	const $ = c(11);
	const aui = useAui();
	const callbackRef = useEffectEvent(callback);
	let t0;
	if ($[0] !== selector) {
		t0 = normalizeEventSelector(selector);
		$[0] = selector;
		$[1] = t0;
	} else t0 = $[1];
	const { scope, event } = t0;
	let t1;
	if ($[2] !== aui || $[3] !== callbackRef || $[4] !== event || $[5] !== scope) {
		t1 = () => aui.on({
			scope,
			event
		}, callbackRef);
		$[2] = aui;
		$[3] = callbackRef;
		$[4] = event;
		$[5] = scope;
		$[6] = t1;
	} else t1 = $[6];
	let t2;
	if ($[7] !== aui || $[8] !== event || $[9] !== scope) {
		t2 = [
			aui,
			scope,
			event
		];
		$[7] = aui;
		$[8] = event;
		$[9] = scope;
		$[10] = t2;
	} else t2 = $[10];
	useEffect(t1, t2);
};
//#endregion
export { useAuiEvent };
