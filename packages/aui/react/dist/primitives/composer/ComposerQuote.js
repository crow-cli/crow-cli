"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/composer/ComposerQuote.tsx
/**
* Renders a container for the quoted text preview in the composer.
* Only renders when a quote is set.
*
* @example
* ```tsx
* <ComposerPrimitive.Quote>
*   <ComposerPrimitive.QuoteText />
*   <ComposerPrimitive.QuoteDismiss>×</ComposerPrimitive.QuoteDismiss>
* </ComposerPrimitive.Quote>
* ```
*/
const ComposerPrimitiveQuote = forwardRef((props, forwardedRef) => {
	const $ = c(3);
	if (!useAuiState(_temp)) return null;
	let t0;
	if ($[0] !== forwardedRef || $[1] !== props) {
		t0 = /* @__PURE__ */ jsx(Primitive$1.div, {
			...props,
			ref: forwardedRef
		});
		$[0] = forwardedRef;
		$[1] = props;
		$[2] = t0;
	} else t0 = $[2];
	return t0;
});
ComposerPrimitiveQuote.displayName = "ComposerPrimitive.Quote";
/**
* Renders the quoted text content.
*
* @example
* ```tsx
* <ComposerPrimitive.QuoteText />
* ```
*/
const ComposerPrimitiveQuoteText = forwardRef((t0, forwardedRef) => {
	const $ = c(7);
	let children;
	let props;
	if ($[0] !== t0) {
		({children, ...props} = t0);
		$[0] = t0;
		$[1] = children;
		$[2] = props;
	} else {
		children = $[1];
		props = $[2];
	}
	const text = useAuiState(_temp2);
	if (!text) return null;
	const t1 = children ?? text;
	let t2;
	if ($[3] !== forwardedRef || $[4] !== props || $[5] !== t1) {
		t2 = /* @__PURE__ */ jsx(Primitive$1.span, {
			...props,
			ref: forwardedRef,
			children: t1
		});
		$[3] = forwardedRef;
		$[4] = props;
		$[5] = t1;
		$[6] = t2;
	} else t2 = $[6];
	return t2;
});
ComposerPrimitiveQuoteText.displayName = "ComposerPrimitive.QuoteText";
/**
* A button that clears the current quote from the composer.
*
* @example
* ```tsx
* <ComposerPrimitive.QuoteDismiss>×</ComposerPrimitive.QuoteDismiss>
* ```
*/
const ComposerPrimitiveQuoteDismiss = forwardRef((t0, forwardedRef) => {
	const $ = c(12);
	let onClick;
	let props;
	if ($[0] !== t0) {
		({onClick, ...props} = t0);
		$[0] = t0;
		$[1] = onClick;
		$[2] = props;
	} else {
		onClick = $[1];
		props = $[2];
	}
	const aui = useAui();
	let t1;
	if ($[3] !== aui) {
		t1 = () => {
			aui.composer.setQuote(void 0);
		};
		$[3] = aui;
		$[4] = t1;
	} else t1 = $[4];
	const handleDismiss = t1;
	let t2;
	if ($[5] !== handleDismiss || $[6] !== onClick) {
		t2 = composeEventHandlers(onClick, handleDismiss);
		$[5] = handleDismiss;
		$[6] = onClick;
		$[7] = t2;
	} else t2 = $[7];
	let t3;
	if ($[8] !== forwardedRef || $[9] !== props || $[10] !== t2) {
		t3 = /* @__PURE__ */ jsx(Primitive$1.button, {
			type: "button",
			...props,
			ref: forwardedRef,
			onClick: t2
		});
		$[8] = forwardedRef;
		$[9] = props;
		$[10] = t2;
		$[11] = t3;
	} else t3 = $[11];
	return t3;
});
ComposerPrimitiveQuoteDismiss.displayName = "ComposerPrimitive.QuoteDismiss";
function _temp(s) {
	return s.composer.quote;
}
function _temp2(s) {
	return s.composer.quote?.text;
}
//#endregion
export { ComposerPrimitiveQuote, ComposerPrimitiveQuoteDismiss, ComposerPrimitiveQuoteText };
