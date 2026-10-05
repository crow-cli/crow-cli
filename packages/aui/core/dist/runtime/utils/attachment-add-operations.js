//#region src/runtime/utils/attachment-add-operations.ts
var AttachmentAddOperations = class {
	operations = /* @__PURE__ */ new Set();
	uploading = /* @__PURE__ */ new Map();
	start() {
		const operation = {
			cancelled: false,
			attachmentIds: /* @__PURE__ */ new Set()
		};
		this.operations.add(operation);
		return operation;
	}
	accept(operation, attachment) {
		if (operation.cancelled) return false;
		operation.attachmentIds.add(attachment.id);
		const entry = this.uploading.get(attachment.id);
		if (entry?.operation !== operation && (entry || attachment.status.type === "running")) this.uploading.set(attachment.id, {
			operation,
			waiters: entry?.waiters ?? /* @__PURE__ */ new Set()
		});
		if (attachment.status.type !== "running") this.settle(attachment.id, operation);
		return true;
	}
	finish(operation) {
		this.operations.delete(operation);
		for (const attachmentId of operation.attachmentIds) this.settle(attachmentId, operation);
	}
	isCancelled(operation) {
		return operation.cancelled;
	}
	cancel(attachmentId) {
		for (const operation of [...this.operations]) {
			if (!operation.attachmentIds.has(attachmentId)) continue;
			operation.cancelled = true;
			this.operations.delete(operation);
		}
		this.settle(attachmentId);
	}
	cancelAll() {
		for (const operation of this.operations) operation.cancelled = true;
		this.operations.clear();
		for (const attachmentId of [...this.uploading.keys()]) this.settle(attachmentId);
	}
	whenSendable(attachmentId) {
		const entry = this.uploading.get(attachmentId);
		if (!entry) return void 0;
		return new Promise((resolve) => entry.waiters.add(resolve));
	}
	settle(attachmentId, operation) {
		const entry = this.uploading.get(attachmentId);
		if (!entry) return;
		if (operation && entry.operation !== operation) return;
		this.uploading.delete(attachmentId);
		for (const resolve of entry.waiters) resolve();
	}
};
const drainAttachmentAdd = async (result, accept) => {
	if (Symbol.asyncIterator in result) {
		for await (const attachment of result) if (!accept(attachment)) break;
	} else accept(await result);
};
//#endregion
export { AttachmentAddOperations, drainAttachmentAdd };
