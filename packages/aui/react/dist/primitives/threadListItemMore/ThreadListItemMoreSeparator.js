"use client";
import { DropdownMenuRenderSeparator } from "../dropdownMenuRenderPrimitives.js";
import { useDropdownMenuScope } from "./scope.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/threadListItemMore/ThreadListItemMoreSeparator.tsx
const ThreadListItemMorePrimitiveSeparator = forwardRef((t0, ref) => {
	const $ = c(7);
	let __scopeThreadListItemMore;
	let rest;
	if ($[0] !== t0) {
		({__scopeThreadListItemMore, ...rest} = t0);
		$[0] = t0;
		$[1] = __scopeThreadListItemMore;
		$[2] = rest;
	} else {
		__scopeThreadListItemMore = $[1];
		rest = $[2];
	}
	const scope = useDropdownMenuScope(__scopeThreadListItemMore);
	let t1;
	if ($[3] !== ref || $[4] !== rest || $[5] !== scope) {
		t1 = /* @__PURE__ */ jsx(DropdownMenuRenderSeparator, {
			...scope,
			...rest,
			ref
		});
		$[3] = ref;
		$[4] = rest;
		$[5] = scope;
		$[6] = t1;
	} else t1 = $[6];
	return t1;
});
ThreadListItemMorePrimitiveSeparator.displayName = "ThreadListItemMorePrimitive.Separator";
//#endregion
export { ThreadListItemMorePrimitiveSeparator };
