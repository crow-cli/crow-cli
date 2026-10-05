import { readCloudArray, readCloudBoolean, readCloudInteger, readCloudNullableString, readCloudRecord, readCloudString, readCloudTimestamp } from "./cloudResponse.js";
import { AssistantCloudThreadMessages } from "./AssistantCloudThreadMessages.js";
//#region src/AssistantCloudThreads.ts
const decodeCloudThread = (value, field) => {
	const thread = readCloudRecord(value, field);
	return {
		title: readCloudNullableString(thread.title, `${field}.title`) ?? "",
		last_message_at: readCloudTimestamp(thread.last_message_at, `${field}.last_message_at`),
		metadata: thread.metadata,
		external_id: readCloudNullableString(thread.external_id, `${field}.external_id`),
		id: readCloudString(thread.id, `${field}.id`),
		project_id: readCloudString(thread.project_id, `${field}.project_id`),
		created_at: readCloudTimestamp(thread.created_at, `${field}.created_at`),
		updated_at: readCloudTimestamp(thread.updated_at, `${field}.updated_at`),
		workspace_id: readCloudString(thread.workspace_id, `${field}.workspace_id`),
		is_archived: readCloudBoolean(thread.is_archived, `${field}.is_archived`)
	};
};
var AssistantCloudThreads = class {
	messages;
	cloud;
	constructor(cloud) {
		this.cloud = cloud;
		this.messages = new AssistantCloudThreadMessages(cloud);
	}
	async list(query) {
		const requestQuery = query?.is_archived === void 0 ? query : {
			...query,
			is_archived: String(query.is_archived)
		};
		const response = readCloudRecord(await this.cloud.makeRequest("/threads", { query: requestQuery }), "thread list response");
		return { threads: readCloudArray(response.threads, "threads").map((thread, index) => decodeCloudThread(thread, `threads[${index}]`)) };
	}
	async get(threadId) {
		const response = readCloudRecord(await this.cloud.makeRequest(`/threads/${encodeURIComponent(threadId)}`), "thread response");
		return decodeCloudThread(response.thread, "thread");
	}
	async create(body) {
		const response = readCloudRecord(await this.cloud.makeRequest("/threads", {
			method: "POST",
			body
		}), "thread create response");
		return { thread_id: readCloudString(response.thread_id, "thread_id") };
	}
	async update(threadId, body) {
		return this.cloud.makeRequest(`/threads/${encodeURIComponent(threadId)}`, {
			method: "PUT",
			body
		});
	}
	/** Moves every thread of the anonymous identity behind `refresh_token` into the caller's workspace. */
	async claim(body) {
		const response = readCloudRecord(await this.cloud.makeRequest("/threads/claim", {
			method: "POST",
			body
		}), "thread claim response");
		return { moved: readCloudInteger(response.moved, "moved") };
	}
	async delete(threadId) {
		return this.cloud.makeRequest(`/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
	}
};
//#endregion
export { AssistantCloudThreads, decodeCloudThread };
