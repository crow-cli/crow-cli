"use client";
import { DropdownMenuRenderTrigger } from "../dropdownMenuRenderPrimitives.js";
import { useThreadListItemFocus } from "../threadListFocusGroup.js";
import { useDropdownMenuScope } from "./scope.js";
import { useThreadListItemMoreSetOpen, useThreadListItemMoreSharedFocusGroup } from "./ThreadListItemMoreRoot.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers, useComposedRefs } from "radix-ui/internal";
import { Direction } from "radix-ui";
//#region src/primitives/threadListItemMore/ThreadListItemMoreTrigger.tsx
const ThreadListItemMorePrimitiveTrigger = forwardRef((t0, ref) => {
	const $ = c(10);
	const { __scopeThreadListItemMore, ...rest } = t0;
	const scope = useDropdownMenuScope(__scopeThreadListItemMore);
	const focus = useThreadListItemFocus();
	const setOpen = useThreadListItemMoreSetOpen();
	const sharedFocusGroup = useThreadListItemMoreSharedFocusGroup();
	const composedRef = useComposedRefs(ref, focus?.moreRef);
	const openKey = Direction.useDirection() === "rtl" ? "ArrowLeft" : "ArrowRight";
	const T0 = DropdownMenuRenderTrigger;
	let t1;
	if ($[0] !== openKey || $[1] !== setOpen || $[2] !== sharedFocusGroup) {
		t1 = (event) => {
			if (!sharedFocusGroup || event.key !== openKey) return;
			if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
			event.preventDefault();
			setOpen(true);
		};
		$[0] = openKey;
		$[1] = setOpen;
		$[2] = sharedFocusGroup;
		$[3] = t1;
	} else t1 = $[3];
	const t2 = composeEventHandlers(rest.onKeyDown, t1);
	let t3;
	if ($[4] !== T0 || $[5] !== composedRef || $[6] !== rest || $[7] !== scope || $[8] !== t2) {
		t3 = /* @__PURE__ */ jsx(T0, {
			...scope,
			...rest,
			onKeyDown: t2,
			ref: composedRef
		});
		$[4] = T0;
		$[5] = composedRef;
		$[6] = rest;
		$[7] = scope;
		$[8] = t2;
		$[9] = t3;
	} else t3 = $[9];
	return t3;
});
ThreadListItemMorePrimitiveTrigger.displayName = "ThreadListItemMorePrimitive.Trigger";
//#endregion
export { ThreadListItemMorePrimitiveTrigger };
