"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { useSelectionToolbarInfo } from "./SelectionToolbarRoot.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/selectionToolbar/SelectionToolbarQuote.tsx
/**
* A button that quotes the currently selected text.
*
* Must be placed inside `SelectionToolbarPrimitive.Root`. Reads the
* selection info from context (captured by the Root), sets it as a
* quote in the thread composer, and clears the selection.
*
* @example
* ```tsx
* <SelectionToolbarPrimitive.Quote>
*   <QuoteIcon /> Quote
* </SelectionToolbarPrimitive.Quote>
* ```
*/
const SelectionToolbarPrimitiveQuote = forwardRef((t0, forwardedRef) => {
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
	const aui = useAui();
	const info = useSelectionToolbarInfo();
	let t1;
	if ($[4] !== aui || $[5] !== info) {
		t1 = () => {
			if (!info) return;
			aui.thread.composer().setQuote({
				text: info.text,
				messageId: info.messageId
			});
			window.getSelection()?.removeAllRanges();
		};
		$[4] = aui;
		$[5] = info;
		$[6] = t1;
	} else t1 = $[6];
	const handleClick = t1;
	const t2 = disabled || !info;
	let t3;
	if ($[7] !== handleClick || $[8] !== onClick) {
		t3 = composeEventHandlers(onClick, handleClick);
		$[7] = handleClick;
		$[8] = onClick;
		$[9] = t3;
	} else t3 = $[9];
	let t4;
	if ($[10] !== forwardedRef || $[11] !== props || $[12] !== t2 || $[13] !== t3) {
		t4 = /* @__PURE__ */ jsx(Primitive$1.button, {
			type: "button",
			...props,
			ref: forwardedRef,
			disabled: t2,
			onClick: t3
		});
		$[10] = forwardedRef;
		$[11] = props;
		$[12] = t2;
		$[13] = t3;
		$[14] = t4;
	} else t4 = $[14];
	return t4;
});
SelectionToolbarPrimitiveQuote.displayName = "SelectionToolbarPrimitive.Quote";
//#endregion
export { SelectionToolbarPrimitiveQuote };
