import { useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useThreadIsEmpty.ts
/**
* @deprecated Use `useAuiState((s) => s.thread.isEmpty)` instead.
*/
const useThreadIsEmpty = () => {
	return useAuiState(_temp);
};
function _temp(s) {
	return s.thread.isEmpty;
}
//#endregion
export { useThreadIsEmpty };
