import { readCloudArray, readCloudRecord } from "./cloudResponse.js";
import { AssistantCloudProjectThreadMessages } from "./AssistantCloudProjectThreadMessages.js";
import { decodeCloudThread } from "./AssistantCloudThreads.js";
//#region src/AssistantCloudProjectThreads.ts
var AssistantCloudProjectThreads = class {
	messages;
	cloud;
	constructor(cloud) {
		this.cloud = cloud;
		this.messages = new AssistantCloudProjectThreadMessages(cloud);
	}
	async list(query) {
		const response = readCloudRecord(await this.cloud.makeRequest("/projects/threads", { query: {
			...query,
			...query?.is_archived !== void 0 ? { is_archived: String(query.is_archived) } : {}
		} }), "project thread list response");
		return { threads: readCloudArray(response.threads, "threads").map((thread, index) => decodeCloudThread(thread, `threads[${index}]`)) };
	}
};
//#endregion
export { AssistantCloudProjectThreads };
