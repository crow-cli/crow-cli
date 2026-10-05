import { readCloudArray, readCloudRecord } from "./cloudResponse.js";
import { decodeCloudMessage } from "./AssistantCloudThreadMessages.js";
//#region src/AssistantCloudProjectThreadMessages.ts
var AssistantCloudProjectThreadMessages = class {
	cloud;
	constructor(cloud) {
		this.cloud = cloud;
	}
	async list(threadId, query) {
		const response = readCloudRecord(await this.cloud.makeRequest(`/projects/threads/${encodeURIComponent(threadId)}/messages`, { query }), "project thread message list response");
		return { messages: readCloudArray(response.messages, "messages").map((message, index) => decodeCloudMessage(message, `messages[${index}]`)) };
	}
};
//#endregion
export { AssistantCloudProjectThreadMessages };
