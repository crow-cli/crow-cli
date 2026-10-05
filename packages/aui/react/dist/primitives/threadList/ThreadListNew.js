"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useThreadListNew } from "@assistant-ui/core/react";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/threadList/ThreadListNew.tsx
const ThreadListPrimitiveNew = forwardRef((t0, forwardedRef) => {
	const $ = c(15);
	let disabled;
	let onClick;
	let props;
	if ($[0] !== t0) {
		({onClick, disabled, ...props} = t0);
		$[0] = t0;
		$[1] = disabled;
		$[2] = onClick;
		$[3] = props;
	} else {
		disabled = $[1];
		onClick = $[2];
		props = $[3];
	}
	const isMain = useAuiState(_temp);
	const { switchToNewThread } = useThreadListNew();
	let t1;
	if ($[4] !== isMain) {
		t1 = isMain ? {
			"data-active": "true",
			"aria-current": "true"
		} : null;
		$[4] = isMain;
		$[5] = t1;
	} else t1 = $[5];
	let t2;
	if ($[6] !== onClick || $[7] !== switchToNewThread) {
		t2 = composeEventHandlers(onClick, switchToNewThread);
		$[6] = onClick;
		$[7] = switchToNewThread;
		$[8] = t2;
	} else t2 = $[8];
	let t3;
	if ($[9] !== disabled || $[10] !== forwardedRef || $[11] !== props || $[12] !== t1 || $[13] !== t2) {
		t3 = /* @__PURE__ */ jsx(Primitive$1.button, {
			type: "button",
			...t1,
			...props,
			ref: forwardedRef,
			disabled,
			onClick: t2
		});
		$[9] = disabled;
		$[10] = forwardedRef;
		$[11] = props;
		$[12] = t1;
		$[13] = t2;
		$[14] = t3;
	} else t3 = $[14];
	return t3;
});
ThreadListPrimitiveNew.displayName = "ThreadListPrimitive.New";
function _temp(s) {
	return s.threads.newThreadId === s.threads.mainThreadId;
}
//#endregion
export { ThreadListPrimitiveNew };
