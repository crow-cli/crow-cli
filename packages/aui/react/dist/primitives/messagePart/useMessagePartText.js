"use client";
import { useAuiState } from "@assistant-ui/store";
//#region src/primitives/messagePart/useMessagePartText.ts
const COMPLETE_STATUS = Object.freeze({ type: "complete" });
const EMPTY_TEXT_PART = Object.freeze({
	type: "text",
	text: "",
	status: COMPLETE_STATUS
});
/**
* @deprecated Use {@link useAuiState} to select and narrow `s.part`.
* Return `null` for optional rendering. Do not throw inside the selector:
* selectors run inside `useSyncExternalStore`'s `getSnapshot`, so a transient
* part mismatch during thread switches can unmount the React root.
*
* @example
* ```tsx
* const text = useAuiState((s) => {
*   if (s.part.type !== "text" && s.part.type !== "reasoning") return null;
*   return s.part;
* });
* ```
*
* See the {@link https://assistant-ui.com/docs/migrations/v0-12 migration guide}.
*/
const useMessagePartText = () => {
	return useAuiState(_temp);
};
function _temp(s) {
	if (s.part.type !== "text" && s.part.type !== "reasoning") return EMPTY_TEXT_PART;
	return s.part;
}
//#endregion
export { useMessagePartText };
