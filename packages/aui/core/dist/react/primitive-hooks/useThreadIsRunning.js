import { useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useThreadIsRunning.ts
/**
* @deprecated Use `useAuiState((s) => s.thread.isRunning)` instead.
*/
const useThreadIsRunning = () => {
	return useAuiState(_temp);
};
function _temp(s) {
	return s.thread.isRunning;
}
//#endregion
export { useThreadIsRunning };
