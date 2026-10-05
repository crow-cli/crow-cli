import { generateId } from "../../../utils/id.js";
import { resolveFileMediaType } from "../../../utils/wire-media.js";
//#region src/react/runtimes/cloud/CloudFileAttachmentAdapter.ts
const DEFAULT_CONTENT_TYPE = "application/octet-stream";
const guessAttachmentType = (contentType) => {
	if (contentType.startsWith("image/")) return "image";
	if (contentType.startsWith("text/")) return "document";
	return "file";
};
var CloudFileAttachmentAdapter = class {
	accept = "*";
	getCloud;
	constructor(cloud) {
		this.getCloud = typeof cloud === "function" ? cloud : () => cloud;
	}
	uploadedUrls = /* @__PURE__ */ new Map();
	activeUploads = /* @__PURE__ */ new Map();
	async *add({ file }) {
		const id = generateId();
		const type = guessAttachmentType(file.type);
		const contentType = file.type || DEFAULT_CONTENT_TYPE;
		let attachment = {
			id,
			type,
			name: file.name,
			contentType,
			file,
			status: {
				type: "running",
				reason: "uploading",
				progress: 0
			}
		};
		const controller = new AbortController();
		const upload = {
			cancelled: false,
			controller
		};
		this.activeUploads.set(id, upload);
		try {
			yield attachment;
			if (upload.cancelled) return;
			const { signedUrl, publicUrl } = await this.getCloud().files.generatePresignedUploadUrl({ filename: file.name });
			if (upload.cancelled) return;
			const res = await fetch(signedUrl, {
				method: "PUT",
				body: file,
				headers: { "Content-Type": contentType },
				mode: "cors",
				signal: controller.signal
			});
			if (upload.cancelled) return;
			if (!res.ok) throw new Error(`Failed to upload file: ${res.status} ${res.statusText}`);
			this.uploadedUrls.set(id, publicUrl);
			attachment = {
				...attachment,
				status: {
					type: "requires-action",
					reason: "composer-send"
				}
			};
			yield attachment;
		} catch (error) {
			if (upload.cancelled) return;
			console.error("[assistant-ui] Failed to upload attachment:", error);
			attachment = {
				...attachment,
				status: {
					type: "incomplete",
					reason: "error",
					message: error instanceof Error ? error.message : String(error)
				}
			};
			yield attachment;
		} finally {
			if (this.activeUploads.get(id) === upload) this.activeUploads.delete(id);
		}
	}
	async remove(attachment) {
		const upload = this.activeUploads.get(attachment.id);
		if (upload) {
			upload.cancelled = true;
			upload.controller.abort();
			this.activeUploads.delete(attachment.id);
		}
		this.uploadedUrls.delete(attachment.id);
	}
	async send(attachment) {
		const url = this.uploadedUrls.get(attachment.id);
		if (!url) throw new Error("Attachment not uploaded");
		this.uploadedUrls.delete(attachment.id);
		let content;
		if (attachment.type === "image") content = [{
			type: "image",
			image: url,
			filename: attachment.name
		}];
		else content = [{
			type: "file",
			data: url,
			mimeType: resolveFileMediaType(url, attachment.contentType),
			filename: attachment.name
		}];
		return {
			...attachment,
			status: { type: "complete" },
			content
		};
	}
};
//#endregion
export { CloudFileAttachmentAdapter };
