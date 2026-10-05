"use client";
import { getMessageQuote } from "@assistant-ui/core/react";
import { useAuiState } from "@assistant-ui/store";
//#region src/hooks/useMessageQuote.ts
/**
* Hook that returns the quote info for the current message, if any.
*
* Reads from `message.metadata.custom.quote`.
*
* @example
* ```tsx
* function QuoteBlock() {
*   const quote = useMessageQuote();
*   if (!quote) return null;
*   return <blockquote>{quote.text}</blockquote>;
* }
* ```
*/
const useMessageQuote = () => {
	return useAuiState(getMessageQuote);
};
//#endregion
export { useMessageQuote };
