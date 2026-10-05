import { generateId } from "../utils/id.js";
//#region src/adapters/attachment.ts
var SimpleImageAttachmentAdapter = class {
	accept = "image/*";
	async add(state) {
		return {
			id: generateId(),
			type: "image",
			name: state.file.name,
			contentType: state.file.type,
			file: state.file,
			status: {
				type: "requires-action",
				reason: "composer-send"
			}
		};
	}
	async send(attachment, options) {
		return {
			...attachment,
			status: { type: "complete" },
			content: [{
				type: "image",
				image: await getFileDataURL(attachment.file, options)
			}]
		};
	}
	async remove() {}
};
const bytesToBase64 = (bytes) => {
	const nodeBuffer = globalThis.Buffer;
	if (nodeBuffer) return nodeBuffer.from(bytes).toString("base64");
	let binary = "";
	const chunkSize = 32768;
	for (let i = 0; i < bytes.length; i += chunkSize) binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
	return btoa(binary);
};
const abortReason = (signal) => {
	if (signal?.reason !== void 0) return signal.reason;
	const error = /* @__PURE__ */ new Error("The attachment read was aborted");
	error.name = "AbortError";
	return error;
};
const throwIfAborted = (signal) => {
	if (signal?.aborted) throw abortReason(signal);
};
const readWithFileReader = (read, signal) => new Promise((resolve, reject) => {
	const reader = new FileReader();
	const onAbort = () => {
		reader.abort();
		reject(abortReason(signal));
	};
	reader.onload = () => {
		signal?.removeEventListener("abort", onAbort);
		resolve(reader.result);
	};
	reader.onerror = (error) => {
		signal?.removeEventListener("abort", onAbort);
		reject(error);
	};
	signal?.addEventListener("abort", onAbort, { once: true });
	try {
		read(reader);
	} catch (error) {
		signal?.removeEventListener("abort", onAbort);
		reject(error);
	}
});
const getFileDataURL = async (file, options) => {
	const signal = options?.signal;
	throwIfAborted(signal);
	if (typeof FileReader === "undefined") {
		const buffer = await file.arrayBuffer();
		throwIfAborted(signal);
		return `data:${file.type || "application/octet-stream"};base64,${bytesToBase64(new Uint8Array(buffer))}`;
	}
	return readWithFileReader((reader) => reader.readAsDataURL(file), signal);
};
const escapeAttachmentName = (name) => name.replaceAll("&", "&amp;").replaceAll("\"", "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
var SimpleTextAttachmentAdapter = class {
	accept = "text/plain,text/html,text/markdown,text/csv,text/xml,text/json,application/json,text/css";
	async add(state) {
		return {
			id: generateId(),
			type: "document",
			name: state.file.name,
			contentType: state.file.type,
			file: state.file,
			status: {
				type: "requires-action",
				reason: "composer-send"
			}
		};
	}
	async send(attachment, options) {
		return {
			...attachment,
			status: { type: "complete" },
			content: [{
				type: "text",
				text: `<attachment name="${escapeAttachmentName(attachment.name)}">\n${await getFileText(attachment.file, options)}\n</attachment>`
			}]
		};
	}
	async remove() {}
};
const getFileText = async (file, options) => {
	const signal = options?.signal;
	throwIfAborted(signal);
	if (typeof FileReader === "undefined") {
		const text = await file.text();
		throwIfAborted(signal);
		return text;
	}
	return readWithFileReader((reader) => reader.readAsText(file), signal);
};
function fileMatchesAccept(file, acceptString) {
	if (acceptString === "*") return true;
	const allowedTypes = acceptString.split(",").map((type) => type.trim().toLowerCase());
	const fileName = file.name.toLowerCase();
	const fileMimeType = file.type.split(";", 1)[0].trim().toLowerCase();
	for (const type of allowedTypes) {
		if (type.startsWith(".") && fileName.endsWith(type)) return true;
		if (type.includes("/") && type === fileMimeType) return true;
		if (type.endsWith("/*")) {
			const generalType = type.split("/")[0];
			if (fileMimeType.startsWith(`${generalType}/`)) return true;
		}
	}
	return false;
}
function attachmentsEqual(a, b) {
	if (a.length !== b.length) return false;
	for (let i = 0; i < a.length; i++) if (a[i]?.id !== b[i]?.id) return false;
	return true;
}
function partToCompleteAttachment(part) {
	const id = generateId();
	if (part.type === "image") return {
		id,
		type: "image",
		name: part.filename ?? "image",
		content: [part],
		status: { type: "complete" }
	};
	if (part.type === "file") return {
		id,
		type: "document",
		name: part.filename ?? "document",
		contentType: part.mimeType,
		content: [part],
		status: { type: "complete" }
	};
	if (part.type === "audio") return {
		id,
		type: "audio",
		name: `audio.${part.audio.format}`,
		contentType: `audio/${part.audio.format}`,
		content: [part],
		status: { type: "complete" }
	};
	return {
		id,
		type: "data",
		name: part.name,
		content: [part],
		status: { type: "complete" }
	};
}
function liftNonTextParts(content) {
	const result = [];
	for (const part of content) if (part.type !== "text") result.push(partToCompleteAttachment(part));
	return result;
}
var CompositeAttachmentAdapter = class {
	_adapters;
	accept;
	constructor(adapters) {
		this._adapters = adapters;
		const wildcardIdx = adapters.findIndex((a) => a.accept === "*");
		if (wildcardIdx !== -1) {
			if (wildcardIdx !== adapters.length - 1) throw new Error("A wildcard adapter (handling all files) can only be specified as the last adapter.");
			this.accept = "*";
		} else this.accept = adapters.map((a) => a.accept).join(",");
	}
	add(state) {
		for (const adapter of this._adapters) if (fileMatchesAccept(state.file, adapter.accept)) return adapter.add(state);
		throw new Error("No matching adapter found for file");
	}
	async send(attachment, options) {
		const adapters = this._adapters.slice();
		for (const adapter of adapters) if (fileMatchesAccept(attachment.file, adapter.accept)) return adapter.send(attachment, options);
		throw new Error("No matching adapter found for attachment");
	}
	async remove(attachment) {
		const adapters = this._adapters.slice();
		for (const adapter of adapters) if (fileMatchesAccept(attachment.file ?? {
			name: attachment.name,
			type: attachment.contentType ?? ""
		}, adapter.accept)) return adapter.remove(attachment);
		throw new Error("No matching adapter found for attachment");
	}
};
//#endregion
export { CompositeAttachmentAdapter, SimpleImageAttachmentAdapter, SimpleTextAttachmentAdapter, attachmentsEqual, fileMatchesAccept, getFileDataURL, liftNonTextParts, partToCompleteAttachment };
