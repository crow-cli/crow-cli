"use client";
import { Primitive } from "../../utils/Primitive.js";
import { HideAndFloatStatus, useActionBarFloatStatus } from "./useActionBarFloatStatus.js";
import { ActionBarInteractionContext } from "./ActionBarInteractionContext.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef, useState } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/actionBar/ActionBarRoot.tsx
/**
* The root container for action bar components.
*
* This component provides intelligent visibility and floating behavior for action bars,
* automatically hiding and showing based on message state, hover status, and configuration.
* It supports floating mode for better UX when space is limited.
*
* @example
* ```tsx
* <ActionBarPrimitive.Root
*   hideWhenRunning={true}
*   autohide="not-last"
*   autohideFloat="single-branch"
* >
*   <ActionBarPrimitive.Copy />
*   <ActionBarPrimitive.Edit />
*   <ActionBarPrimitive.Reload />
* </ActionBarPrimitive.Root>
* ```
*/
const ActionBarPrimitiveRoot = forwardRef((t0, ref) => {
	const $ = c(18);
	let autohide;
	let autohideFloat;
	let hideWhenRunning;
	let rest;
	if ($[0] !== t0) {
		({hideWhenRunning, autohide, autohideFloat, ...rest} = t0);
		$[0] = t0;
		$[1] = autohide;
		$[2] = autohideFloat;
		$[3] = hideWhenRunning;
		$[4] = rest;
	} else {
		autohide = $[1];
		autohideFloat = $[2];
		hideWhenRunning = $[3];
		rest = $[4];
	}
	const [interactionCount, setInteractionCount] = useState(0);
	let t1;
	if ($[5] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = () => {
			let released = false;
			setInteractionCount(_temp);
			return () => {
				if (released) return;
				released = true;
				setInteractionCount(_temp2);
			};
		};
		$[5] = t1;
	} else t1 = $[5];
	const acquireInteractionLock = t1;
	let t2;
	if ($[6] === Symbol.for("react.memo_cache_sentinel")) {
		t2 = { acquireInteractionLock };
		$[6] = t2;
	} else t2 = $[6];
	const interactionContext = t2;
	const t3 = interactionCount > 0;
	let t4;
	if ($[7] !== autohide || $[8] !== autohideFloat || $[9] !== hideWhenRunning || $[10] !== t3) {
		t4 = {
			hideWhenRunning,
			autohide,
			autohideFloat,
			forceVisible: t3
		};
		$[7] = autohide;
		$[8] = autohideFloat;
		$[9] = hideWhenRunning;
		$[10] = t3;
		$[11] = t4;
	} else t4 = $[11];
	const hideAndfloatStatus = useActionBarFloatStatus(t4);
	if (hideAndfloatStatus === HideAndFloatStatus.Hidden) return null;
	let t5;
	if ($[12] !== hideAndfloatStatus) {
		t5 = hideAndfloatStatus === HideAndFloatStatus.Floating ? { "data-floating": "true" } : null;
		$[12] = hideAndfloatStatus;
		$[13] = t5;
	} else t5 = $[13];
	let t6;
	if ($[14] !== ref || $[15] !== rest || $[16] !== t5) {
		t6 = /* @__PURE__ */ jsx(ActionBarInteractionContext.Provider, {
			value: interactionContext,
			children: /* @__PURE__ */ jsx(Primitive.div, {
				...t5,
				...rest,
				ref
			})
		});
		$[14] = ref;
		$[15] = rest;
		$[16] = t5;
		$[17] = t6;
	} else t6 = $[17];
	return t6;
});
ActionBarPrimitiveRoot.displayName = "ActionBarPrimitive.Root";
function _temp(count) {
	return count + 1;
}
function _temp2(count_0) {
	return Math.max(0, count_0 - 1);
}
//#endregion
export { ActionBarPrimitiveRoot };
