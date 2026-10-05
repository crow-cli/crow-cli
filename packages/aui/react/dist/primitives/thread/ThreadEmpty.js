"use client";
import { useAuiState } from "@assistant-ui/store";
//#region src/primitives/thread/ThreadEmpty.ts
/**
* @deprecated Use `<AuiIf condition={(s) => s.thread.isEmpty} />` instead.
*/
const ThreadPrimitiveEmpty = (t0) => {
	const { children } = t0;
	return useAuiState(_temp) ? children : null;
};
ThreadPrimitiveEmpty.displayName = "ThreadPrimitive.Empty";
function _temp(s) {
	return s.thread.isEmpty;
}
//#endregion
export { ThreadPrimitiveEmpty };
