"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useActionBarStopSpeaking } from "@assistant-ui/core/react";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/actionBar/ActionBarStopSpeaking.tsx
const useActionBarStopSpeaking$1 = () => {
	const { disabled, stopSpeaking } = useActionBarStopSpeaking();
	if (disabled) return null;
	return stopSpeaking;
};
const ActionBarPrimitiveStopSpeaking = forwardRef((props, ref) => {
	const $ = c(10);
	const callback = useActionBarStopSpeaking$1();
	const t0 = !callback;
	let t1;
	if ($[0] !== callback) {
		t1 = () => {
			callback?.();
		};
		$[0] = callback;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== props.onClick || $[3] !== t1) {
		t2 = composeEventHandlers(props.onClick, t1);
		$[2] = props.onClick;
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	let t3;
	if ($[5] !== props || $[6] !== ref || $[7] !== t0 || $[8] !== t2) {
		t3 = /* @__PURE__ */ jsx(Primitive$1.button, {
			type: "button",
			disabled: t0,
			...props,
			ref,
			onClick: t2
		});
		$[5] = props;
		$[6] = ref;
		$[7] = t0;
		$[8] = t2;
		$[9] = t3;
	} else t3 = $[9];
	return t3;
});
ActionBarPrimitiveStopSpeaking.displayName = "ActionBarPrimitive.StopSpeaking";
//#endregion
export { ActionBarPrimitiveStopSpeaking };
