"use client";
import { DropdownMenuRenderContent } from "../dropdownMenuRenderPrimitives.js";
import { useThreadListItemFocus } from "../threadListFocusGroup.js";
import { useDropdownMenuScope } from "./scope.js";
import { useThreadListItemMoreSetOpen, useThreadListItemMoreSharedFocusGroup } from "./ThreadListItemMoreRoot.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
import { Direction, DropdownMenu } from "radix-ui";
//#region src/primitives/threadListItemMore/ThreadListItemMoreContent.tsx
const ThreadListItemMorePrimitiveContent = forwardRef((t0, forwardedRef) => {
	const $ = c(21);
	const { __scopeThreadListItemMore, portalProps, sideOffset: t1, ...props } = t0;
	const sideOffset = t1 === void 0 ? 4 : t1;
	const scope = useDropdownMenuScope(__scopeThreadListItemMore);
	const setOpen = useThreadListItemMoreSetOpen();
	const focus = useThreadListItemFocus();
	const sharedFocusGroup = useThreadListItemMoreSharedFocusGroup();
	const closeKey = Direction.useDirection() === "rtl" ? "ArrowRight" : "ArrowLeft";
	const t2 = DropdownMenu;
	const T0 = DropdownMenuRenderContent;
	let t3;
	if ($[0] !== closeKey || $[1] !== focus?.moreRef || $[2] !== setOpen || $[3] !== sharedFocusGroup) {
		t3 = (event) => {
			if (!sharedFocusGroup || event.key !== closeKey) return;
			if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
			event.preventDefault();
			setOpen(false);
			focus?.moreRef.current?.focus();
		};
		$[0] = closeKey;
		$[1] = focus?.moreRef;
		$[2] = setOpen;
		$[3] = sharedFocusGroup;
		$[4] = t3;
	} else t3 = $[4];
	const t4 = composeEventHandlers(props.onKeyDown, t3);
	let t5;
	if ($[5] !== focus?.moreRef || $[6] !== sharedFocusGroup) {
		t5 = () => {
			if (!sharedFocusGroup) return;
			focus?.moreRef.current?.focus();
		};
		$[5] = focus?.moreRef;
		$[6] = sharedFocusGroup;
		$[7] = t5;
	} else t5 = $[7];
	const t6 = composeEventHandlers(props.onEscapeKeyDown, t5);
	let t7;
	if ($[8] !== T0 || $[9] !== forwardedRef || $[10] !== props || $[11] !== scope || $[12] !== sideOffset || $[13] !== t4 || $[14] !== t6) {
		t7 = /* @__PURE__ */ jsx(T0, {
			...scope,
			...props,
			onKeyDown: t4,
			onEscapeKeyDown: t6,
			ref: forwardedRef,
			sideOffset
		});
		$[8] = T0;
		$[9] = forwardedRef;
		$[10] = props;
		$[11] = scope;
		$[12] = sideOffset;
		$[13] = t4;
		$[14] = t6;
		$[15] = t7;
	} else t7 = $[15];
	let t8;
	if ($[16] !== portalProps || $[17] !== scope || $[18] !== t2.Portal || $[19] !== t7) {
		t8 = /* @__PURE__ */ jsx(t2.Portal, {
			...scope,
			...portalProps,
			children: t7
		});
		$[16] = portalProps;
		$[17] = scope;
		$[18] = t2.Portal;
		$[19] = t7;
		$[20] = t8;
	} else t8 = $[20];
	return t8;
});
ThreadListItemMorePrimitiveContent.displayName = "ThreadListItemMorePrimitive.Content";
//#endregion
export { ThreadListItemMorePrimitiveContent };
