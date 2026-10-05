import { isJSONValue, isRecord } from "../../../utils/json/is-json.js";
import { readToolInteractionLog } from "../../../runtime/utils/tool-interactions.js";
import { fromThreadMessageLike } from "../../../runtime/utils/thread-message-like.js";
import { isStoredAuiV0RolePart, isStoredMessageRole, isStoredMessageStatus, parseStoredAttachment, parseStoredDate, parseStoredThreadSteps } from "../../../runtime/utils/stored-message-parts.js";
//#region src/react/runtimes/cloud/auiV0.ts
const encodeAttachmentPart = (part) => {
	const type = part.type;
	switch (type) {
		case "text": return {
			type: "text",
			...part.id !== void 0 ? { id: part.id } : void 0,
			text: part.text,
			...part.providerMetadata !== void 0 ? { providerMetadata: part.providerMetadata } : void 0,
			...part.parentId !== void 0 ? { parentId: part.parentId } : void 0
		};
		case "image": return {
			type: "image",
			...part.id !== void 0 ? { id: part.id } : void 0,
			image: part.image,
			...part.filename != null ? { filename: part.filename } : void 0,
			...part.providerMetadata !== void 0 ? { providerMetadata: part.providerMetadata } : void 0
		};
		case "file": return {
			type: "file",
			...part.id !== void 0 ? { id: part.id } : void 0,
			data: part.data,
			mimeType: part.mimeType,
			...part.filename != null ? { filename: part.filename } : void 0,
			...part.sourceType != null ? { sourceType: part.sourceType } : void 0,
			...part.providerMetadata != null ? { providerMetadata: part.providerMetadata } : void 0,
			...part.parentId !== void 0 ? { parentId: part.parentId } : void 0
		};
		case "audio": return {
			type: "audio",
			audio: {
				data: part.audio.data,
				format: part.audio.format
			}
		};
		case "data":
			if (!isJSONValue(part.data)) console.warn(`attachment data is not JSON! ${JSON.stringify(part)}`);
			return {
				type: "data",
				...part.id !== void 0 ? { id: part.id } : void 0,
				name: part.name,
				data: part.data
			};
		default: throw new Error(`Attachment part type not supported by aui/v0: ${type}`);
	}
};
const encodeAttachments = (message) => {
	if (message.role !== "user" || message.attachments.length === 0) return;
	return message.attachments.map(({ id, type, name, contentType, status, content }) => ({
		id,
		type,
		name,
		status,
		...contentType != null ? { contentType } : void 0,
		content: content.map(encodeAttachmentPart)
	}));
};
const serializableArtifact = (artifact) => {
	if (artifact === void 0) return void 0;
	try {
		const serialized = JSON.stringify(artifact);
		return serialized === void 0 ? void 0 : JSON.parse(serialized);
	} catch {
		return;
	}
};
const hasLosslessJSONShape = (value, depth = 0) => {
	if (depth > 100) return false;
	if (value === void 0 || typeof value === "function") return false;
	if (typeof value === "number") return Number.isFinite(value);
	if (typeof value !== "object" || value === null) return true;
	if (typeof value.toJSON === "function") return true;
	if ((value instanceof Map || value instanceof Set) && value.size > 0) return false;
	if (Array.isArray(value)) {
		if (Reflect.ownKeys(value).length !== value.length + 1) return false;
		for (let index = 0; index < value.length; index++) if (!Object.hasOwn(value, index) || !hasLosslessJSONShape(value[index], depth + 1)) return false;
		return true;
	}
	return Reflect.ownKeys(value).every((key) => typeof key === "string" && Object.getOwnPropertyDescriptor(value, key)?.enumerable === true && hasLosslessJSONShape(value[key], depth + 1));
};
const losesDataInJSON = (value) => {
	try {
		return !hasLosslessJSONShape(value);
	} catch {
		return true;
	}
};
function auiV0Encode(message) {
	const status = message.status?.type === "running" ? {
		type: "incomplete",
		reason: "cancelled"
	} : message.status;
	const attachments = encodeAttachments(message);
	return {
		role: message.role,
		content: message.content.map((part) => {
			const type = part.type;
			switch (type) {
				case "text": return {
					type: "text",
					...part.id !== void 0 ? { id: part.id } : void 0,
					text: part.text,
					...part.providerMetadata !== void 0 ? { providerMetadata: part.providerMetadata } : void 0,
					...part.parentId !== void 0 ? { parentId: part.parentId } : void 0
				};
				case "reasoning": return {
					type: "reasoning",
					...part.id !== void 0 ? { id: part.id } : void 0,
					text: part.text,
					...part.unstable_summary !== void 0 ? { unstable_summary: part.unstable_summary } : void 0,
					...part.providerMetadata !== void 0 ? { providerMetadata: part.providerMetadata } : void 0,
					...part.parentId !== void 0 ? { parentId: part.parentId } : void 0
				};
				case "source":
					if (part.sourceType === "url") return {
						type: "source",
						sourceType: "url",
						id: part.id,
						url: part.url,
						...part.title != null ? { title: part.title } : void 0,
						...part.providerMetadata != null ? { providerMetadata: part.providerMetadata } : void 0,
						...part.parentId !== void 0 ? { parentId: part.parentId } : void 0
					};
					return {
						type: "source",
						sourceType: "document",
						id: part.id,
						title: part.title,
						mediaType: part.mediaType,
						...part.filename != null ? { filename: part.filename } : void 0,
						...part.providerMetadata != null ? { providerMetadata: part.providerMetadata } : void 0,
						...part.parentId !== void 0 ? { parentId: part.parentId } : void 0
					};
				case "tool-call": {
					const result = serializableArtifact(part.result);
					if (part.result !== void 0 && (result === void 0 || losesDataInJSON(part.result))) console.warn(result === void 0 ? `tool-call result for ${part.toolCallId} cannot be serialized as JSON; omitted` : `tool-call result for ${part.toolCallId} loses data in JSON; persisted as its JSON form`);
					const artifact = serializableArtifact(part.artifact);
					if (part.artifact !== void 0 && artifact === void 0) console.warn(`tool-call artifact is not JSON for ${part.toolCallId}`);
					const interactions = readToolInteractionLog(part.unstable_interactions);
					return {
						type: "tool-call",
						toolCallId: part.toolCallId,
						toolName: part.toolName,
						...JSON.stringify(part.args) === part.argsText ? { args: part.args } : { argsText: part.argsText },
						...result !== void 0 ? { result } : void 0,
						...artifact !== void 0 ? { artifact } : void 0,
						...part.modelContent !== void 0 ? { modelContent: part.modelContent } : void 0,
						...part.providerMetadata !== void 0 ? { providerMetadata: part.providerMetadata } : void 0,
						...part.isPreliminary ? { isPreliminary: true } : void 0,
						...part.isError ? { isError: true } : void 0,
						...part.interrupt !== void 0 ? { interrupt: {
							type: part.interrupt.type,
							payload: part.interrupt.payload
						} } : void 0,
						...part.timing !== void 0 ? { timing: part.timing } : void 0,
						...part.mcp !== void 0 ? { mcp: part.mcp } : void 0,
						...part.approval ? { approval: part.approval } : void 0,
						...part.parentId !== void 0 ? { parentId: part.parentId } : void 0,
						...part.messages !== void 0 ? { messages: part.messages.map(encodeNestedMessage) } : void 0,
						...interactions !== void 0 ? { unstable_interactions: interactions } : void 0
					};
				}
				case "image": return {
					type: "image",
					...part.id !== void 0 ? { id: part.id } : void 0,
					image: part.image,
					...part.filename != null ? { filename: part.filename } : void 0,
					...part.providerMetadata != null ? { providerMetadata: part.providerMetadata } : void 0
				};
				case "file": return {
					type: "file",
					...part.id !== void 0 ? { id: part.id } : void 0,
					data: part.data,
					mimeType: part.mimeType,
					...part.filename != null ? { filename: part.filename } : void 0,
					...part.sourceType ? { sourceType: part.sourceType } : void 0,
					...part.providerMetadata != null ? { providerMetadata: part.providerMetadata } : void 0,
					...part.parentId !== void 0 ? { parentId: part.parentId } : void 0
				};
				case "data":
					if (!isJSONValue(part.data)) console.warn(`data part is not JSON! ${JSON.stringify(part)}`);
					return {
						type: "data",
						...part.id !== void 0 ? { id: part.id } : void 0,
						name: part.name,
						data: part.data
					};
				case "audio": return {
					type: "audio",
					audio: {
						data: part.audio.data,
						format: part.audio.format
					}
				};
				case "generative-ui": return {
					type: "generative-ui",
					spec: part.spec,
					...part.id !== void 0 ? { id: part.id } : void 0,
					...part.parentId !== void 0 ? { parentId: part.parentId } : void 0
				};
				default: throw new Error(`Message part type not supported by aui/v0: ${type}`);
			}
		}),
		metadata: message.metadata,
		...status ? { status } : void 0,
		...attachments ? { attachments } : void 0
	};
}
const readableAuiV0Parts = (role, content, depth) => content.flatMap((part) => {
	if (!isStoredAuiV0RolePart(role, part)) return [];
	if (part.type !== "tool-call" || part.messages === void 0) return [part];
	const { messages, ...toolCall } = part;
	if (!Array.isArray(messages) || depth >= 100) return [toolCall];
	return [{
		...toolCall,
		messages: messages.flatMap((message) => {
			const nested = readableAuiV0Message(message, depth + 1);
			return nested ? [nested] : [];
		})
	}];
});
const readableAuiV0Attachments = (attachments) => attachments.flatMap((attachment) => {
	const parsed = parseStoredAttachment(attachment, (value) => isStoredAuiV0RolePart("user", value));
	return parsed ? [parsed] : [];
});
const readableAuiV0Message = (value, depth) => {
	if (!isRecord(value) || !isStoredMessageRole(value.role) || !Array.isArray(value.content)) return null;
	const { role } = value;
	const content = readableAuiV0Parts(role, value.content, depth);
	if (role === "system" && content.length !== 1) return null;
	const { attachments, createdAt, status, metadata, ...rest } = value;
	const storedCreatedAt = parseStoredDate(createdAt);
	const readableMetadata = !isRecord(metadata) ? metadata : role === "assistant" ? {
		...metadata,
		steps: parseStoredThreadSteps(metadata.steps)
	} : {
		...metadata,
		steps: void 0
	};
	return {
		...rest,
		...storedCreatedAt ? { createdAt } : void 0,
		...role === "assistant" && isStoredMessageStatus(status) ? { status } : void 0,
		...metadata !== void 0 ? { metadata: readableMetadata } : void 0,
		content,
		...role === "user" && Array.isArray(attachments) ? { attachments: readableAuiV0Attachments(attachments) } : void 0
	};
};
/**
* Decodes a stored row, dropping the parts, attachments and nested messages
* that cannot be read back instead of rejecting the row, and returning null
* when the row itself is unreadable. Loading a thread must not fail because a
* single stored row is malformed.
*/
function auiV0DecodeSafely(cloudMessage) {
	try {
		const payload = readableAuiV0Message(cloudMessage.content, 0);
		if (!payload) throw new Error("stored row is not an aui/v0 message");
		return {
			parentId: cloudMessage.parent_id,
			message: decodeAuiV0Message({
				...payload,
				id: cloudMessage.id,
				createdAt: cloudMessage.created_at
			}, cloudMessage.id)
		};
	} catch (error) {
		console.warn(`aui/v0: dropping unreadable message ${cloudMessage.id}`, error);
		return null;
	}
}
function auiV0Decode(cloudMessage) {
	const payload = cloudMessage.content;
	const message = decodeAuiV0Message({
		...payload,
		id: cloudMessage.id,
		createdAt: cloudMessage.created_at
	}, cloudMessage.id);
	return {
		parentId: cloudMessage.parent_id,
		message
	};
}
const encodeNestedMessage = (message) => ({
	...auiV0Encode(message),
	id: message.id,
	createdAt: message.createdAt.toISOString()
});
const decodeAuiV0Message = (payload, fallbackId) => fromThreadMessageLike({
	...payload,
	content: payload.content.map((part, index) => {
		if (part.type !== "tool-call" || part.messages === void 0) return part;
		return {
			...part,
			messages: part.messages.map((message, nestedIndex) => decodeAuiV0Message({
				...message,
				createdAt: message.createdAt !== void 0 ? new Date(message.createdAt) : payload.createdAt
			}, message.id ?? `${fallbackId}-${part.toolCallId}-${index}-${nestedIndex}`))
		};
	})
}, fallbackId, {
	type: "complete",
	reason: "unknown"
});
//#endregion
export { auiV0Decode, auiV0DecodeSafely, auiV0Encode };
