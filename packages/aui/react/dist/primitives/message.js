import { __exportAll } from "../_virtual/_rolldown/runtime.js";
import { MessagePrimitiveRoot } from "./message/MessageRoot.js";
import { MessagePrimitivePartByIndex as MessagePrimitivePartByIndexBase, MessagePrimitiveParts } from "./message/MessageParts.js";
import { MessagePrimitiveIf } from "./message/MessageIf.js";
import { MessagePrimitiveAttachmentByIndex, MessagePrimitiveAttachments } from "./message/MessageAttachments.js";
import { MessagePrimitiveError } from "./message/MessageError.js";
import { MessagePrimitiveUnstable_PartsGrouped, MessagePrimitiveUnstable_PartsGroupedByParentId } from "./message/MessagePartsGrouped.js";
import { MessagePrimitiveGenerativeUI as GenerativeUI, MessagePrimitiveGroupedParts as GroupedParts, MessagePrimitiveQuote as Quote } from "@assistant-ui/core/react";
//#region src/primitives/message.ts
var message_exports = /* @__PURE__ */ __exportAll({
	AttachmentByIndex: () => MessagePrimitiveAttachmentByIndex,
	Attachments: () => MessagePrimitiveAttachments,
	Content: () => MessagePrimitiveParts,
	Error: () => MessagePrimitiveError,
	GenerativeUI: () => GenerativeUI,
	GroupedParts: () => GroupedParts,
	If: () => MessagePrimitiveIf,
	PartByIndex: () => MessagePrimitivePartByIndexBase,
	Parts: () => MessagePrimitiveParts,
	Quote: () => Quote,
	Root: () => MessagePrimitiveRoot,
	Unstable_PartsGrouped: () => MessagePrimitiveUnstable_PartsGrouped,
	Unstable_PartsGroupedByParentId: () => MessagePrimitiveUnstable_PartsGroupedByParentId
});
//#endregion
export { MessagePrimitiveAttachmentByIndex as AttachmentByIndex, MessagePrimitiveAttachments as Attachments, MessagePrimitiveParts as Content, MessagePrimitiveError as Error, GenerativeUI, GroupedParts, MessagePrimitiveIf as If, MessagePrimitivePartByIndexBase as PartByIndex, MessagePrimitiveParts as Parts, Quote, MessagePrimitiveRoot as Root, MessagePrimitiveUnstable_PartsGrouped as Unstable_PartsGrouped, MessagePrimitiveUnstable_PartsGroupedByParentId as Unstable_PartsGroupedByParentId, message_exports };
