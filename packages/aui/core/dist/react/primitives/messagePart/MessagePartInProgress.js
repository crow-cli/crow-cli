import { useAuiState } from "@assistant-ui/store";
//#region src/react/primitives/messagePart/MessagePartInProgress.ts
const MessagePartPrimitiveInProgress = (t0) => {
	const { children } = t0;
	return useAuiState(_temp) ? children : null;
};
MessagePartPrimitiveInProgress.displayName = "MessagePartPrimitive.InProgress";
function _temp(s) {
	return s.part.status.type === "running";
}
//#endregion
export { MessagePartPrimitiveInProgress };
