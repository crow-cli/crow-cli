"use client";
import { Primitive } from "../../utils/Primitive.js";
import { ThreadListCollection } from "../threadListFocusGroup.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/threadList/ThreadListRoot.tsx
const ThreadListPrimitiveRoot = forwardRef((props, ref) => {
	const $ = c(3);
	let t0;
	if ($[0] !== props || $[1] !== ref) {
		t0 = /* @__PURE__ */ jsx(ThreadListCollection.Provider, {
			scope: void 0,
			children: /* @__PURE__ */ jsx(ThreadListCollection.Slot, {
				scope: void 0,
				children: /* @__PURE__ */ jsx(Primitive.div, {
					...props,
					ref
				})
			})
		});
		$[0] = props;
		$[1] = ref;
		$[2] = t0;
	} else t0 = $[2];
	return t0;
});
ThreadListPrimitiveRoot.displayName = "ThreadListPrimitive.Root";
//#endregion
export { ThreadListPrimitiveRoot };
