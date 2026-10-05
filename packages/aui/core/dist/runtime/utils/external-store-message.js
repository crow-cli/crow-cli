//#region src/runtime/utils/external-store-message.ts
const symbolInnerMessage = Symbol("innerMessage");
const symbolInnerMessages = Symbol("innerMessages");
const EMPTY_ARRAY = [];
/**
* Attach the original external store message(s) to a ThreadMessage or message part.
* This is a no-op if the target already has a bound message.
* Use `getExternalStoreMessages` to retrieve the bound messages later.
*
* @deprecated This API is experimental and may change without notice.
*/
const bindExternalStoreMessage = (target, message) => {
	if (symbolInnerMessage in target) return;
	target[symbolInnerMessage] = message;
};
const getExternalStoreMessages = (input) => {
	const container = "messages" in input && !("type" in input && input.type === "tool-call") ? input.messages : input;
	const value = container[symbolInnerMessages] || container[symbolInnerMessage];
	if (!value) return EMPTY_ARRAY;
	if (Array.isArray(value)) return value;
	container[symbolInnerMessages] = [value];
	return container[symbolInnerMessages];
};
const FALLBACK_ID_PREFIX = "__external_store_fallback_";
//#endregion
export { FALLBACK_ID_PREFIX, bindExternalStoreMessage, getExternalStoreMessages, symbolInnerMessage };
