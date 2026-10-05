"use client";
import { useAuiState } from "./useAuiState.js";
//#region src/AuiIf.ts
/** Renders `children` while `condition` selects `true` from the assistant state. */
const AuiIf = (t0) => {
	const { children, condition } = t0;
	return useAuiState(condition) ? children : null;
};
AuiIf.displayName = "AuiIf";
//#endregion
export { AuiIf };
