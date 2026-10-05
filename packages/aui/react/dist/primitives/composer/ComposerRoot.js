"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { useComposerSend } from "./ComposerSend.js";
import { ComposerCompactContext } from "./ComposerCompactContext.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef, useState } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/composer/ComposerRoot.tsx
const CONTENT_EDITABLE_SELECTOR = "[contenteditable]:not([contenteditable='false'])";
const COMPOSER_INPUT_SELECTOR = `textarea:not(:disabled), ${CONTENT_EDITABLE_SELECTOR}`;
const INTERACTIVE_ELEMENT_SELECTOR = [
	"a",
	"audio[controls]",
	"button",
	"details",
	"embed",
	"iframe",
	"input",
	"label",
	"select",
	"summary",
	"textarea",
	"video[controls]",
	CONTENT_EDITABLE_SELECTOR,
	"[tabindex]"
].join(", ");
/**
* The root form container for message composition.
*
* This component provides a form wrapper that handles message submission when the form
* is submitted (e.g., via Enter key or submit button). It automatically prevents the
* default form submission and triggers the composer's send functionality.
*
* Clicking blank form space focuses the composer input (the first textarea or
* contenteditable inside the form). Text selection cannot start from blank
* areas; descendants that need native mousedown defaults can call
* `stopPropagation()` in their own `onMouseDown`.
*
* @example
* ```tsx
* <ComposerPrimitive.Root>
*   <ComposerPrimitive.Input placeholder="Type your message..." />
*   <ComposerPrimitive.Send>Send</ComposerPrimitive.Send>
* </ComposerPrimitive.Root>
* ```
*/
const ComposerPrimitiveRoot = forwardRef((t0, forwardedRef) => {
	const $ = c(24);
	let compact;
	let onMouseDown;
	let onSubmit;
	let rest;
	if ($[0] !== t0) {
		({onSubmit, onMouseDown, compact, ...rest} = t0);
		$[0] = t0;
		$[1] = compact;
		$[2] = onMouseDown;
		$[3] = onSubmit;
		$[4] = rest;
	} else {
		compact = $[1];
		onMouseDown = $[2];
		onSubmit = $[3];
		rest = $[4];
	}
	const send = useComposerSend();
	const [multiline, setMultiline] = useState(false);
	let t1;
	if ($[5] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = { setMultiline };
		$[5] = t1;
	} else t1 = $[5];
	const compactContext = t1;
	let t2;
	if ($[6] !== compact) {
		t2 = (s) => compact ? s.composer.attachments.length === 0 && s.composer.quote == null && s.composer.queue.length === 0 && s.composer.dictation == null && !s.composer.text.includes("\n") : false;
		$[6] = compact;
		$[7] = t2;
	} else t2 = $[7];
	const isCompact = useAuiState(t2) && !multiline;
	let t3;
	if ($[8] !== send) {
		t3 = (e) => {
			e.preventDefault();
			if (!send) return;
			send();
		};
		$[8] = send;
		$[9] = t3;
	} else t3 = $[9];
	const handleSubmit = t3;
	const handleMouseDown = _temp;
	const t4 = compact ? compactContext : null;
	const t5 = isCompact ? "" : void 0;
	let t6;
	if ($[10] !== handleSubmit || $[11] !== onSubmit) {
		t6 = composeEventHandlers(onSubmit, handleSubmit);
		$[10] = handleSubmit;
		$[11] = onSubmit;
		$[12] = t6;
	} else t6 = $[12];
	let t7;
	if ($[13] !== onMouseDown) {
		t7 = composeEventHandlers(onMouseDown, handleMouseDown);
		$[13] = onMouseDown;
		$[14] = t7;
	} else t7 = $[14];
	let t8;
	if ($[15] !== forwardedRef || $[16] !== rest || $[17] !== t5 || $[18] !== t6 || $[19] !== t7) {
		t8 = /* @__PURE__ */ jsx(Primitive$1.form, {
			...rest,
			"data-compact": t5,
			ref: forwardedRef,
			onSubmit: t6,
			onMouseDown: t7
		});
		$[15] = forwardedRef;
		$[16] = rest;
		$[17] = t5;
		$[18] = t6;
		$[19] = t7;
		$[20] = t8;
	} else t8 = $[20];
	let t9;
	if ($[21] !== t4 || $[22] !== t8) {
		t9 = /* @__PURE__ */ jsx(ComposerCompactContext.Provider, {
			value: t4,
			children: t8
		});
		$[21] = t4;
		$[22] = t8;
		$[23] = t9;
	} else t9 = $[23];
	return t9;
});
ComposerPrimitiveRoot.displayName = "ComposerPrimitive.Root";
function _temp(e_0) {
	if (e_0.button !== 0) return;
	const target = e_0.target;
	if (!(target instanceof Element) || !e_0.currentTarget.contains(target)) return;
	const interactive = target.closest(INTERACTIVE_ELEMENT_SELECTOR);
	if (interactive && e_0.currentTarget.contains(interactive)) return;
	const input = e_0.currentTarget.querySelector(COMPOSER_INPUT_SELECTOR);
	if (!input) return;
	e_0.preventDefault();
	input.focus();
}
//#endregion
export { ComposerPrimitiveRoot };
