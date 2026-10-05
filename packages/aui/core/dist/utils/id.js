import { customAlphabet } from "nanoid/non-secure";
//#region src/utils/id.ts
/**
* @deprecated This API is experimental and may change without notice.
*/
const generateId = customAlphabet("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", 7);
const errorPrefix = "__error__";
const generateErrorMessageId = () => `${errorPrefix}${generateId()}`;
const isErrorMessageId = (id) => id.startsWith(errorPrefix);
//#endregion
export { generateErrorMessageId, generateId, isErrorMessageId };
