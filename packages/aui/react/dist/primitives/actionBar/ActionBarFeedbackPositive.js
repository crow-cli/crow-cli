"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useActionBarFeedbackPositive } from "@assistant-ui/core/react";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/actionBar/ActionBarFeedbackPositive.tsx
const useActionBarFeedbackPositive$1 = () => {
	const { submit } = useActionBarFeedbackPositive();
	return submit;
};
const ActionBarPrimitiveFeedbackPositive = forwardRef((t0, forwardedRef) => {
	const $ = c(18);
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
	const isSubmitted = useAuiState(_temp);
	const callback = useActionBarFeedbackPositive$1();
	let t1;
	if ($[4] !== isSubmitted) {
		t1 = isSubmitted ? { "data-submitted": "true" } : {};
		$[4] = isSubmitted;
		$[5] = t1;
	} else t1 = $[5];
	const t2 = disabled || !callback;
	let t3;
	if ($[6] !== callback) {
		t3 = () => {
			callback?.();
		};
		$[6] = callback;
		$[7] = t3;
	} else t3 = $[7];
	let t4;
	if ($[8] !== onClick || $[9] !== t3) {
		t4 = composeEventHandlers(onClick, t3);
		$[8] = onClick;
		$[9] = t3;
		$[10] = t4;
	} else t4 = $[10];
	let t5;
	if ($[11] !== forwardedRef || $[12] !== isSubmitted || $[13] !== props || $[14] !== t1 || $[15] !== t2 || $[16] !== t4) {
		t5 = /* @__PURE__ */ jsx(Primitive$1.button, {
			type: "button",
			"aria-pressed": isSubmitted,
			...t1,
			...props,
			ref: forwardedRef,
			disabled: t2,
			onClick: t4
		});
		$[11] = forwardedRef;
		$[12] = isSubmitted;
		$[13] = props;
		$[14] = t1;
		$[15] = t2;
		$[16] = t4;
		$[17] = t5;
	} else t5 = $[17];
	return t5;
});
ActionBarPrimitiveFeedbackPositive.displayName = "ActionBarPrimitive.FeedbackPositive";
function _temp(s) {
	return s.message.metadata.submittedFeedback?.type === "positive";
}
//#endregion
export { ActionBarPrimitiveFeedbackPositive };
