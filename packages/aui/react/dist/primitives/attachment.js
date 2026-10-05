import { __exportAll } from "../_virtual/_rolldown/runtime.js";
import { AttachmentPrimitiveRoot } from "./attachment/AttachmentRoot.js";
import { AttachmentPrimitiveThumb } from "./attachment/AttachmentThumb.js";
import { AttachmentPrimitiveName } from "./attachment/AttachmentName.js";
import { AttachmentPrimitiveRemove } from "./attachment/AttachmentRemove.js";
//#region src/primitives/attachment.ts
var attachment_exports = /* @__PURE__ */ __exportAll({
	Name: () => AttachmentPrimitiveName,
	Remove: () => AttachmentPrimitiveRemove,
	Root: () => AttachmentPrimitiveRoot,
	unstable_Thumb: () => AttachmentPrimitiveThumb
});
//#endregion
export { AttachmentPrimitiveName as Name, AttachmentPrimitiveRemove as Remove, AttachmentPrimitiveRoot as Root, attachment_exports, AttachmentPrimitiveThumb as unstable_Thumb };
