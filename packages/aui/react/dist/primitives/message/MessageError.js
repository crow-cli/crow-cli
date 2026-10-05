"use client";
import { useMessageError } from "@assistant-ui/core/react";
//#region src/primitives/message/MessageError.ts
const MessagePrimitiveError = (t0) => {
	const { children } = t0;
	return useMessageError() !== void 0 ? children : null;
};
MessagePrimitiveError.displayName = "MessagePrimitive.Error";
//#endregion
export { MessagePrimitiveError };
