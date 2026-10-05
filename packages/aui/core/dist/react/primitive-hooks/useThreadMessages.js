import { useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useThreadMessages.ts
const useThreadMessages = () => {
	return useAuiState(_temp);
};
function _temp(s) {
	return s.thread.messages;
}
//#endregion
export { useThreadMessages };
