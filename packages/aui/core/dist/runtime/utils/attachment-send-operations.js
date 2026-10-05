import { isAttachmentComplete } from "../../types/attachment.js";
//#region src/runtime/utils/attachment-send-operations.ts
var AttachmentSendOperations = class {
	entries = /* @__PURE__ */ new WeakMap();
	removed = /* @__PURE__ */ new WeakSet();
	markRemoved(attachment) {
		this.removed.add(attachment);
	}
	unmarkRemoved(attachment) {
		this.removed.delete(attachment);
	}
	isRemoved(attachment) {
		return this.removed.has(attachment);
	}
	async send(attachment, adapter, signal) {
		if (isAttachmentComplete(attachment)) return attachment;
		const entry = this.entries.get(attachment) ?? {};
		if (entry.result) return entry.result;
		if (!adapter) throw new Error("Attachments are not supported");
		this.entries.set(attachment, entry);
		const result = await adapter.send(attachment, signal ? { signal } : void 0);
		entry.result = result;
		return result;
	}
	transfer(original, replacement) {
		const entry = this.entries.get(original);
		if (entry) this.entries.set(replacement, entry);
		return replacement;
	}
};
//#endregion
export { AttachmentSendOperations };
