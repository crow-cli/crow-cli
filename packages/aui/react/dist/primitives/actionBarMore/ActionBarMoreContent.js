"use client";
import { useDropdownMenuScope } from "./scope.js";
import { DropdownMenuRenderContent } from "../dropdownMenuRenderPrimitives.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { DropdownMenu } from "radix-ui";
//#region src/primitives/actionBarMore/ActionBarMoreContent.tsx
const ActionBarMorePrimitiveContent = forwardRef((t0, forwardedRef) => {
	const $ = c(14);
	let __scopeActionBarMore;
	let portalProps;
	let props;
	let t1;
	if ($[0] !== t0) {
		({__scopeActionBarMore, portalProps, sideOffset: t1, ...props} = t0);
		$[0] = t0;
		$[1] = __scopeActionBarMore;
		$[2] = portalProps;
		$[3] = props;
		$[4] = t1;
	} else {
		__scopeActionBarMore = $[1];
		portalProps = $[2];
		props = $[3];
		t1 = $[4];
	}
	const sideOffset = t1 === void 0 ? 4 : t1;
	const scope = useDropdownMenuScope(__scopeActionBarMore);
	let t2;
	if ($[5] !== forwardedRef || $[6] !== props || $[7] !== scope || $[8] !== sideOffset) {
		t2 = /* @__PURE__ */ jsx(DropdownMenuRenderContent, {
			...scope,
			...props,
			ref: forwardedRef,
			sideOffset
		});
		$[5] = forwardedRef;
		$[6] = props;
		$[7] = scope;
		$[8] = sideOffset;
		$[9] = t2;
	} else t2 = $[9];
	let t3;
	if ($[10] !== portalProps || $[11] !== scope || $[12] !== t2) {
		t3 = /* @__PURE__ */ jsx(DropdownMenu.Portal, {
			...scope,
			...portalProps,
			children: t2
		});
		$[10] = portalProps;
		$[11] = scope;
		$[12] = t2;
		$[13] = t3;
	} else t3 = $[13];
	return t3;
});
ActionBarMorePrimitiveContent.displayName = "ActionBarMorePrimitive.Content";
//#endregion
export { ActionBarMorePrimitiveContent };
