import { messageErrorText } from "../../store/primitive-predicates.js";
import { useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useMessageError.ts
const useMessageError = () => {
	return useAuiState(messageErrorText);
};
//#endregion
export { useMessageError };
