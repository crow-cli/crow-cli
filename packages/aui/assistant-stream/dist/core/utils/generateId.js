import { customAlphabet } from "nanoid/non-secure";
//#region src/core/utils/generateId.ts
const generateId = customAlphabet("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", 7);
//#endregion
export { generateId };
