//#region src/types/attachment.ts
const isCreateAttachment = (attachment) => "content" in attachment && !("lastModified" in attachment);
const isAttachmentComplete = (attachment) => attachment.status.type === "complete";
//#endregion
export { isAttachmentComplete, isCreateAttachment };
