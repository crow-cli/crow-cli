"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { ThreadListCollection, useThreadListItemFocus } from "../threadListFocusGroup.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useThreadListItemTrigger } from "@assistant-ui/core/react";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { useComposedRefs } from "radix-ui/internal";
//#region src/primitives/threadListItem/ThreadListItemTrigger.tsx
const useThreadListItemTrigger$1 = () => {
	const { switchTo } = useThreadListItemTrigger();
	return switchTo;
};
const ThreadListItemTriggerButton = createActionButton("ThreadListItemPrimitive.Trigger", useThreadListItemTrigger$1);
const ThreadListItemPrimitiveTrigger = forwardRef((props, forwardedRef) => {
	const $ = c(3);
	const focus = useThreadListItemFocus();
	const ref = useComposedRefs(forwardedRef, focus?.triggerRef);
	let t0;
	if ($[0] !== props || $[1] !== ref) {
		t0 = /* @__PURE__ */ jsx(ThreadListCollection.ItemSlot, {
			scope: void 0,
			children: /* @__PURE__ */ jsx(ThreadListItemTriggerButton, {
				...props,
				ref
			})
		});
		$[0] = props;
		$[1] = ref;
		$[2] = t0;
	} else t0 = $[2];
	return t0;
});
ThreadListItemPrimitiveTrigger.displayName = "ThreadListItemPrimitive.Trigger";
//#endregion
export { ThreadListItemPrimitiveTrigger };
