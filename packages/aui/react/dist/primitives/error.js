import { __exportAll } from "../_virtual/_rolldown/runtime.js";
import { ErrorPrimitiveRoot } from "./error/ErrorRoot.js";
import { ErrorPrimitiveMessage } from "./error/ErrorMessage.js";
//#region src/primitives/error.ts
var error_exports = /* @__PURE__ */ __exportAll({
	Message: () => ErrorPrimitiveMessage,
	Root: () => ErrorPrimitiveRoot
});
//#endregion
export { ErrorPrimitiveMessage as Message, ErrorPrimitiveRoot as Root, error_exports };
