"use client";
import { usePopoverScope } from "./scope.js";
import { PopoverRenderContent } from "./popoverRenderPrimitives.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
import { Popover } from "radix-ui";
//#region src/primitives/assistantModal/AssistantModalContent.tsx
const AssistantModalPrimitiveContent = forwardRef((t0, forwardedRef) => {
	const $ = c(22);
	let __scopeAssistantModal;
	let align;
	let onInteractOutside;
	let portalProps;
	let props;
	let side;
	let t1;
	if ($[0] !== t0) {
		({__scopeAssistantModal, side, align, onInteractOutside, dissmissOnInteractOutside: t1, portalProps, ...props} = t0);
		$[0] = t0;
		$[1] = __scopeAssistantModal;
		$[2] = align;
		$[3] = onInteractOutside;
		$[4] = portalProps;
		$[5] = props;
		$[6] = side;
		$[7] = t1;
	} else {
		__scopeAssistantModal = $[1];
		align = $[2];
		onInteractOutside = $[3];
		portalProps = $[4];
		props = $[5];
		side = $[6];
		t1 = $[7];
	}
	const dissmissOnInteractOutside = t1 === void 0 ? false : t1;
	const scope = usePopoverScope(__scopeAssistantModal);
	const t2 = side ?? "top";
	const t3 = align ?? "end";
	const t4 = dissmissOnInteractOutside ? void 0 : _temp;
	let t5;
	if ($[8] !== onInteractOutside || $[9] !== t4) {
		t5 = composeEventHandlers(onInteractOutside, t4);
		$[8] = onInteractOutside;
		$[9] = t4;
		$[10] = t5;
	} else t5 = $[10];
	let t6;
	if ($[11] !== forwardedRef || $[12] !== props || $[13] !== scope || $[14] !== t2 || $[15] !== t3 || $[16] !== t5) {
		t6 = /* @__PURE__ */ jsx(PopoverRenderContent, {
			...scope,
			...props,
			ref: forwardedRef,
			side: t2,
			align: t3,
			onInteractOutside: t5
		});
		$[11] = forwardedRef;
		$[12] = props;
		$[13] = scope;
		$[14] = t2;
		$[15] = t3;
		$[16] = t5;
		$[17] = t6;
	} else t6 = $[17];
	let t7;
	if ($[18] !== portalProps || $[19] !== scope || $[20] !== t6) {
		t7 = /* @__PURE__ */ jsx(Popover.Portal, {
			...scope,
			...portalProps,
			children: t6
		});
		$[18] = portalProps;
		$[19] = scope;
		$[20] = t6;
		$[21] = t7;
	} else t7 = $[21];
	return t7;
});
AssistantModalPrimitiveContent.displayName = "AssistantModalPrimitive.Content";
function _temp(e) {
	return e.preventDefault();
}
//#endregion
export { AssistantModalPrimitiveContent };
