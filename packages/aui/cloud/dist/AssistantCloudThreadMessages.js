import { readCloudArray, readCloudEnum, readCloudInteger, readCloudJSONObject, readCloudNullableString, readCloudRecord, readCloudString, readCloudTimestamp } from "./cloudResponse.js";
//#region src/AssistantCloudThreadMessages.ts
const MESSAGE_FEEDBACK_TYPES = ["positive", "negative"];
const decodeCloudMessage = (value, field) => {
	const message = readCloudRecord(value, field);
	return {
		id: readCloudString(message.id, `${field}.id`),
		parent_id: readCloudNullableString(message.parent_id, `${field}.parent_id`),
		height: readCloudInteger(message.height, `${field}.height`),
		created_at: readCloudTimestamp(message.created_at, `${field}.created_at`),
		updated_at: readCloudTimestamp(message.updated_at, `${field}.updated_at`),
		format: readCloudString(message.format, `${field}.format`),
		content: readCloudJSONObject(message.content, `${field}.content`),
		external_id: readCloudNullableString(message.external_id ?? null, `${field}.external_id`)
	};
};
var AssistantCloudThreadMessages = class {
	cloud;
	constructor(cloud) {
		this.cloud = cloud;
	}
	async list(threadId, query) {
		const response = readCloudRecord(await this.cloud.makeRequest(`/threads/${encodeURIComponent(threadId)}/messages`, { query }), "thread message list response");
		return { messages: readCloudArray(response.messages, "messages").map((message, index) => decodeCloudMessage(message, `messages[${index}]`)) };
	}
	async create(threadId, body) {
		const response = readCloudRecord(await this.cloud.makeRequest(`/threads/${encodeURIComponent(threadId)}/messages`, {
			method: "POST",
			body: {
				parent_id: body.parent_id,
				format: body.format,
				content: body.content,
				...body.external_id !== void 0 ? { external_id: body.external_id } : void 0,
				...body.parent_external_id !== void 0 ? { parent_external_id: body.parent_external_id } : void 0
			}
		}), "thread message create response");
		return { message_id: readCloudString(response.message_id, "message_id") };
	}
	async update(threadId, messageId, body) {
		return this.cloud.makeRequest(`/threads/${encodeURIComponent(threadId)}/messages/${encodeURIComponent(messageId)}`, {
			method: "PUT",
			body
		});
	}
	async feedback(threadId, messageId, body) {
		const comment = body.comment?.trim();
		const response = readCloudRecord(await this.cloud.makeRequest(`/threads/${encodeURIComponent(threadId)}/messages/${encodeURIComponent(messageId)}/feedback`, {
			method: "POST",
			body: {
				type: body.type,
				...comment ? { comment } : void 0
			}
		}), "thread message feedback response");
		return {
			feedback_id: readCloudString(response.feedback_id, "feedback_id"),
			type: readCloudEnum(response.type, "type", MESSAGE_FEEDBACK_TYPES),
			..."comment" in response ? { comment: readCloudNullableString(response.comment, "comment") } : void 0
		};
	}
};
//#endregion
export { AssistantCloudThreadMessages, decodeCloudMessage };
