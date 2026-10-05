"use client";
import { useAuiState } from "@assistant-ui/store";
//#region src/hooks/useMessageTiming.ts
/**
* Hook that returns timing information for the current assistant message.
*
* Reads from `message.metadata.timing`.
*
* @example
* ```tsx
* function MessageStats() {
*   const timing = useMessageTiming();
*   if (!timing) return null;
*   return <span>{timing.tokensPerSecond?.toFixed(1)} tok/s</span>;
* }
* ```
*/
const useMessageTiming = () => {
	return useAuiState(_temp);
};
function _temp(s) {
	return s.message.role === "assistant" ? s.message.metadata?.timing : void 0;
}
//#endregion
export { useMessageTiming };
