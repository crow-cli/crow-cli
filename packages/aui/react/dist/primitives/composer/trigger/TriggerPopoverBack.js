"use client";
import { Primitive as Primitive$1 } from "../../../utils/Primitive.js";
import { useTriggerPopoverScopeContext } from "./TriggerPopover.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/composer/trigger/TriggerPopoverBack.tsx
/**
* A button that navigates back from category items to the category list.
* Only renders when a category is active (drill-down view).
*/
const ComposerPrimitiveTriggerPopoverBack = forwardRef((t0, forwardedRef) => {
	const $ = c(10);
	let onClick;
	let props;
	if ($[0] !== t0) {
		({onClick, ...props} = t0);
		$[0] = t0;
		$[1] = onClick;
		$[2] = props;
	} else {
		onClick = $[1];
		props = $[2];
	}
	const { activeCategoryId, isSearchMode, goBack, open } = useTriggerPopoverScopeContext();
	if (!open || !activeCategoryId || isSearchMode) return null;
	let t1;
	if ($[3] !== goBack || $[4] !== onClick) {
		t1 = composeEventHandlers(onClick, goBack);
		$[3] = goBack;
		$[4] = onClick;
		$[5] = t1;
	} else t1 = $[5];
	let t2;
	if ($[6] !== forwardedRef || $[7] !== props || $[8] !== t1) {
		t2 = /* @__PURE__ */ jsx(Primitive$1.button, {
			type: "button",
			...props,
			ref: forwardedRef,
			onClick: t1
		});
		$[6] = forwardedRef;
		$[7] = props;
		$[8] = t1;
		$[9] = t2;
	} else t2 = $[9];
	return t2;
});
ComposerPrimitiveTriggerPopoverBack.displayName = "ComposerPrimitive.TriggerPopoverBack";
//#endregion
export { ComposerPrimitiveTriggerPopoverBack };
