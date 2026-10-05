import { getMessageQuote } from "../../utils/getMessageQuote.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { memo } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { Fragment as Fragment$1, jsx } from "react/jsx-runtime";
//#region src/react/primitives/message/MessageQuote.tsx
/**
* Renders a quote block if the message has quote metadata.
* Place this above `MessagePrimitive.Parts` in your message layout.
*
* @example
* ```tsx
* <MessagePrimitive.Quote>
*   {({ text, messageId }) => <QuoteBlock text={text} messageId={messageId} />}
* </MessagePrimitive.Quote>
* <MessagePrimitive.Parts>
*   {({ part }) => { ... }}
* </MessagePrimitive.Parts>
* ```
*/
const MessagePrimitiveQuoteImpl = (t0) => {
	const $ = c(5);
	const { children } = t0;
	const quoteInfo = useAuiState(getMessageQuote);
	if (!quoteInfo) return null;
	let t1;
	if ($[0] !== children || $[1] !== quoteInfo) {
		t1 = children(quoteInfo);
		$[0] = children;
		$[1] = quoteInfo;
		$[2] = t1;
	} else t1 = $[2];
	let t2;
	if ($[3] !== t1) {
		t2 = /* @__PURE__ */ jsx(Fragment$1, { children: t1 });
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
};
const MessagePrimitiveQuote = memo(MessagePrimitiveQuoteImpl);
MessagePrimitiveQuote.displayName = "MessagePrimitive.Quote";
//#endregion
export { MessagePrimitiveQuote };
