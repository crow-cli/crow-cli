"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useActionBarCopy } from "@assistant-ui/core/react";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/actionBar/ActionBarCopy.tsx
/**
* Hook that provides copy functionality for action bar buttons.
*
* This hook returns a callback function that copies message content to the clipboard,
* or null if copying is not available. It handles both regular message content and
* composer text when in editing mode.
*
* @param options Configuration options
* @param options.copiedDuration Duration in milliseconds to show the copied state
* @returns A copy callback function, or null if copying is disabled
*
* @example
* ```tsx
* function CustomCopyButton() {
*   const copy = useActionBarPrimitiveCopy({ copiedDuration: 2000 });
*
*   return (
*     <button onClick={copy} disabled={!copy}>
*       {copy ? "Copy" : "Cannot Copy"}
*     </button>
*   );
* }
* ```
*/
const useActionBarPrimitiveCopy = (t0) => {
	const $ = c(4);
	let t1;
	if ($[0] !== t0) {
		t1 = t0 === void 0 ? {} : t0;
		$[0] = t0;
		$[1] = t1;
	} else t1 = $[1];
	const { copiedDuration: t2 } = t1;
	const copiedDuration = t2 === void 0 ? 3e3 : t2;
	let t3;
	if ($[2] !== copiedDuration) {
		t3 = {
			copiedDuration,
			copyToClipboard: _temp
		};
		$[2] = copiedDuration;
		$[3] = t3;
	} else t3 = $[3];
	const { copy, disabled } = useActionBarCopy(t3);
	if (disabled) return null;
	return copy;
};
/**
* A button component that copies message content to the clipboard.
*
* This component automatically handles copying message text to the clipboard
* and provides visual feedback through the data-copied attribute. It's disabled
* when there's no copyable content available.
*
* @example
* ```tsx
* <ActionBarPrimitive.Copy copiedDuration={2000}>
*   Copy Message
* </ActionBarPrimitive.Copy>
* ```
*/
const ActionBarPrimitiveCopy = forwardRef((t0, forwardedRef) => {
	const $ = c(20);
	let copiedDuration;
	let disabled;
	let onClick;
	let props;
	if ($[0] !== t0) {
		({copiedDuration, onClick, disabled, ...props} = t0);
		$[0] = t0;
		$[1] = copiedDuration;
		$[2] = disabled;
		$[3] = onClick;
		$[4] = props;
	} else {
		copiedDuration = $[1];
		disabled = $[2];
		onClick = $[3];
		props = $[4];
	}
	const isCopied = useAuiState(_temp2);
	let t1;
	if ($[5] !== copiedDuration) {
		t1 = { copiedDuration };
		$[5] = copiedDuration;
		$[6] = t1;
	} else t1 = $[6];
	const callback = useActionBarPrimitiveCopy(t1);
	let t2;
	if ($[7] !== isCopied) {
		t2 = isCopied ? { "data-copied": "true" } : {};
		$[7] = isCopied;
		$[8] = t2;
	} else t2 = $[8];
	const t3 = disabled || !callback;
	let t4;
	if ($[9] !== callback) {
		t4 = () => {
			callback?.();
		};
		$[9] = callback;
		$[10] = t4;
	} else t4 = $[10];
	let t5;
	if ($[11] !== onClick || $[12] !== t4) {
		t5 = composeEventHandlers(onClick, t4);
		$[11] = onClick;
		$[12] = t4;
		$[13] = t5;
	} else t5 = $[13];
	let t6;
	if ($[14] !== forwardedRef || $[15] !== props || $[16] !== t2 || $[17] !== t3 || $[18] !== t5) {
		t6 = /* @__PURE__ */ jsx(Primitive$1.button, {
			type: "button",
			...t2,
			...props,
			ref: forwardedRef,
			disabled: t3,
			onClick: t5
		});
		$[14] = forwardedRef;
		$[15] = props;
		$[16] = t2;
		$[17] = t3;
		$[18] = t5;
		$[19] = t6;
	} else t6 = $[19];
	return t6;
});
ActionBarPrimitiveCopy.displayName = "ActionBarPrimitive.Copy";
function _temp(text) {
	if (typeof navigator === "undefined" || !navigator.clipboard) return Promise.reject(/* @__PURE__ */ new Error("Clipboard API is unavailable"));
	return navigator.clipboard.writeText(text);
}
function _temp2(s) {
	return s.message.isCopied;
}
//#endregion
export { ActionBarPrimitiveCopy };
